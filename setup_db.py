"""
setup_db.py - One-click MySQL database setup for FinSight Pro
Run this FIRST before anything else.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import mysql.connector
from loguru import logger
from config.config import config

def setup_database():
    logger.info("=== FinSight Pro - Database Setup ===")
    
    # Step 1: Connect WITHOUT a database selected first
    try:
        conn = mysql.connector.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD
        )
        cursor = conn.cursor()
        logger.success(f"Connected to MySQL at {config.DB_HOST}:{config.DB_PORT}")
    except mysql.connector.Error as e:
        logger.error(f"Cannot connect to MySQL: {e}")
        logger.error("Please check your .env file (DB_HOST, DB_USER, DB_PASSWORD)")
        sys.exit(1)

    # Step 2: Create the database explicitly first
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE `{config.DB_NAME}`")
        conn.commit()
        logger.success(f"Database '{config.DB_NAME}' created/selected")
    except mysql.connector.Error as e:
        logger.error(f"Failed to create database: {e}")
        sys.exit(1)

    # Step 3: Read schema — skip the CREATE DATABASE and USE lines (already done)
    schema_path = os.path.join(os.path.dirname(__file__), 'sql', 'schema.sql')
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found: {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r') as f:
        raw = f.read()

    # Step 4: Split into individual statements properly
    # Handle DELIMITER // blocks (stored procedures) separately
    statements = []
    in_proc    = False
    proc_lines = []

    for line in raw.splitlines():
        s = line.strip()

        # Skip the CREATE DATABASE / USE lines — already handled above
        if s.upper().startswith('CREATE DATABASE') or s.upper().startswith('USE '):
            continue

        if s.upper().startswith('DELIMITER //'):
            in_proc = True
            proc_lines = []
            continue
        if s.upper().startswith('DELIMITER ;'):
            in_proc = False
            # Everything collected between DELIMITER // and DELIMITER ; is one statement
            stmt = '\n'.join(proc_lines).strip()
            # Strip trailing //
            if stmt.endswith('//'):
                stmt = stmt[:-2].strip()
            if stmt:
                statements.append(stmt)
            proc_lines = []
            continue

        if in_proc:
            proc_lines.append(line)
        else:
            # Normal statements end with ;
            # Accumulate lines until we hit a ;
            if not hasattr(setup_database, '_buf'):
                setup_database._buf = []
            setup_database._buf.append(line)
            if s.endswith(';') and not s.startswith('--') and not s.startswith('#'):
                full = '\n'.join(setup_database._buf).strip()
                if full:
                    statements.append(full)
                setup_database._buf = []

    # Clear buffer
    setup_database._buf = []

    # Step 5: Execute each statement
    executed = 0
    errors   = 0
    IGNORABLE = (1050, 1051, 1060, 1061, 1062, 1091,  # table/key exists
                 1304, 1305, 1360,                       # proc/func exists
                 1065)                                    # empty query

    for stmt in statements:
        stmt = stmt.strip().rstrip(';').strip()
        if not stmt or stmt.startswith('--') or stmt.startswith('#'):
            continue
        try:
            cursor.execute(stmt)
            conn.commit()
            executed += 1
        except mysql.connector.Error as e:
            if e.errno in IGNORABLE:
                executed += 1  # already exists — that's fine
            else:
                logger.warning(f"SQL Warning [{e.errno}]: {e.msg[:120]}")
                errors += 1

    cursor.close()
    conn.close()

    logger.success(f"Schema executed: {executed} statements, {errors} non-critical warnings")
    logger.success(f"Database '{config.DB_NAME}' is fully ready!")

    # Step 6: Create stored procedure (needs separate connection with multi_statements)
    try:
        conn2 = mysql.connector.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME
        )
        cur2 = conn2.cursor()
        cur2.execute("DROP PROCEDURE IF EXISTS sp_refresh_kpi_snapshots")
        proc_sql = """
CREATE PROCEDURE sp_refresh_kpi_snapshots(IN p_date DATE)
BEGIN
    DELETE FROM kpi_snapshots WHERE snapshot_date = p_date;
    INSERT INTO kpi_snapshots (snapshot_date, platform_id, total_txns, total_volume,
                               success_rate, fraud_rate, avg_txn_amount, new_users, active_users)
    SELECT
        p_date,
        platform_id,
        COUNT(*)                             AS total_txns,
        SUM(amount_inr)                      AS total_volume,
        ROUND(AVG(status='SUCCESS')*100,2) AS success_rate,
        ROUND(AVG(is_fraud)*100,4)           AS fraud_rate,
        AVG(amount_inr)                      AS avg_txn_amount,
        0                                    AS new_users,
        COUNT(DISTINCT customer_id)          AS active_users
    FROM transactions
    WHERE DATE(initiated_at) = p_date
    GROUP BY platform_id;
END
"""
        cur2.execute(proc_sql)
        conn2.commit()
        cur2.close()
        conn2.close()
        logger.success("Stored procedure sp_refresh_kpi_snapshots created")
    except Exception as e:
        logger.warning(f"Stored procedure (non-critical): {e}")
    
    # Step 3: Create output directories
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    os.makedirs(config.EXPORT_DIR, exist_ok=True)
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    logger.success("Created output directories")
    
    logger.info("\n" + "="*50)
    logger.info("Next Steps:")
    logger.info("  1. python data_generation/generate_data.py --rows 500000")
    logger.info("  2. python ml_models/scripts/train_models.py")
    logger.info("  3. python backend/app.py")
    logger.info("  4. Open http://localhost:5000")
    logger.info("="*50)

if __name__ == "__main__":
    setup_database()
