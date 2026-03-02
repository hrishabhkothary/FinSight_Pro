"""
data_generation/generate_data.py
FinSight Pro - Synthetic Financial Dataset Generator
Generates 500K+ realistic transactions across Razorpay, JusPay, PayTM, Upstox, etc.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from faker import Faker
from datetime import datetime, timedelta
import random
import mysql.connector
from tqdm import tqdm
from loguru import logger
from config.config import config

fake = Faker('en_IN')
np.random.seed(config.RANDOM_SEED)
random.seed(config.RANDOM_SEED)

# ── Constants ────────────────────────────────────────────────────────────────
PLATFORMS = {
    1: {"name": "Razorpay",        "type": "Payment Gateway"},
    2: {"name": "JusPay",          "type": "Payment Gateway"},
    3: {"name": "PayTM",           "type": "UPI"},
    4: {"name": "PhonePe",         "type": "UPI"},
    5: {"name": "GooglePay",       "type": "UPI"},
    6: {"name": "Upstox",          "type": "Investment"},
    7: {"name": "Zerodha",         "type": "Investment"},
    8: {"name": "Groww",           "type": "Investment"},
    9: {"name": "HDFC Securities", "type": "Investment"},
    10:{"name": "ICICI Direct",    "type": "Investment"},
}

MERCHANT_CATEGORIES = ["Ecommerce","Food","Travel","Healthcare","Education",
                        "Utilities","Retail","Entertainment","Insurance","Govt"]
INDIAN_CITIES = ["Mumbai","Delhi","Bangalore","Hyderabad","Chennai","Kolkata",
                 "Pune","Ahmedabad","Jaipur","Lucknow","Surat","Bhopal",
                 "Chandigarh","Kochi","Indore","Nagpur","Patna","Visakhapatnam"]
STATES = ["Maharashtra","Karnataka","Tamil Nadu","Telangana","Gujarat","Rajasthan",
          "Uttar Pradesh","West Bengal","Delhi","Punjab","Madhya Pradesh"]
SEGMENTS = ["Retail","HNI","Institutional","SME"]
DEVICE_TYPES = ["Mobile","Desktop","Tablet","POS"]
CURRENCIES = ["INR","USD","EUR","GBP","JPY","SGD","AED"]
FX_RATES = {"INR":1,"USD":83.5,"EUR":90.2,"GBP":105.8,"JPY":0.56,"SGD":62.1,"AED":22.7}
SECTORS = ["IT","Banking","FMCG","Auto","Pharma","Energy","Metals","Telecom","Realty","Infra"]
SYMBOLS = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","WIPRO","BAJFINANCE",
           "AXISBANK","NESTLEIND","TATAMOTORS","ONGC","NTPC","POWERGRID","SBIN","LT"]

def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME, autocommit=False
    )

def generate_customers(n=50000):
    logger.info(f"Generating {n} customers...")
    customers = []
    for i in tqdm(range(n), desc="Customers"):
        cid = f"CUST{str(i+1).zfill(8)}"
        segment = np.random.choice(SEGMENTS, p=[0.6,0.15,0.1,0.15])
        income_base = {"Retail":400000,"HNI":2500000,"Institutional":10000000,"SME":1500000}[segment]
        income = max(200000, int(np.random.lognormal(np.log(income_base), 0.5)))
        customers.append({
            "customer_id":  cid,
            "name":         fake.name(),
            "email":        fake.unique.email(),
            "phone":        fake.phone_number()[:15],
            "city":         random.choice(INDIAN_CITIES),
            "state":        random.choice(STATES),
            "country":      "India",
            "segment":      segment,
            "kyc_status":   np.random.choice(["Verified","Pending","Rejected"], p=[0.8,0.15,0.05]),
            "risk_tier":    np.random.choice(["Low","Medium","High","Critical"], p=[0.55,0.3,0.12,0.03]),
            "credit_score": int(np.clip(np.random.normal(700, 80), 300, 900)),
            "annual_income":income,
            "created_at":   fake.date_time_between(start_date="-3y", end_date="-30d"),
            "is_active":    random.random() > 0.05,
            "churn_risk":   round(random.uniform(0, 1), 4),
        })
    return pd.DataFrame(customers)

def _txn_amount_for_type(txn_type):
    ranges = {
        "UPI":        (10, 100000),
        "Card":       (500, 500000),
        "NetBanking": (1000, 5000000),
        "Wallet":     (10, 10000),
        "BNPL":       (500, 50000),
        "Investment": (500, 10000000),
        "FX":         (1000, 2000000),
    }
    lo, hi = ranges.get(txn_type, (100, 100000))
    return round(np.random.lognormal(np.log((lo+hi)/4), 0.8), 2)

def generate_transactions(customer_ids, n=500000):
    logger.info(f"Generating {n} transactions...")
    txns = []
    start_date = datetime.now() - timedelta(days=365*2)
    
    platform_ids = list(PLATFORMS.keys())
    platform_weights_payment = [0.25,0.15,0.2,0.2,0.2,0,0,0,0,0]
    platform_weights_invest   = [0,0,0,0,0,0.25,0.25,0.2,0.15,0.15]
    
    for i in tqdm(range(n), desc="Transactions"):
        cid = random.choice(customer_ids)
        txn_type = np.random.choice(
            ["UPI","Card","NetBanking","Wallet","BNPL","Investment","FX"],
            p=[0.35,0.2,0.15,0.1,0.08,0.1,0.02]
        )
        if txn_type in ["Investment","FX"]:
            pid = np.random.choice(platform_ids[5:], p=[0.25,0.25,0.2,0.15,0.15])
        else:
            pid = np.random.choice(platform_ids[:5])
        
        currency = "INR" if random.random() > 0.05 else random.choice(CURRENCIES[1:])
        amount   = _txn_amount_for_type(txn_type)
        amount_inr = round(amount * FX_RATES.get(currency, 1), 2)
        
        # Fraud signal: higher amounts, odd hours, foreign IPs → elevated risk
        initiated = start_date + timedelta(seconds=random.randint(0, int((datetime.now()-start_date).total_seconds())))
        hour = initiated.hour
        is_odd_hour = hour < 5 or hour > 23
        fraud_base = 0.01 + (0.05 if is_odd_hour else 0) + (0.03 if amount_inr > 500000 else 0)
        fraud_score = round(min(np.random.beta(1, 20) + fraud_base, 1.0), 4)
        is_fraud    = fraud_score > 0.7 and random.random() < config.FRAUD_RATIO * 10
        
        status = "SUCCESS"
        if is_fraud:
            status = random.choice(["FAILED","FLAGGED","REFUNDED"])
        elif random.random() < 0.03:
            status = "FAILED"
        elif random.random() < 0.01:
            status = "PENDING"
        
        latency = int(np.random.lognormal(4, 0.8))  # ms
        
        txns.append({
            "txn_id":           f"TXN{str(i+1).zfill(10)}",
            "customer_id":      cid,
            "platform_id":      pid,
            "txn_type":         txn_type,
            "amount":           amount,
            "currency":         currency,
            "amount_inr":       amount_inr,
            "status":           status,
            "is_fraud":         int(is_fraud),
            "fraud_score":      fraud_score,
            "merchant_id":      f"MER{random.randint(10000,99999)}",
            "merchant_name":    fake.company()[:100],
            "merchant_category":random.choice(MERCHANT_CATEGORIES),
            "device_type":      random.choice(DEVICE_TYPES),
            "ip_country":       "India" if random.random() > 0.05 else fake.country(),
            "initiated_at":     initiated,
            "completed_at":     initiated + timedelta(milliseconds=latency) if status=="SUCCESS" else None,
            "latency_ms":       latency,
            "fee_amount":       round(amount_inr * random.uniform(0.001, 0.025), 4),
        })
    return pd.DataFrame(txns)

def generate_portfolios(customer_ids, n=100000):
    logger.info(f"Generating {n} portfolio entries...")
    portfolios = []
    invest_platforms = [6,7,8,9,10]
    asset_classes = ["Equity","MutualFund","ETF","Bond","Crypto","FX","Commodity"]
    
    # HNI/Institutional customers → more portfolio entries
    for i in tqdm(range(n), desc="Portfolios"):
        cid = random.choice(customer_ids)
        asset = random.choice(asset_classes)
        symbol = random.choice(SYMBOLS) if asset in ["Equity","ETF"] else f"{asset[:3].upper()}{random.randint(100,999)}"
        qty = round(random.uniform(1, 10000), 4)
        avg_buy = round(random.uniform(10, 50000), 4)
        curr_price = round(avg_buy * random.uniform(0.5, 3.0), 4)
        invested = round(qty * avg_buy, 2)
        curr_val  = round(qty * curr_price, 2)
        
        portfolios.append({
            "portfolio_id":   f"PF{str(i+1).zfill(9)}",
            "customer_id":    cid,
            "platform_id":    random.choice(invest_platforms),
            "asset_class":    asset,
            "symbol":         symbol,
            "company_name":   fake.company()[:100],
            "quantity":       qty,
            "avg_buy_price":  avg_buy,
            "current_price":  curr_price,
            "invested_amount":invested,
            "current_value":  curr_val,
            "pnl":            round(curr_val - invested, 2),
            "pnl_pct":        round((curr_val - invested)/invested * 100, 4),
            "sector":         random.choice(SECTORS),
            "exchange":       random.choice(["NSE","BSE","NASDAQ","NYSE"]),
        })
    return pd.DataFrame(portfolios)

def bulk_insert(conn, df, table, batch_size=5000):
    """Efficient bulk insert with prepared statements."""
    cursor = conn.cursor()
    cols = ", ".join(df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
    
    records = [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False)]
    for i in tqdm(range(0, len(records), batch_size), desc=f"Inserting {table}"):
        cursor.executemany(sql, records[i:i+batch_size])
        conn.commit()
    cursor.close()
    logger.success(f"Inserted {len(df):,} rows into {table}")

def run_generation(rows=500000):
    logger.info("=== FinSight Pro Data Generation Started ===")
    
    conn = get_db_connection()
    
    # Generate & insert customers
    n_customers = min(50000, rows // 10)
    cdf = generate_customers(n_customers)
    bulk_insert(conn, cdf, "customers")
    customer_ids = cdf["customer_id"].tolist()
    
    # Generate & insert transactions (in chunks to manage memory)
    chunk_size = 100000
    for chunk_num in range(0, rows, chunk_size):
        chunk = min(chunk_size, rows - chunk_num)
        tdf = generate_transactions(customer_ids, n=chunk)
        bulk_insert(conn, tdf, "transactions")
        del tdf
    
    # Generate & insert portfolios
    n_portfolios = min(100000, rows // 5)
    pdf = generate_portfolios(customer_ids, n=n_portfolios)
    bulk_insert(conn, pdf, "portfolios")
    
    conn.close()
    logger.success("=== Data Generation Complete ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FinSight Pro Data Generator")
    parser.add_argument("--rows", type=int, default=500000, help="Number of transactions")
    args = parser.parse_args()
    run_generation(args.rows)
