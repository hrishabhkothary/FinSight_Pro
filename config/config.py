# config/config.py - Central Configuration for FinSight Pro

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ─── Database ────────────────────────────────────────────────
    DB_HOST     = os.getenv("DB_HOST", "localhost")
    DB_PORT     = int(os.getenv("DB_PORT", 3306))
    DB_USER     = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_NAME     = os.getenv("DB_NAME", "finsight_pro")
    DB_URI      = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # ─── Flask ───────────────────────────────────────────────────
    SECRET_KEY  = os.getenv("SECRET_KEY", "finsight-ultra-secure-key-2024")
    DEBUG       = os.getenv("DEBUG", "True") == "True"
    PORT        = int(os.getenv("PORT", 5000))

    # ─── API Keys ────────────────────────────────────────────────
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "demo")
    RAZORPAY_KEY      = os.getenv("RAZORPAY_KEY", "demo")

    # ─── Data Generation ─────────────────────────────────────────
    SYNTHETIC_ROWS     = int(os.getenv("SYNTHETIC_ROWS", 500000))
    FRAUD_RATIO        = float(os.getenv("FRAUD_RATIO", 0.035))
    RANDOM_SEED        = 42

    # ─── ML Model Paths ──────────────────────────────────────────
    MODEL_DIR          = "ml_models/trained"
    FRAUD_MODEL_PATH   = f"{MODEL_DIR}/fraud_detector.joblib"
    CHURN_MODEL_PATH   = f"{MODEL_DIR}/churn_predictor.joblib"
    RISK_MODEL_PATH    = f"{MODEL_DIR}/risk_scorer.joblib"
    ANOMALY_MODEL_PATH = f"{MODEL_DIR}/anomaly_detector.joblib"

    # ─── Export Paths ────────────────────────────────────────────
    EXPORT_DIR  = "exports"
    REPORTS_DIR = "reports"

    # ─── Platform Config ─────────────────────────────────────────
    PLATFORMS = ["Razorpay", "JusPay", "PayTM", "PhonePe", "GooglePay",
                 "Upstox", "Zerodha", "Groww", "HDFC Securities", "ICICI Direct"]
    CATEGORIES = ["UPI", "Card", "NetBanking", "Wallet", "BNPL",
                  "MutualFund", "Stocks", "ForeignExchange", "Crypto", "IPO"]
    CURRENCIES  = ["INR", "USD", "EUR", "GBP", "JPY", "SGD", "AED", "CNY"]

config = Config()
