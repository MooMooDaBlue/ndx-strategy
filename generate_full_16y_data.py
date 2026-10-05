"""
Regenerate both models from TQQQ inception (2010-02-11, $10,000) using the SAME engine as the
live strategy (trading_strategy.compute_indicators / decide_signal / execute_trade).
Cash earns the historical 13-week T-bill yield (^IRX), not a flat rate.
Writes portfolio_state*.json, daily_summary*.csv, trade_log*.csv, docs/data.json, performance_chart.png.
"""
import os
import sys
import json
import logging
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import run_cloud_strategy as rcs

START = "2010-02-11"
CAP = ts.CONFIG["starting_capital"]
ts.log.setLevel(logging.WARNING)  # keep per-trade logging out of strategy.log


def _dl(ticker, start):
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])


print("1. Downloading data...")
ndx, tqqq, sqqq = _dl("^NDX", "2008-01-01"), _dl("TQQQ", START), _dl("SQQQ", START)
try:
    irx = _dl("^IRX", "2009-12-01")["Close"] / 100.0
except Exception as e:
    print(f"   ^IRX unavailable ({e}); using flat {ts.CONFIG['risk_free_annual_rate']:.2%}")
    irx = None

ind = ts.compute_indicators(ndx, ts.CONFIG)
idx = ind.index.intersection(tqqq.index).intersection(sqqq.index)
idx = idx[idx >= pd.Timestamp(START)]
df = ind.loc[idx].copy()
df["tqqq"] = tqqq.loc[idx, "Close"]
df["sqqq"] = sqqq.loc[idx, "Close"]
df["rf"] = irx.reindex(idx).ffill().fillna(0.0) if irx is not None else ts.CONFIG["risk_free_annual_rate"]

# Drop a partial (in-session) bar for today if needed
now = ts.now_et()
if df.index[-1].date() == now.date() and now.hour < 17:
    df = df.iloc[:-1]
print(f"2. Simulating {len(df)} sessions {df.index[0].date()} -> {df.index[-1].date()}")


def simulate(model):
    p = {
        "position": "CASH",
        "allocation_pct": 0.0,
        "cash": CAP,
        "tqqq_shares": 0.0,
        "sqqq_shares": 0.0,
        "tqqq_avg_cost": 0.0,
        "sqqq_avg_cost": 0.0,
        "total_value": CAP,
        "starting_capital": CAP,
        "trim_active": False,
        "prev_rsi": 50.0
    }
    trades, daily, prev_d = [], [], None
    ndx0, tqqq0 = float(df["close"].iloc[0]), float(df["tqqq"].iloc[0])
    for t, row in df.iterrows():
        d = t.date()
        if prev_d is not None and p["cash"] > 0:
            p["cash"] += p["cash"] * float(row["rf"]) / 365 * (d - prev_d).days
        prev_d = d
        price, rsi = float(row["close"]), float(row["rsi"])
        dec = ts.decide_signal(price, float(row["sma50"]), float(row["sma250"]), rsi, float(row["atr"]),
                               bool(row["bearish_div"]), p["position"], p["trim_active"], p["prev_rsi"],
                               ts.CONFIG, model)
        p["trim_active"], p["prev_rsi"] = dec["trim_active"], rsi
        sd = {
            "signal": dec["signal"],
            "reason": dec["reason"],
            "date": d.isoformat(),
            "timestamp": f"{d.isoformat()}T15:50:00",
            "price": price,
            "sma50": float(row["sma50"]),
            "sma250": float(row["sma250"]),
            "rsi": rsi,
            "atr": float(row["atr"]),
            "in_buffer_zone_entry": dec.get("in_buffer_zone_entry", False),
            "in_buffer_zone_exit": dec.get("in_buffer_zone_exit", False),
            "bearish_div": bool(row["bearish_div"])
        }
        p, new = ts.execute_trade(p, sd, float(row["tqqq"]), float(row["sqqq"]), ts.CONFIG)
        for tr in new:
            for k in ("shares", "price", "value", "ndx_price", "sma50", "sma250", "rsi"):
                tr[k] = round(float(tr[k]), 4 if k == "shares" else 2)
            trades.append(tr)
        p = ts.update_portfolio_value(p, float(row["tqqq"]), float(row["sqqq"]))
        v = p["total_value"]
        daily.append({
            "date": d.isoformat(),
            "position": p["position"],
            "allocation_pct": ts.ALLOC_PCT[p["position"]],
            "total_value": round(v, 2),
            "cash": round(p["cash"], 2),
            "tqqq_shares": round(p["tqqq_shares"], 4),
            "sqqq_shares": round(p["sqqq_shares"], 4),
            "ndx_price": round(price, 2),
            "sma50": round(float(row["sma50"]), 2),
            "sma250": round(float(row["sma250"]), 2),
            "rsi": round(rsi, 2),
            "signal": dec["signal"],
            "reason": dec["reason"],
            "pnl_dollar": round(v - CAP, 2),
            "pnl_pct": round((v / CAP - 1) * 100, 2),
            "ndx_buyhold_pnl_pct": round((price / ndx0 - 1) * 100, 2),
            "tqqq_buyhold_pnl_pct": round((float(row["tqqq"]) / tqqq0 - 1) * 100, 2),
        })
    last = df.iloc[-1]
    p.update({
        "last_run_date": df.index[-1].date().isoformat(),
        "last_updated": f"{df.index[-1].date().isoformat()}T15:50:00",
        "benchmark_ndx_start": ndx0,
        "benchmark_tqqq_start": tqqq0,
        "last_tqqq_price": float(last["tqqq"]),
        "last_sqqq_price": float(last["sqqq"]),
        "last_atr": float(last["atr"])
    })
    return p, daily, trades


p_sym, d_sym, t_sym = simulate("symmetric_atr")
p_orig, d_orig, t_orig = simulate("original_agile")
for name, p, t in (("Symmetric ATR", p_sym, t_sym), ("Original Agile", p_orig, t_orig)):
    print(f"   {name}: ${p['total_value']:,.2f} ({(p['total_value']/CAP-1)*100:+,.2f}%) | {len(t)} trade legs")

print("3. Writing files...")
for fname, p in (("portfolio_state.json", p_sym), ("portfolio_state_original.json", p_orig)):
    with open(os.path.join(BASE_DIR, fname), "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)
ds = pd.DataFrame(d_sym)
ds["total_value_orig"] = [r["total_value"] for r in d_orig]
ds["pos_orig"] = [r["position"] for r in d_orig]
ds.to_csv(os.path.join(BASE_DIR, "daily_summary.csv"), index=False)
pd.DataFrame(d_orig).to_csv(os.path.join(BASE_DIR, "daily_summary_original.csv"), index=False)
pd.DataFrame(t_sym).to_csv(os.path.join(BASE_DIR, "trade_log.csv"), index=False)
pd.DataFrame(t_orig).to_csv(os.path.join(BASE_DIR, "trade_log_original.csv"), index=False)

rcs.generate_chart()
rcs.export_pages_data()
print("Done.")
