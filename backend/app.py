"""
backend/app.py - FinSight Pro Flask Backend
Full-featured REST API + WebSocket server for real-time financial analytics
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import pandas as pd
import numpy as np
import mysql.connector
import joblib
import json
import threading
import time
from datetime import datetime, timedelta
from loguru import logger
from io import BytesIO
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

from config.config import config

# ── App Init ─────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder='../frontend/templates',
    static_folder='../frontend/static'
)
app.config['SECRET_KEY'] = config.SECRET_KEY
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── DB Helper ─────────────────────────────────────────────────────────────────
from sqlalchemy import create_engine, text as sa_text

_engine = None
def get_engine():
    global _engine
    if _engine is None:
        url = (f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
               f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
        _engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    return _engine

def get_db():
    return mysql.connector.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME, connection_timeout=10
    )

def query_df(sql, params=None):
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(sa_text(sql), conn)
        return df
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return pd.DataFrame()

# ── ML Model Loader ──────────────────────────────────────────────────────────
models = {}
def load_models():
    global models
    for name, path in [
        ("fraud",   config.FRAUD_MODEL_PATH),
        ("churn",   config.CHURN_MODEL_PATH),
        ("risk",    config.RISK_MODEL_PATH),
        ("anomaly", config.ANOMALY_MODEL_PATH),
    ]:
        if os.path.exists(path):
            try:
                models[name] = joblib.load(path)
                logger.success(f"Loaded {name} model from {path}")
            except Exception as e:
                logger.warning(f"Could not load {name} model: {e}")

load_models()

# ─────────────────────────────────────────────────────────────────────────────
# ── ROUTES: PAGES ────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ─────────────────────────────────────────────────────────────────────────────
# ── API: DASHBOARD KPIs ──────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/kpis", methods=["GET"])
def api_kpis():
    days = int(request.args.get("days", 30))
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    df = query_df(f"""
        SELECT
            COUNT(*)                                   AS total_txns,
            SUM(amount_inr)                             AS total_volume,
            AVG(amount_inr)                             AS avg_txn,
            ROUND(AVG(is_fraud)*100, 3)                AS fraud_rate,
            ROUND(SUM(status='SUCCESS')*100.0/COUNT(*),2) AS success_rate,
            COUNT(DISTINCT customer_id)                AS unique_customers,
            SUM(fee_amount)                             AS total_fees,
            AVG(latency_ms)                             AS avg_latency,
            SUM(is_fraud)                               AS fraud_count
        FROM transactions
        WHERE initiated_at >= '{since}'
    """)
    
    if df.empty:
        return jsonify({"error": "No data"}), 404
    
    row = df.iloc[0]
    return jsonify({
        "total_txns":        int(row.get("total_txns", 0) or 0),
        "total_volume":      float(row.get("total_volume", 0) or 0),
        "avg_txn":           float(row.get("avg_txn", 0) or 0),
        "fraud_rate":        float(row.get("fraud_rate", 0) or 0),
        "success_rate":      float(row.get("success_rate", 0) or 0),
        "unique_customers":  int(row.get("unique_customers", 0) or 0),
        "total_fees":        float(row.get("total_fees", 0) or 0),
        "avg_latency":       float(row.get("avg_latency", 0) or 0),
        "fraud_count":       int(row.get("fraud_count", 0) or 0),
    })

# ── API: PLATFORM KPIs ───────────────────────────────────────────────────────
@app.route("/api/platforms", methods=["GET"])
def api_platforms():
    df = query_df("SELECT * FROM v_platform_kpis ORDER BY total_volume_inr DESC")
    return jsonify(df.fillna(0).to_dict(orient="records"))

# ── API: TRANSACTION TREND ───────────────────────────────────────────────────
@app.route("/api/trend/daily", methods=["GET"])
def api_daily_trend():
    days = int(request.args.get("days", 90))
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = query_df(f"""
        SELECT DATE(initiated_at) AS date,
               COUNT(*)           AS txn_count,
               SUM(amount_inr)    AS volume,
               SUM(is_fraud)      AS fraud_count,
               AVG(is_fraud)*100  AS fraud_rate
        FROM transactions
        WHERE initiated_at >= '{since}'
        GROUP BY DATE(initiated_at)
        ORDER BY date
    """)
    df['date'] = df['date'].astype(str)
    return jsonify(df.fillna(0).to_dict(orient="records"))

# ── API: FRAUD ANALYTICS ─────────────────────────────────────────────────────
@app.route("/api/fraud/summary", methods=["GET"])
def api_fraud_summary():
    df = query_df("SELECT * FROM v_fraud_funnel")
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/fraud/heatmap", methods=["GET"])
def api_fraud_heatmap():
    df = query_df("SELECT * FROM v_hourly_heatmap ORDER BY day_of_week, hour_of_day")
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/fraud/top_merchants", methods=["GET"])
def api_fraud_merchants():
    df = query_df("""
        SELECT merchant_name, merchant_category,
               COUNT(*) AS fraud_txns, SUM(amount_inr) AS fraud_volume
        FROM transactions WHERE is_fraud=1
        GROUP BY merchant_name, merchant_category
        ORDER BY fraud_txns DESC LIMIT 20
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

