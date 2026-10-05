"""
Web Dashboard Server for NDX Strategy (View-Only)
=================================================
Local read-only dashboard. Does NOT schedule, does NOT execute trades, does NOT write state.
Trading is executed exclusively by GitHub Actions in the cloud.

Usage:
    python web_dashboard.py [--no-browser]
"""

import os
import sys
import json
import socket
import webbrowser
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import pandas as pd
import holidays
import yfinance as yf

# Fix Windows console encoding for special characters
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
PORT = 5050

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts

# ─────────────────────────────────────────────
# TOP 20 NDX CONSTITUENTS & LIVE QUOTE ENGINE
# ─────────────────────────────────────────────
TOP_20_NDX = [
    {"symbol": "NVDA", "name": "NVIDIA", "weight": 8.8},
    {"symbol": "AAPL", "name": "Apple", "weight": 8.4},
    {"symbol": "MSFT", "name": "Microsoft", "weight": 7.9},
    {"symbol": "AMZN", "name": "Amazon", "weight": 5.5},
    {"symbol": "GOOGL", "name": "Alphabet", "weight": 5.2},
    {"symbol": "META", "name": "Meta", "weight": 5.1},
    {"symbol": "TSLA", "name": "Tesla", "weight": 3.2},
    {"symbol": "AVGO", "name": "Broadcom", "weight": 4.8},
    {"symbol": "COST", "name": "Costco", "weight": 2.4},
    {"symbol": "NFLX", "name": "Netflix", "weight": 2.1},
    {"symbol": "AMD", "name": "AMD", "weight": 1.9},
    {"symbol": "ASML", "name": "ASML", "weight": 1.7},
    {"symbol": "PEP", "name": "PepsiCo", "weight": 1.3},
    {"symbol": "LIN", "name": "Linde", "weight": 1.3},
    {"symbol": "CSCO", "name": "Cisco", "weight": 1.5},
    {"symbol": "TMUS", "name": "T-Mobile", "weight": 1.4},
    {"symbol": "QCOM", "name": "Qualcomm", "weight": 1.5},
    {"symbol": "ADBE", "name": "Adobe", "weight": 1.3},
    {"symbol": "TXN", "name": "Texas Inst", "weight": 1.2},
    {"symbol": "AMAT", "name": "Applied Mat", "weight": 1.2},
]

_quotes_cache = {
    "timestamp": 0.0,
    "data": None,
    "lock": threading.Lock()
}

def get_ndx_top20_quotes(force: bool = False) -> dict:
    """Fetch real-time regular and extended-hours quotes for Top 20 NDX constituents with 10s TTL."""
    now = time.time()
    if not force and _quotes_cache["data"] and (now - _quotes_cache["timestamp"] < 10.0):
        return _quotes_cache["data"]

    with _quotes_cache["lock"]:
        if not force and _quotes_cache["data"] and (time.time() - _quotes_cache["timestamp"] < 10.0):
            return _quotes_cache["data"]

        def _fetch_sym(item):
            sym = item["symbol"]
            name = item["name"]
            weight = item["weight"]
            try:
                inf = yf.Ticker(sym).info
                reg_p = inf.get("regularMarketPrice") or inf.get("currentPrice") or 0.0
                reg_chg = inf.get("regularMarketChangePercent") or 0.0
                post_p = inf.get("postMarketPrice")
                post_pct = inf.get("postMarketChangePercent")
                pre_p = inf.get("preMarketPrice")
                pre_pct = inf.get("preMarketChangePercent")

                ext_p = None
                ext_pct = None
                ext_type = None

                if post_p and post_p > 0:
                    ext_p = post_p
                    ext_pct = post_pct if post_pct is not None else ((post_p - reg_p) / reg_p * 100 if reg_p > 0 else 0.0)
                    ext_type = "AH"
                elif pre_p and pre_p > 0:
                    ext_p = pre_p
                    ext_pct = pre_pct if pre_pct is not None else ((pre_p - reg_p) / reg_p * 100 if reg_p > 0 else 0.0)
                    ext_type = "PRE"

                return {
                    "symbol": sym,
                    "name": name,
                    "weight": weight,
                    "price": round(float(reg_p), 2),
                    "change_pct": round(float(reg_chg), 2),
                    "ext_price": round(float(ext_p), 2) if ext_p else None,
                    "ext_change_pct": round(float(ext_pct), 2) if ext_pct is not None else None,
                    "ext_type": ext_type
                }
            except Exception:
                if _quotes_cache["data"] and "quotes" in _quotes_cache["data"]:
                    for prev in _quotes_cache["data"]["quotes"]:
                        if prev.get("symbol") == sym:
                            return prev
                return {
                    "symbol": sym,
                    "name": name,
                    "weight": weight,
                    "price": 0.0,
                    "change_pct": 0.0,
                    "ext_price": None,
                    "ext_change_pct": None,
                    "ext_type": None
                }

        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                quotes = list(executor.map(_fetch_sym, TOP_20_NDX))

            advancing = sum(1 for q in quotes if (q.get("change_pct") or 0) > 0)
            declining = sum(1 for q in quotes if (q.get("change_pct") or 0) < 0)
            flat = len(quotes) - advancing - declining

            result = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 10,
                "advancing": advancing,
                "declining": declining,
                "flat": flat,
                "advancing_pct": round(advancing / len(quotes) * 100, 1) if quotes else 0,
                "quotes": quotes
            }
            _quotes_cache["timestamp"] = time.time()
            _quotes_cache["data"] = result
            return result
        except Exception:
            if _quotes_cache["data"]:
                return _quotes_cache["data"]
            return {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": 10,
                "advancing": 0,
                "declining": 0,
                "flat": 20,
                "advancing_pct": 0,
                "quotes": []
            }


