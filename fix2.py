import json

with open("trade_log.csv", "a") as f:
    f.write("2026-05-05,2026-05-05T13:50:13.580477,SELL,TQQQ,2038.528169970249,67.44000244140625,137478.344759669,28019.271484375,25298.019296875,24266.80728125,76.19226168896336,Overextended: RSI 76.2 >= 75\n")

with open("daily_summary.csv", "r") as f:
    lines = f.readlines()
while lines and lines[-1].strip() == "":
    lines.pop()
if lines:
    lines.pop()
with open("daily_summary.csv", "w") as f:
    f.writelines(lines)

portfolio = {
  "position": "TQQQ_30",
  "allocation_pct": 1.0,
  "cash": 97764.87,
  "tqqq_shares": 611.5584509910747,
  "sqqq_shares": 0.0,
  "tqqq_avg_cost": 67.44000244140625,
  "sqqq_avg_cost": 0.0,
  "total_value": 142035.58,
  "starting_capital": 100000.0,
  "last_signal": "Trim lock active: RSI 47.7 below 75 but hasn't reset (need cross above 60 from below) — staying at 30%",
  "last_updated": "2026-06-09T13:50:13.580477",
  "benchmark_ndx_start": 25009.568359375,
  "benchmark_tqqq_start": 49.95909881591797,
  "last_run_date": "2026-06-09",
  "trim_active": True,
  "prev_rsi": 47.67
}

with open("portfolio_state.json", "w") as f:
    json.dump(portfolio, f, indent=2)
