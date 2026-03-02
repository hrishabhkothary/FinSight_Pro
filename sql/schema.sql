-- ============================================================
-- FinSight Pro - Complete MySQL Schema
-- Financial Intelligence & Analytics Platform
-- ============================================================

CREATE DATABASE IF NOT EXISTS finsight_pro CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE finsight_pro;

-- ─────────────────────────────────────────────────────────────
-- 1. USERS / CUSTOMERS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    customer_id     VARCHAR(20)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    phone           VARCHAR(15),
    city            VARCHAR(60),
    state           VARCHAR(60),
    country         VARCHAR(60)  DEFAULT 'India',
    segment         ENUM('Retail','HNI','Institutional','SME') DEFAULT 'Retail',
    kyc_status      ENUM('Verified','Pending','Rejected') DEFAULT 'Pending',
    risk_tier       ENUM('Low','Medium','High','Critical')  DEFAULT 'Low',
    credit_score    SMALLINT,
    annual_income   DECIMAL(15,2),
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    is_active       BOOLEAN      DEFAULT TRUE,
    churn_risk      FLOAT        DEFAULT 0.0,
    INDEX idx_segment   (segment),
    INDEX idx_risk_tier (risk_tier),
    INDEX idx_city      (city)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 2. PAYMENT PLATFORMS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS platforms (
    platform_id   INT          PRIMARY KEY AUTO_INCREMENT,
    platform_name VARCHAR(50)  NOT NULL UNIQUE,
    platform_type ENUM('Payment Gateway','UPI','Investment','Crypto','BNPL'),
    api_version   VARCHAR(10)  DEFAULT 'v3',
    uptime_pct    FLOAT        DEFAULT 99.9,
    is_active     BOOLEAN      DEFAULT TRUE
) ENGINE=InnoDB;

INSERT IGNORE INTO platforms (platform_name, platform_type) VALUES
('Razorpay',        'Payment Gateway'),
('JusPay',          'Payment Gateway'),
('PayTM',           'UPI'),
('PhonePe',         'UPI'),
('GooglePay',       'UPI'),
('Upstox',          'Investment'),
('Zerodha',         'Investment'),
('Groww',           'Investment'),
('HDFC Securities', 'Investment'),
('ICICI Direct',    'Investment');

