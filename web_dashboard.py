"""
Web Dashboard Server for NDX Strategy (View-Only)
=================================================
Local read-only dashboard. Does NOT schedule, does NOT execute trades, does NOT write state.
Trading is executed exclusively by GitHub Actions in the cloud.
Serves the same docs/ frontend that GitHub Pages publishes, plus live /api endpoints.

Usage:
    python web_dashboard.py [--no-browser]
"""

import os
import sys
import json
import socket
import subprocess
import webbrowser
import threading
import time
from datetime import datetime, time as dtime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "docs")
PORT = 5050

sys.path.insert(0, BASE_DIR)
import trading_strategy as ts

# ─────────────────────────────────────────────
# TOP 20 NDX CONSTITUENTS & LIVE QUOTE ENGINE
# ─────────────────────────────────────────────
# Approximate index weights (%) — static, not fetched. Update when the index rebalances.
TOP_20_AS_OF = "2026-10"
TOP_20_NDX = sorted([
    {"symbol": "NVDA", "name": "NVIDIA", "weight": 8.8},
    {"symbol": "AAPL", "name": "Apple", "weight": 8.4},
    {"symbol": "MSFT", "name": "Microsoft", "weight": 7.9},
    {"symbol": "AMZN", "name": "Amazon", "weight": 5.5},
    {"symbol": "GOOGL", "name": "Alphabet", "weight": 5.2},
    {"symbol": "META", "name": "Meta", "weight": 5.1},
    {"symbol": "AVGO", "name": "Broadcom", "weight": 4.8},
    {"symbol": "TSLA", "name": "Tesla", "weight": 3.2},
    {"symbol": "COST", "name": "Costco", "weight": 2.4},
    {"symbol": "NFLX", "name": "Netflix", "weight": 2.1},
    {"symbol": "AMD", "name": "AMD", "weight": 1.9},
    {"symbol": "ASML", "name": "ASML", "weight": 1.7},
    {"symbol": "CSCO", "name": "Cisco", "weight": 1.5},
    {"symbol": "QCOM", "name": "Qualcomm", "weight": 1.5},
    {"symbol": "TMUS", "name": "T-Mobile", "weight": 1.4},
    {"symbol": "PEP", "name": "PepsiCo", "weight": 1.3},
    {"symbol": "LIN", "name": "Linde", "weight": 1.3},
    {"symbol": "ADBE", "name": "Adobe", "weight": 1.3},
    {"symbol": "TXN", "name": "Texas Inst", "weight": 1.2},
    {"symbol": "AMAT", "name": "Applied Mat", "weight": 1.2},
], key=lambda q: -q["weight"])

QUOTES_TTL = 10.0
REGULAR_OPEN, REGULAR_CLOSE = dtime(9, 30), dtime(16, 0)

_quotes_cache = {
    "timestamp": 0.0,
    "data": None,
    "lock": threading.Lock()
}


def _close_frame(df: pd.DataFrame, symbols: list) -> pd.DataFrame:
    """Extract a symbols-as-columns Close frame from a (possibly MultiIndex) yf.download result."""
    if df is None or df.empty:
        return pd.DataFrame(columns=symbols)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].set_axis(symbols[:1], axis=1)
    return close.reindex(columns=symbols)


def build_quotes(daily_close: pd.DataFrame, intraday_close: pd.DataFrame) -> list:
    """Pure: daily closes give regular price + change; the latest prepost bar gives AH/PRE."""
    quotes = []
    for item in TOP_20_NDX:
        sym = item["symbol"]
        q = dict(item, price=0.0, change_pct=0.0, ext_price=None, ext_change_pct=None, ext_type=None)
        d = daily_close[sym].dropna() if sym in daily_close else pd.Series(dtype=float)
        if len(d):
            reg = float(d.iloc[-1])
            q["price"] = round(reg, 2)
            if len(d) > 1 and d.iloc[-2] > 0:
                q["change_pct"] = round((reg / float(d.iloc[-2]) - 1) * 100, 2)
            s = intraday_close[sym].dropna() if sym in intraday_close else pd.Series(dtype=float)
            if len(s):
                t_last = s.index[-1]
                t_last = t_last.tz_convert(ts.ET) if t_last.tzinfo else t_last
                last_daily = pd.Timestamp(d.index[-1]).date()
                ext_type = None
                if t_last.time() >= REGULAR_CLOSE and t_last.date() == last_daily:
                    ext_type = "AH"
                elif t_last.time() < REGULAR_OPEN and t_last.date() > last_daily:
                    ext_type = "PRE"
                if ext_type and reg > 0:
                    ext = float(s.iloc[-1])
                    q.update(ext_price=round(ext, 2), ext_change_pct=round((ext / reg - 1) * 100, 2),
                             ext_type=ext_type)
        quotes.append(q)
    return quotes