# ── API: CUSTOMER ANALYTICS ──────────────────────────────────────────────────
@app.route("/api/customers/segments", methods=["GET"])
def api_customer_segments():
    df = query_df("""
        SELECT segment, risk_tier,
               COUNT(*) AS count,
               AVG(credit_score) AS avg_credit,
               AVG(annual_income) AS avg_income,
               AVG(churn_risk) AS avg_churn_risk
        FROM customers GROUP BY segment, risk_tier ORDER BY segment, risk_tier
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/customers/top", methods=["GET"])
def api_top_customers():
    limit = int(request.args.get("limit", 20))
    df = query_df(f"""
        SELECT customer_id, name, segment, city, risk_tier,
               lifetime_value, total_txns, portfolio_value, total_pnl, fraud_incidents
        FROM v_customer_360
        ORDER BY lifetime_value DESC LIMIT {limit}
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/customers/<customer_id>", methods=["GET"])
def api_customer_detail(customer_id):
    df = query_df(f"""
        SELECT * FROM v_customer_360 WHERE customer_id='{customer_id}'
    """)
    if df.empty:
        return jsonify({"error": "Customer not found"}), 404
    
    txns = query_df(f"""
        SELECT txn_id, txn_type, amount_inr, status, is_fraud,
               platform_id, initiated_at, merchant_name
        FROM transactions WHERE customer_id='{customer_id}'
        ORDER BY initiated_at DESC LIMIT 50
    """)
    txns['initiated_at'] = txns['initiated_at'].astype(str)
    
    return jsonify({
        "profile": df.fillna(0).iloc[0].to_dict(),
        "recent_transactions": txns.fillna(0).to_dict(orient="records")
    })

# ── API: INVESTMENT ANALYTICS ─────────────────────────────────────────────────
@app.route("/api/investments/summary", methods=["GET"])
def api_investments():
    df = query_df("""
        SELECT asset_class, sector,
               COUNT(*) AS positions,
               SUM(invested_amount) AS total_invested,
               SUM(current_value) AS total_current_value,
               SUM(pnl) AS total_pnl,
               AVG(pnl_pct) AS avg_return_pct
        FROM portfolios
        GROUP BY asset_class, sector
        ORDER BY total_invested DESC
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/investments/topstocks", methods=["GET"])
def api_top_stocks():
    df = query_df("""
        SELECT symbol, company_name, sector, exchange,
               SUM(quantity) AS total_qty,
               AVG(avg_buy_price) AS avg_cost,
               AVG(current_price) AS avg_curr_price,
               SUM(pnl) AS total_pnl,
               AVG(pnl_pct) AS avg_pnl_pct
        FROM portfolios WHERE asset_class='Equity'
        GROUP BY symbol, company_name, sector, exchange
        ORDER BY total_pnl DESC LIMIT 20
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

# ── API: ML PREDICT (REAL-TIME) ───────────────────────────────────────────────
@app.route("/api/ml/predict_fraud", methods=["POST"])
def api_predict_fraud():
    if "fraud" not in models:
        return jsonify({"error": "Fraud model not loaded. Run train_models.py first."}), 503
    
    data = request.json
    artifact = models["fraud"]
    model    = artifact["model"]
    features = artifact["features"]
    
    # Build feature vector
    try:
        row = {f: 0 for f in features}
        row.update({
            "amount_inr":   float(data.get("amount_inr", 0)),
            "amount_log":   np.log1p(float(data.get("amount_inr", 0))),
            "txn_hour":     int(data.get("txn_hour", 12)),
            "txn_day":      int(data.get("txn_day", 2)),
            "latency_ms":   int(data.get("latency_ms", 300)),
            "latency_log":  np.log1p(int(data.get("latency_ms", 300))),
            "foreign_ip":   int(data.get("foreign_ip", 0)),
            "credit_score": int(data.get("credit_score", 700)),
            "annual_income":float(data.get("annual_income", 500000)),
            "is_high_value":int(float(data.get("amount_inr", 0)) > 500000),
            "is_night_txn": int(int(data.get("txn_hour", 12)) < 5 or int(data.get("txn_hour", 12)) > 22),
            "churn_risk":   float(data.get("churn_risk", 0.3)),
            "fee_ratio":    float(data.get("fee_amount", 0)) / (float(data.get("amount_inr", 1)) + 1),
        })
        X = pd.DataFrame([row])[features]
        prob   = model.predict_proba(X)[0][1]
        label  = "FRAUD" if prob > 0.5 else "LEGITIMATE"
        return jsonify({
            "fraud_probability": round(float(prob), 4),
            "label": label,
            "risk_level": "HIGH" if prob > 0.7 else ("MEDIUM" if prob > 0.4 else "LOW"),
            "model_version": artifact.get("version", "v2.0")
        })
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/ml/models_info", methods=["GET"])
def api_models_info():
    info = {}
    for name, artifact in models.items():
        info[name] = {
            "trained_at":  artifact.get("trained_at", "N/A"),
            "version":     artifact.get("version", "N/A"),
            "auc_roc":     artifact.get("auc_roc", "N/A"),
            "loaded":      True
        }
    return jsonify(info)

# ── API: REAL-TIME DATA UPLOAD ────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    f    = request.files["file"]
    table = request.form.get("table", "transactions")
    
    try:
        if f.filename.endswith(".csv"):
            df = pd.read_csv(f)
        elif f.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(f)
        else:
            return jsonify({"error": "Only CSV and XLSX supported"}), 400
        
        conn   = get_db()
        cursor = conn.cursor()
        cols   = ", ".join(df.columns)
        ph     = ", ".join(["%s"] * len(df.columns))
        sql    = f"INSERT IGNORE INTO {table} ({cols}) VALUES ({ph})"
        records = [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False)]
        cursor.executemany(sql, records)
        conn.commit()
        conn.close()
        
        return jsonify({"inserted": len(records), "table": table, "columns": list(df.columns)})
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500

# ── API: EXPORT EXCEL ─────────────────────────────────────────────────────────
@app.route("/api/export/excel", methods=["GET"])
def api_export_excel():
    report_type = request.args.get("type", "transactions")
    days        = int(request.args.get("days", 30))
    since       = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    queries = {
        "transactions": f"SELECT * FROM v_txn_full WHERE initiated_at >= '{since}' LIMIT 50000",
        "platforms":    "SELECT * FROM v_platform_kpis",
        "customers":    "SELECT * FROM v_customer_360 LIMIT 10000",
        "investments":  "SELECT * FROM portfolios LIMIT 20000",
    }
    sql = queries.get(report_type, queries["transactions"])
    df  = query_df(sql)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=report_type.title())
        # Add summary sheet
        summary = pd.DataFrame({
            "Metric": ["Total Rows", "Exported At", "Report Type", "Date Range"],
            "Value":  [len(df), datetime.now().isoformat(), report_type, f"Last {days} days"]
        })
        summary.to_excel(writer, index=False, sheet_name="Summary")
    
    output.seek(0)
    filename = f"finsight_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=filename)

