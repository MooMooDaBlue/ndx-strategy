"""
NDX SMA + RSI Automated Paper Trading Strategy
================================================
Rules:
  1. NDX > 250-day SMA AND > 50-day SMA AND RSI(14) < 75  → Full TQQQ (100%)
  2. NDX > 250-day SMA AND > 50-day SMA AND RSI(14) > 75  → Trim to 30% TQQQ (overextended)
  3. NDX > 250-day SMA AND > 50-day SMA AND bearish RSI divergence → Trim to 50% TQQQ
  4. NDX < 50-day SMA (above 250)                          → Exit to Cash
  5. NDX < 250-day SMA AND < 50-day SMA AND RSI 35-55     → Enter SQQQ (short)
  6. NDX < 250-day SMA AND < 50-day SMA AND RSI < 30      → Stay Cash (oversold, don't chase)
  7. NDX recrosses 50-day SMA AND RSI crossing above 50   → Re-enter Full TQQQ
  8. NDX recrosses 50-day SMA AND RSI still < 50          → Stay Cash (wait for confirmation)

Hysteresis (symmetric_atr model): enter longs only above SMA50 + 1.0*ATR; exit only below
SMA50 - 1.0*ATR. original_agile model: enter above SMA50 * 1.01, exit below SMA50.
Overbought trim lock: after RSI >= 75 trims to 30%, stay trimmed until RSI dips below 60 and
re-crosses above it. All times are US/Eastern.

Run this script daily at 3:50pm EST on trading days.
Data source: Yahoo Finance (yfinance) - free, no API key required.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    """Naive datetime in US/Eastern — the single clock used for all state, guards and logs."""
    return datetime.now(ET).replace(tzinfo=None)

# ─────────────────────────────────────────────
# CONFIGURATION — Edit these settings
# ─────────────────────────────────────────────
CONFIG = {
    # Live trading starting capital
    "starting_capital": 10_000.00,
    "tqqq_ticker": "TQQQ",
    "sqqq_ticker": "SQQQ",

    # File paths (created automatically)
    "portfolio_file": os.path.join(BASE_DIR, "portfolio_state.json"),
    "trade_log_file": os.path.join(BASE_DIR, "trade_log.csv"),
    "daily_log_file": os.path.join(BASE_DIR, "daily_summary.csv"),

    # RSI thresholds
    "rsi_overbought": 75,           # Trim to 30% above this
    "rsi_trim_medium": 50,          # Re-entry confirmation threshold
    "rsi_oversold": 30,             # Don't enter SQQQ below this
    "rsi_sqqq_entry_min": 35,       # SQQQ entry RSI floor
    "rsi_sqqq_entry_max": 55,       # SQQQ entry RSI ceiling

    # Anti-whipsaw & downside protection: dynamic ATR buffer around SMA50
    # Requires price to clear SMA50 + (mult * ATR) to enter/re-enter longs.
    # Protects against whipsaw by only exiting when price breaks below SMA50 - (mult * ATR).
    "atr_buffer_multiplier": 1.0,

    # Original Agile model: re-entry requires price > SMA50 * (1 + pct)
    "orig_entry_buffer_pct": 0.01,

    # RSI re-entry buffer: after overbought trim, stay trimmed until
    # RSI crosses above this threshold from below (momentum reset proof)
    "rsi_reset_threshold": 60,

    # Risk-free rate for cash interest accrual (annual, e.g. 0.045 = 4.5%)
    "risk_free_annual_rate": 0.045,

    # Allocation rules
    "full_tqqq_pct": 1.00,
    "trim_tqqq_pct": 0.30,
    "trim_medium_pct": 0.50,        # Bearish divergence trim
    "sqqq_pct": 1.00,               # 100% SQQQ when short signal fires
    "cash_pct": 1.00,

    # SMA periods
    "sma_short": 50,
    "sma_long": 250,
    "rsi_period": 14,

    # Divergence lookback (bars to check for bearish divergence)
    "divergence_lookback": 20,

    # Push notifications via ntfy.sh (free, no account needed)
    # Set the NTFY_TOPIC environment variable / secret
    "ntfy_enabled": bool(os.environ.get("NTFY_TOPIC")),
    "ntfy_topic": os.environ.get("NTFY_TOPIC", ""),
}

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "strategy.log"), encoding="utf-8"),
        logging.StreamHandler(open(1, "w", encoding="utf-8", closefd=False))
    ]
)
log = logging.getLogger(__name__)
# Log timestamps in US/Eastern regardless of machine timezone (cloud = UTC, local = MT)
logging.Formatter.converter = lambda *args: now_et().timetuple()


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────
def fetch_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch historical OHLCV data from Yahoo Finance."""
    log.info(f"Fetching data for {ticker}...")
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(subset=['Close'], inplace=True)
    log.info(f"  {ticker}: {len(df)} bars fetched, latest close: {df['Close'].iloc[-1]:.2f}")
    return df