def get_ndx_top20_quotes(force: bool = False) -> dict:
    """Regular + extended-hours quotes for the Top 20 NDX names in two batched requests (10s TTL)."""
    if not force and _quotes_cache["data"] and (time.time() - _quotes_cache["timestamp"] < QUOTES_TTL):
        return _quotes_cache["data"]

    with _quotes_cache["lock"]:
        if not force and _quotes_cache["data"] and (time.time() - _quotes_cache["timestamp"] < QUOTES_TTL):
            return _quotes_cache["data"]
        symbols = [q["symbol"] for q in TOP_20_NDX]
        try:
            daily = yf.download(symbols, period="5d", interval="1d", auto_adjust=False,
                                progress=False, threads=True)
            intraday = yf.download(symbols, period="2d", interval="5m", prepost=True,
                                   auto_adjust=False, progress=False, threads=True)
            quotes = build_quotes(_close_frame(daily, symbols), _close_frame(intraday, symbols))
            if not any(q["price"] for q in quotes):
                raise RuntimeError("no quotes returned")
        except Exception as e:
            if _quotes_cache["data"]:
                return _quotes_cache["data"]
            return {"updated_at": datetime.now(timezone.utc).isoformat(), "ttl_seconds": QUOTES_TTL,
                    "advancing": 0, "declining": 0, "flat": 0, "advancing_pct": 0,
                    "weights_as_of": TOP_20_AS_OF, "error": str(e), "quotes": []}

        priced = [q for q in quotes if q["price"]]
        advancing = sum(1 for q in priced if q["change_pct"] > 0)
        declining = sum(1 for q in priced if q["change_pct"] < 0)
        result = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": QUOTES_TTL,
            "advancing": advancing,
            "declining": declining,
            "flat": len(priced) - advancing - declining,
            "advancing_pct": round(advancing / len(priced) * 100, 1) if priced else 0,
            "weights_as_of": TOP_20_AS_OF,
            "quotes": quotes,
        }
        _quotes_cache["timestamp"] = time.time()
        _quotes_cache["data"] = result
        return result


# ─────────────────────────────────────────────
# DATA AGGREGATION FOR DASHBOARD
# ─────────────────────────────────────────────
MODEL_FILES = {
    "symmetric_atr": ("portfolio_state.json", "daily_summary.csv", "trade_log.csv"),
    "original_agile": ("portfolio_state_agile.json", "daily_summary_agile.csv", "trade_log_agile.csv"),
}
# Per-row columns the frontend never reads (the cross-model columns live in the other model's file)
_DROP_DAILY_COLS = ["total_value_agile", "pos_agile", "tqqq_shares", "sqqq_shares", "pnl_dollar"]


def _compute_stats(portfolio: dict, daily_records: list, trades: list) -> dict:
    starting_cap = float(portfolio.get("starting_capital", ts.CONFIG["starting_capital"]))
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
    tqqq_price, sqqq_price = portfolio.get("last_tqqq_price"), portfolio.get("last_sqqq_price")

    return {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "high_water_mark": round(hwm, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trading_days_tracked": len(daily_records),
        "total_trades": len(trades),
        "ndx_price": round(ndx_price, 2),
        # None (rendered as "—") when no run has recorded a price yet — never a made-up number
        "tqqq_price": round(tqqq_price, 2) if tqqq_price else None,
        "sqqq_price": round(sqqq_price, 2) if sqqq_price else None,
        "sma50": round(sma50, 2),
        "sma250": round(sma250, 2),
        "rsi": round(rsi, 2),
        "dist_sma50_pts": round(dist_sma50_pts, 2),
        "dist_sma50_pct": round(dist_sma50_pct, 2),
        "dist_sma250_pts": round(dist_sma250_pts, 2),
        "dist_sma250_pct": round(dist_sma250_pct, 2),
    }


def _read_csv_records(path: str, fill) -> list:
    if not os.path.exists(path):
        return []
    try:
        return pd.read_csv(path).fillna(fill).to_dict(orient="records")
    except Exception as e:
        print(f"Error reading {os.path.basename(path)}: {e}")
        return []


def _load_model(portfolio_name: str, daily_name: str, trade_name: str) -> dict:
    portfolio_file = os.path.join(BASE_DIR, portfolio_name)
    portfolio = None
    if os.path.exists(portfolio_file):
        try:
            with open(portfolio_file, "r", encoding="utf-8") as f:
                portfolio = json.load(f)
        except Exception as e:
            print(f"Error reading {portfolio_name}: {e}")
    if portfolio is None:
        portfolio = ts.new_portfolio(ts.CONFIG["starting_capital"])

    daily = _read_csv_records(os.path.join(BASE_DIR, daily_name), 0)
    trades = _read_csv_records(os.path.join(BASE_DIR, trade_name), "")
    stats = _compute_stats(portfolio, daily, trades)

    # Compact rows: per-day reason text is only shown for the latest session
    for r in daily[:-1]:
        r.pop("reason", None)
    for r in daily:
        for c in _DROP_DAILY_COLS:
            r.pop(c, None)

    starting_cap = float(portfolio.get("starting_capital", ts.CONFIG["starting_capital"]))
    return {
        "portfolio": portfolio,
        "daily_summary": daily,
        "trades": trades,
        "stats": stats,
        "starting_capital": starting_cap,
        "ending_value": round(float(portfolio.get("total_value", starting_cap)), 2),
        "total_return_pct": stats["total_pnl_pct"],
    }


def _read_recent_logs(n: int = 100) -> list:
    log_file = ts.CONFIG["log_file"]
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f.readlines()[-n:] if line.strip()]
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []


