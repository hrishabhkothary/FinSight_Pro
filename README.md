# FinSight Pro 🔥
### Enterprise Financial Intelligence & Analytics Platform

> **Razorpay · JusPay · PayTM · PhonePe · GooglePay · Upstox · Zerodha · Groww**

---

## 🚀 Quick Start (5 Steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure database (.env file — edit DB_PASSWORD)
# (See .env file in project root)

# 3. Setup MySQL schema
python setup_db.py

# 4. Generate 500K transactions
python data_generation/generate_data.py --rows 500000

# 5. Train ML models
python ml_models/scripts/train_models.py

# 6. Run the app
python run.py
# Open: http://localhost:5000
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Core |
| Database | MySQL 8.x | Storage + Advanced SQL |
| API | Flask + SocketIO | REST + WebSocket |
| ML | XGBoost, LightGBM, Scikit-learn | Fraud, Churn, Risk |
| Frontend | Chart.js, D3.js | Dashboard |
| Reports | ReportLab, OpenPyXL | PDF + Excel exports |
| Data | Pandas, NumPy, Faker | ETL + Synthetic data |

---

## Dashboard Features

- **Real-time KPIs** — 8 metric cards with live WebSocket ticker
- **Fraud Intelligence** — Heatmap, funnel, top merchants
- **Customer 360** — Segments, CLV, geographic analytics
- **Investments** — Portfolio by asset class, top stocks
- **Platform Analytics** — Razorpay vs JusPay vs Upstox KPI matrix
- **ML Models** — Live model registry with AUC-ROC scores
- **Fraud Predictor** — Real-time single transaction scoring
- **Upload Data** — Drag-and-drop CSV/XLSX → MySQL
- **Export Reports** — Excel (multi-sheet) + Executive PDF

---

## Full Documentation

See `FinSight_Pro_Master_Documentation.pdf` and 'FinSight_Pro_Setup_Guide.pdf' for complete setup guide, tech stack explanation, SQL features, ML model details, and enterprise usage instructions.

---

## Power BI Integration

1. Open Power BI Desktop
2. Get Data → MySQL Database
3. Server: `localhost`, Database: `finsight_pro`
4. Select views: `v_platform_kpis`, `v_customer_360`, `v_txn_full`
5. Build dashboards on pre-aggregated data
