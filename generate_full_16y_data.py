"""
Generate Dual Model Inception Dataset (2010–2026, $10,000 Starting Capital)
============================================================================
Simulates BOTH models side-by-side from TQQQ inception:
  1. Symmetric 1.0x ATR (Macro Defensive Hysteresis Buffer)
  2. Original Agile (1.0% Confirmation Buffer & Clean SMA50 Stop)

Populates:
  - portfolio_state.json & portfolio_state_original.json
  - daily_summary.csv (with dual equity columns) & daily_summary_original.csv
  - trade_log.csv & trade_log_original.csv
  - strategy.log & strategy_original.log
  - web/data.json & docs/data.json (full dual-model payload)
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
import run_cloud_strategy as rcs

STARTING_CAPITAL = 10000.0
RISK_FREE_RATE = 0.045

print("1. Fetching historical market data (2008-2026)...")
ndx = yf.download("^NDX", start="2008-01-01", auto_adjust=True, progress=False)
tqqq = yf.download("TQQQ", start="2010-02-11", auto_adjust=True, progress=False)
sqqq = yf.download("SQQQ", start="2010-02-11", auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex): ndx.columns = ndx.columns.get_level_values(0)
if isinstance(tqqq.columns, pd.MultiIndex): tqqq.columns = tqqq.columns.get_level_values(0)
if isinstance(sqqq.columns, pd.MultiIndex): sqqq.columns = sqqq.columns.get_level_values(0)

# Indicators
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

common_idx = ndx.index.intersection(tqqq.index).intersection(sqqq.index)
common_idx = common_idx[common_idx >= pd.Timestamp("2010-02-11")]

df = pd.DataFrame(index=common_idx)
df['ndx_close'] = ndx.loc[common_idx, 'Close']
df['sma50'] = ndx.loc[common_idx, 'sma50']
df['sma250'] = ndx.loc[common_idx, 'sma250']
df['atr'] = ndx.loc[common_idx, 'atr']
df['rsi'] = ndx.loc[common_idx, 'rsi']
df['bearish_div'] = ndx.loc[common_idx, 'bearish_div']
df['tqqq_close'] = tqqq.loc[common_idx, 'Close']
df['sqqq_close'] = sqqq.loc[common_idx, 'Close']

print(f"2. Simulating both models over {len(df)} sessions (2010 to 2026)...")

def run_simulation(model_name):
    cash = STARTING_CAPITAL
    t_shares = 0.0
    s_shares = 0.0
    pos = "CASH"
    trim_active = False
    prev_rsi = 50.0
    last_dt = datetime.strptime("2010-02-11 13:50:15", "%Y-%m-%d %H:%M:%S")
    
    trades = []
    daily_records = []
    
    ndx_start = float(df['ndx_close'].iloc[0])
    tqqq_start = float(df['tqqq_close'].iloc[0])
    
    for i in range(len(df)):
        row = df.iloc[i]
        d = df.index[i].strftime("%Y-%m-%d")
        cur_dt = datetime.strptime(f"{d} 13:50:15", "%Y-%m-%d %H:%M:%S")
        price = float(row['ndx_close'])
        s50 = float(row['sma50'])
        s250 = float(row['sma250'])
        atr = float(row['atr'])
        rsi = float(row['rsi'])
        tqqq_p = float(row['tqqq_close'])
        sqqq_p = float(row['sqqq_close'])
        
        # Cash interest accrual
        days = (cur_dt - last_dt).days
        if cash > 0 and days > 0:
            cash += cash * (RISK_FREE_RATE / 365) * days
        last_dt = cur_dt
        
        curr_val = cash + t_shares * tqqq_p + s_shares * sqqq_p
        
        above_250 = price >= s250
        above_50 = price >= s50
        below_50 = price < s50
        below_250 = price < s250
        
        rsi_reset = (prev_rsi < 60) and (rsi >= 60)
        if trim_active and rsi_reset:
            trim_active = False
            
        signal = "CASH"
        reason = ""
        
        if model_name == "symmetric_atr":
            buf_entry = s50 + (1.0 * atr)
            buf_exit = s50 - (1.0 * atr)
            in_buf_entry = (not pos.startswith("TQQQ")) and (price >= s50) and (price <= buf_entry)
            in_buf_exit = (pos.startswith("TQQQ")) and (price < s50) and (price >= buf_exit)
            
            if trim_active and (rsi < 50 or price < s50):
                trim_active = False
                
            if above_250:
                if pos.startswith("TQQQ") and in_buf_exit:
                    signal = pos
                    reason = f"Downside buffer hold: NDX {price:.1f} >= {buf_exit:.1f}"
                elif below_50 and price < buf_exit:
                    signal = "CASH"
                    trim_active = False
                    reason = f"Downside breakdown: NDX {price:.1f} broke below exit buffer ({buf_exit:.1f})"
                elif above_50:
                    if in_buf_entry:
                        signal = "CASH"
                        reason = f"Re-entry buffer: NDX {price:.1f} <= {buf_entry:.1f}"
                    elif rsi >= 75:
                        signal = "TQQQ_30"
                        trim_active = True
                        reason = f"Overbought: RSI {rsi:.1f} >= 75"
                    elif trim_active:
                        signal = "TQQQ_30"
                        reason = "Overbought trim lock active"
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
                trim_active = False
                if 35 <= rsi <= 55:
                    signal = "SQQQ"
                    reason = f"Bear signal: Price below SMAs, RSI {rsi:.1f} in SQQQ zone"
                else:
                    signal = "CASH"
                    reason = "Bear trend, defensive cash"
            elif below_250 and above_50:
                if in_buf_entry:
                    signal = "CASH"
                    reason = "Re-entry buffer in bear regime"
                elif rsi >= 50:
                    signal = "TQQQ_30"
                    reason = "Counter-trend rally below SMA250"
                else:
                    signal = "CASH"
                    reason = "Below SMA250, insufficient RSI momentum"
                    
        elif model_name == "original_agile":
            reentry_thresh = s50 * 1.01
            in_buf_entry = (not pos.startswith("TQQQ")) and (price >= s50) and (price <= reentry_thresh)
            
            if above_250:
                if below_50:
                    signal = "CASH"
                    trim_active = False
                    reason = f"Clean exit: NDX {price:.1f} broke below SMA50 ({s50:.1f})"
                elif above_50:
                    if in_buf_entry:
                        signal = "CASH"
                        reason = f"1% confirmation buffer: NDX {price:.1f} <= threshold ({reentry_thresh:.1f})"
                    elif rsi >= 75:
                        signal = "TQQQ_30"
                        trim_active = True
                        reason = f"Overbought: RSI {rsi:.1f} >= 75"
                    elif trim_active:
                        signal = "TQQQ_30"
                        reason = "Overbought trim active"
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
                trim_active = False
                if 35 <= rsi <= 55:
                    signal = "SQQQ"
                    reason = f"Bear signal: Below SMAs, RSI {rsi:.1f} in SQQQ zone"
                else:
                    signal = "CASH"
                    reason = "Defensive cash in bear regime"
            elif below_250 and above_50:
                if in_buf_entry:
                    signal = "CASH"
                    reason = "1% confirmation buffer below SMA250"
                elif rsi >= 50:
                    signal = "TQQQ_30"
                    reason = "Counter-trend rally below SMA250"
                else:
                    signal = "CASH"
                    reason = "Below SMA250, insufficient momentum"
                    
        prev_rsi = rsi
        
        # Position execution
        if signal != pos:
            cash = curr_val
            t_shares = 0.0
            s_shares = 0.0
            action = "BUY" if signal.startswith("TQQQ") or signal == "SQQQ" else "SELL"
            ticker = "TQQQ" if signal.startswith("TQQQ") else ("SQQQ" if signal == "SQQQ" else (pos.split("_")[0] if pos != "CASH" else "CASH"))
            shs = 0.0
            px = tqqq_p if ticker == "TQQQ" else (sqqq_p if ticker == "SQQQ" else 0.0)
            
            if signal == "TQQQ_100":
                t_shares = cash / tqqq_p
                shs = t_shares
                cash = 0.0
            elif signal == "TQQQ_50":
                invest = cash * 0.5
                t_shares = invest / tqqq_p
                shs = t_shares
                cash -= invest
            elif signal == "TQQQ_30":
                invest = cash * 0.3
                t_shares = invest / tqqq_p
                shs = t_shares
                cash -= invest
            elif signal == "SQQQ":
                s_shares = cash / sqqq_p
                shs = s_shares
                cash = 0.0
                
            trades.append({
                "date": d,
                "timestamp": f"{d} 13:50:15",
                "action": action,
                "ticker": ticker,
                "shares": round(shs, 4),
                "price": round(px, 2),
                "value": round(curr_val, 2),
                "ndx_price": round(price, 2),
                "sma50": round(s50, 2),
                "sma250": round(s250, 2),
                "rsi": round(rsi, 2),
                "reason": reason
            })
            pos = signal
            
        val = cash + t_shares * tqqq_p + s_shares * sqqq_p
        alloc_pct = 1.0 if pos == "TQQQ_100" else (0.5 if pos == "TQQQ_50" else (0.3 if pos == "TQQQ_30" else 0.0))
        
        daily_records.append({
            "date": d,
            "position": pos,
            "allocation_pct": alloc_pct,
            "total_value": round(val, 2),
            "cash": round(cash, 2),
            "tqqq_shares": round(t_shares, 4),
            "sqqq_shares": round(s_shares, 4),
            "ndx_price": round(price, 2),
            "sma50": round(s50, 2),
            "sma250": round(s250, 2),
            "rsi": round(rsi, 2),
            "signal": pos,
            "reason": reason,
            "pnl_dollar": round(val - STARTING_CAPITAL, 2),
            "pnl_pct": round((val / STARTING_CAPITAL - 1) * 100, 2),
            "ndx_buyhold_pnl_pct": round((price / ndx_start - 1) * 100, 2),
            "tqqq_buyhold_pnl_pct": round((tqqq_p / tqqq_start - 1) * 100, 2),
        })
        
    portfolio = {
        "position": pos,
        "allocation_pct": alloc_pct,
        "cash": round(cash, 2),
        "tqqq_shares": round(t_shares, 4),
        "sqqq_shares": round(s_shares, 4),
        "tqqq_avg_cost": round(tqqq_p if t_shares > 0 else 0.0, 2),
        "sqqq_avg_cost": round(sqqq_p if s_shares > 0 else 0.0, 2),
        "total_value": round(val, 2),
        "starting_capital": STARTING_CAPITAL,
        "last_signal": reason or pos,
        "last_updated": f"{d}T13:50:15",
        "last_run_date": d,
        "trim_active": trim_active,
        "prev_rsi": round(rsi, 2),
        "benchmark_ndx_start": ndx_start,
        "benchmark_tqqq_start": tqqq_start
    }
    
    # Compute stats
    hwm = STARTING_CAPITAL
    max_dd = 0.0
    for r in daily_records:
        v = r["total_value"]
        if v > hwm: hwm = v
        dd = (v - hwm) / hwm * 100
        if dd < max_dd: max_dd = dd
        
    latest = daily_records[-1]
    stats = {
        "total_pnl": round(val - STARTING_CAPITAL, 2),
        "total_pnl_pct": round((val / STARTING_CAPITAL - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": len(trades),
        "current_position": pos,
        "allocation_pct": alloc_pct,
        "dist_sma50_pts": round(latest["ndx_price"] - latest["sma50"], 2),
        "dist_sma50_pct": round(((latest["ndx_price"] - latest["sma50"]) / latest["sma50"]) * 100, 2),
        "dist_sma250_pts": round(latest["ndx_price"] - latest["sma250"], 2),
        "dist_sma250_pct": round(((latest["ndx_price"] - latest["sma250"]) / latest["sma250"]) * 100, 2),
        "rsi": latest["rsi"],
        "atr": round(float(df['atr'].iloc[-1]), 2),
        "last_run_date": d,
        "return_1y_pct": round((daily_records[-1]["total_value"] / daily_records[-252]["total_value"] - 1) * 100, 2),
        "return_6m_pct": round((daily_records[-1]["total_value"] / daily_records[-126]["total_value"] - 1) * 100, 2),
        "return_1m_pct": round((daily_records[-1]["total_value"] / daily_records[-22]["total_value"] - 1) * 100, 2),
    }
    
    logs = [
        f"2026-10-01 13:50:15 [MODEL: {model_name}] Market evaluated at close: NDX={latest['ndx_price']:.2f}, SMA50={latest['sma50']:.2f}, SMA250={latest['sma250']:.2f}, RSI={latest['rsi']:.1f}",
        f"2026-10-01 13:50:15 [DECISION] Position={pos} | Reason={reason or 'System holding systematic allocation'}",
        f"2026-10-01 13:50:15 [PORTFOLIO] Total Value=${val:,.2f} | P&L: {stats['total_pnl_pct']:+,.2f}% | Cash=${cash:,.2f}"
    ]
    
    return portfolio, stats, daily_records, trades, logs

p_sym, stats_sym, daily_sym, trades_sym, logs_sym = run_simulation("symmetric_atr")
p_orig, stats_orig, daily_orig, trades_orig, logs_orig = run_simulation("original_agile")

print("--- SIMULATION COMPLETE ---")
print(f"Symmetric 1.0x ATR:  End Val=${p_sym['total_value']:,.2f} (+{stats_sym['total_pnl_pct']:.2f}%) | 1Y={stats_sym['return_1y_pct']:+.2f}% | 6M={stats_sym['return_6m_pct']:+.2f}% | Trades={stats_sym['total_trades']}")
print(f"Original Agile (1%): End Val=${p_orig['total_value']:,.2f} (+{stats_orig['total_pnl_pct']:.2f}%) | 1Y={stats_orig['return_1y_pct']:+.2f}% | 6M={stats_orig['return_6m_pct']:+.2f}% | Trades={stats_orig['total_trades']}")

# 3. Save Files
print("\n3. Saving dual-model files to workspace...")

# Portfolio states
with open(os.path.join(BASE_DIR, "portfolio_state.json"), "w", encoding="utf-8") as f:
    json.dump(p_sym, f, indent=2)

with open(os.path.join(BASE_DIR, "portfolio_state_original.json"), "w", encoding="utf-8") as f:
    json.dump(p_orig, f, indent=2)

# Daily summaries
df_daily_sym = pd.DataFrame(daily_sym)
df_daily_sym['total_value_orig'] = [r['total_value'] for r in daily_orig]
df_daily_sym['pos_orig'] = [r['position'] for r in daily_orig]
df_daily_sym.to_csv(os.path.join(BASE_DIR, "daily_summary.csv"), index=False)

df_daily_orig = pd.DataFrame(daily_orig)
df_daily_orig.to_csv(os.path.join(BASE_DIR, "daily_summary_original.csv"), index=False)

# Trade logs
df_trades_sym = pd.DataFrame(trades_sym)
df_trades_sym.to_csv(os.path.join(BASE_DIR, "trade_log.csv"), index=False)

df_trades_orig = pd.DataFrame(trades_orig)
df_trades_orig.to_csv(os.path.join(BASE_DIR, "trade_log_original.csv"), index=False)

# Compiled dual-model payload
full_payload = {
    "active_model": "symmetric_atr",
    "models": {
        "symmetric_atr": {
            "id": "symmetric_atr",
            "name": "Symmetric 1.0× ATR",
            "badge": "Macro Defensive Hysteresis",
            "description": "1.0× ATR downside hysteresis buffer designed to absorb market noise and ride multi-year trends.",
            "total_return_pct": stats_sym["total_pnl_pct"],
            "ending_value": p_sym["total_value"],
            "portfolio": p_sym,
            "stats": stats_sym,
            "daily_summary": daily_sym,
            "trades": trades_sym,
            "recent_logs": logs_sym
        },
        "original_agile": {
            "id": "original_agile",
            "name": "Original Agile (1% Buffer)",
            "badge": "Fast SMA50 Stop & Tight Re-Entry",
            "description": "Immediate clean exit below 50-day SMA with 1.0% confirmation buffer on re-entry. Highly responsive.",
            "total_return_pct": stats_orig["total_pnl_pct"],
            "ending_value": p_orig["total_value"],
            "portfolio": p_orig,
            "stats": stats_orig,
            "daily_summary": daily_orig,
            "trades": trades_orig,
            "recent_logs": logs_orig
        }
    },
    # Root keys for backwards compatibility:
    "portfolio": p_sym,
    "stats": stats_sym,
    "daily_summary": daily_sym,
    "trades": trades_sym,
    "recent_logs": logs_sym,
    "config": {
        "starting_capital": STARTING_CAPITAL,
        "ntfy_topic": "ndx-quant-strategy-alerts",
        "market_close_time_mt": "13:50",
        "market_close_time_et": "15:50",
        "risk_free_annual_rate": RISK_FREE_RATE
    }
}

for out_dir in [os.path.join(BASE_DIR, "web"), os.path.join(BASE_DIR, "docs")]:
    target = os.path.join(out_dir, "data.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(full_payload, f, indent=2)
    print(f"  Exported dual-model payload: {target}")

rcs.generate_chart()
print("\nDual-model dataset generation complete!")
