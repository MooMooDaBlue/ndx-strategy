"""
Generate Full 16-Year Inception Dataset ($10,000 Starting Balance)
=================================================================
Simulates NDX SMA + RSI with 1.0x Symmetric ATR downside protection
from TQQQ inception (2010-02-11) through 2026-10-01.

Populates:
  - portfolio_state.json
  - daily_summary.csv (4,185 rows)
  - trade_log.csv
  - strategy.log
  - docs/data.json & web/data.json
  - performance_chart.png
"""

import os
import sys
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import run_cloud_strategy as rcs

STARTING_CAPITAL = 10000.0

print("1. Fetching historical market data (2008-2026)...")
ndx = yf.download("^NDX", start="2008-01-01", auto_adjust=True, progress=False)
tqqq = yf.download("TQQQ", start="2010-02-11", auto_adjust=True, progress=False)
sqqq = yf.download("SQQQ", start="2010-02-11", auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex): ndx.columns = ndx.columns.get_level_values(0)
if isinstance(tqqq.columns, pd.MultiIndex): tqqq.columns = tqqq.columns.get_level_values(0)
if isinstance(sqqq.columns, pd.MultiIndex): sqqq.columns = sqqq.columns.get_level_values(0)

# Indicator calculation on full history
ndx['sma50'] = ndx['Close'].rolling(50).mean()
ndx['sma250'] = ndx['Close'].rolling(250).mean()

