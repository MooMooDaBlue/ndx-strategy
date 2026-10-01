import yfinance as yf
import pandas as pd
ndx = yf.download("^NDX", period="5d")
print("NDX\n", ndx)
tqqq = yf.download("TQQQ", period="5d")
print("TQQQ\n", tqqq)
