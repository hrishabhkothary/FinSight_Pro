"""
run.py - FinSight Pro Master Startup Script
Usage: python run.py [--mode dev|prod]
"""

import sys, os, subprocess, threading, time

def check_requirements():
    """Verify Python packages are installed."""
    import importlib
    required = ['flask','flask_cors','flask_socketio','pandas','numpy',
                'mysql.connector','sklearn','xgboost','lightgbm','joblib',
                'plotly','reportlab','loguru']
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg.replace('.','_') if '.' not in pkg else pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)
    print("✓ All packages verified")

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("""
╔═══════════════════════════════════════════════════════╗
║          FinSight Pro - Financial Intelligence        ║
║     Razorpay · JusPay · PayTM · Upstox · Zerodha    ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    check_requirements()
    
    # Import and run app
    sys.path.insert(0, '.')
    from backend.app import app, socketio
    from config.config import config
    import threading
    from backend.app import emit_live_metrics
    
    t = threading.Thread(target=emit_live_metrics, daemon=True)
    t.start()
    
    print(f"\n🚀 Starting FinSight Pro on http://localhost:{config.PORT}")
    print("   Press Ctrl+C to stop\n")
    
    socketio.run(app, host="0.0.0.0", port=config.PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
