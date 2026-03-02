"""
backend/analytics.py - FinSight Pro EDA & Analytics Engine
Advanced pandas/numpy analytics used by the API and standalone
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import mysql.connector
from loguru import logger
from config.config import config

sns.set_theme(style="darkgrid", palette="muted")

def get_conn():
    return mysql.connector.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

# ── 1. Transaction EDA ────────────────────────────────────────────────────────
def analyze_transactions():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT t.*, p.platform_name, c.segment, c.city, c.risk_tier
        FROM transactions t
        JOIN platforms p ON t.platform_id = p.platform_id
        JOIN customers c ON t.customer_id = c.customer_id
        LIMIT 100000
    """, conn)
    conn.close()
    
    logger.info(f"Loaded {len(df):,} transactions for EDA")
    
    # ── Basic Stats ──────────────────────────────────────────────
    stats = df['amount_inr'].describe()
    logger.info(f"\nAmount Statistics:\n{stats}")
    
    # ── Fraud rate by platform ───────────────────────────────────
    fraud_by_platform = df.groupby('platform_name').agg(
        total=('txn_id','count'),
        fraud=('is_fraud','sum'),
        fraud_rate=('is_fraud','mean'),
        avg_amount=('amount_inr','mean'),
        total_volume=('amount_inr','sum')
    ).round(4)
    logger.info(f"\nFraud by Platform:\n{fraud_by_platform}")
    
    # ── Time-series decomposition ────────────────────────────────
    df['initiated_at'] = pd.to_datetime(df['initiated_at'])
    df['date']   = df['initiated_at'].dt.date
    df['hour']   = df['initiated_at'].dt.hour
    df['weekday']= df['initiated_at'].dt.day_name()
    
    daily = df.groupby('date').agg(
        txns=('txn_id','count'),
        volume=('amount_inr','sum'),
        fraud_rate=('is_fraud','mean')
    )
    
    # ── Correlation matrix for numeric features ──────────────────
    num_cols = ['amount_inr','latency_ms','fee_amount','is_fraud','fraud_score']
    corr = df[num_cols].corr()
    logger.info(f"\nCorrelation Matrix:\n{corr.round(3)}")
    
    # ── Plotly: Amount distribution ──────────────────────────────
    fig = px.histogram(
        df[df['amount_inr'] < df['amount_inr'].quantile(0.99)],
        x='amount_inr', color='txn_type',
        title='Transaction Amount Distribution by Type',
        nbins=100, template='plotly_dark',
        color_discrete_sequence=px.colors.qualitative.Bold
    )
    pio.write_html(fig, f"{config.REPORTS_DIR}/txn_distribution.html")
    
    # ── Plotly: Fraud scatter ─────────────────────────────────────
    sample = df.sample(min(10000, len(df)))
    fig2 = px.scatter(
        sample, x='amount_inr', y='fraud_score',
        color='is_fraud', size='latency_ms',
        hover_data=['platform_name','txn_type'],
        title='Fraud Score vs Transaction Amount',
        template='plotly_dark', log_x=True
    )
    pio.write_html(fig2, f"{config.REPORTS_DIR}/fraud_scatter.html")
    
    logger.success(f"Charts saved to {config.REPORTS_DIR}/")
    return fraud_by_platform, daily

