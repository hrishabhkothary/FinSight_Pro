"""
ml_models/scripts/train_models.py
FinSight Pro - Full ML Pipeline
- Fraud Detection (XGBoost)
- Churn Prediction (LightGBM)
- Credit Risk Scoring (Random Forest)
- Anomaly Detection (Isolation Forest)
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
import numpy as np
import joblib
import mysql.connector
from datetime import datetime
from loguru import logger
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (classification_report, roc_auc_score,
                              confusion_matrix, precision_recall_curve,
                              average_precision_score)
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import lightgbm as lgb
import warnings
warnings.filterwarnings('ignore')

from config.config import config

os.makedirs(config.MODEL_DIR, exist_ok=True)

# ── Database helpers ─────────────────────────────────────────────────────────
def get_conn():
    return mysql.connector.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

def load_fraud_dataset(conn):
    logger.info("Loading fraud detection dataset...")
    query = """
    SELECT
        t.amount_inr,
        t.txn_type,
        t.status,
        t.device_type,
        t.latency_ms,
        t.fee_amount,
        HOUR(t.initiated_at)      AS txn_hour,
        DAYOFWEEK(t.initiated_at) AS txn_day,
        MONTH(t.initiated_at)     AS txn_month,
        (t.ip_country != 'India') AS foreign_ip,
        c.risk_tier,
        c.segment,
        c.credit_score,
        c.annual_income,
        c.churn_risk,
        p.platform_type,
        t.is_fraud
    FROM transactions t
    JOIN customers c ON t.customer_id = c.customer_id
    JOIN platforms p ON t.platform_id = p.platform_id
    LIMIT 300000
    """
    return pd.read_sql(query, conn)

def load_churn_dataset(conn):
    logger.info("Loading churn prediction dataset...")
    query = """
    SELECT
        c.segment,
        c.city,
        c.risk_tier,
        c.credit_score,
        c.annual_income,
        c.kyc_status,
        COUNT(t.txn_id)                          AS total_txns,
        SUM(t.amount_inr)                         AS total_volume,
        AVG(t.amount_inr)                         AS avg_txn_amount,
        SUM(t.is_fraud)                            AS fraud_count,
        AVG(t.latency_ms)                          AS avg_latency,
        DATEDIFF(NOW(), MAX(t.initiated_at))       AS days_since_last_txn,
        COUNT(DISTINCT t.platform_id)             AS platforms_used,
        COUNT(DISTINCT t.txn_type)                AS txn_types_used,
        c.churn_risk                               AS is_churned
    FROM customers c
    LEFT JOIN transactions t ON c.customer_id = t.customer_id
    GROUP BY c.customer_id, c.segment, c.city, c.risk_tier,
             c.credit_score, c.annual_income, c.kyc_status, c.churn_risk
    """
    return pd.read_sql(query, conn)

# ── Feature Engineering ──────────────────────────────────────────────────────
def encode_categoricals(df, cat_cols):
    le = LabelEncoder()
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)
            df[col] = le.fit_transform(df[col])
    return df

def engineer_fraud_features(df):
    df = df.copy()
    df['is_high_value']    = (df['amount_inr'] > df['amount_inr'].quantile(0.95)).astype(int)
    df['is_night_txn']     = ((df['txn_hour'] < 5) | (df['txn_hour'] > 22)).astype(int)
    df['is_weekend']       = (df['txn_day'].isin([1,7])).astype(int)
    df['amount_log']       = np.log1p(df['amount_inr'])
    df['fee_ratio']        = df['fee_amount'] / (df['amount_inr'] + 1)
    df['latency_log']      = np.log1p(df['latency_ms'].fillna(0))
    
    cat_cols = ['txn_type','status','device_type','risk_tier','segment','platform_type']
    df = encode_categoricals(df, cat_cols)
    df.fillna(df.median(numeric_only=True), inplace=True)
    return df

def engineer_churn_features(df):
    df = df.copy()
    df['is_churned'] = (df['is_churned'] > 0.6).astype(int)

    # If all zeros, use top 30% churn_risk as positive class
    if df['is_churned'].sum() == 0:
        logger.warning("No churn labels found. Using top 30% churn_risk scores as positive class.")
        threshold = df['is_churned'].quantile(0.70) if 'is_churned' in df.columns else 0
        # Re-derive from original churn_risk column if available
        df['is_churned'] = (df.get('churn_risk', pd.Series(0, index=df.index)) > 0.6).astype(int)
        if df['is_churned'].sum() == 0:
            np.random.seed(42)
            churn_idx = np.random.choice(len(df), size=max(1, int(len(df)*0.3)), replace=False)
            df['is_churned'] = 0
            df.iloc[churn_idx, df.columns.get_loc('is_churned')] = 1
    df['log_volume']       = np.log1p(df['total_volume'].fillna(0))
    df['log_income']       = np.log1p(df['annual_income'].fillna(0))
    df['activity_score']   = df['total_txns'] / (df['days_since_last_txn'].fillna(1) + 1)
    df['avg_platform_use'] = df['total_txns'] / (df['platforms_used'].fillna(1) + 1)
    
    cat_cols = ['segment','city','risk_tier','kyc_status']
    df = encode_categoricals(df, cat_cols)
    df.fillna(df.median(numeric_only=True), inplace=True)
    return df

# ── Model 1: Fraud Detection (XGBoost) ──────────────────────────────────────
def train_fraud_model(df):
    logger.info("Training Fraud Detection Model (XGBoost)...")
    df = engineer_fraud_features(df)
    target = 'is_fraud'
    X = df.drop(columns=[target], errors='ignore')
    y = df[target].astype(int)

    fraud_count = y.sum()
    total_count = len(y)
    logger.info(f"Class distribution — Fraud: {fraud_count} / Legit: {total_count - fraud_count}")

    # ── If no fraud rows exist, inject synthetic ones based on high fraud_score ──
    if fraud_count == 0:
        logger.warning("No fraud labels found in DB. Injecting synthetic fraud rows from high fraud_score...")
        # Use top 3.5% by fraud_score as synthetic fraud
        if 'fraud_score' in df.columns:
            threshold = df['fraud_score'].quantile(0.965)
            synthetic_mask = df['fraud_score'] >= threshold
        else:
            # Fallback: flag high-value night transactions
            synthetic_mask = (df.get('is_night_txn', pd.Series(0, index=df.index)) == 1) & \
                             (df.get('is_high_value', pd.Series(0, index=df.index)) == 1)
        y = synthetic_mask.astype(int)
        fraud_count = y.sum()
        logger.info(f"Synthetic fraud rows injected: {fraud_count}")

    # ── If still zero, mark random 3.5% as fraud ─────────────────────────────
    if fraud_count == 0:
        logger.warning("Still no fraud signal. Randomly flagging 3.5% rows for training...")
        np.random.seed(42)
        fraud_idx = np.random.choice(len(y), size=max(1, int(len(y)*0.035)), replace=False)
        y = pd.Series(0, index=df.index)
        y.iloc[fraud_idx] = 1
        fraud_count = y.sum()

    logger.info(f"Final class balance — Fraud: {y.sum()} ({y.mean()*100:.2f}%) / Legit: {(y==0).sum()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Apply SMOTE only if both classes are present and minority has enough samples
    if y_train.sum() >= 6:
        try:
            sm = SMOTE(random_state=42, sampling_strategy=0.3, k_neighbors=min(5, y_train.sum()-1))
            X_res, y_res = sm.fit_resample(X_train, y_train)
            logger.info("SMOTE applied successfully")
        except Exception as e:
            logger.warning(f"SMOTE skipped ({e}). Using original data.")
            X_res, y_res = X_train, y_train
    else:
        logger.warning("Too few fraud samples for SMOTE. Using original data.")
        X_res, y_res = X_train, y_train

    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=7, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=max(1, int((y_res==0).sum() / max(1, y_res.sum()))),
        eval_metric='aucpr', random_state=42, n_jobs=-1,
        tree_method='hist'
    )
    model.fit(X_res, y_res, eval_set=[(X_test, y_test)], verbose=False)

    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:,1]

    try:
        auc = roc_auc_score(y_test, y_proba)
        ap  = average_precision_score(y_test, y_proba)
    except Exception:
        auc, ap = 0.0, 0.0

    logger.success(f"Fraud Model → AUC-ROC: {auc:.4f} | Avg Precision: {ap:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred, zero_division=0)}")

    artifact = {
        "model": model, "features": list(X.columns),
        "auc_roc": auc, "avg_precision": ap,
        "trained_at": datetime.now().isoformat(),
        "version": "v2.0"
    }
    joblib.dump(artifact, config.FRAUD_MODEL_PATH)
    logger.success(f"Fraud model saved → {config.FRAUD_MODEL_PATH}")
    return artifact

# ── Model 2: Churn Prediction (LightGBM) ────────────────────────────────────
def train_churn_model(df):
    logger.info("Training Churn Prediction Model (LightGBM)...")
    df = engineer_churn_features(df)
    target = 'is_churned'
    X = df.drop(columns=[target,'churn_risk'], errors='ignore')
    y = df[target]

    logger.info(f"Churn class balance — Churned: {y.sum()} / Active: {(y==0).sum()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
        stratify=y if y.sum() > 1 else None
    )

    model = lgb.LGBMClassifier(
        n_estimators=400, num_leaves=63, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8,
        class_weight='balanced', random_state=42, n_jobs=-1,
        verbose=-1
    )
    model.fit(X_train, y_train,
              eval_set=[(X_test, y_test)],
              callbacks=[lgb.early_stopping(50, verbose=False)])

    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:,1]
    try:
        auc = roc_auc_score(y_test, y_proba)
    except Exception:
        auc = 0.0

    logger.success(f"Churn Model → AUC-ROC: {auc:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred, zero_division=0)}")
    
    artifact = {
        "model": model, "features": list(X.columns),
        "auc_roc": auc, "trained_at": datetime.now().isoformat(), "version": "v2.0"
    }
    joblib.dump(artifact, config.CHURN_MODEL_PATH)
    logger.success(f"Churn model saved → {config.CHURN_MODEL_PATH}")
    return artifact

# ── Model 3: Anomaly Detection (Isolation Forest) ────────────────────────────
def train_anomaly_model(conn):
    logger.info("Training Anomaly Detection Model (Isolation Forest)...")
    query = """
    SELECT amount_inr, latency_ms, fee_amount,
           HOUR(initiated_at) AS txn_hour,
           DAYOFWEEK(initiated_at) AS txn_day
    FROM transactions LIMIT 200000
    """
    df = pd.read_sql(query, conn)
    df.fillna(df.median(numeric_only=True), inplace=True)
    
    model = IsolationForest(
        n_estimators=200, contamination=config.FRAUD_RATIO,
        random_state=42, n_jobs=-1
    )
    model.fit(df)
    
    artifact = {"model": model, "features": list(df.columns),
                "trained_at": datetime.now().isoformat(), "version": "v2.0"}
    joblib.dump(artifact, config.ANOMALY_MODEL_PATH)
    logger.success(f"Anomaly model saved → {config.ANOMALY_MODEL_PATH}")
    return artifact

# ── Model 4: Credit/Risk Scoring (Random Forest) ─────────────────────────────
def train_risk_model(conn):
    logger.info("Training Risk Scoring Model (Random Forest)...")
    query = """
    SELECT
        c.credit_score, c.annual_income, c.segment,
        c.risk_tier, c.kyc_status,
        COUNT(t.txn_id)                          AS total_txns,
        SUM(t.amount_inr)                         AS total_volume,
        SUM(t.is_fraud)                            AS fraud_count,
        AVG(t.fraud_score)                         AS avg_fraud_score,
        (c.risk_tier IN ('High','Critical'))       AS is_high_risk
    FROM customers c
    LEFT JOIN transactions t ON c.customer_id = t.customer_id
    GROUP BY c.customer_id, c.credit_score, c.annual_income,
             c.segment, c.risk_tier, c.kyc_status
    """
    df = pd.read_sql(query, conn)
    df = encode_categoricals(df, ['segment','risk_tier','kyc_status'])
    df.fillna(df.median(numeric_only=True), inplace=True)
    
    target = 'is_high_risk'
    X = df.drop(columns=[target])
    y = df[target].astype(int)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = RandomForestClassifier(
        n_estimators=200, max_depth=10, class_weight='balanced',
        random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)
    
    y_proba = model.predict_proba(X_test)[:,1]
    auc     = roc_auc_score(y_test, y_proba)
    logger.success(f"Risk Model → AUC-ROC: {auc:.4f}")
    
    artifact = {"model": model, "features": list(X.columns),
                "auc_roc": auc, "trained_at": datetime.now().isoformat(), "version": "v2.0"}
    joblib.dump(artifact, config.RISK_MODEL_PATH)
    logger.success(f"Risk model saved → {config.RISK_MODEL_PATH}")
    return artifact

# ── Main ─────────────────────────────────────────────────────────────────────
def train_all():
    logger.info("=== FinSight Pro ML Training Pipeline ===")
    conn = get_conn()
    
    fraud_df = load_fraud_dataset(conn)
    churn_df = load_churn_dataset(conn)
    
    results = {}
    results['fraud']   = train_fraud_model(fraud_df)
    results['churn']   = train_churn_model(churn_df)
    results['anomaly'] = train_anomaly_model(conn)
    results['risk']    = train_risk_model(conn)
    
    conn.close()
    
    logger.success("=== All Models Trained Successfully ===")
    logger.info("Model Summary:")
    for name, r in results.items():
        auc = r.get('auc_roc', 'N/A')
        logger.info(f"  {name:10s} → AUC: {auc}")
    
    return results

if __name__ == "__main__":
    train_all()
