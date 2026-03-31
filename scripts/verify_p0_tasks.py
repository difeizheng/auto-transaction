"""
P0 Task Verification Script
Test non-trading hours fallback, signal scheduler, etc.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from src.data_pipeline.realtime_feed import price_cache
from src.strategy_engine.signal_scheduler import signal_scheduler

def test_trading_hours():
    """Test trading hours detection"""
    print("\n=== Testing Trading Hours Detection ===")

    now = datetime.now()
    is_trading = price_cache._is_trading_hours()
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Is trading hours: {is_trading}")

    if not is_trading:
        print("[OK] Non-trading hours will use database cache")
    else:
        print("[OK] Trading hours will use real-time prices")

def test_signal_scheduler():
    """Test signal scheduler status"""
    print("\n=== Testing Signal Scheduler ===")

    if hasattr(signal_scheduler, '_running'):
        print(f"Scheduler running: {signal_scheduler._running}")

    print(f"Signals generated today: {signal_scheduler._signals_generated_today}")
    print(f"Last signal date: {signal_scheduler._last_signal_date}")

    pending = signal_scheduler.get_pending_signals()
    print(f"Pending signals: {len(pending)}")

    if pending:
        print("\nPending signals list:")
        for sig in pending[:5]:
            print(f"  - {sig.ts_code} {sig.direction} @ {sig.target_price:.2f}")

def test_daemon_scripts():
    """Test daemon scripts"""
    print("\n=== Testing Daemon Scripts ===")

    deploy_dir = Path(__file__).parent.parent / "deploy"

    files = [
        "paper_trading_daemon.bat",
        "daemon.ps1",
        "daemon_config.json.example",
        "README.md"
    ]

    print("Deployment files check:")
    for f in files:
        path = deploy_dir / f
        if path.exists():
            print(f"  [OK] {f}")
        else:
            print(f"  [FAIL] {f} (not found)")

    print("\nUsage:")
    print("  PowerShell: .\\deploy\\daemon.ps1 -Action status")
    print("  CMD: deploy\\paper_trading_daemon.bat status")

def test_database_cache():
    """Test database cache"""
    print("\n=== Testing Database Cache ===")

    from src.utils.database import Database

    db = Database()

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM daily_quotes")
            count = cursor.fetchone()[0]
            print(f"[OK] Database connection OK")
            print(f"  Daily quotes count: {count}")
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM signals")
            count = cursor.fetchone()[0]
            print(f"  Signals count: {count}")
    except Exception as e:
        print(f"  Signals table query failed: {e}")

def main():
    """Main function"""
    print("=" * 60)
    print("P0 Tasks Verification")
    print("=" * 60)

    test_trading_hours()
    test_signal_scheduler()
    test_daemon_scripts()
    test_database_cache()

    print("\n" + "=" * 60)
    print("Verification Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run .\\deploy\\daemon.ps1 -Action start to start daemon")
    print("2. Wait for 14:50 to check signal generation")
    print("3. Check signals execution at 9:31 next day")

if __name__ == "__main__":
    main()
