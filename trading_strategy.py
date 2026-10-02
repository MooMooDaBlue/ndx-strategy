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

Anti-Whipsaw Hysteresis (Dynamic ATR re-entry buffer):
  - EXIT remains at price < SMA50 (immediate protection)
  - RE-ENTRY requires price > SMA50 + (0.5 * ATR) (Dynamic volatility buffer)
  - Prevents repeated buy/sell churn by expanding during high volatility and shrinking during calm markets
  - Buffer only applies when NOT already in a TQQQ position

RSI Re-entry Buffer (Overbought Trim):
  - After trimming to 30% due to RSI >= 75, stay trimmed until RSI crosses above 60 from below
  - Proves momentum has genuinely recovered, not just ticked down 1 point

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

# ─────────────────────────────────────────────
# CONFIGURATION — Edit these settings
# ─────────────────────────────────────────────
CONFIG = {
    # Live trading starting capital
    "starting_capital": 10_000.00,
    "tqqq_ticker": "TQQQ",
    "sqqq_ticker": "SQQQ",

    # File paths (created automatically)
    "portfolio_file": "portfolio_state.json",
    "trade_log_file": "trade_log.csv",
    "daily_log_file": "daily_summary.csv",

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
    # Subscribe to this topic in the ntfy app on your phone
    "ntfy_enabled": True,
    "ntfy_topic": "ndx-quant-strategy-alerts",
}

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
    handlers=[
        logging.FileHandler("strategy.log", encoding="utf-8"),
        logging.StreamHandler(open(1, "w", encoding="utf-8", closefd=False))
    ]
)
log = logging.getLogger(__name__)


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


# ─────────────────────────────────────────────
# TECHNICAL INDICATORS
# ─────────────────────────────────────────────
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


def detect_bearish_divergence(price: pd.Series, rsi: pd.Series, lookback: int = 10) -> bool:
    """
    Bearish divergence: price making higher highs but RSI making lower highs
    over the last `lookback` bars.
    """
    if len(price) < lookback * 2:
        return False
    recent_price = price.iloc[-lookback:]
    prior_price = price.iloc[-lookback*2:-lookback]
    recent_rsi = rsi.iloc[-lookback:]
    prior_rsi = rsi.iloc[-lookback*2:-lookback]

    price_higher_high = recent_price.max() > prior_price.max()
    rsi_lower_high = recent_rsi.max() < prior_rsi.max()

    return price_higher_high and rsi_lower_high