# ─────────────────────────────────────────────
# NYSE TRADING DAY CHECK (holidays.NYSE)
# ─────────────────────────────────────────────
def is_trading_day(dt: date | None = None) -> bool:
    """True if dt (default: today ET) is a weekday and not an NYSE market holiday."""
    if dt is None:
        dt = ts.now_et().date()
    if dt.weekday() >= 5:
        return False
    return dt not in holidays.NYSE(years=dt.year)


# ─────────────────────────────────────────────
# DATA AGGREGATION FOR DASHBOARD
# ─────────────────────────────────────────────
def _compute_stats(portfolio: dict, daily_records: list, trades: list, tqqq_price: float, sqqq_price: float) -> dict:
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
    ndx_price = float(latest_daily.get("ndx_price", 0.0))
    sma50 = float(latest_daily.get("sma50", 0.0))
    sma250 = float(latest_daily.get("sma250", 0.0))
    rsi = float(latest_daily.get("rsi", 50.0))

    dist_sma50_pts = ndx_price - sma50
    dist_sma50_pct = (dist_sma50_pts / sma50) * 100 if sma50 > 0 else 0
    dist_sma250_pts = ndx_price - sma250
    dist_sma250_pct = (dist_sma250_pts / sma250) * 100 if sma250 > 0 else 0

    return {
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
    }