# ── API: EXPORT PDF REPORT ────────────────────────────────────────────────────
@app.route("/api/export/pdf", methods=["GET"])
def api_export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable)
    from reportlab.lib.units import cm
    
    output   = BytesIO()
    doc      = SimpleDocTemplate(output, pagesize=A4,
                                  leftMargin=2*cm, rightMargin=2*cm,
                                  topMargin=2*cm, bottomMargin=2*cm)
    styles   = getSampleStyleSheet()
    story    = []
    
    NAVY  = colors.HexColor("#0d1b2a")
    GOLD  = colors.HexColor("#f5a623")
    TEAL  = colors.HexColor("#17a2b8")
    
    title_style = ParagraphStyle("Title2", parent=styles["Title"],
                                  fontSize=22, textColor=NAVY, spaceAfter=10)
    h1_style    = ParagraphStyle("H1", parent=styles["Heading1"],
                                  fontSize=14, textColor=NAVY, spaceAfter=6)
    body_style  = styles["Normal"]
    
    # Title
    story.append(Paragraph("FinSight Pro – Executive Analytics Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}", body_style))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD))
    story.append(Spacer(1, 0.5*cm))
    
    # KPIs
    kpi_df = query_df("""
        SELECT COUNT(*) total_txns, SUM(amount_inr) total_volume,
               ROUND(AVG(is_fraud)*100,3) fraud_rate,
               ROUND(SUM(status='SUCCESS')*100.0/COUNT(*),2) success_rate
        FROM transactions WHERE initiated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """)
    
    story.append(Paragraph("30-Day KPI Summary", h1_style))
    if not kpi_df.empty:
        r = kpi_df.iloc[0]
        kpi_data = [
            ["Metric", "Value"],
            ["Total Transactions", f"{int(r.get('total_txns',0) or 0):,}"],
            ["Total Volume (INR)", f"₹{float(r.get('total_volume',0) or 0):,.2f}"],
            ["Fraud Rate", f"{float(r.get('fraud_rate',0) or 0):.3f}%"],
            ["Success Rate", f"{float(r.get('success_rate',0) or 0):.2f}%"],
        ]
        tbl = Table(kpi_data, colWidths=[8*cm, 8*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 11),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.lightgrey),
            ("PADDING",    (0,0), (-1,-1), 8),
        ]))
        story.append(tbl)
    
    story.append(Spacer(1, 0.5*cm))
    
    # Platform table
    story.append(Paragraph("Platform Performance", h1_style))
    pf_df = query_df("SELECT platform_name, total_txns, total_volume_inr, fraud_rate_pct, success_rate_pct FROM v_platform_kpis ORDER BY total_volume_inr DESC LIMIT 10")
    if not pf_df.empty:
        pf_data = [["Platform","Txns","Volume (INR)","Fraud%","Success%"]]
        for _, row in pf_df.iterrows():
            pf_data.append([
                str(row.get("platform_name","")),
                f"{int(row.get('total_txns',0) or 0):,}",
                f"₹{float(row.get('total_volume_inr',0) or 0):,.0f}",
                f"{float(row.get('fraud_rate_pct',0) or 0):.3f}%",
                f"{float(row.get('success_rate_pct',0) or 0):.1f}%",
            ])
        tbl2 = Table(pf_data, colWidths=[4*cm, 2.5*cm, 4.5*cm, 2.5*cm, 3*cm])
        tbl2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), TEAL),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#e8f4fd")]),
            ("GRID",          (0,0), (-1,-1), 0.3, colors.lightgrey),
            ("PADDING",       (0,0), (-1,-1), 6),
        ]))
        story.append(tbl2)
    
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Paragraph("© FinSight Pro | Confidential & Proprietary", body_style))
    
    doc.build(story)
    output.seek(0)
    filename = f"FinSight_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)