# ─────────────────────────────────────────────
# SIGNAL ENGINE
# ─────────────────────────────────────────────
def determine_signal(ndx_df: pd.DataFrame, cfg: dict, current_position: str = "CASH",
                     trim_active: bool = False, prev_rsi: float = 50.0) -> dict:
    """
    Core signal logic. Returns signal dict with position, reason, and key values.
    Accepts current_position to apply symmetric ATR hysteresis and downside protection buffers on SMA50.
    Accepts trim_active / prev_rsi for RSI re-entry buffer after overbought trims.
    """
    close = ndx_df["Close"].squeeze()

    sma50  = calculate_sma(close, cfg["sma_short"])
    sma250 = calculate_sma(close, cfg["sma_long"])
    rsi    = calculate_rsi(close, cfg["rsi_period"])
    atr    = calculate_atr(ndx_df, 14)

    # Current values
    price    = float(close.iloc[-1])
    s50      = float(sma50.iloc[-1])
    s250     = float(sma250.iloc[-1])
    rsi_val  = float(rsi.iloc[-1])
    rsi_prev = float(rsi.iloc[-2])  # previous RSI for crossing logic
    atr_val  = float(atr.iloc[-1])

    above_50  = price >= s50
    above_250 = price >= s250
    below_50  = price < s50
    below_250 = price < s250

    bearish_div = detect_bearish_divergence(close, rsi, cfg["divergence_lookback"])

    # RSI crossing above 50 (momentum confirmation for re-entry)
    rsi_crossing_above_50 = (rsi_val >= cfg["rsi_trim_medium"]) and (rsi_prev < cfg["rsi_trim_medium"])

    # ── SYMMETRIC ATR HYSTERESIS & DOWNSIDE PROTECTION BUFFER ──────
    # 1. Entry buffer: When NOT in a TQQQ position, require price to clear
    #    SMA50 by an additional dynamic buffer based on ATR before entering.
    # 2. Downside exit buffer: When holding TQQQ, do NOT sell on minor intraday
    #    or 1-point dips below SMA50. Require a confirmed break below
    #    SMA50 - (mult * ATR) to exit to cash.
    atr_mult = cfg.get("atr_buffer_multiplier", 1.0)
    buffered_sma50_entry = s50 + (atr_mult * atr_val)
    buffered_sma50_exit  = s50 - (atr_mult * atr_val)

    in_buffer_zone_entry = (
        not current_position.startswith("TQQQ")
        and above_50
        and price <= buffered_sma50_entry
    )
    in_buffer_zone_exit = (
        current_position.startswith("TQQQ")
        and below_50
        and price >= buffered_sma50_exit
    )
    in_buffer_zone = in_buffer_zone_entry or in_buffer_zone_exit
    buffered_sma50 = buffered_sma50_entry

    # ── RSI RE-ENTRY BUFFER (OVERBOUGHT TRIM) ─
    # After trimming to 30% due to RSI >= 75, stay trimmed until RSI
    # crosses above the reset threshold from below — proving momentum
    # has genuinely recovered, not just ticked down 1 point.
    rsi_reset_threshold = cfg.get("rsi_reset_threshold", 60)
    rsi_reset = (prev_rsi < rsi_reset_threshold) and (rsi_val >= rsi_reset_threshold)
    if trim_active and rsi_reset:
        trim_active = False  # Momentum confirmed recovered
        log.info(f"  RSI reset confirmed: prev {prev_rsi:.1f} → {rsi_val:.1f} (crossed above {rsi_reset_threshold}) — trim lock released")

    # ── SIGNAL DECISION TREE ──────────────────
    if above_250:
        if current_position.startswith("TQQQ") and in_buffer_zone_exit:
            # Downside protection buffer: NDX dipped below SMA50 but remains above the ATR buffer
            # Hold long position to avoid whipsaw churn
            signal = current_position
            reason = (f"Downside buffer hold: NDX {price:.1f} dipped below SMA50 ({s50:.1f}) "
                      f"but remains above downside exit buffer ({buffered_sma50_exit:.1f}) — holding {current_position}")
        elif below_50 and price < buffered_sma50_exit:
            # Confirmed breakdown below downside exit buffer
            signal = "CASH"
            trim_active = False  # Exiting to cash clears trim state
            reason = (f"Downside breakdown: NDX {price:.1f} broke below SMA50 exit buffer "
                      f"({buffered_sma50_exit:.1f}) — exiting longs to cash")
        elif above_50:
            if in_buffer_zone_entry:
                signal = "CASH"
                reason = (f"Re-entry buffer: NDX {price:.1f} above SMA50 ({s50:.1f}) "
                          f"but below re-entry threshold ({buffered_sma50_entry:.1f}) — waiting for confirmation")
            elif rsi_val >= cfg["rsi_overbought"]:
                signal = "TQQQ_30"
                trim_active = True  # Lock trim until RSI resets
                reason = f"Overextended: RSI {rsi_val:.1f} >= {cfg['rsi_overbought']} — trim locked until RSI resets below {rsi_reset_threshold}"
            elif trim_active:
                # RSI dropped below overbought but hasn't fully reset yet.
                signal = "TQQQ_30"
                reason = (f"Trim lock active: RSI {rsi_val:.1f} below {cfg['rsi_overbought']} but hasn't reset "
                          f"(need cross above {rsi_reset_threshold} from below) — staying at 30%")
            elif bearish_div:
                signal = "TQQQ_50"
                reason = f"Bearish RSI divergence detected — trimming to 50%"
            else:
                signal = "TQQQ_100"
                reason = f"Bull trend confirmed: Price > SMA50 & SMA250, RSI {rsi_val:.1f}"
        else:
            signal = "CASH"
            reason = "Holding cash"

    elif below_250 and below_50:
        trim_active = False  # Regime change clears trim state
        if cfg["rsi_sqqq_entry_min"] <= rsi_val <= cfg["rsi_sqqq_entry_max"]:
            signal = "SQQQ"
            reason = f"Bear signal: Price below both SMAs, RSI {rsi_val:.1f} in entry zone [{cfg['rsi_sqqq_entry_min']}-{cfg['rsi_sqqq_entry_max']}]"
        elif rsi_val < cfg["rsi_oversold"]:
            signal = "CASH"
            reason = f"Bear trend but RSI {rsi_val:.1f} oversold — staying cash, don't chase short"
        else:
            signal = "CASH"
            reason = f"Bear trend, RSI {rsi_val:.1f} outside SQQQ entry zone — holding cash"

    elif below_250 and above_50:
        trim_active = False  # Regime change clears trim state
        # Price recovered above 50 but still below 250 — transitional zone
        if in_buffer_zone_entry:
            signal = "CASH"
            reason = (f"Re-entry buffer: NDX {price:.1f} above SMA50 ({s50:.1f}) "
                      f"but below re-entry threshold ({buffered_sma50_entry:.1f}) — waiting for confirmation")
        elif rsi_val >= cfg["rsi_trim_medium"]:
            signal = "TQQQ_30"
            reason = f"Recovery above SMA50 with RSI {rsi_val:.1f} > 50, but below SMA250 — cautious 30%"
        else:
            signal = "CASH"
            reason = f"Recovery above SMA50 but RSI {rsi_val:.1f} < 50 — waiting for confirmation"
    else:
        signal = "CASH"
        reason = "Unclear regime — staying cash"

    return {
        "signal": signal,
        "price": price,
        "sma50": s50,
        "sma250": s250,
        "rsi": rsi_val,
        "above_50": above_50,
        "above_250": above_250,
        "bearish_divergence": bearish_div,
        "in_buffer_zone": in_buffer_zone,
        "in_buffer_zone_entry": in_buffer_zone_entry,
        "in_buffer_zone_exit": in_buffer_zone_exit,
        "buffered_sma50": round(buffered_sma50, 2),
        "buffered_sma50_entry": round(buffered_sma50_entry, 2),
        "buffered_sma50_exit": round(buffered_sma50_exit, 2),
        "trim_active": trim_active,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "date": date.today().isoformat(),
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
        now = datetime.now()
        days_elapsed = (now - last_updated).days
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
def execute_trade(portfolio: dict, signal_data: dict, tqqq_price: float, sqqq_price: float, cfg: dict) -> tuple:
    """
    Execute paper trade based on signal. Returns (portfolio, trade_record).
    """
    signal = signal_data["signal"]
    current_position = portfolio["position"]
    trade_record = None

    # Update current market value first
    portfolio = update_portfolio_value(portfolio, tqqq_price, sqqq_price)
    total_value = portfolio["total_value"]

    # ── NO CHANGE NEEDED ─────────────────────
    # Map signal to position label for comparison
    signal_position_map = {
        "TQQQ_100": "TQQQ_100",
        "TQQQ_50": "TQQQ_50",
        "TQQQ_30": "TQQQ_30",
        "SQQQ": "SQQQ",
        "CASH": "CASH",
    }

    if signal_position_map.get(signal) == current_position:
        log.info(f"  No change — already in {current_position}")
        return portfolio, None

    log.info(f"  TRADE SIGNAL: {current_position} → {signal}")

    # ── STEP 1: LIQUIDATE CURRENT POSITION ───
    if current_position.startswith("TQQQ"):
        proceeds = portfolio["tqqq_shares"] * tqqq_price
        portfolio["cash"] += proceeds
        trade_record = _make_trade("SELL", "TQQQ", portfolio["tqqq_shares"], tqqq_price, proceeds, signal_data)
        portfolio["tqqq_shares"] = 0.0
        portfolio["tqqq_avg_cost"] = 0.0
        log.info(f"  Sold TQQQ: {trade_record['shares']:.4f} shares @ ${tqqq_price:.2f} = ${proceeds:,.2f}")

    elif current_position == "SQQQ":
        proceeds = portfolio["sqqq_shares"] * sqqq_price
        portfolio["cash"] += proceeds
        trade_record = _make_trade("SELL", "SQQQ", portfolio["sqqq_shares"], sqqq_price, proceeds, signal_data)
        portfolio["sqqq_shares"] = 0.0
        portfolio["sqqq_avg_cost"] = 0.0
        log.info(f"  Sold SQQQ: {trade_record['shares']:.4f} shares @ ${sqqq_price:.2f} = ${proceeds:,.2f}")

    # ── STEP 2: ENTER NEW POSITION ────────────
    if signal == "TQQQ_100":
        invest = portfolio["cash"] * cfg["full_tqqq_pct"]
        shares = invest / tqqq_price
        portfolio["tqqq_shares"] = shares
        portfolio["tqqq_avg_cost"] = tqqq_price
        portfolio["cash"] -= invest
        buy_record = _make_trade("BUY", "TQQQ", shares, tqqq_price, invest, signal_data)
        log.info(f"  Bought TQQQ (100%): {shares:.4f} shares @ ${tqqq_price:.2f} = ${invest:,.2f}")
        if trade_record is None:
            trade_record = buy_record

    elif signal == "TQQQ_50":
        invest = total_value * cfg["trim_medium_pct"]
        # Adjust for any existing shares
        current_tqqq_value = portfolio["tqqq_shares"] * tqqq_price
        if invest > current_tqqq_value:
            additional = invest - current_tqqq_value
            shares = additional / tqqq_price
            portfolio["tqqq_shares"] += shares
            portfolio["cash"] -= additional
        else:
            reduce = current_tqqq_value - invest
            shares_to_sell = reduce / tqqq_price
            portfolio["tqqq_shares"] -= shares_to_sell
            portfolio["cash"] += reduce
        buy_record = _make_trade("ADJUST", "TQQQ_50%", portfolio["tqqq_shares"], tqqq_price, invest, signal_data)
        log.info(f"  Adjusted TQQQ to 50%: {portfolio['tqqq_shares']:.4f} shares")
        if trade_record is None:
            trade_record = buy_record

    elif signal == "TQQQ_30":
        invest = total_value * cfg["trim_tqqq_pct"]
        current_tqqq_value = portfolio["tqqq_shares"] * tqqq_price
        if invest > current_tqqq_value:
            additional = invest - current_tqqq_value
            shares = additional / tqqq_price
            portfolio["tqqq_shares"] += shares
            portfolio["cash"] -= additional
        else:
            reduce = current_tqqq_value - invest
            shares_to_sell = reduce / tqqq_price
            portfolio["tqqq_shares"] -= shares_to_sell
            portfolio["cash"] += reduce
        buy_record = _make_trade("ADJUST", "TQQQ_30%", portfolio["tqqq_shares"], tqqq_price, invest, signal_data)
        log.info(f"  Adjusted TQQQ to 30%: {portfolio['tqqq_shares']:.4f} shares")
        if trade_record is None:
            trade_record = buy_record

    elif signal == "SQQQ":
        invest = portfolio["cash"] * cfg["sqqq_pct"]
        shares = invest / sqqq_price
        portfolio["sqqq_shares"] = shares
        portfolio["sqqq_avg_cost"] = sqqq_price
        portfolio["cash"] -= invest
        buy_record = _make_trade("BUY", "SQQQ", shares, sqqq_price, invest, signal_data)
        log.info(f"  Bought SQQQ (100%): {shares:.4f} shares @ ${sqqq_price:.2f} = ${invest:,.2f}")
        if trade_record is None:
            trade_record = buy_record

    elif signal == "CASH":
        log.info(f"  Moved to 100% Cash: ${portfolio['cash']:,.2f}")
        if trade_record is None:
            trade_record = _make_trade("CASH", "CASH", 0, 0, portfolio["cash"], signal_data)

    # Update portfolio metadata
    portfolio["position"] = signal
    portfolio["last_signal"] = signal_data["reason"]
    portfolio["last_updated"] = signal_data["timestamp"]
    portfolio = update_portfolio_value(portfolio, tqqq_price, sqqq_price)

    return portfolio, trade_record


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

    alloc = portfolio.get("allocation_pct")
    if alloc is None:
        pos = portfolio.get("position", "CASH")
        if pos == "TQQQ_100" or pos == "SQQQ":
            alloc = 1.0
        elif pos == "TQQQ_50":
            alloc = 0.5
        elif pos == "TQQQ_30":
            alloc = 0.3
        else:
            alloc = 0.0

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
                     in_buffer_zone: bool, trim_active: bool = False) -> dict:
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
def run_strategy():
    log.info("=" * 60)
    log.info("NDX SMA + RSI Strategy — Daily Run")
    log.info(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    cfg = CONFIG

    # ── 1. FETCH MARKET DATA ──────────────────
    try:
        ndx_df  = fetch_data("^NDX", period="2y")    # Nasdaq 100 Index
        tqqq_df = fetch_data(cfg.get("tqqq_ticker", "TQQQ"), period="5d")
        sqqq_df = fetch_data(cfg.get("sqqq_ticker", "SQQQ"), period="5d")
    except Exception as e:
        log.error(f"Data fetch failed: {e}")
        send_alert("⚠️ Strategy ERROR", f"Data fetch failed: {e}", cfg)
        return

    tqqq_price = float(tqqq_df["Close"].iloc[-1])
    sqqq_price = float(sqqq_df["Close"].iloc[-1])

    log.info(f"Current Prices — TQQQ: ${tqqq_price:.2f} | SQQQ: ${sqqq_price:.2f}")

    # ── 2. LOAD PORTFOLIO (before signal, needed for re-entry buffer) ──
    portfolio = load_portfolio(cfg["portfolio_file"], cfg["starting_capital"])

    # ── SAME-DAY GUARD ────────────────────────
    today_str = date.today().isoformat()
    if portfolio.get("last_run_date") == today_str:
        log.info(f"  Already ran today ({today_str}) — skipping duplicate run.")
        return

    # ── CASH INTEREST ACCRUAL ─────────────────
    portfolio = accrue_cash_interest(portfolio, cfg)

    # ── 3. CALCULATE SIGNAL ───────────────────
    try:
        signal_data = determine_signal(
            ndx_df, cfg,
            current_position=portfolio["position"],
            trim_active=portfolio.get("trim_active", False),
            prev_rsi=portfolio.get("prev_rsi", 50.0),
        )
    except Exception as e:
        log.error(f"Signal calculation failed: {e}")
        send_alert("Strategy ERROR", f"Signal calc failed: {e}", cfg)
        return

    # Persist RSI trim state back to portfolio for next run
    portfolio["trim_active"] = signal_data.get("trim_active", False)
    portfolio["prev_rsi"] = signal_data["rsi"]

    log.info(f"Signal: {signal_data['signal']} | RSI: {signal_data['rsi']:.1f} | "
             f"NDX: {signal_data['price']:.1f} | SMA50: {signal_data['sma50']:.1f} | "
             f"SMA250: {signal_data['sma250']:.1f}")
    log.info(f"Reason: {signal_data['reason']}")
    if signal_data.get("in_buffer_zone_entry"):
        log.info(f"  -> Re-entry buffer active: threshold = {signal_data.get('buffered_sma50_entry', signal_data['buffered_sma50']):.1f}")
    if signal_data.get("in_buffer_zone_exit"):
        log.info(f"  -> Downside exit buffer active: protection floor = {signal_data.get('buffered_sma50_exit', signal_data['buffered_sma50']):.1f}")
    if signal_data.get("trim_active"):
        log.info(f"  -> RSI trim lock active: waiting for RSI to cross above {cfg.get('rsi_reset_threshold', 60)} from below")

    # ── BENCHMARK INITIALIZATION ──────────────
    if "benchmark_ndx_start" not in portfolio:
        portfolio["benchmark_ndx_start"] = signal_data["price"]
        portfolio["benchmark_tqqq_start"] = tqqq_price
        log.info(f"  Benchmark tracking started: NDX={signal_data['price']:.1f}, TQQQ=${tqqq_price:.2f}")

    # ── 4. EXECUTE PAPER TRADE ────────────────
    prev_position = portfolio["position"]  # capture before trade modifies it
    try:
        portfolio, trade = execute_trade(portfolio, signal_data, tqqq_price, sqqq_price, cfg)
    except Exception as e:
        log.error(f"Trade execution failed: {e}")
        send_alert("Strategy ERROR", f"Trade execution failed: {e}", cfg)
        return

    # ── 5. SAVE STATE ─────────────────────────
    portfolio["last_run_date"] = today_str
    # Always advance last_updated so interest accrual on the next run only
    # counts days since today, not since the last trade.
    if not trade:
        portfolio["last_updated"] = datetime.now().isoformat()
    save_portfolio(portfolio, cfg["portfolio_file"])

    if trade:
        log_trade(trade, cfg["trade_log_file"])

    log_daily_summary(portfolio, signal_data, cfg["daily_log_file"], tqqq_price)

    # ── 6. PRINT SUMMARY ──────────────────────
    pnl_pct = (portfolio["total_value"] / portfolio["starting_capital"] - 1) * 100
    log.info("-" * 60)
    log.info(f"PORTFOLIO SUMMARY")
    log.info(f"  Position:      {portfolio['position']}")
    log.info(f"  Total Value:   ${portfolio['total_value']:>12,.2f}")
    log.info(f"  Cash:          ${portfolio['cash']:>12,.2f}")
    log.info(f"  TQQQ Shares:   {portfolio['tqqq_shares']:>12.4f}")
    log.info(f"  SQQQ Shares:   {portfolio['sqqq_shares']:>12.4f}")
    log.info(f"  Total P&L:     ${portfolio['total_value'] - portfolio['starting_capital']:>+12,.2f} ({pnl_pct:+.2f}%)")
    log.info("=" * 60)

    # ── 7. PUSH NOTIFICATION (ALWAYS) ────────
    made_trade = trade and trade["action"] != "CASH"
    action_info = _classify_action(
        signal=signal_data["signal"],
        made_trade=made_trade,
        prev_position=prev_position,
        in_buffer_zone=signal_data.get("in_buffer_zone", False),
        trim_active=signal_data.get("trim_active", False),
    )
    subject = f"{action_info['label']} | {signal_data['date']}"
    body = _build_notification_body(
        signal_data=signal_data,
        portfolio=portfolio,
        tqqq_price=tqqq_price,
        sqqq_price=sqqq_price,
        made_trade=made_trade,
        prev_position=prev_position,
    )
    send_alert(subject, body, cfg, tags=action_info["tags"], priority=action_info["priority"])


if __name__ == "__main__":
    run_strategy()
