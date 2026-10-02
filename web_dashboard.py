"""
Web Dashboard Server with Integrated Auto-Scheduler for NDX Strategy
====================================================================
Runs an institutional-grade real-time dashboard in your browser AND
automatically executes the trading strategy daily at 1:50 PM Mountain Time
(3:50 PM Eastern Time) on NYSE trading days.

No need to run scheduler.py separately!

Usage:
    python web_dashboard.py
"""

import os
import sys
import json
import time
import socket
import webbrowser
import threading
from datetime import datetime, date, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse
import pandas as pd
import schedule
import holidays

# Fix Windows console encoding for special characters
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
PORT = 5050

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts

STRATEGY_LOCK = threading.Lock()


# ─────────────────────────────────────────────
# NYSE HOLIDAY CALENDAR & TRADING DAY CHECK
# ─────────────────────────────────────────────
def _easter_date(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_nyse_holiday(check_date: date) -> bool:
    """Check if date is an observed NYSE market holiday."""
    us_holidays = holidays.US(years=check_date.year)
    nyse_open = {
        "Columbus Day", "Veterans Day", "Indigenous Peoples' Day",
        "Columbus Day (Observed)", "Veterans Day (Observed)"
    }
    if check_date in us_holidays:
        return us_holidays.get(check_date) not in nyse_open

    easter = _easter_date(check_date.year)
    return check_date == (easter - timedelta(days=2))


def is_trading_day() -> bool:
    """Returns True if today is a weekday and not an NYSE market holiday."""
    today = datetime.now().date()
    if today.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if is_nyse_holiday(today):
        return False
    return True


def execute_daily_strategy():
    """Execute strategy run safely with a lock. Used by scheduler and API."""
    if not STRATEGY_LOCK.acquire(blocking=False):
        return {"status": "busy", "message": "Strategy execution is already in progress"}

    try:
        now = datetime.now()
        print(f"\n{'='*60}")
        print(f"  [AUTO-SCHEDULER] Daily Run Triggered: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        if not is_trading_day():
            msg = "Not an NYSE trading day (weekend or market holiday) — skipping."
            print(f"  [AUTO-SCHEDULER] {msg}")
            print(f"{'='*60}\n")
            return {"status": "skipped", "message": msg}

        print("  [AUTO-SCHEDULER] Executing strategy...")
        ts.run_strategy()
        print(f"  [AUTO-SCHEDULER] Finished successfully at {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}\n")
        return {"status": "success", "message": "Strategy executed successfully"}
    except Exception as e:
        print(f"  [AUTO-SCHEDULER ERROR] {e}")
        return {"status": "error", "message": str(e)}
    finally:
        STRATEGY_LOCK.release()


def start_scheduler_thread():
    """Runs in background: executes strategy daily at 1:50 PM Mountain Time."""
    # 1:50 PM Mountain Time = 3:50 PM Eastern Time
    schedule.every().day.at("13:50").do(execute_daily_strategy)

    def scheduler_loop():
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print(f"[SCHEDULER LOOP ERROR] {e}")
            time.sleep(10)

    t = threading.Thread(target=scheduler_loop, daemon=True, name="StrategySchedulerThread")
    t.start()


# ─────────────────────────────────────────────
# DATA AGGREGATION FOR DASHBOARD
# ─────────────────────────────────────────────
def get_dashboard_data():
    """Read and compile all current data from files into a complete, fresh JSON payload."""
    portfolio_file = os.path.join(BASE_DIR, "portfolio_state.json")
    daily_file = os.path.join(BASE_DIR, "daily_summary.csv")
    trade_file = os.path.join(BASE_DIR, "trade_log.csv")
    log_file = os.path.join(BASE_DIR, "strategy.log")

    # 1. Load Portfolio State (Symmetric 1.0x ATR)
    if os.path.exists(portfolio_file):
        with open(portfolio_file, "r", encoding="utf-8") as f:
            portfolio = json.load(f)
    else:
        portfolio = {
            "position": "CASH",
            "allocation_pct": 1.0,
            "cash": 10000.0,
            "tqqq_shares": 0.0,
            "sqqq_shares": 0.0,
            "tqqq_avg_cost": 0.0,
            "sqqq_avg_cost": 0.0,
            "total_value": 10000.0,
            "starting_capital": 10000.0,
            "last_signal": "System Initialized",
            "last_updated": datetime.now().isoformat(),
            "last_run_date": None,
            "trim_active": False,
            "prev_rsi": 50.0,
            "benchmark_ndx_start": 29404.63,
            "benchmark_tqqq_start": 38.71
        }

    # 2. Load Daily Summaries
    daily_records = []
    if os.path.exists(daily_file):
        try:
            df_daily = pd.read_csv(daily_file)
            df_daily = df_daily.fillna(0)
            daily_records = df_daily.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading daily summary: {e}")

    # 3. Load Trade Log
    trades = []
    if os.path.exists(trade_file):
        try:
            df_trades = pd.read_csv(trade_file)
            df_trades = df_trades.fillna("")
            trades = df_trades.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading trade log: {e}")

    # 4. Load Recent Log Lines (last 100 lines)
    recent_logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                recent_logs = [line.strip() for line in lines[-100:] if line.strip()]
        except Exception as e:
            print(f"Error reading log file: {e}")

    # 5. Compute Key Statistics
    starting_cap = float(portfolio.get("starting_capital", 10000.0))
    current_val = float(portfolio.get("total_value", starting_cap))
    total_pnl = current_val - starting_cap
    total_pnl_pct = (current_val / starting_cap - 1) * 100 if starting_cap > 0 else 0.0

    hwm = starting_cap
    max_dd = 0.0
    for r in daily_records:
        val = float(r.get("total_value", starting_cap))
        if val > hwm:
            hwm = val
        dd = (val - hwm) / hwm * 100 if hwm > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    latest_daily = daily_records[-1] if daily_records else {}
    ndx_price = float(latest_daily.get("ndx_price", 30807.93))
    sma50 = float(latest_daily.get("sma50", 29457.93))
    sma250 = float(latest_daily.get("sma250", 27024.66))
    rsi = float(latest_daily.get("rsi", 65.3))

    dist_sma50_pts = ndx_price - sma50
    dist_sma50_pct = (dist_sma50_pts / sma50) * 100 if sma50 > 0 else 0
    dist_sma250_pts = ndx_price - sma250
    dist_sma250_pct = (dist_sma250_pts / sma250) * 100 if sma250 > 0 else 0

    # Next run scheduled calculation (1:50 PM MT = 13:50)
    now = datetime.now()
    target_today = now.replace(hour=13, minute=50, second=0, microsecond=0)
    if now < target_today:
        next_run_dt = target_today
    else:
        next_run_dt = target_today + timedelta(days=1)
        if next_run_dt.weekday() == 5:
            next_run_dt += timedelta(days=2)
        elif next_run_dt.weekday() == 6:
            next_run_dt += timedelta(days=1)

    # Extract latest live prices for active ETFs
    tqqq_price = 0.0
    sqqq_price = 0.0
    for line in reversed(recent_logs):
        if "Current Prices — TQQQ:" in line:
            try:
                parts = line.split("TQQQ: $")[1].split(" | SQQQ: $")
                tqqq_price = float(parts[0])
                sqqq_price = float(parts[1].split()[0])
                break
            except Exception:
                pass
    if tqqq_price <= 0 and portfolio.get("tqqq_shares", 0) > 0:
        tqqq_price = round((portfolio["total_value"] - portfolio.get("cash", 0)) / portfolio["tqqq_shares"], 2)
    if sqqq_price <= 0:
        sqqq_price = 33.12  # fallback

    fresh_stats = {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "high_water_mark": round(hwm, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trading_days_tracked": len(daily_records),
        "total_trades": len(trades),
        "ndx_price": round(ndx_price, 2),
        "tqqq_price": round(tqqq_price, 2),
        "sqqq_price": round(sqqq_price, 2),
        "sma50": round(sma50, 2),
        "sma250": round(sma250, 2),
        "rsi": round(rsi, 2),
        "dist_sma50_pts": round(dist_sma50_pts, 2),
        "dist_sma50_pct": round(dist_sma50_pct, 2),
        "dist_sma250_pts": round(dist_sma250_pts, 2),
        "dist_sma250_pct": round(dist_sma250_pct, 2),
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "next_run_time": next_run_dt.strftime("%Y-%m-%d %H:%M:%S MT"),
    }

    # Load existing template if available so model definitions and descriptions are preserved
    data_json_path = os.path.join(WEB_DIR, "data.json")
    base_data = None
    if os.path.exists(data_json_path):
        try:
            with open(data_json_path, "r", encoding="utf-8") as f:
                base_data = json.load(f)
        except Exception as e:
            print(f"Error loading {data_json_path}: {e}")

    if base_data and isinstance(base_data, dict):
        data = base_data
        data["portfolio"] = portfolio
        data["daily_summary"] = daily_records
        data["trades"] = trades
        data["recent_logs"] = recent_logs
        if "stats" in data and isinstance(data["stats"], dict):
            data["stats"].update(fresh_stats)
        else:
            data["stats"] = fresh_stats

        # Update models structure
        if "models" in data and isinstance(data["models"], dict):
            # Symmetric ATR model
            if "symmetric_atr" in data["models"]:
                m_sym = data["models"]["symmetric_atr"]
                m_sym["portfolio"] = portfolio
                m_sym["ending_value"] = round(current_val, 2)
                m_sym["total_return_pct"] = round(total_pnl_pct, 2)
                m_sym["daily_summary"] = daily_records
                m_sym["trades"] = trades
                m_sym["recent_logs"] = recent_logs
                if "stats" in m_sym and isinstance(m_sym["stats"], dict):
                    m_sym["stats"].update(fresh_stats)
                else:
                    m_sym["stats"] = fresh_stats

            # Original Agile model
            if "original_agile" in data["models"]:
                m_orig = data["models"]["original_agile"]
                orig_p_file = os.path.join(BASE_DIR, "portfolio_state_original.json")
                orig_d_file = os.path.join(BASE_DIR, "daily_summary_original.csv")
                orig_t_file = os.path.join(BASE_DIR, "trade_log_original.csv")

                if os.path.exists(orig_p_file):
                    try:
                        with open(orig_p_file, "r", encoding="utf-8") as f:
                            p_orig = json.load(f)
                        m_orig["portfolio"] = p_orig
                        orig_val = float(p_orig.get("total_value", 10000.0))
                        orig_start = float(p_orig.get("starting_capital", 10000.0))
                        orig_pnl_pct = (orig_val / orig_start - 1) * 100
                        m_orig["ending_value"] = round(orig_val, 2)
                        m_orig["total_return_pct"] = round(orig_pnl_pct, 2)
                        if "stats" in m_orig and isinstance(m_orig["stats"], dict):
                            m_orig["stats"]["total_pnl"] = round(orig_val - orig_start, 2)
                            m_orig["stats"]["total_pnl_pct"] = round(orig_pnl_pct, 2)
                            m_orig["stats"]["ndx_price"] = round(ndx_price, 2)
                            m_orig["stats"]["sma50"] = round(sma50, 2)
                            m_orig["stats"]["sma250"] = round(sma250, 2)
                            m_orig["stats"]["rsi"] = round(rsi, 2)
                    except Exception as e:
                        print(f"Error loading original portfolio state: {e}")

                if os.path.exists(orig_d_file):
                    try:
                        df_orig = pd.read_csv(orig_d_file).fillna(0)
                        m_orig["daily_summary"] = df_orig.to_dict(orient="records")
                    except Exception as e:
                        print(f"Error loading original daily summary: {e}")

                if os.path.exists(orig_t_file):
                    try:
                        df_ot = pd.read_csv(orig_t_file).fillna("")
                        m_orig["trades"] = df_ot.to_dict(orient="records")
                    except Exception as e:
                        print(f"Error loading original trades: {e}")

        data["scheduler"] = {
            "active": True,
            "is_active_session": is_trading_day(),
            "scheduled_time": "1:50 PM MT (3:50 PM ET)",
            "next_run_target": "13:50:00 MT (15:50:00 ET)",
            "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run_date": portfolio.get("last_run_date"),
        }
        return data

    return {
        "portfolio": portfolio,
        "daily_summary": daily_records,
        "trades": trades,
        "recent_logs": recent_logs,
        "stats": fresh_stats,
        "scheduler": {
            "active": True,
            "is_active_session": is_trading_day(),
            "scheduled_time": "1:50 PM MT (3:50 PM ET)",
            "next_run_target": "13:50:00 MT (15:50:00 ET)",
            "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run_date": portfolio.get("last_run_date"),
        },
        "config": {
            "starting_capital": starting_cap,
            "rsi_overbought": ts.CONFIG.get("rsi_overbought", 75),
            "rsi_trim_medium": ts.CONFIG.get("rsi_trim_medium", 50),
            "rsi_oversold": ts.CONFIG.get("rsi_oversold", 30),
            "atr_buffer_multiplier": ts.CONFIG.get("atr_buffer_multiplier", 1.0),
            "tqqq_ticker": ts.CONFIG.get("tqqq_ticker", "TQQQ"),
            "sqqq_ticker": ts.CONFIG.get("sqqq_ticker", "SQQQ"),
            "ntfy_topic": ts.CONFIG.get("ntfy_topic", "ndx-quant-strategy-alerts"),
        }
    }


# ─────────────────────────────────────────────
# HTTP HANDLER WITH API & ASSETS
# ─────────────────────────────────────────────
class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving web assets, data API, and execution triggers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/data":
            try:
                data = get_dashboard_data()
                payload = json.dumps(data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/run_strategy":
            try:
                result = execute_daily_strategy()
                payload = json.dumps(result).encode("utf-8")
                code = 200 if result.get("status") in ("success", "skipped") else 500
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def run_server(port=PORT, auto_open=True):
    actual_port = port
    while is_port_in_use(actual_port):
        actual_port += 1

    # Start the integrated auto-scheduler thread
    start_scheduler_thread()

    server_address = ("", actual_port)
    httpd = HTTPServer(server_address, DashboardHandler)
    url = f"http://localhost:{actual_port}"

    print("=" * 65)
    print("  [ONLINE] NDX QUANT STRATEGY — DASHBOARD & AUTO-SCHEDULER")
    print("=" * 65)
    print(f"  Local URL:        {url}")
    print(f"  Live Data API:    {url}/api/data")
    print(f"  Auto-Scheduler:   ACTIVE — Daily at 1:50 PM MT (3:50 PM ET)")
    print(f"                    (No need to run scheduler.py separately!)")
    print("  Press Ctrl+C to terminate the server.")
    print("=" * 65)

    if auto_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard server stopped.")
        httpd.server_close()


if __name__ == "__main__":
    auto_browser = "--no-browser" not in sys.argv
    run_server(PORT, auto_open=auto_browser)