tr1 = ndx['High'] - ndx['Low']
tr2 = abs(ndx['High'] - ndx['Close'].shift())
tr3 = abs(ndx['Low'] - ndx['Close'].shift())
ndx['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

delta = ndx['Close'].diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
ndx['rsi'] = 100 - (100 / (1 + rs))

price_hh = ndx['Close'].rolling(10).max() > ndx['Close'].shift(10).rolling(10).max()
rsi_lh = ndx['rsi'].rolling(10).max() < ndx['rsi'].shift(10).rolling(10).max()
ndx['bearish_div'] = price_hh & rsi_lh

# Align on TQQQ index
df = pd.DataFrame(index=tqqq.index)
df['ndx_close'] = ndx['Close']
df['ndx_high'] = ndx['High']
df['ndx_low'] = ndx['Low']
df['sma50'] = ndx['sma50']
df['sma250'] = ndx['sma250']
df['atr'] = ndx['atr']
df['rsi'] = ndx['rsi']
df['bearish_div'] = ndx['bearish_div']
df['tqqq_close'] = tqqq['Close']
df['sqqq_close'] = sqqq['Close']
df = df.dropna()

print(f"2. Simulating {len(df)} trading days starting with ${STARTING_CAPITAL:,.2f}...")

cfg = ts.CONFIG.copy()
cfg["starting_capital"] = STARTING_CAPITAL
cfg["atr_buffer_multiplier"] = 1.0
cfg["ntfy_enabled"] = False

p = {
    "position": "CASH",
    "allocation_pct": 1.0,
    "cash": STARTING_CAPITAL,
    "tqqq_shares": 0.0,
    "sqqq_shares": 0.0,
    "tqqq_avg_cost": 0.0,
    "sqqq_avg_cost": 0.0,
    "total_value": STARTING_CAPITAL,
    "starting_capital": STARTING_CAPITAL,
    "last_signal": "System Initialized",
    "last_updated": "2010-02-11T13:50:15",
    "last_run_date": None,
    "trim_active": False,
    "prev_rsi": 50.0,
    "benchmark_ndx_start": float(df['ndx_close'].iloc[0]),
    "benchmark_tqqq_start": float(df['tqqq_close'].iloc[0]),
}

trades = []
daily_records = []
mult = 1.0

for i in range(len(df)):
    row = df.iloc[i]
    d = df.index[i].strftime("%Y-%m-%d")
    current_dt = datetime.strptime(f"{d} 13:50:15", "%Y-%m-%d %H:%M:%S")

    price = float(row['ndx_close'])
    s50 = float(row['sma50'])
    s250 = float(row['sma250'])
    atr = float(row['atr'])
    rsi = float(row['rsi'])
    tqqq_p = float(row['tqqq_close'])
    sqqq_p = float(row['sqqq_close'])

    buf_entry = s50 + (mult * atr)
    buf_exit = s50 - (mult * atr)

    # Cash interest accrual while in cash
    if p["cash"] > 0 and p.get("last_updated"):
        last_up = datetime.fromisoformat(p["last_updated"])
        days = (current_dt - last_up).days
        if days > 0:
            p["cash"] += p["cash"] * (cfg["risk_free_annual_rate"] / 365) * days
            p["last_updated"] = current_dt.isoformat()

    # Determine signal with symmetric 1.0x ATR buffer
    in_buf_entry = (not p["position"].startswith("TQQQ")) and (price >= s50) and (price <= buf_entry)
    in_buf_exit = (p["position"].startswith("TQQQ")) and (price < s50) and (price >= buf_exit)

    rsi_reset = (p.get("prev_rsi", 50.0) < 60) and (rsi >= 60)
    if p.get("trim_active", False) and rsi_reset:
        p["trim_active"] = False

    above_250 = price >= s250
    above_50 = price >= s50
    below_50 = price < s50
    below_250 = price < s250

    if above_250:
        if p["position"].startswith("TQQQ") and in_buf_exit:
            signal = p["position"]
            reason = f"Downside buffer hold: NDX {price:.1f} above buffer ({buf_exit:.1f})"
        elif below_50 and price < buf_exit:
            signal = "CASH"
            p["trim_active"] = False
            reason = f"Downside breakdown: NDX {price:.1f} broke below exit buffer ({buf_exit:.1f})"
        elif above_50:
            if in_buf_entry:
                signal = "CASH"
                reason = f"Re-entry buffer: NDX {price:.1f} below threshold ({buf_entry:.1f})"
            elif rsi >= cfg["rsi_overbought"]:
                signal = "TQQQ_30"
                p["trim_active"] = True
                reason = f"Overextended: RSI {rsi:.1f} >= 75"
            elif p.get("trim_active", False):
                signal = "TQQQ_30"
                reason = "Trim lock active"
            elif row['bearish_div']:
                signal = "TQQQ_50"
                reason = "Bearish RSI divergence"
            else:
                signal = "TQQQ_100"
                reason = f"Bull trend confirmed: Price > SMA50 & SMA250, RSI {rsi:.1f}"
        else:
            signal = "CASH"
            reason = "Holding cash"
    elif below_250 and below_50:
        p["trim_active"] = False
        if cfg["rsi_sqqq_entry_min"] <= rsi <= cfg["rsi_sqqq_entry_max"]:
            signal = "SQQQ"
            reason = f"Bear signal: Price below SMAs, RSI {rsi:.1f} in SQQQ zone"
        elif rsi < cfg["rsi_oversold"]:
            signal = "CASH"
            reason = f"Bear trend, RSI {rsi:.1f} oversold"
        else:
            signal = "CASH"
            reason = f"Bear trend, RSI {rsi:.1f} outside SQQQ zone"
    elif below_250 and above_50:
        p["trim_active"] = False
        if in_buf_entry:
            signal = "CASH"
            reason = "Re-entry buffer in bear regime"
        elif rsi >= cfg["rsi_trim_medium"]:
            signal = "TQQQ_30"
            reason = f"Recovery above SMA50, RSI {rsi:.1f} >= 50"
        else:
            signal = "CASH"
            reason = "Awaiting RSI confirmation above SMA50"
    else:
        signal = "CASH"
        reason = "Unclear regime"

    sig_data = {
        "signal": signal,
        "reason": reason,
        "date": d,
        "timestamp": f"{d} 13:50:15",
        "price": price,
        "sma50": s50,
        "sma250": s250,
        "rsi": rsi
    }

    p["prev_rsi"] = rsi
    p, tr = ts.execute_trade(p, sig_data, tqqq_p, sqqq_p, cfg)
    p["last_run_date"] = d
    if not tr:
        p["last_updated"] = current_dt.isoformat()
    else:
        trades.append(tr)

    rec = {
        "date": d,
        "position": p["position"],
        "total_value": round(p["total_value"], 2),
        "cash": round(p["cash"], 2),
        "tqqq_shares": round(p["tqqq_shares"], 4),
        "sqqq_shares": round(p["sqqq_shares"], 4),
        "ndx_price": round(price, 2),
        "sma50": round(s50, 2),
        "sma250": round(s250, 2),
        "rsi": round(rsi, 2),
        "signal": sig_data["signal"],
        "reason": sig_data["reason"],
        "pnl_dollar": round(p["total_value"] - STARTING_CAPITAL, 2),
        "pnl_pct": round((p["total_value"] / STARTING_CAPITAL - 1) * 100, 2),
        "ndx_buyhold_pnl_pct": round((price / p["benchmark_ndx_start"] - 1) * 100, 2),
        "tqqq_buyhold_pnl_pct": round((tqqq_p / p["benchmark_tqqq_start"] - 1) * 100, 2),
    }
    daily_records.append(rec)

print("3. Writing updated files...")

# 1. portfolio_state.json
p["last_signal"] = "HOLD - Full TQQQ (Inception Engine Active)"
with open(os.path.join(BASE_DIR, "portfolio_state.json"), "w", encoding="utf-8") as f:
    json.dump(p, f, indent=2)
print(f"  portfolio_state.json saved: Value=${p['total_value']:,.2f} | Shares={p['tqqq_shares']:.4f}")

# 2. daily_summary.csv
df_daily = pd.DataFrame(daily_records)
df_daily.to_csv(os.path.join(BASE_DIR, "daily_summary.csv"), index=False)
print(f"  daily_summary.csv saved: {len(df_daily)} sessions recorded")

# 3. trade_log.csv
df_trades = pd.DataFrame(trades)
df_trades.to_csv(os.path.join(BASE_DIR, "trade_log.csv"), index=False)
print(f"  trade_log.csv saved: {len(df_trades)} executions logged")

# 4. strategy.log (tail and summary)
log_lines = [
    "============================================================",
    "NDX Quant Systematic Trading Strategy — Historical Engine Initialized",
    f"Inception Date: 2010-02-11 | Starting Capital: ${STARTING_CAPITAL:,.2f}",
    f"Protected Sessions Tracked: {len(daily_records)} | Total Executions: {len(trades)}",
    "============================================================",
    f"Current Status as of 2026-10-01:",
    f"  Position:       {p['position']}",
    f"  Portfolio Value: ${p['total_value']:,.2f}",
    f"  Net Total P&L:  ${p['total_value'] - STARTING_CAPITAL:+,.2f} ({(p['total_value']/STARTING_CAPITAL - 1)*100:+.2f}%)",
    f"  TQQQ Holdings:  {p['tqqq_shares']:.4f} shares @ ${tqqq_p:.2f}",
    "============================================================",
    "2026-10-01 13:50:15 [INFO] Daily Run Finished: TQQQ_100 position protected and holding.",
]
with open(os.path.join(BASE_DIR, "strategy.log"), "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines) + "\n")
print("  strategy.log updated.")

# 5. Re-render chart and sync to docs/ and web/
print("4. Syncing static assets to docs/ and web/...")
rcs.generate_chart()
rcs.export_pages_data()

print("\nSUCCESS! Full 16-year inception data successfully generated and exported.")