def fetch_market_data(cfg: dict = None) -> tuple:
    """Fetch NDX (2y) and TQQQ/SQQQ (5d); fail if the latest bar is not today's ET session."""
    cfg = cfg or CONFIG
    ndx_df = fetch_data("^NDX", period="2y")
    tqqq_df = fetch_data(cfg["tqqq_ticker"], period="5d")
    sqqq_df = fetch_data(cfg["sqqq_ticker"], period="5d")
    today = now_et().date()
    if not os.environ.get("ALLOW_STALE_DATA"):
        for name, df in (("^NDX", ndx_df), ("TQQQ", tqqq_df), ("SQQQ", sqqq_df)):
            last_bar = pd.Timestamp(df.index[-1]).date()
            if last_bar != today:
                raise RuntimeError(f"Stale data for {name}: latest bar {last_bar}, expected {today}")
    return ndx_df, tqqq_df, sqqq_df


# ─────────────────────────────────────────────
# TECHNICAL INDICATORS
# ─────────────────────────────────────────────
ALLOC_PCT = {"TQQQ_100": 1.0, "TQQQ_50": 0.5, "TQQQ_30": 0.3, "SQQQ": 1.0, "CASH": 0.0}


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI — the correct implementation."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Use Wilder's smoothing (equivalent to EWM with alpha=1/period)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range for dynamic volatility scaling."""
    tr1 = df['High'] - df['Low']
    tr2 = abs(df['High'] - df['Close'].shift())
    tr3 = abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def bearish_divergence_series(close: pd.Series, rsi: pd.Series, lookback: int) -> pd.Series:
    """True where the max price of the last `lookback` bars exceeds the prior window's max
    while the max RSI of the last window is lower than the prior window's max."""
    price_hh = close.rolling(lookback).max() > close.shift(lookback).rolling(lookback).max()
    rsi_lh = rsi.rolling(lookback).max() < rsi.shift(lookback).rolling(lookback).max()
    return (price_hh & rsi_lh).fillna(False)