-- ─────────────────────────────────────────────────────────────
-- 3. TRANSACTIONS (Core Fact Table)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    txn_id          VARCHAR(30)   PRIMARY KEY,
    customer_id     VARCHAR(20)   NOT NULL,
    platform_id     INT           NOT NULL,
    txn_type        ENUM('UPI','Card','NetBanking','Wallet','BNPL','Investment','FX') NOT NULL,
    amount          DECIMAL(18,4) NOT NULL,
    currency        VARCHAR(5)    DEFAULT 'INR',
    amount_inr      DECIMAL(18,2) NOT NULL,
    status          ENUM('SUCCESS','FAILED','PENDING','REFUNDED','FLAGGED') DEFAULT 'SUCCESS',
    is_fraud        BOOLEAN       DEFAULT FALSE,
    fraud_score     FLOAT         DEFAULT 0.0,
    merchant_id     VARCHAR(20),
    merchant_name   VARCHAR(100),
    merchant_category VARCHAR(50),
    device_type     ENUM('Mobile','Desktop','Tablet','POS') DEFAULT 'Mobile',
    ip_country      VARCHAR(60),
    initiated_at    DATETIME      NOT NULL,
    completed_at    DATETIME,
    latency_ms      INT,
    fee_amount      DECIMAL(10,4) DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    INDEX idx_customer   (customer_id),
    INDEX idx_platform   (platform_id),
    INDEX idx_initiated  (initiated_at),
    INDEX idx_fraud      (is_fraud),
    INDEX idx_status     (status)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 4. INVESTMENT PORTFOLIOS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id    VARCHAR(20) PRIMARY KEY,
    customer_id     VARCHAR(20) NOT NULL,
    platform_id     INT         NOT NULL,
    asset_class     ENUM('Equity','MutualFund','ETF','Bond','Crypto','FX','Commodity'),
    symbol          VARCHAR(20),
    company_name    VARCHAR(100),
    quantity        DECIMAL(18,6),
    avg_buy_price   DECIMAL(18,4),
    current_price   DECIMAL(18,4),
    invested_amount DECIMAL(18,2),
    current_value   DECIMAL(18,2),
    pnl             DECIMAL(18,2),
    pnl_pct         FLOAT,
    sector          VARCHAR(60),
    exchange        VARCHAR(20) DEFAULT 'NSE',
    last_updated    DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    INDEX idx_customer    (customer_id),
    INDEX idx_asset_class (asset_class)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 5. FRAUD ALERTS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id        INT         PRIMARY KEY AUTO_INCREMENT,
    txn_id          VARCHAR(30) NOT NULL,
    customer_id     VARCHAR(20) NOT NULL,
    alert_type      VARCHAR(60),
    fraud_score     FLOAT,
    model_version   VARCHAR(20),
    status          ENUM('Open','Investigating','Resolved','FalsePositive') DEFAULT 'Open',
    analyst_id      VARCHAR(20),
    created_at      DATETIME    DEFAULT CURRENT_TIMESTAMP,
    resolved_at     DATETIME,
    FOREIGN KEY (txn_id)      REFERENCES transactions(txn_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 6. MARKET DATA (Live Prices)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_data (
    id          BIGINT      PRIMARY KEY AUTO_INCREMENT,
    symbol      VARCHAR(20) NOT NULL,
    price       DECIMAL(18,4),
    open_price  DECIMAL(18,4),
    high_price  DECIMAL(18,4),
    low_price   DECIMAL(18,4),
    volume      BIGINT,
    change_pct  FLOAT,
    recorded_at DATETIME    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_symbol     (symbol),
    INDEX idx_recorded   (recorded_at)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 7. RISK SCORES (ML Output Log)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_scores (
    id              BIGINT      PRIMARY KEY AUTO_INCREMENT,
    customer_id     VARCHAR(20) NOT NULL,
    fraud_risk      FLOAT,
    churn_risk      FLOAT,
    credit_risk     FLOAT,
    composite_score FLOAT,
    model_version   VARCHAR(20),
    scored_at       DATETIME    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    INDEX idx_customer (customer_id),
    INDEX idx_scored   (scored_at)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 8. KPI SNAPSHOTS (Daily Aggregations)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    id              INT         PRIMARY KEY AUTO_INCREMENT,
    snapshot_date   DATE        NOT NULL,
    platform_id     INT,
    total_txns      INT,
    total_volume    DECIMAL(20,2),
    success_rate    FLOAT,
    fraud_rate      FLOAT,
    avg_txn_amount  DECIMAL(15,2),
    new_users       INT,
    active_users    INT,
    created_at      DATETIME    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    UNIQUE KEY uq_snapshot (snapshot_date, platform_id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 9. ADVANCED SQL VIEWS
-- ─────────────────────────────────────────────────────────────

-- View: Full Transaction Detail (JOIN)
CREATE OR REPLACE VIEW v_txn_full AS
SELECT
    t.txn_id,
    c.name          AS customer_name,
    c.segment       AS customer_segment,
    c.city,
    c.risk_tier,
    p.platform_name,
    p.platform_type,
    t.txn_type,
    t.amount_inr,
    t.currency,
    t.status,
    t.is_fraud,
    t.fraud_score,
    t.merchant_name,
    t.merchant_category,
    t.device_type,
    t.initiated_at,
    t.latency_ms,
    t.fee_amount
FROM transactions t
JOIN customers  c ON t.customer_id = c.customer_id
JOIN platforms  p ON t.platform_id = p.platform_id;

-- View: Platform KPIs (GROUP BY + aggregates)
CREATE OR REPLACE VIEW v_platform_kpis AS
SELECT
    p.platform_name,
    p.platform_type,
    COUNT(t.txn_id)                        AS total_txns,
    SUM(t.amount_inr)                      AS total_volume_inr,
    AVG(t.amount_inr)                      AS avg_txn_amount,
    SUM(t.is_fraud)                        AS fraud_count,
    ROUND(AVG(t.is_fraud)*100,3)           AS fraud_rate_pct,
    SUM(CASE WHEN t.status='SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    ROUND(SUM(CASE WHEN t.status='SUCCESS' THEN 1 ELSE 0 END)*100.0/COUNT(*),2) AS success_rate_pct,
    AVG(t.latency_ms)                      AS avg_latency_ms,
    COUNT(DISTINCT t.customer_id)          AS unique_customers,
    SUM(t.fee_amount)                      AS total_fees
FROM transactions t
JOIN platforms p ON t.platform_id = p.platform_id
GROUP BY p.platform_id, p.platform_name, p.platform_type;

-- View: Customer 360 (JOIN + subquery)
CREATE OR REPLACE VIEW v_customer_360 AS
SELECT
    c.customer_id,
    c.name,
    c.email,
    c.segment,
    c.city,
    c.risk_tier,
    c.credit_score,
    c.annual_income,
    c.kyc_status,
    c.churn_risk,
    COUNT(t.txn_id)                        AS total_txns,
    SUM(t.amount_inr)                      AS lifetime_value,
    AVG(t.amount_inr)                      AS avg_txn_amount,
    SUM(t.is_fraud)                        AS fraud_incidents,
    MAX(t.initiated_at)                    AS last_txn_date,
    COALESCE(SUM(pf.current_value),0)      AS portfolio_value,
    COALESCE(SUM(pf.pnl),0)               AS total_pnl
FROM customers c
LEFT JOIN transactions t  ON c.customer_id = t.customer_id
LEFT JOIN portfolios   pf ON c.customer_id = pf.customer_id
GROUP BY c.customer_id, c.name, c.email, c.segment, c.city,
         c.risk_tier, c.credit_score, c.annual_income, c.kyc_status, c.churn_risk;

-- View: Fraud Funnel (UNION of transaction statuses)
CREATE OR REPLACE VIEW v_fraud_funnel AS
SELECT 'Total Transactions' AS stage, COUNT(*) AS count, SUM(amount_inr) AS volume FROM transactions
UNION ALL
SELECT 'Flagged by Model',   COUNT(*), SUM(amount_inr) FROM transactions WHERE fraud_score > 0.5
UNION ALL
SELECT 'Confirmed Fraud',    COUNT(*), SUM(amount_inr) FROM transactions WHERE is_fraud = TRUE
UNION ALL
SELECT 'Refunded',           COUNT(*), SUM(amount_inr) FROM transactions WHERE status = 'REFUNDED';

-- View: Hourly Transaction Heatmap
CREATE OR REPLACE VIEW v_hourly_heatmap AS
SELECT
    DAYOFWEEK(initiated_at)  AS day_of_week,
    HOUR(initiated_at)       AS hour_of_day,
    COUNT(*)                 AS txn_count,
    SUM(amount_inr)          AS volume,
    ROUND(AVG(is_fraud)*100,4) AS fraud_rate
FROM transactions
GROUP BY DAYOFWEEK(initiated_at), HOUR(initiated_at);

-- Stored Procedure created by setup_db.py
