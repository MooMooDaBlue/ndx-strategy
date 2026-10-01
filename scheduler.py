"""
Windows Auto-Scheduler for NDX Strategy
========================================
This script runs trading_strategy.py every trading day at 3:50pm EST.
Run this ONCE and leave it running in the background (or set it up as a
Windows Task Scheduler task — see README.md for instructions).

Just double-click this file or run: python scheduler.py
"""

import schedule
import time
import subprocess
import sys
import os
from datetime import datetime, date, timedelta
import holidays


# Path to your strategy script
STRATEGY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_strategy.py")

# ─────────────────────────────────────────────
# NYSE HOLIDAY CALENDAR
# ─────────────────────────────────────────────
def _easter_date(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_nyse_holiday(check_date: date) -> bool:
    """
    Check if a date is an NYSE holiday.
    More accurate than holidays.US() which includes Columbus Day and
    Veterans Day (NYSE is open) and misses Good Friday (NYSE is closed).
    """
    # Start with US federal holidays
    us_holidays = holidays.US(years=check_date.year)

    # Holidays where NYSE IS OPEN (remove from skip list)
    nyse_open = {"Columbus Day", "Veterans Day",
                 "Indigenous Peoples' Day", "Columbus Day (Observed)",
                 "Veterans Day (Observed)"}

    # Check if it's a federal holiday that NYSE observes
    if check_date in us_holidays:
        holiday_name = us_holidays.get(check_date)
        if holiday_name in nyse_open:
            return False  # NYSE is open on this federal holiday
        return True  # NYSE is closed on this federal holiday

    # Good Friday: NYSE is closed (not a federal holiday)
    easter = _easter_date(check_date.year)
    good_friday = easter - timedelta(days=2)
    if check_date == good_friday:
        return True

    return False


def is_trading_day() -> bool:
    """Returns True if today is a weekday and not an NYSE market holiday."""
    today = datetime.now().date()
    if today.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if is_nyse_holiday(today):
        print(f"  [{datetime.now().strftime('%H:%M')}] Today is an NYSE market holiday — skipping.")
        return False
    return True


# ─────────────────────────────────────────────
# MARKET HOURS SAFETY CHECK
# ─────────────────────────────────────────────
def is_within_execution_window() -> bool:
    """
    Safety check: only execute if current time is near the scheduled run.
    Prevents accidental runs if the scheduler restarts at the wrong time.
    Allows execution between 1:30 PM and 2:30 PM Mountain Time.
    """
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    window_start = 13 * 60 + 30   # 1:30 PM MT
    window_end   = 14 * 60 + 30   # 2:30 PM MT
    return window_start <= current_minutes <= window_end


def run_strategy():
    """Execute the trading strategy script."""
    now = datetime.now()
    print(f"\n{'='*60}")
    print(f"  Scheduler trigger: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    if not is_trading_day():
        print(f"  Not a trading day — skipping execution.")
        return

    if not is_within_execution_window():
        print(f"  Outside execution window (1:30-2:30 PM MT) — skipping.")
        print(f"  Current time: {now.strftime('%H:%M')} MT")
        return

    print(f"  Running strategy...")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            [sys.executable, STRATEGY_SCRIPT],
            capture_output=False,
            text=True
        )
        if result.returncode != 0:
            print(f"  ⚠️  Strategy exited with code {result.returncode}")
        else:
            print(f"\n  ✅ Strategy run complete.")
    except Exception as e:
        print(f"  ❌ Failed to run strategy: {e}")


def main():
    print("=" * 60)
    print("  NDX Strategy Scheduler — Started")
    print(f"  Strategy will run daily at 1:50 PM MT (3:50 PM EST)")
    print(f"  Script path: {STRATEGY_SCRIPT}")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    # Schedule for 3:50 PM EST = 1:50 PM Mountain Time
    # This uses your LOCAL system time (Mountain Time / UTC-7).
    # If you move to a different timezone, adjust accordingly.
    schedule.every().day.at("13:50").do(run_strategy)

    print(f"\n  Next run scheduled for 1:50 PM MT (3:50 PM EST) today (if trading day).")
    print(f"  Current time: {datetime.now().strftime('%H:%M:%S')}\n")

    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds


if __name__ == "__main__":
    main()
