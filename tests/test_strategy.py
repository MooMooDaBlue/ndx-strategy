import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trading_strategy as ts

CFG = ts.CONFIG


def _p(**kw):
    p = {
        "position": "CASH",
        "allocation_pct": 0.0,
        "cash": 10000.0,
        "tqqq_shares": 0.0,
        "sqqq_shares": 0.0,
        "tqqq_avg_cost": 0.0,
        "sqqq_avg_cost": 0.0,
        "total_value": 10000.0,
        "starting_capital": 10000.0
    }
    p.update(kw)
    return p


def _sd(signal):
    return {
        "signal": signal,
        "reason": "test",
        "date": "2026-01-02",
        "timestamp": "2026-01-02T15:50:00",
        "price": 100.0,
        "sma50": 95.0,
        "sma250": 90.0,
        "rsi": 55.0
    }


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


def test_no_change_returns_no_trades():
    p = _p(position="TQQQ_100", cash=0.0, tqqq_shares=200.0)
    _, trades = ts.execute_trade(p, _sd("TQQQ_100"), 50.0, 20.0, CFG)
    assert trades == []


def test_interest_uses_calendar_days(monkeypatch):
    fixed = datetime(2026, 1, 6, 15, 49, 0)
    monkeypatch.setattr(ts, "now_et", lambda: fixed)
    p = _p(last_updated=(fixed - timedelta(hours=23, minutes=55)).isoformat())  # <24h, previous day
    p = ts.accrue_cash_interest(p, CFG)
    assert p["cash"] > 10000.0


def test_overbought_trims_and_locks():
    d = ts.decide_signal(110, 100, 90, 80, 2, False, "TQQQ_100", False, 70, CFG)
    assert d["signal"] == "TQQQ_30" and d["trim_active"]


def test_trim_lock_releases_on_recross():
    d = ts.decide_signal(110, 100, 90, 62, 2, False, "TQQQ_30", True, 58, CFG)
    assert d["signal"] == "TQQQ_100" and not d["trim_active"]


def test_symmetric_exit_buffer_holds():
    d = ts.decide_signal(99, 100, 90, 45, 2, False, "TQQQ_100", False, 50, CFG)
    assert d["signal"] == "TQQQ_100" and d["in_buffer_zone_exit"]


def test_original_model_exits_below_sma50():
    d = ts.decide_signal(99, 100, 90, 45, 2, False, "TQQQ_100", False, 50, CFG, model="original_agile")
    assert d["signal"] == "CASH"


def test_bear_regime_enters_sqqq_in_zone():
    d = ts.decide_signal(80, 100, 90, 45, 2, False, "CASH", False, 50, CFG)
    assert d["signal"] == "SQQQ"
