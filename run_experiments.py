import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("Fetching real historical data (from TQQQ inception in Feb 2010)...")
start_date_warmup = "2009-01-01"
end_date = "2026-06-11"

ndx = yf.download("^NDX", start=start_date_warmup, end=end_date, auto_adjust=True, progress=False)
vix = yf.download("^VIX", start=start_date_warmup, end=end_date, auto_adjust=True, progress=False)
tqqq = yf.download("TQQQ", start="2010-02-11", end=end_date, auto_adjust=True, progress=False)
sqqq = yf.download("SQQQ", start="2010-02-11", end=end_date, auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex):
    ndx.columns = ndx.columns.get_level_values(0)
    vix.columns = vix.columns.get_level_values(0)
    tqqq.columns = tqqq.columns.get_level_values(0)
    sqqq.columns = sqqq.columns.get_level_values(0)

df = pd.DataFrame(index=ndx.index)
df['ndx_close'] = ndx['Close']
df['ndx_high'] = ndx['High']
df['ndx_low'] = ndx['Low']
df['vix'] = vix['Close'].ffill()

# SMAs
df['sma50'] = df['ndx_close'].rolling(50).mean()
df['sma250'] = df['ndx_close'].rolling(250).mean()

# ATR
df['tr1'] = df['ndx_high'] - df['ndx_low']
df['tr2'] = abs(df['ndx_high'] - df['ndx_close'].shift())
df['tr3'] = abs(df['ndx_low'] - df['ndx_close'].shift())
df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
df['atr'] = df['tr'].rolling(14).mean()

# RSI
delta = df['ndx_close'].diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
df['rsi'] = 100 - (100 / (1 + rs))

df['price_hh'] = df['ndx_close'].rolling(10).max() > df['ndx_close'].shift(10).rolling(10).max()
df['rsi_lh'] = df['rsi'].rolling(10).max() < df['rsi'].shift(10).rolling(10).max()
df['bearish_div'] = df['price_hh'] & df['rsi_lh']
df['prev_rsi'] = df['rsi'].shift(1)

# Now merge TQQQ and SQQQ
df['tqqq_close'] = tqqq['Close']
df['sqqq_close'] = sqqq['Close']

df = df.dropna()

def backtest(df, use_atr_buffer=False, use_trailing_stop=False, use_vix=False):
    cash = 100000.0
    tqqq_shares = 0.0
    sqqq_shares = 0.0
    position = "CASH"
    trim_active = False
    
    highest_close_since_entry = 0
    
    portfolio_value = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        tqqq_price = row['tqqq_close']
        sqqq_price = row['sqqq_close']
        total_val = cash + tqqq_shares * tqqq_price + sqqq_shares * sqqq_price
        portfolio_value.append(total_val)
        
        price = row['ndx_close']
        s50 = row['sma50']
        s250 = row['sma250']
        rsi = row['rsi']
        prev_rsi_val = row['prev_rsi']
        atr = row['atr']
        vix_val = row['vix']
        
        if position.startswith("TQQQ"):
            highest_close_since_entry = max(highest_close_since_entry, price)
        else:
            highest_close_since_entry = 0
            
        above_250 = price >= s250
        above_50 = price >= s50
        below_50 = price < s50
        below_250 = price < s250
        
        rsi_reset = (prev_rsi_val < 60) and (rsi >= 60)
        if trim_active and rsi_reset:
            trim_active = False
            
        signal = "CASH"
        
        if use_atr_buffer:
            reentry_threshold = s50 + (0.5 * atr)
        else:
            reentry_threshold = s50 * 1.01
            
        in_buffer = (not position.startswith("TQQQ")) and above_50 and (price <= reentry_threshold)
        
        hit_trailing_stop = False
        if use_trailing_stop and position == "TQQQ_100":
            if price < highest_close_since_entry - (3 * atr):
                hit_trailing_stop = True
                
        if above_250 and above_50:
            if in_buffer:
                signal = "CASH"
            elif rsi >= 75:
                signal = "TQQQ_30"
                trim_active = True
            elif trim_active:
                signal = "TQQQ_30"
            elif hit_trailing_stop:
                signal = "TQQQ_50"
            elif row['bearish_div']:
                signal = "TQQQ_50"
            else:
                signal = "TQQQ_100"
                
            if use_vix and vix_val > 30 and signal == "TQQQ_100":
                signal = "TQQQ_50"
                
        elif above_250 and below_50:
            signal = "CASH"
            trim_active = False
        elif below_250 and below_50:
            trim_active = False
            if 35 <= rsi <= 55: signal = "SQQQ"
            elif rsi < 30: signal = "CASH"
            else: signal = "CASH"
        elif below_250 and above_50:
            trim_active = False
            if in_buffer: signal = "CASH"
            elif rsi >= 50: signal = "TQQQ_30"
            else: signal = "CASH"
                
        if signal != position:
            cash = total_val
            tqqq_shares = 0
            sqqq_shares = 0
            
            if signal == "TQQQ_100":
                tqqq_shares = cash / tqqq_price
                cash = 0
            elif signal == "TQQQ_50":
                invest = cash * 0.50
                tqqq_shares = invest / tqqq_price
                cash -= invest
            elif signal == "TQQQ_30":
                invest = cash * 0.30
                tqqq_shares = invest / tqqq_price
                cash -= invest
            elif signal == "SQQQ":
                sqqq_shares = cash / sqqq_price
                cash = 0
                
            position = signal
            
    return portfolio_value[-1]

res_base = backtest(df, False, False, False)
res_atr = backtest(df, True, False, False)
res_ts = backtest(df, False, True, False)
res_vix = backtest(df, False, False, True)
res_opt = backtest(df, True, True, False)
res_atr_vix = backtest(df, True, False, True)
res_all = backtest(df, True, True, True)

print(f"Baseline (60 RSI trim lock): ${res_base:,.2f}")
print(f"Baseline + ATR Buffer: ${res_atr:,.2f}")
print(f"Baseline + Trailing Stop: ${res_ts:,.2f}")
print(f"Baseline + VIX Filter: ${res_vix:,.2f}")
print(f"ATR Buffer + Trailing Stop: ${res_opt:,.2f}")
print(f"ATR Buffer + VIX Filter: ${res_atr_vix:,.2f}")
print(f"All Active (ATR Buff + TS + VIX): ${res_all:,.2f}")

tqqq_bh = 100000.0 / df['tqqq_close'].iloc[0] * df['tqqq_close'].iloc[-1]
print(f"TQQQ Buy & Hold: ${tqqq_bh:,.2f}")