def compute_indicators(ndx_df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """All indicators used by the live engine, the cloud runner and the backtest."""
    close = ndx_df["Close"].squeeze()
    out = pd.DataFrame(index=ndx_df.index)
    out["close"] = close
    out["sma50"] = calculate_sma(close, cfg["sma_short"])
    out["sma250"] = calculate_sma(close, cfg["sma_long"])
    out["rsi"] = calculate_rsi(close, cfg["rsi_period"])
    out["atr"] = calculate_atr(ndx_df, 14)
    out["bearish_div"] = bearish_divergence_series(close, out["rsi"], cfg["divergence_lookback"])
    return out


# ─────────────────────────────────────────────
# SIGNAL ENGINE
# ─────────────────────────────────────────────
def decide_signal(price: float, s50: float, s250: float, rsi_val: float, atr_val: float,
                  bearish_div: bool, current_position: str, trim_active: bool,
                  prev_rsi: float, cfg: dict, model: str = "symmetric_atr") -> dict:
    """
    Pure decision function shared by the live engine, both models and the backtest.
    model="symmetric_atr": entry > SMA50 + k*ATR, exit < SMA50 - k*ATR.
    model="original_agile": entry > SMA50 * (1 + pct), clean exit < SMA50.
    """
    holding_tqqq = current_position.startswith("TQQQ")
    above_50, above_250 = price >= s50, price >= s250
    below_50 = not above_50
    reset_lvl = cfg.get("rsi_reset_threshold", 60)

    if model == "original_agile":
        entry_level = s50 * (1 + cfg.get("orig_entry_buffer_pct", 0.01))
        exit_level = s50
    else:
        mult = cfg.get("atr_buffer_multiplier", 1.0)
        entry_level = s50 + mult * atr_val
        exit_level = s50 - mult * atr_val

    in_entry = (not holding_tqqq) and above_50 and price <= entry_level
    in_exit = holding_tqqq and below_50 and price >= exit_level

    # Trim lock releases only when RSI dips below the reset level and re-crosses above it
    if trim_active and prev_rsi < reset_lvl <= rsi_val:
        trim_active = False
        log.info(f"  RSI reset: {prev_rsi:.1f} -> {rsi_val:.1f} crossed {reset_lvl} — trim lock released")

    if above_250:
        if in_exit:
            signal = current_position
            reason = (f"Downside buffer hold: NDX {price:.1f} below SMA50 ({s50:.1f}) "
                      f"but above exit floor ({exit_level:.1f})")
        elif below_50:
            signal, trim_active = "CASH", False
            reason = f"Exit: NDX {price:.1f} below SMA50 exit level ({exit_level:.1f})"
        elif in_entry:
            signal = "CASH"
            reason = (f"Re-entry buffer: NDX {price:.1f} above SMA50 ({s50:.1f}) "
                      f"but below entry level ({entry_level:.1f})")
        elif rsi_val >= cfg["rsi_overbought"]:
            signal, trim_active = "TQQQ_30", True
            reason = (f"Overbought: RSI {rsi_val:.1f} >= {cfg['rsi_overbought']} — trimmed until RSI "
                      f"dips and re-crosses above {reset_lvl}")
        elif trim_active:
            signal = "TQQQ_30"
            reason = f"Trim lock active: waiting for RSI to re-cross above {reset_lvl} (now {rsi_val:.1f})"
        elif bearish_div:
            signal, reason = "TQQQ_50", "Bearish RSI divergence — trimming to 50%"
        else:
            signal = "TQQQ_100"
            reason = (f"Full bull: NDX {price:,.1f} is above SMA50 ({s50:,.1f}) and SMA250 ({s250:,.1f}); "
                      f"RSI {rsi_val:.1f} is below the {cfg['rsi_overbought']} overbought trim line")
    elif below_50:  # below both SMAs
        trim_active = False
        if cfg["rsi_sqqq_entry_min"] <= rsi_val <= cfg["rsi_sqqq_entry_max"]:
            signal = "SQQQ"
            reason = (f"Bear signal: below both SMAs, RSI {rsi_val:.1f} in "
                      f"[{cfg['rsi_sqqq_entry_min']}-{cfg['rsi_sqqq_entry_max']}]")
        elif rsi_val < cfg["rsi_oversold"]:
            signal, reason = "CASH", f"Bear trend but RSI {rsi_val:.1f} oversold — not chasing short"
        else:
            signal, reason = "CASH", f"Bear trend, RSI {rsi_val:.1f} outside SQQQ zone — holding cash"
    else:  # below SMA250, above SMA50
        trim_active = False
        if in_entry:
            signal = "CASH"
            reason = f"Re-entry buffer below SMA250: NDX {price:.1f} <= entry level ({entry_level:.1f})"
        elif rsi_val >= cfg["rsi_trim_medium"]:
            signal = "TQQQ_30"
            reason = f"Recovery above SMA50 with RSI {rsi_val:.1f}, but below SMA250 — cautious 30%"
        else:
            signal = "CASH"
            reason = f"Recovery above SMA50 but RSI {rsi_val:.1f} < {cfg['rsi_trim_medium']} — waiting"

    return {
        "signal": signal, "reason": reason, "trim_active": trim_active,
        "in_buffer_zone_entry": in_entry, "in_buffer_zone_exit": in_exit,
        "entry_level": entry_level, "exit_level": exit_level,
    }


def determine_signal(ndx_df: pd.DataFrame, cfg: dict, current_position: str = "CASH",
                     trim_active: bool = False, prev_rsi: float = 50.0,
                     model: str = "symmetric_atr") -> dict:
    """Compute indicators on ndx_df and return the signal dict for the latest bar."""
    last = compute_indicators(ndx_df, cfg).iloc[-1]
    if pd.isna(last[["sma50", "sma250", "rsi", "atr"]]).any():
        raise ValueError("Not enough NDX history to compute indicators")
    price, s50, s250 = float(last["close"]), float(last["sma50"]), float(last["sma250"])
    rsi_val, atr_val = float(last["rsi"]), float(last["atr"])
    d = decide_signal(price, s50, s250, rsi_val, atr_val, bool(last["bearish_div"]),
                      current_position, trim_active, prev_rsi, cfg, model)
    now = now_et()
    return {
        "signal": d["signal"], "reason": d["reason"], "trim_active": d["trim_active"],
        "price": price, "sma50": s50, "sma250": s250, "rsi": rsi_val, "atr": atr_val,
        "above_50": price >= s50, "above_250": price >= s250,
        "bearish_divergence": bool(last["bearish_div"]),
        "in_buffer_zone_entry": d["in_buffer_zone_entry"],
        "in_buffer_zone_exit": d["in_buffer_zone_exit"],
        "in_buffer_zone": d["in_buffer_zone_entry"] or d["in_buffer_zone_exit"],
        "buffered_sma50": round(d["entry_level"], 2),
        "buffered_sma50_entry": round(d["entry_level"], 2),
        "buffered_sma50_exit": round(d["exit_level"], 2),
        "timestamp": now.isoformat(),
        "date": now.date().isoformat(),
    }


# ─────────────────────────────────────────────
# PORTFOLIO STATE MANAGEMENT
# ─────────────────────────────────────────────
def load_portfolio(filepath: str, starting_capital: float) -> dict:
    """Load portfolio state from disk, or initialize if first run."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            portfolio = json.load(f)
        log.info(f"Portfolio loaded: {portfolio['position']} | Value: ${portfolio['total_value']:,.2f}")
    else:
        portfolio = {
            "position": "CASH",
            "allocation_pct": 1.0,
            "cash": starting_capital,
            "tqqq_shares": 0.0,
            "sqqq_shares": 0.0,
            "tqqq_avg_cost": 0.0,
            "sqqq_avg_cost": 0.0,
            "total_value": starting_capital,
            "starting_capital": starting_capital,
            "last_signal": None,
            "last_updated": None,
            "last_run_date": None,
            "trim_active": False,
            "prev_rsi": 50.0,
        }
        log.info(f"New portfolio initialized with ${starting_capital:,.2f}")
        save_portfolio(portfolio, filepath)
    return portfolio


def save_portfolio(portfolio: dict, filepath: str):
    with open(filepath, "w") as f:
        json.dump(portfolio, f, indent=2)


def update_portfolio_value(portfolio: dict, tqqq_price: float, sqqq_price: float) -> dict:
    """Recalculate total portfolio value based on current prices."""
    tqqq_value = portfolio["tqqq_shares"] * tqqq_price
    sqqq_value = portfolio["sqqq_shares"] * sqqq_price
    portfolio["total_value"] = portfolio["cash"] + tqqq_value + sqqq_value
    return portfolio


# ─────────────────────────────────────────────
# CASH INTEREST ACCRUAL
# ─────────────────────────────────────────────
def accrue_cash_interest(portfolio: dict, cfg: dict) -> dict:
    """Apply daily risk-free rate to cash holdings based on calendar days elapsed.

    IMPORTANT: last_updated is advanced here so each run only accrues interest
    for the days since the *previous run*, not since the last trade.  Without
    this, every no-trade cash day would re-accrue all historical interest from
    the original trade timestamp.
    """
    if portfolio["cash"] <= 0 or not portfolio.get("last_updated"):
        return portfolio

    annual_rate = cfg.get("risk_free_annual_rate", 0.0)
    if annual_rate <= 0:
        return portfolio

    try:
        last_updated = datetime.fromisoformat(portfolio["last_updated"])
        now = now_et()
        days_elapsed = (now.date() - last_updated.date()).days  # calendar days, immune to run-time jitter
    except (ValueError, TypeError):
        return portfolio

    if days_elapsed > 0:
        interest = portfolio["cash"] * (annual_rate / 365) * days_elapsed
        portfolio["cash"] += interest
        log.info(f"  Cash interest accrued: ${interest:.2f} ({days_elapsed} days @ {annual_rate*100:.1f}% annual)")
        # Advance the timestamp so the next run only accrues from today onward.
        portfolio["last_updated"] = now.isoformat()

    return portfolio


# ─────────────────────────────────────────────
# TRADE EXECUTION (PAPER)
# ─────────────────────────────────────────────
def execute_trade(portfolio: dict, signal_data: dict, tqqq_price: float, sqqq_price: float,
                  cfg: dict) -> tuple:
    """
    Move the paper portfolio to the target allocation for signal_data["signal"].
    Returns (portfolio, trades) where trades lists EVERY leg executed (SELL / TRIM / BUY).
    An empty list means no change was needed.
    """
    signal = signal_data["signal"]
    current = portfolio["position"]
    trades = []
    portfolio = update_portfolio_value(portfolio, tqqq_price, sqqq_price)

    if signal == current:
        log.info(f"  No change — already in {current}")
        return portfolio, trades
    log.info(f"  TRADE SIGNAL: {current} → {signal}")

    # 1. Close any SQQQ position we are leaving
    if portfolio["sqqq_shares"] > 0 and signal != "SQQQ":
        shares = portfolio["sqqq_shares"]
        proceeds = shares * sqqq_price
        portfolio["cash"] += proceeds
        portfolio["sqqq_shares"] = 0.0
        portfolio["sqqq_avg_cost"] = 0.0
        trades.append(_make_trade("SELL", "SQQQ", shares, sqqq_price, proceeds, signal_data))
        log.info(f"  Sold SQQQ: {shares:.4f} @ ${sqqq_price:.2f} = ${proceeds:,.2f}")

    # 2. Resize TQQQ to its target weight (0 when leaving TQQQ)
    total_value = portfolio["cash"] + portfolio["tqqq_shares"] * tqqq_price
    target_pct = ALLOC_PCT.get(signal, 0.0) if signal.startswith("TQQQ") else 0.0
    delta = total_value * target_pct - portfolio["tqqq_shares"] * tqqq_price
    if delta > 0.01:
        shares = delta / tqqq_price
        old = portfolio["tqqq_shares"]
        portfolio["tqqq_avg_cost"] = (old * portfolio["tqqq_avg_cost"] + shares * tqqq_price) / (old + shares) if (old + shares) > 0 else tqqq_price
        portfolio["tqqq_shares"] = old + shares
        portfolio["cash"] -= delta
        trades.append(_make_trade("BUY", "TQQQ", shares, tqqq_price, delta, signal_data))
        log.info(f"  Bought TQQQ: {shares:.4f} @ ${tqqq_price:.2f} = ${delta:,.2f} (target {target_pct:.0%})")
    elif delta < -0.01:
        shares = min(-delta / tqqq_price, portfolio["tqqq_shares"])
        proceeds = shares * tqqq_price
        portfolio["cash"] += proceeds
        if target_pct == 0:
            action = "SELL"
            portfolio["tqqq_shares"] = 0.0
            portfolio["tqqq_avg_cost"] = 0.0
        else:
            action = "TRIM"
            portfolio["tqqq_shares"] -= shares
        trades.append(_make_trade(action, "TQQQ", shares, tqqq_price, proceeds, signal_data))
        log.info(f"  {action} TQQQ: {shares:.4f} @ ${tqqq_price:.2f} = ${proceeds:,.2f} (target {target_pct:.0%})")

    # 3. Open SQQQ
    if signal == "SQQQ":
        invest = portfolio["cash"] * cfg["sqqq_pct"]
        shares = invest / sqqq_price
        portfolio["sqqq_shares"] = shares
        portfolio["sqqq_avg_cost"] = sqqq_price
        portfolio["cash"] -= invest
        trades.append(_make_trade("BUY", "SQQQ", shares, sqqq_price, invest, signal_data))
        log.info(f"  Bought SQQQ: {shares:.4f} @ ${sqqq_price:.2f} = ${invest:,.2f}")

    portfolio["position"] = signal
    portfolio["allocation_pct"] = ALLOC_PCT.get(signal, 0.0)
    portfolio["last_signal"] = signal_data["reason"]
    portfolio["last_updated"] = signal_data["timestamp"]
    portfolio = update_portfolio_value(portfolio, tqqq_price, sqqq_price)
    return portfolio, trades


def _make_trade(action, ticker, shares, price, value, signal_data):
    return {
        "date": signal_data["date"],
        "timestamp": signal_data["timestamp"],
        "action": action,
        "ticker": ticker,
        "shares": shares,
        "price": price,
        "value": value,
        "ndx_price": signal_data["price"],
        "sma50": signal_data["sma50"],
        "sma250": signal_data["sma250"],
        "rsi": signal_data["rsi"],
        "reason": signal_data["reason"],
    }


# ─────────────────────────────────────────────
# LOGGING TO CSV
# ─────────────────────────────────────────────
def log_trade(trade: dict, filepath: str):
    df = pd.DataFrame([trade])
    header = not os.path.exists(filepath)
    df.to_csv(filepath, mode="a", header=header, index=False)


def log_daily_summary(portfolio: dict, signal_data: dict, filepath: str, tqqq_price: float = 0.0):
    # Benchmark buy-and-hold comparison
    ndx_start = portfolio.get("benchmark_ndx_start", signal_data["price"])
    tqqq_start = portfolio.get("benchmark_tqqq_start", tqqq_price) if tqqq_price > 0 else 1.0

    alloc = ALLOC_PCT.get(portfolio.get("position", "CASH"), 0.0)

    record = {
        "date": signal_data["date"],
        "position": portfolio["position"],
        "allocation_pct": alloc,
        "total_value": round(portfolio["total_value"], 2),
        "cash": round(portfolio["cash"], 2),
        "tqqq_shares": round(portfolio["tqqq_shares"], 4),
        "sqqq_shares": round(portfolio["sqqq_shares"], 4),
        "ndx_price": round(signal_data["price"], 2),
        "sma50": round(signal_data["sma50"], 2),
        "sma250": round(signal_data["sma250"], 2),
        "rsi": round(signal_data["rsi"], 2),
        "signal": signal_data["signal"],
        "reason": signal_data["reason"],
        "pnl_dollar": round(portfolio["total_value"] - portfolio["starting_capital"], 2),
        "pnl_pct": round((portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100, 2),
        "ndx_buyhold_pnl_pct": round((signal_data["price"] / ndx_start - 1) * 100, 2),
        "tqqq_buyhold_pnl_pct": round((tqqq_price / tqqq_start - 1) * 100, 2) if tqqq_price > 0 else 0.0,
    }

    # If daily_summary.csv has existing columns, reindex to match them strictly
    if os.path.exists(filepath):
        try:
            existing_cols = pd.read_csv(filepath, nrows=0).columns.tolist()
            if "total_value_orig" in existing_cols and "total_value_orig" not in record:
                orig_file = os.path.join(os.path.dirname(filepath) or ".", "portfolio_state_original.json")
                if os.path.exists(orig_file):
                    try:
                        with open(orig_file, "r", encoding="utf-8") as f:
                            p_orig = json.load(f)
                        record["total_value_orig"] = round(p_orig.get("total_value", 0.0), 2)
                        record["pos_orig"] = p_orig.get("position", "CASH")
                    except Exception:
                        record["total_value_orig"] = record["total_value"]
                        record["pos_orig"] = record["position"]
                else:
                    record["total_value_orig"] = record["total_value"]
                    record["pos_orig"] = record["position"]
            df = pd.DataFrame([record])
            df = df.reindex(columns=existing_cols)
            df.to_csv(filepath, mode="a", header=False, index=False)
        except Exception:
            df = pd.DataFrame([record])
            df.to_csv(filepath, mode="a", header=False, index=False)
    else:
        df = pd.DataFrame([record])
        df.to_csv(filepath, mode="w", header=True, index=False)

    log.info(f"  Daily summary logged: Value=${record['total_value']:,.2f} | P&L={record['pnl_pct']:+.2f}%")
    log.info(f"  Benchmarks: NDX B&H={record['ndx_buyhold_pnl_pct']:+.2f}% | TQQQ B&H={record['tqqq_buyhold_pnl_pct']:+.2f}%")


# ─────────────────────────────────────────────
# PUSH NOTIFICATIONS VIA NTFY.SH
# ─────────────────────────────────────────────
def send_alert(subject: str, body: str, cfg: dict,
               tags: str = "chart_with_upwards_trend", priority: str = "high"):
    if not cfg.get("ntfy_enabled") or not cfg.get("ntfy_topic"):
        return
    try:
        # Strip non-ASCII chars (emoji) from title since HTTP headers require ASCII
        clean_title = subject.encode("ascii", "ignore").decode("ascii").strip()
        requests.post(
            f"https://ntfy.sh/{cfg['ntfy_topic']}",
            data=body.encode("utf-8"),
            headers={
                "Title": clean_title,
                "Priority": priority,
                "Tags": tags,
                "Markdown": "yes",
            },
            timeout=10,
        )
        log.info("  Push notification sent via ntfy.")
    except Exception as e:
        log.warning(f"  Push notification failed: {e}")


def _classify_action(signal: str, made_trade: bool, prev_position: str,
                     in_buffer_zone: bool, trim_active: bool = False,
                     in_buffer_zone_exit: bool = False) -> dict:
    """
    Map signal + trade context into a human-readable action label,
    emoji tags for ntfy, and notification priority.
    """
    if made_trade:
        # Re-entry: scaling back up from a trim
        if signal == "TQQQ_100" and prev_position in ("TQQQ_30", "TQQQ_50"):
            return {"label": "RE-ENTER - Full TQQQ", "tags": "green_circle,rocket", "priority": "high"}
        trade_map = {
            "TQQQ_100": ("BUY - Full TQQQ",            "green_circle,rocket",                  "high"),
            "TQQQ_50":  ("TRIM - Bearish Divergence",   "warning,chart_with_downwards_trend",   "high"),
            "TQQQ_30":  ("TRIM - RSI Overbought",       "orange_circle,scissors",               "high"),
            "SQQQ":     ("SHORT - Enter SQQQ",          "red_circle,bear",                      "urgent"),
            "CASH":     ("SELL - Exit to Cash",          "red_circle,stop_sign",                 "high"),
        }
        label, tags, prio = trade_map.get(signal, (f"TRADE - {signal}", "chart_with_upwards_trend", "high"))
        return {"label": label, "tags": tags, "priority": prio}
    else:
        if in_buffer_zone_exit:
            return {"label": "HOLD - Downside Buffer", "tags": "shield", "priority": "default"}
        if in_buffer_zone:
            return {"label": "WAIT - Re-entry Buffer", "tags": "hourglass_flowing_sand", "priority": "default"}
        if trim_active and signal == "TQQQ_30":
            return {"label": "WAIT - RSI Trim Lock", "tags": "lock", "priority": "default"}
        hold_map = {
            "TQQQ_100": ("HOLD - Full TQQQ",  "white_circle"),
            "TQQQ_50":  ("HOLD - 50% TQQQ",   "white_circle"),
            "TQQQ_30":  ("HOLD - 30% TQQQ",   "white_circle"),
            "SQQQ":     ("HOLD - SQQQ",        "white_circle"),
            "CASH":     ("HOLD - Cash",         "white_circle,dollar"),
        }
        label, tags = hold_map.get(signal, (f"STATUS - {signal}", "white_circle"))
        return {"label": label, "tags": tags, "priority": "default"}


def _build_notification_body(signal_data: dict, portfolio: dict,
                             tqqq_price: float, sqqq_price: float,
                             made_trade: bool, prev_position: str) -> str:
    """Build a markdown-formatted notification body with market data and portfolio breakdown."""
    signal = signal_data["signal"]
    rsi_val = signal_data["rsi"]

    # ── Header ────────────────────────────────
    if made_trade:
        alloc = {"TQQQ_100": "100%", "TQQQ_50": "50%", "TQQQ_30": "30%"}
        if signal.startswith("TQQQ") and prev_position.startswith("TQQQ"):
            desc = f"Adjusted TQQQ {alloc.get(prev_position, prev_position)} \u2192 {alloc.get(signal, signal)}"
        elif signal.startswith("TQQQ"):
            desc = f"Entered TQQQ ({alloc.get(signal, signal)})"
        elif signal == "SQQQ":
            desc = "Entered SQQQ (short)"
        elif signal == "CASH" and prev_position == "SQQQ":
            desc = "Sold all SQQQ \u2192 Cash"
        elif signal == "CASH":
            desc = "Sold all TQQQ \u2192 Cash"
        else:
            desc = f"{prev_position} \u2192 {signal}"
        header = f"**Action:** {desc}\n**Reason:** {signal_data['reason']}"
    else:
        pos_labels = {
            "TQQQ_100": "Full TQQQ (100%)", "TQQQ_50": "TQQQ (50%)",
            "TQQQ_30": "TQQQ (30%)", "SQQQ": "SQQQ (short)", "CASH": "Cash",
        }
        header = (f"**Position:** {pos_labels.get(signal, signal)}\n"
                  f"**Signal:** {signal_data['reason']}")

    # ── Market section ────────────────────────
    sma50_flag  = "\u2705 Above" if signal_data["above_50"]  else "\u274c Below"
    sma250_flag = "\u2705 Above" if signal_data["above_250"] else "\u274c Below"
    if rsi_val >= 75:
        rsi_flag = "\u26a0\ufe0f Overbought"
    elif rsi_val <= 30:
        rsi_flag = "\u26a0\ufe0f Oversold"
    else:
        rsi_flag = "\u2705 Normal"

    market = (
        f"\u2501\u2501\u2501\u2501\u2501\u2501 \U0001f4ca MARKET \u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"NDX         {signal_data['price']:,.1f}\n"
        f"SMA 50      {signal_data['sma50']:,.1f}  {sma50_flag}\n"
        f"SMA 250     {signal_data['sma250']:,.1f}  {sma250_flag}\n"
        f"RSI(14)     {rsi_val:.1f}  {rsi_flag}"
    )
    if signal_data.get("bearish_divergence"):
        market += "\n\u26a0\ufe0f Bearish RSI divergence detected"

    # ── Portfolio section ─────────────────────
    invested = portfolio["tqqq_shares"] * tqqq_price + portfolio["sqqq_shares"] * sqqq_price
    cash = portfolio["cash"]
    total = portfolio["total_value"]
    inv_pct = (invested / total * 100) if total > 0 else 0
    cash_pct = (cash / total * 100) if total > 0 else 0
    pnl = total - portfolio["starting_capital"]
    pnl_pct = (total / portfolio["starting_capital"] - 1) * 100
    pnl_sign = "+" if pnl >= 0 else ""

    portfolio_section = (
        f"\u2501\u2501\u2501\u2501\u2501\u2501 \U0001f4b0 PORTFOLIO \u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Total       ${total:,.2f}\n"
        f"\u251c Invested  ${invested:,.2f}  ({inv_pct:.1f}%)\n"
        f"\u2514 Cash      ${cash:,.2f}  ({cash_pct:.1f}%)"
    )
    if portfolio["tqqq_shares"] > 0:
        portfolio_section += f"\nTQQQ        {portfolio['tqqq_shares']:,.2f} shares @ ${tqqq_price:.2f}"
    if portfolio["sqqq_shares"] > 0:
        portfolio_section += f"\nSQQQ        {portfolio['sqqq_shares']:,.2f} shares @ ${sqqq_price:.2f}"
    portfolio_section += f"\nP&L         {pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)"

    return f"{header}\n\n{market}\n\n{portfolio_section}"


# ─────────────────────────────────────────────
# MAIN RUN FUNCTION
# ─────────────────────────────────────────────
def run_strategy(model: str = "symmetric_atr", portfolio_file: str = None,
                 trade_log_file: str = None, daily_log_file: str = None,
                 market_data: tuple = None, notify: bool = True) -> bool:
    """
    Run one daily evaluation for `model`.
    Returns True if a run executed, False if skipped (already ran today).
    Raises on any failure so callers / CI can detect it.
    """
    cfg = CONFIG
    portfolio_file = portfolio_file or cfg["portfolio_file"]
    trade_log_file = trade_log_file or cfg["trade_log_file"]
    daily_log_file = daily_log_file or cfg["daily_log_file"]
    now = now_et()
    today_str = now.date().isoformat()

    log.info("=" * 60)
    log.info(f"NDX SMA + RSI Strategy — Daily Run [{model}] — {now:%Y-%m-%d %H:%M:%S} ET")
    log.info("=" * 60)

    portfolio = load_portfolio(portfolio_file, cfg["starting_capital"])
    if portfolio.get("last_run_date") == today_str:
        log.info(f"  Already ran today ({today_str}) — skipping duplicate run.")
        return False

    try:
        ndx_df, tqqq_df, sqqq_df = market_data or fetch_market_data(cfg)
        tqqq_price = float(tqqq_df["Close"].iloc[-1])
        sqqq_price = float(sqqq_df["Close"].iloc[-1])
        log.info(f"Current Prices — TQQQ: ${tqqq_price:.2f} | SQQQ: ${sqqq_price:.2f}")

        portfolio = accrue_cash_interest(portfolio, cfg)
        signal_data = determine_signal(
            ndx_df, cfg, current_position=portfolio["position"],
            trim_active=portfolio.get("trim_active", False),
            prev_rsi=portfolio.get("prev_rsi", 50.0), model=model)

        portfolio["trim_active"] = signal_data["trim_active"]
        portfolio["prev_rsi"] = signal_data["rsi"]
        portfolio["last_tqqq_price"] = tqqq_price
        portfolio["last_sqqq_price"] = sqqq_price
        portfolio["last_atr"] = signal_data["atr"]
        log.info(f"Signal: {signal_data['signal']} | RSI: {signal_data['rsi']:.1f} | "
                 f"NDX: {signal_data['price']:.1f} | SMA50: {signal_data['sma50']:.1f} | "
                 f"SMA250: {signal_data['sma250']:.1f}")
        log.info(f"Reason: {signal_data['reason']}")

        if "benchmark_ndx_start" not in portfolio:
            portfolio["benchmark_ndx_start"] = signal_data["price"]
            portfolio["benchmark_tqqq_start"] = tqqq_price

        prev_position = portfolio["position"]
        portfolio, trades = execute_trade(portfolio, signal_data, tqqq_price, sqqq_price, cfg)

        # Always reflect today's evaluation, not just the reason from the last trade
        portfolio["last_signal"] = signal_data["reason"]
        portfolio["last_run_date"] = today_str
        portfolio["last_updated"] = now.isoformat()
        save_portfolio(portfolio, portfolio_file)
        for t in trades:
            log_trade(t, trade_log_file)
        log_daily_summary(portfolio, signal_data, daily_log_file, tqqq_price)
    except Exception as e:
        log.exception(f"Strategy run failed [{model}]: {e}")
        if notify:
            send_alert(f"Strategy ERROR [{model}]", f"{type(e).__name__}: {e}", cfg,
                       tags="warning", priority="urgent")
        raise

    pnl_pct = (portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100
    log.info(f"PORTFOLIO [{model}]: {portfolio['position']} | ${portfolio['total_value']:,.2f} "
             f"| cash ${portfolio['cash']:,.2f} | P&L {pnl_pct:+.2f}%")

    if notify:
        made_trade = bool(trades)
        action_info = _classify_action(
            signal=signal_data["signal"], made_trade=made_trade, prev_position=prev_position,
            in_buffer_zone=signal_data["in_buffer_zone_entry"],
            trim_active=signal_data["trim_active"],
            in_buffer_zone_exit=signal_data["in_buffer_zone_exit"])
        body = _build_notification_body(signal_data, portfolio, tqqq_price, sqqq_price,
                                        made_trade, prev_position)
        send_alert(f"{action_info['label']} | {signal_data['date']}", body, cfg,
                   tags=action_info["tags"], priority=action_info["priority"])
    return True


if __name__ == "__main__":
    run_strategy()