def get_dashboard_data() -> dict:
    """Read and compile all current data fresh from CSV and JSON state files.
    Each model's data lives once under `models`; shared fields live once at the top level."""
    models = {name: _load_model(*files) for name, files in MODEL_FILES.items()}
    primary = models["symmetric_atr"]
    portfolio = primary["portfolio"]
    daily = primary["daily_summary"]

    return {
        "models": models,
        "recent_logs": _read_recent_logs(),
        "ndx_heatmap": get_ndx_top20_quotes(),
        "meta": {
            "history_start": daily[0]["date"] if daily else None,
            "backtest_end": portfolio.get("backtest_end"),
            "live_since": portfolio.get("live_since"),
            "slippage_bps": ts.CONFIG["slippage_bps"],
        },
        "scheduler": {
            "active": False,
            "is_active_session": ts.is_trading_day(),
            "scheduled_time": "GitHub Actions (after 4:00 PM ET close, NYSE days)",
            "next_run_target": "Cloud-managed",
            "server_time": ts.now_et().strftime("%Y-%m-%d %H:%M:%S ET"),
            "last_run_date": portfolio.get("last_run_date"),
        },
        "config": {
            "starting_capital": primary["starting_capital"],
            "rsi_overbought": ts.CONFIG["rsi_overbought"],
            "rsi_trim_medium": ts.CONFIG["rsi_trim_medium"],
            "rsi_oversold": ts.CONFIG["rsi_oversold"],
            "atr_buffer_multiplier": ts.CONFIG["atr_buffer_multiplier"],
            "tqqq_ticker": ts.CONFIG["tqqq_ticker"],
            "sqqq_ticker": ts.CONFIG["sqqq_ticker"],
        }
    }


# ─────────────────────────────────────────────
# HTTP HANDLER (VIEW-ONLY)
# ─────────────────────────────────────────────
class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving web assets and data API. View-only; cannot trigger trades."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def _send_json(self, producer):
        try:
            payload = json.dumps(producer(), separators=(",", ":")).encode("utf-8")
            status = 200
        except Exception as e:
            payload, status = json.dumps({"error": str(e)}).encode("utf-8"), 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/quotes":
            return self._send_json(get_ndx_top20_quotes)
        if path == "/api/data":
            return self._send_json(get_dashboard_data)
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress routine GET logging for static assets and quotes to keep console clean
        if len(args) > 0 and "GET /api/data" not in str(args[0]):
            return
        super().log_message(format, *args)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def warn_if_behind_origin():
    """The cloud commits state daily; warn when this checkout hasn't pulled it."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=BASE_DIR, timeout=20, check=True,
                       capture_output=True)
        behind = subprocess.run(["git", "rev-list", "--count", "HEAD..@{u}"], cwd=BASE_DIR,
                                timeout=10, capture_output=True, text=True, check=True).stdout.strip()
        if behind and int(behind) > 0:
            print(f"  [WARNING] Local checkout is {behind} commit(s) behind origin — "
                  f"dashboard shows stale state. Run: git pull --ff-only")
    except Exception:
        pass


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
    warn_if_behind_origin()
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_server(PORT, auto_open="--no-browser" not in sys.argv)