def get_dashboard_data() -> dict:
    """Read and compile all current data fresh from CSV and JSON state files."""
    portfolio_file = os.path.join(BASE_DIR, "portfolio_state.json")
    daily_file = os.path.join(BASE_DIR, "daily_summary.csv")
    trade_file = os.path.join(BASE_DIR, "trade_log.csv")
    log_file = os.path.join(BASE_DIR, "strategy.log")

    orig_p_file = os.path.join(BASE_DIR, "portfolio_state_original.json")
    orig_d_file = os.path.join(BASE_DIR, "daily_summary_original.csv")
    orig_t_file = os.path.join(BASE_DIR, "trade_log_original.csv")

    # 1. Primary Portfolio State (Symmetric 1.0x ATR)
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

    # 2. Daily Summaries
    daily_records = []
    if os.path.exists(daily_file):
        try:
            df_daily = pd.read_csv(daily_file).fillna(0)
            daily_records = df_daily.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading daily summary: {e}")

    # 3. Trade Log
    trades = []
    if os.path.exists(trade_file):
        try:
            df_trades = pd.read_csv(trade_file).fillna("")
            trades = df_trades.to_dict(orient="records")
        except Exception as e:
            print(f"Error reading trade log: {e}")

    # 4. Recent Log Lines (last 100 lines)
    recent_logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                recent_logs = [line.strip() for line in lines[-100:] if line.strip()]
        except Exception as e:
            print(f"Error reading log file: {e}")

    # 5. Live / Recent ETF prices from logs or portfolio
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
        sqqq_price = 33.12
    if tqqq_price <= 0:
        tqqq_price = 81.01

    stats_sym = _compute_stats(portfolio, daily_records, trades, tqqq_price, sqqq_price)

    # 6. Original Agile Model
    if os.path.exists(orig_p_file):
        try:
            with open(orig_p_file, "r", encoding="utf-8") as f:
                p_orig = json.load(f)
        except Exception:
            p_orig = portfolio.copy()
    else:
        p_orig = portfolio.copy()

    orig_daily = []
    if os.path.exists(orig_d_file):
        try:
            orig_daily = pd.read_csv(orig_d_file).fillna(0).to_dict(orient="records")
        except Exception as e:
            print(f"Error reading original daily summary: {e}")

    orig_trades = []
    if os.path.exists(orig_t_file):
        try:
            orig_trades = pd.read_csv(orig_t_file).fillna("").to_dict(orient="records")
        except Exception as e:
            print(f"Error reading original trade log: {e}")

    stats_orig = _compute_stats(p_orig, orig_daily, orig_trades, tqqq_price, sqqq_price)

    starting_cap = float(portfolio.get("starting_capital", 10000.0))
    current_val = float(portfolio.get("total_value", starting_cap))
    orig_start = float(p_orig.get("starting_capital", 10000.0))
    orig_val = float(p_orig.get("total_value", orig_start))

    models = {
        "symmetric_atr": {
            "portfolio": portfolio,
            "daily_summary": daily_records,
            "trades": trades,
            "recent_logs": recent_logs,
            "stats": stats_sym,
            "starting_capital": starting_cap,
            "ending_value": round(current_val, 2),
            "total_return_pct": stats_sym["total_pnl_pct"],
        },
        "original_agile": {
            "portfolio": p_orig,
            "daily_summary": orig_daily,
            "trades": orig_trades,
            "recent_logs": recent_logs,
            "stats": stats_orig,
            "starting_capital": orig_start,
            "ending_value": round(orig_val, 2),
            "total_return_pct": stats_orig["total_pnl_pct"],
        }
    }

    server_time_str = ts.now_et().strftime("%Y-%m-%d %H:%M:%S ET")

    return {
        "portfolio": portfolio,
        "daily_summary": daily_records,
        "trades": trades,
        "recent_logs": recent_logs,
        "stats": stats_sym,
        "models": models,
        "ndx_heatmap": get_ndx_top20_quotes(),
        "scheduler": {
            "active": False,
            "is_active_session": is_trading_day(),
            "scheduled_time": "GitHub Actions (3:50 PM ET NYSE days)",
            "next_run_target": "Cloud-managed",
            "server_time": server_time_str,
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
        }
    }


# ─────────────────────────────────────────────
# HTTP HANDLER (VIEW-ONLY)
# ─────────────────────────────────────────────
class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving web assets and data API. View-only; cannot trigger trades."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/quotes":
            try:
                quotes_data = get_ndx_top20_quotes()
                payload = json.dumps(quotes_data, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if parsed.path == "/api/data":
            try:
                data = get_dashboard_data()
                payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        super().do_GET()

    def log_message(self, format, *args):
        # Suppress routine GET logging for static assets and quotes to keep console clean
        if len(args) > 0 and not any(k in str(args[0]) for k in ["GET /api/data"]):
            return
        super().log_message(format, *args)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def run_server(port: int = PORT, auto_open: bool = True):
    actual_port = port
    while is_port_in_use(actual_port):
        actual_port += 1

    server_address = ("127.0.0.1", actual_port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    url = f"http://127.0.0.1:{actual_port}"

    print("=" * 65)
    print("  [ONLINE] NDX QUANT STRATEGY — VIEW-ONLY DASHBOARD")
    print("=" * 65)
    print(f"  Local URL:        {url}")
    print(f"  Live Data API:    {url}/api/data")
    print(f"  Execution Engine: Cloud-Only (GitHub Actions)")
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
