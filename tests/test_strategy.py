"""Offline unit tests — no test touches the network or the committed state/log files."""
import os
import sys
import json
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trading_strategy as ts
import run_cloud_strategy as rcs
import web_dashboard as wd

CFG = dict(ts.CONFIG, slippage_bps=0.0)


def _p(**kw):
    p = ts.new_portfolio(10000.0)
    p.update(kw)
    return p


def _sd(signal):
    return {
        "signal": signal,
        "reason": "test",
        "date": "2026-01-02",
        "timestamp": "2026-01-02T16:00:00",
        "price": 100.0,
        "sma50": 95.0,
        "sma250": 90.0,
        "rsi": 55.0
    }


def _ohlc(closes, start="2025-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                         "Volume": 0.0, "Dividends": 0.0, "Stock Splits": 0.0})


# ── Execution ────────────────────────────────
def test_cash_to_full_tqqq_is_single_buy():
    p, trades = ts.execute_trade(_p(), _sd("TQQQ_100"), 50.0, 20.0, CFG)
    assert [t["action"] for t in trades] == ["BUY"]
    assert abs(p["tqqq_shares"] - 200) < 1e-6 and abs(p["cash"]) < 1e-6
    assert p["allocation_pct"] == 1.0


def test_full_to_30_is_trim():
    p = _p(position="TQQQ_100", cash=0.0, tqqq_shares=200.0, tqqq_avg_cost=50.0)
    p, trades = ts.execute_trade(p, _sd("TQQQ_30"), 50.0, 20.0, CFG)
    assert [t["action"] for t in trades] == ["TRIM"]
    assert abs(p["tqqq_shares"] - 60) < 1e-6 and abs(p["cash"] - 7000) < 1e-6
    assert p["allocation_pct"] == 0.3


def test_sqqq_to_tqqq_logs_both_legs_and_conserves_value():
    p = _p(position="SQQQ", cash=0.0, sqqq_shares=500.0, sqqq_avg_cost=20.0)
    p, trades = ts.execute_trade(p, _sd("TQQQ_100"), 50.0, 20.0, CFG)
    assert [t["action"] for t in trades] == ["SELL", "BUY"]
    assert abs(p["total_value"] - 10000) < 1e-6


def test_slippage_charged_on_every_leg():
    cfg = dict(ts.CONFIG, slippage_bps=10.0)
    p = _p(position="SQQQ", cash=0.0, sqqq_shares=500.0, sqqq_avg_cost=20.0)
    p, trades = ts.execute_trade(p, _sd("TQQQ_100"), 50.0, 20.0, cfg)
    assert trades[0]["price"] == pytest.approx(20.0 * 0.999) and trades[1]["price"] == pytest.approx(50.0 * 1.001)
    # Lost ~10 bps on the sell and ~10 bps on the buy
    assert p["total_value"] == pytest.approx(10000 * 0.999 / 1.001, rel=1e-9)
    assert all(t["cost"] > 0 for t in trades)


def test_no_change_returns_no_trades():
    p = _p(position="TQQQ_100", cash=0.0, tqqq_shares=200.0)
    _, trades = ts.execute_trade(p, _sd("TQQQ_100"), 50.0, 20.0, CFG)
    assert trades == []


# ── Interest / corporate actions ─────────────
def test_interest_uses_calendar_days(monkeypatch):
    fixed = datetime(2026, 1, 6, 16, 49, 0)
    monkeypatch.setattr(ts, "now_et", lambda: fixed)
    p = _p(last_updated=(fixed - timedelta(hours=23, minutes=55)).isoformat())  # <24h, previous day
    p = ts.accrue_cash_interest(p, 0.04)
    assert p["cash"] == pytest.approx(10000 * (1 + 0.04 / 365))


def test_reverse_split_adjusts_shares_not_value():
    df = _ohlc([10.0, 10.0, 50.0])  # 1:5 reverse split on the last bar (prices are split-adjusted)
    df.iloc[2, df.columns.get_loc("Stock Splits")] = 0.2
    p = _p(position="SQQQ", cash=0.0, sqqq_shares=1000.0, sqqq_avg_cost=10.0)
    since = df.index[0].date().isoformat()
    events = ts.apply_corporate_actions(p, {"sqqq": df}, since, df.index[2].date())
    assert len(events) == 1
    assert p["sqqq_shares"] == pytest.approx(200.0) and p["sqqq_avg_cost"] == pytest.approx(50.0)
    assert ts.update_portfolio_value(p, 0, 50.0)["total_value"] == pytest.approx(10000.0)


def test_dividend_credits_cash_once():
    df = _ohlc([50.0, 50.0, 50.0])
    df.iloc[1, df.columns.get_loc("Dividends")] = 0.10
    p = _p(position="TQQQ_100", cash=0.0, tqqq_shares=200.0)
    ts.apply_corporate_actions(p, {"tqqq": df}, df.index[0].date().isoformat(), df.index[2].date())
    assert p["cash"] == pytest.approx(20.0)
    # A later run (since = after the ex-date) must not credit it again
    ts.apply_corporate_actions(p, {"tqqq": df}, df.index[1].date().isoformat(), df.index[2].date())
    assert p["cash"] == pytest.approx(20.0)


# ── Signal engine ────────────────────────────
def test_overbought_trims_and_locks():
    d = ts.decide_signal(110, 100, 90, 80, 2, False, "TQQQ_100", False, 70, CFG)
    assert d["signal"] == "TQQQ_30" and d["trim_active"]


def test_trim_lock_releases_on_recross():
    d = ts.decide_signal(110, 100, 90, 62, 2, False, "TQQQ_30", True, 58, CFG)
    assert d["signal"] == "TQQQ_100" and not d["trim_active"]


def test_trim_lock_holds_without_recross():
    d = ts.decide_signal(110, 100, 90, 65, 2, False, "TQQQ_30", True, 64, CFG)
    assert d["signal"] == "TQQQ_30" and d["trim_active"]


def test_bearish_divergence_trims_to_50():
    d = ts.decide_signal(110, 100, 90, 60, 2, True, "TQQQ_100", False, 60, CFG)
    assert d["signal"] == "TQQQ_50"


def test_symmetric_exit_buffer_holds():
    d = ts.decide_signal(99, 100, 90, 45, 2, False, "TQQQ_100", False, 50, CFG)
    assert d["signal"] == "TQQQ_100" and d["in_buffer_zone_exit"]


def test_symmetric_exit_buffer_holds_below_sma250():
    # Below both SMAs but above SMA50 - ATR: the buffer applies in the bear regime too
    d = ts.decide_signal(99, 100, 105, 45, 2, False, "TQQQ_100", False, 50, CFG)
    assert d["signal"] == "TQQQ_100" and d["in_buffer_zone_exit"]


def test_exit_below_buffer_floor():
    d = ts.decide_signal(97, 100, 90, 45, 2, False, "TQQQ_100", False, 50, CFG)
    assert d["signal"] == "CASH"


def test_original_model_exits_below_sma50():
    d = ts.decide_signal(99, 100, 90, 45, 2, False, "TQQQ_100", False, 50, CFG, model="original_agile")
    assert d["signal"] == "CASH"


def test_entry_buffer_waits_in_cash():
    d = ts.decide_signal(101, 100, 90, 55, 2, False, "CASH", False, 50, CFG)
    assert d["signal"] == "CASH" and d["in_buffer_zone_entry"]


def test_bear_regime_enters_sqqq_in_zone():
    d = ts.decide_signal(80, 100, 90, 45, 2, False, "CASH", False, 50, CFG)
    assert d["signal"] == "SQQQ"


def test_sqqq_exits_when_oversold():
    d = ts.decide_signal(80, 100, 90, 25, 2, False, "SQQQ", False, 30, CFG)
    assert d["signal"] == "CASH"


def test_recovery_below_sma250_is_cautious_30():
    assert ts.decide_signal(110, 100, 120, 55, 2, False, "CASH", False, 50, CFG)["signal"] == "TQQQ_30"
    assert ts.decide_signal(110, 100, 120, 45, 2, False, "CASH", False, 50, CFG)["signal"] == "CASH"


def test_determine_signal_uses_previous_bar_rsi(monkeypatch):
    seen = {}
    real = ts.decide_signal

    def spy(*args, **kw):
        seen["prev_rsi"] = args[8]
        return real(*args, **kw)

    monkeypatch.setattr(ts, "decide_signal", spy)
    rng = np.random.default_rng(0)
    df = _ohlc(list(100 + np.cumsum(rng.normal(0.1, 1, 400))))
    ts.determine_signal(df, CFG)
    rsi = ts.compute_indicators(df, CFG)["rsi"]
    assert seen["prev_rsi"] == pytest.approx(float(rsi.iloc[-2]))


def test_rsi_is_100_without_losses():
    assert ts.calculate_rsi(pd.Series(np.arange(1.0, 40.0))).iloc[-1] == 100.0


# ── Data freshness ───────────────────────────
class _MockTicker:
    def __init__(self, bars):
        self._bars = bars

    def history(self, **kw):
        return self._bars


def test_ensure_today_bar_builds_from_todays_intraday(monkeypatch):
    today = date(2026, 10, 5)
    idx = pd.date_range("2026-10-05 09:30", periods=3, freq="5min", tz=ts.ET)
    bars = pd.DataFrame({"Open": [81, 82, 83], "High": [82, 84, 83.5], "Low": [80.5, 81, 82],
                         "Close": [82, 83, 83.12], "Volume": [1, 1, 1]}, index=idx, dtype=float)
    monkeypatch.setattr(ts.yf, "Ticker", lambda t: _MockTicker(bars))
    out = ts._ensure_today_bar(_ohlc([80.0], "2026-10-02"), "TQQQ", today)
    assert pd.Timestamp(out.index[-1]).date() == today
    last = out.iloc[-1]
    assert (last["Open"], last["High"], last["Low"], last["Close"]) == (81, 84, 80.5, 83.12)


def test_ensure_today_bar_refuses_stale_intraday(monkeypatch):
    idx = pd.date_range("2026-10-02 15:50", periods=2, freq="5min", tz=ts.ET)
    bars = pd.DataFrame({"Open": 80.0, "High": 80.0, "Low": 80.0, "Close": 80.0, "Volume": 1.0}, index=idx)
    monkeypatch.setattr(ts.yf, "Ticker", lambda t: _MockTicker(bars))
    stale = _ohlc([80.0], "2026-10-02")
    out = ts._ensure_today_bar(stale, "TQQQ", date(2026, 10, 5))
    assert len(out) == 1  # nothing fabricated → fetch_market_data's freshness check will fail


# ── CSV logging ──────────────────────────────
def test_upsert_is_idempotent_and_keeps_new_columns(tmp_path):
    f = str(tmp_path / "daily.csv")
    ts.upsert_rows(f, [{"date": "2026-01-02", "total_value": 1.0}], "2026-01-02")
    ts.upsert_rows(f, [{"date": "2026-01-05", "total_value": 2.0, "extra": "x"}], "2026-01-05")
    ts.upsert_rows(f, [{"date": "2026-01-05", "total_value": 3.0, "extra": "y"}], "2026-01-05")
    df = pd.read_csv(f)
    assert df["date"].tolist() == ["2026-01-02", "2026-01-05"]
    assert df["total_value"].tolist() == [1.0, 3.0] and df["extra"].iloc[-1] == "y"


def test_run_strategy_end_to_end(tmp_path, monkeypatch):
    rng = np.random.default_rng(1)
    ndx = _ohlc(list(1000 + np.cumsum(rng.normal(1, 5, 400))))
    today = ndx.index[-1].to_pydatetime().replace(hour=16, minute=30)
    monkeypatch.setattr(ts, "now_et", lambda: today)
    etf = _ohlc([50.0] * 400)
    files = dict(portfolio_file=str(tmp_path / "p.json"), trade_log_file=str(tmp_path / "t.csv"),
                 daily_log_file=str(tmp_path / "d.csv"))
    md = ts.MarketData(ndx, etf, etf, 0.04)
    assert ts.run_strategy(market_data=md, notify=False, extra_daily_fields={"total_value_agile": 1}, **files)
    assert not ts.run_strategy(market_data=md, notify=False, **files)  # same day → skipped
    state = json.load(open(files["portfolio_file"]))
    assert state["last_run_date"] == today.date().isoformat() and state["live_since"] == state["last_run_date"]
    daily = pd.read_csv(files["daily_log_file"])
    assert len(daily) == 1 and daily["source"].iloc[0] == "live" and "total_value_agile" in daily


# ── Cloud runner ─────────────────────────────
@pytest.mark.parametrize("hh,mm,expected", [(15, 50, False), (16, 0, True), (23, 59, True), (9, 0, False)])
def test_execution_window_is_after_close(monkeypatch, hh, mm, expected):
    monkeypatch.delenv("FORCE_RUN", raising=False)
    monkeypatch.setattr(ts, "now_et", lambda: datetime(2026, 10, 5, hh, mm))
    assert rcs.in_execution_window() is expected


def test_already_ran_requires_both_models(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "now_et", lambda: datetime(2026, 10, 5, 17, 0))
    main_f, agile_f = tmp_path / "m.json", tmp_path / "a.json"
    monkeypatch.setitem(ts.CONFIG, "portfolio_file", str(main_f))
    monkeypatch.setitem(rcs.AGILE_FILES, "portfolio_file", str(agile_f))
    main_f.write_text(json.dumps({"last_run_date": "2026-10-05"}))
    assert not rcs._already_ran_today()  # agile state missing
    agile_f.write_text(json.dumps({"last_run_date": "2026-10-02"}))
    assert not rcs._already_ran_today()
    agile_f.write_text(json.dumps({"last_run_date": "2026-10-05"}))
    assert rcs._already_ran_today()


def test_trading_day_calendar():
    assert ts.is_trading_day(date(2026, 10, 5))
    assert not ts.is_trading_day(date(2026, 10, 3))   # Saturday
    assert not ts.is_trading_day(date(2026, 12, 25))  # Christmas


# ── Dashboard ────────────────────────────────
def test_build_quotes_regular_and_after_hours():
    syms = [q["symbol"] for q in wd.TOP_20_NDX]
    didx = pd.to_datetime(["2026-10-02", "2026-10-05"])
    daily = pd.DataFrame({s: [100.0, 102.0] for s in syms}, index=didx)
    iidx = pd.DatetimeIndex([pd.Timestamp("2026-10-05 15:55", tz=ts.ET), pd.Timestamp("2026-10-05 17:30", tz=ts.ET)])
    intraday = pd.DataFrame({s: [102.0, 103.02] for s in syms}, index=iidx)
    quotes = wd.build_quotes(daily, intraday)
    assert len(quotes) == 20 and [q["weight"] for q in quotes] == sorted([q["weight"] for q in quotes], reverse=True)
    q = quotes[0]
    assert q["price"] == 102.0 and q["change_pct"] == 2.0
    assert q["ext_type"] == "AH" and q["ext_change_pct"] == 1.0


def test_build_quotes_no_extended_during_session():
    syms = [q["symbol"] for q in wd.TOP_20_NDX]
    daily = pd.DataFrame({s: [100.0, 101.0] for s in syms}, index=pd.to_datetime(["2026-10-02", "2026-10-05"]))
    intraday = pd.DataFrame({s: [101.0] for s in syms},
                            index=pd.DatetimeIndex([pd.Timestamp("2026-10-05 11:00", tz=ts.ET)]))
    assert all(q["ext_type"] is None for q in wd.build_quotes(daily, intraday))


def test_stats_never_invent_prices():
    stats = wd._compute_stats(ts.new_portfolio(10000.0), [], [])
    assert stats["tqqq_price"] is None and stats["sqqq_price"] is None