# ── 2. Customer Lifetime Value (CLV) Analysis ─────────────────────────────────
def analyze_clv():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT
            c.customer_id, c.segment, c.city, c.annual_income, c.credit_score,
            COUNT(t.txn_id)      AS txn_count,
            SUM(t.amount_inr)    AS lifetime_value,
            AVG(t.amount_inr)    AS avg_txn,
            MIN(t.initiated_at)  AS first_txn,
            MAX(t.initiated_at)  AS last_txn,
            SUM(t.is_fraud)      AS fraud_count,
            SUM(t.fee_amount)    AS total_fees
        FROM customers c
        LEFT JOIN transactions t ON c.customer_id = t.customer_id
        GROUP BY c.customer_id, c.segment, c.city, c.annual_income, c.credit_score
    """, conn)
    conn.close()
    
    # RFM Score (Recency, Frequency, Monetary)
    df['last_txn']  = pd.to_datetime(df['last_txn'])
    df['first_txn'] = pd.to_datetime(df['first_txn'])
    ref = df['last_txn'].max()
    df['recency'] = (ref - df['last_txn']).dt.days
    
    # Quantile-based scoring
    df['R'] = pd.qcut(df['recency'],     5, labels=[5,4,3,2,1], duplicates='drop').astype(int)
    df['F'] = pd.qcut(df['txn_count'],   5, labels=[1,2,3,4,5], duplicates='drop').astype(int)
    df['M'] = pd.qcut(df['lifetime_value'].clip(lower=0.01), 5, labels=[1,2,3,4,5], duplicates='drop').astype(int)
    df['rfm_score'] = df['R'] + df['F'] + df['M']
    
    def rfm_segment(score):
        if score >= 13: return 'Champions'
        if score >= 10: return 'Loyal'
        if score >= 7:  return 'Potential'
        if score >= 4:  return 'At Risk'
        return 'Lost'
    
    df['rfm_segment'] = df['rfm_score'].apply(rfm_segment)
    
    logger.info(f"\nRFM Segments:\n{df['rfm_segment'].value_counts()}")
    logger.info(f"\nCLV by Segment:\n{df.groupby('segment')['lifetime_value'].describe().round(2)}")
    
    return df

# ── 3. Portfolio Risk Analysis ────────────────────────────────────────────────
def analyze_portfolios():
    conn = get_conn()
    df = pd.read_sql("""
        SELECT pf.*, p.platform_name, c.segment
        FROM portfolios pf
        JOIN platforms p ON pf.platform_id = p.platform_id
        JOIN customers c ON pf.customer_id = c.customer_id
    """, conn)
    conn.close()
    
    # Sharpe-like ratio (using pnl_pct as return)
    by_asset = df.groupby('asset_class').agg(
        total_invested=('invested_amount','sum'),
        total_value=('current_value','sum'),
        avg_return=('pnl_pct','mean'),
        volatility=('pnl_pct','std'),
        positions=('portfolio_id','count')
    ).round(3)
    by_asset['sharpe_proxy'] = (by_asset['avg_return'] / (by_asset['volatility'] + 1e-6)).round(3)
    
    logger.info(f"\nPortfolio Analysis by Asset Class:\n{by_asset}")
    return by_asset

# ── 4. Advanced SQL Analytics Runner ─────────────────────────────────────────
def run_advanced_sql():
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    
    queries = {
        "Top Cities by Volume (with RANK)": """
            SELECT city, total_volume, txn_count,
                   RANK() OVER (ORDER BY total_volume DESC) AS city_rank
            FROM (
                SELECT c.city, SUM(t.amount_inr) AS total_volume, COUNT(*) AS txn_count
                FROM transactions t JOIN customers c ON t.customer_id=c.customer_id
                GROUP BY c.city
            ) sub LIMIT 15
        """,
        "YoY Growth (SELF JOIN)": """
            SELECT
                YEAR(t1.initiated_at) AS year,
                SUM(t1.amount_inr)    AS volume,
                LAG(SUM(t1.amount_inr)) OVER (ORDER BY YEAR(t1.initiated_at)) AS prev_year_volume,
                ROUND((SUM(t1.amount_inr) - LAG(SUM(t1.amount_inr)) OVER (ORDER BY YEAR(t1.initiated_at)))
                      / NULLIF(LAG(SUM(t1.amount_inr)) OVER (ORDER BY YEAR(t1.initiated_at)),0)*100, 2) AS yoy_growth_pct
            FROM transactions t1
            GROUP BY YEAR(t1.initiated_at)
        """,
        "High-Value Fraud (HAVING + subquery)": """
            SELECT customer_id, COUNT(*) AS fraud_txns, SUM(amount_inr) AS fraud_amount
            FROM transactions
            WHERE is_fraud=1 AND amount_inr > (SELECT AVG(amount_inr)*5 FROM transactions)
            GROUP BY customer_id
            HAVING fraud_txns > 1
            ORDER BY fraud_amount DESC LIMIT 10
        """,
        "Platform Cross-Sell (UNION)": """
            SELECT customer_id, 'Payment' AS category, COUNT(*) AS txns
            FROM transactions WHERE txn_type IN ('UPI','Card','NetBanking','Wallet','BNPL')
            GROUP BY customer_id
            UNION ALL
            SELECT customer_id, 'Investment' AS category, COUNT(*) AS txns
            FROM transactions WHERE txn_type = 'Investment'
            GROUP BY customer_id
        """,
    }
    
    results = {}
    for name, sql in queries.items():
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            df = pd.DataFrame(rows)
            results[name] = df
            logger.info(f"\n{name}:\n{df.head(5)}")
        except Exception as e:
            logger.warning(f"Query failed [{name}]: {e}")
    
    cursor.close()
    conn.close()
    return results

if __name__ == "__main__":
    logger.info("Running FinSight Pro Analytics Engine...")
    analyze_transactions()
    analyze_clv()
    analyze_portfolios()
    run_advanced_sql()
    logger.success("Analytics complete. Check reports/ for charts.")