# ── WEBSOCKET: Real-time streaming ───────────────────────────────────────────
def emit_live_metrics():
    """Background thread: broadcast live KPIs every 5s."""
    import random
    while True:
        try:
            df = query_df("""
                SELECT COUNT(*) as txns, SUM(amount_inr) as vol, AVG(is_fraud)*100 as fr
                FROM transactions WHERE initiated_at >= NOW() - INTERVAL 1 HOUR
            """)
            if not df.empty:
                r = df.iloc[0]
                socketio.emit("live_kpi", {
                    "txns_last_hour": int(r.get("txns", 0) or 0),
                    "volume_last_hour": float(r.get("vol", 0) or 0),
                    "fraud_rate_last_hour": float(r.get("fr", 0) or 0),
                    "timestamp": datetime.now().isoformat(),
                    # Simulate live transaction stream
                    "live_txn": {
                        "amount": round(random.uniform(100, 100000), 2),
                        "platform": random.choice(["Razorpay","PayTM","PhonePe","JusPay"]),
                        "type": random.choice(["UPI","Card","NetBanking"]),
                        "status": random.choice(["SUCCESS","SUCCESS","SUCCESS","FAILED"]),
                    }
                })
        except Exception as e:
            logger.warning(f"Live metric emit error: {e}")
        time.sleep(5)

@socketio.on("connect")
def on_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"message": "Connected to FinSight Pro live feed"})

@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

# ── API: VISUALIZATION DATA ───────────────────────────────────────────────────
@app.route("/api/charts/txn_types", methods=["GET"])
def api_chart_txn_types():
    df = query_df("""
        SELECT txn_type, COUNT(*) as count, SUM(amount_inr) as volume
        FROM transactions GROUP BY txn_type ORDER BY count DESC
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/charts/geographic", methods=["GET"])
def api_chart_geographic():
    df = query_df("""
        SELECT c.city, c.state, COUNT(t.txn_id) as txns, SUM(t.amount_inr) as volume
        FROM transactions t JOIN customers c ON t.customer_id=c.customer_id
        GROUP BY c.city, c.state ORDER BY txns DESC LIMIT 30
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

@app.route("/api/charts/risk_distribution", methods=["GET"])
def api_risk_distribution():
    df = query_df("""
        SELECT risk_tier, segment, COUNT(*) as count, AVG(credit_score) as avg_credit
        FROM customers GROUP BY risk_tier, segment
    """)
    return jsonify(df.fillna(0).to_dict(orient="records"))

# ── Health check ─────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    db_ok = False
    try:
        with get_engine().connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        db_ok = True
    except:
        pass
    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "models_loaded": list(models.keys()),
        "timestamp": datetime.now().isoformat()
    })

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start live metric thread
    t = threading.Thread(target=emit_live_metrics, daemon=True)
    t.start()
    
    logger.info(f"Starting FinSight Pro on http://localhost:{config.PORT}")
    socketio.run(app, host="0.0.0.0", port=config.PORT, debug=config.DEBUG, use_reloader=False)