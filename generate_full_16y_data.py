"""
Regenerate both models from TQQQ inception (2010-02-11, $10,000) using the SAME engine as the
live strategy (trading_strategy.compute_indicators / decide_signal / execute_trade), including
slippage. Cash earns the historical 13-week T-bill yield (^IRX), not a flat rate.
Prices are total-return adjusted (auto_adjust), so dividends are reinvested implicitly.

Every row is tagged source=backtest; live runs append source=live rows after `backtest_end`.
Writes portfolio_state*.json, daily_summary*.csv, trade_log*.csv, docs/data.json, performance_chart.png.
"""
import os
import sys
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import trading_strategy as ts
import run_cloud_strategy as rcs

START = "2010-02-11"
CAP = ts.CONFIG["starting_capital"]


def _dl(ticker, start):
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])


def load_history() -> pd.DataFrame:
    ndx, tqqq, sqqq = _dl("^NDX", "2008-01-01"), _dl("TQQQ", START), _dl("SQQQ", START)
    try:
        irx = _dl(ts.CONFIG["risk_free_ticker"], "2009-12-01")["Close"] / 100.0
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
    return df


def simulate(df: pd.DataFrame, model: str):
    p = ts.new_portfolio(CAP)
    trades, daily, prev_d = [], [], None
    ndx0, tqqq0 = float(df["close"].iloc[0]), float(df["tqqq"].iloc[0])
    p.update(benchmark_ndx_start=ndx0, benchmark_tqqq_start=tqqq0)
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
            "timestamp": f"{d.isoformat()}T16:00:00",
            "price": price,
            "sma50": float(row["sma50"]),
            "sma250": float(row["sma250"]),
            "rsi": rsi,
        }
        p, new = ts.execute_trade(p, sd, float(row["tqqq"]), float(row["sqqq"]), ts.CONFIG)
        trades.extend(new)
        p = ts.update_portfolio_value(p, float(row["tqqq"]), float(row["sqqq"]))
        daily.append(ts.build_daily_record(p, sd, float(row["tqqq"]), source="backtest"))
    last = df.iloc[-1]
    end = df.index[-1].date().isoformat()
    p.update({
        "last_signal": daily[-1]["reason"],
        "last_run_date": end,
        "last_updated": f"{end}T16:00:00",
        "backtest_end": end,
        "last_tqqq_price": float(last["tqqq"]),
        "last_sqqq_price": float(last["sqqq"]),
        "last_atr": float(last["atr"]),
        "last_rf_rate": float(last["rf"]),
    })
    return p, daily, trades


def main():
    print("1. Downloading data...")
    df = load_history()
    print(f"2. Simulating {len(df)} sessions {df.index[0].date()} -> {df.index[-1].date()}")
    p_sym, d_sym, t_sym = simulate(df, "symmetric_atr")
    p_agile, d_agile, t_agile = simulate(df, "original_agile")
    for name, p, t in (("Symmetric ATR", p_sym, t_sym), ("Original Agile", p_agile, t_agile)):
        print(f"   {name}: ${p['total_value']:,.2f} ({(p['total_value']/CAP-1)*100:+,.2f}%) | {len(t)} trade legs")

    print("3. Writing files...")
    ts.save_portfolio(p_sym, ts.CONFIG["portfolio_file"])
    ts.save_portfolio(p_agile, rcs.AGILE_FILES["portfolio_file"])
    ds = pd.DataFrame(d_sym)
    ds["total_value_agile"] = [r["total_value"] for r in d_agile]
    ds["pos_agile"] = [r["position"] for r in d_agile]
    ds.to_csv(ts.CONFIG["daily_log_file"], index=False)
    pd.DataFrame(d_agile).to_csv(rcs.AGILE_FILES["daily_log_file"], index=False)
    pd.DataFrame(t_sym).to_csv(ts.CONFIG["trade_log_file"], index=False)
    pd.DataFrame(t_agile).to_csv(rcs.AGILE_FILES["trade_log_file"], index=False)

    rcs.generate_chart()
    rcs.export_pages_data()
    print("Done.")


if __name__ == "__main__":
    main()
