"""
One-shot backfill runner for a missed trading day (July 13, 2026).
Patches date.today() and datetime.now() via monkeypatching the trading_strategy module
AFTER import, so the strategy logs everything under the correct date.
"""
import datetime
import sys
import os

TARGET_DATE_STR = "2026-07-13"
TARGET_DATE = datetime.date(2026, 7, 13)
TARGET_DATETIME = datetime.datetime(2026, 7, 13, 13, 50, 15)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import strategy first (uses datetime at module level only for logging setup)
import trading_strategy

# Now patch the datetime references INSIDE the trading_strategy module
# by replacing the date and datetime objects it uses
import unittest.mock as mock

# We need to patch 'date.today' and 'datetime.now' as used in trading_strategy
# The module uses: datetime.now() and date.today() directly

with mock.patch("trading_strategy.datetime") as mock_dt, \
     mock.patch("trading_strategy.date") as mock_date:

    # Make datetime.now() return our target
    mock_dt.now.return_value = TARGET_DATETIME
    mock_dt.fromisoformat.side_effect = datetime.datetime.fromisoformat
    mock_dt.isoformat = datetime.datetime.isoformat

    # Make date.today() return our target date
    mock_date.today.return_value = TARGET_DATE
    mock_date.fromisoformat.side_effect = datetime.date.fromisoformat

    trading_strategy.run_strategy()
