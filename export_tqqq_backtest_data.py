import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("Fetching historical data from Yahoo Finance (with 2009 warmup for SMAs)...")
start_date_warmup = "2009-01-01"

# Fetching data up to current / latest available date
ndx = yf.download("^NDX", start=start_date_warmup, auto_adjust=True, progress=False)
vix = yf.download("^VIX", start=start_date_warmup, auto_adjust=True, progress=False)
tqqq = yf.download("TQQQ", start="2010-02-11", auto_adjust=True, progress=False)
sqqq = yf.download("SQQQ", start="2010-02-11", auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex):
    ndx.columns = ndx.columns.get_level_values(0)
    vix.columns = vix.columns.get_level_values(0)
    tqqq.columns = tqqq.columns.get_level_values(0)
    sqqq.columns = sqqq.columns.get_level_values(0)

df = pd.DataFrame(index=ndx.index)
df['NDX_Close'] = ndx['Close']
df['NDX_High'] = ndx['High']
df['NDX_Low'] = ndx['Low']
df['VIX_Close'] = vix['Close'].ffill()

# SMAs
df['SMA50'] = df['NDX_Close'].rolling(50).mean()
df['SMA250'] = df['NDX_Close'].rolling(250).mean()

# ATR
df['tr1'] = df['NDX_High'] - df['NDX_Low']
df['tr2'] = abs(df['NDX_High'] - df['NDX_Close'].shift())
df['tr3'] = abs(df['NDX_Low'] - df['NDX_Close'].shift())
df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
df['ATR'] = df['tr'].rolling(14).mean()

# RSI
delta = df['NDX_Close'].diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
df['RSI'] = 100 - (100 / (1 + rs))

# Bearish Divergence
df['price_hh'] = df['NDX_Close'].rolling(10).max() > df['NDX_Close'].shift(10).rolling(10).max()
df['rsi_lh'] = df['RSI'].rolling(10).max() < df['RSI'].shift(10).rolling(10).max()
df['Bearish_Div'] = df['price_hh'] & df['rsi_lh']
df['prev_rsi'] = df['RSI'].shift(1)

# Merge TQQQ and SQQQ (this drops dates prior to TQQQ inception on 2010-02-11)
df['TQQQ_Close'] = tqqq['Close']
df['SQQQ_Close'] = sqqq['Close']

df = df.dropna(subset=['NDX_Close', 'SMA50', 'SMA250', 'ATR', 'RSI', 'TQQQ_Close', 'SQQQ_Close'])
# Clean up temporary calculation columns
df = df.drop(columns=['tr1', 'tr2', 'tr3', 'tr', 'price_hh', 'rsi_lh'])

def run_backtest_series(df, use_atr_buffer=False, use_trailing_stop=False, use_vix=False, prefix="Baseline"):
    cash = 100000.0
    tqqq_shares = 0.0
    sqqq_shares = 0.0
    position = "CASH"
    trim_active = False
    
    highest_close_since_entry = 0
    
    portfolio_values = []
    positions = []
    cash_list = []
    tqqq_shares_list = []
    sqqq_shares_list = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        tqqq_price = row['TQQQ_Close']
        sqqq_price = row['SQQQ_Close']
        total_val = cash + tqqq_shares * tqqq_price + sqqq_shares * sqqq_price
        
        portfolio_values.append(total_val)
        positions.append(position)
        cash_list.append(cash)
        tqqq_shares_list.append(tqqq_shares)
        sqqq_shares_list.append(sqqq_shares)
        
        price = row['NDX_Close']
        s50 = row['SMA50']
        s250 = row['SMA250']
        rsi = row['RSI']
        prev_rsi_val = row['prev_rsi']
        atr = row['ATR']
        vix_val = row['VIX_Close']
        
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
            elif row['Bearish_Div']:
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
            
    df[f"{prefix}_Value"] = portfolio_values
    df[f"{prefix}_Position"] = positions
    if prefix == "All_Active":
        df["All_Active_Cash"] = cash_list
        df["All_Active_TQQQ_Shares"] = tqqq_shares_list
        df["All_Active_SQQQ_Shares"] = sqqq_shares_list

print("Running backtest variations across all historical dates...")
run_backtest_series(df, False, False, False, prefix="Baseline")
run_backtest_series(df, True, False, False, prefix="ATR_Buffer")
run_backtest_series(df, False, True, False, prefix="Trailing_Stop")
run_backtest_series(df, False, False, True, prefix="VIX_Filter")
run_backtest_series(df, True, True, False, prefix="ATR_TS")
run_backtest_series(df, True, False, True, prefix="ATR_VIX")
run_backtest_series(df, True, True, True, prefix="All_Active")

# Add Buy & Hold benchmarks
df['TQQQ_BuyHold_Value'] = 100000.0 / df['TQQQ_Close'].iloc[0] * df['TQQQ_Close']
df['NDX_BuyHold_Value'] = 100000.0 / df['NDX_Close'].iloc[0] * df['NDX_Close']

# Drop temp column
df = df.drop(columns=['prev_rsi'])

output_filename = "tqqq_backtest_data_since_inception.csv"
df.to_csv(output_filename)

print(f"\nSuccessfully exported {len(df)} daily records from {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}.")
print(f"File saved to: {output_filename}")
print(f"\nFinal Strategy Summary (Starting capital: $100,000):")
print(f"  Baseline (60 RSI trim lock):       ${df['Baseline_Value'].iloc[-1]:,.2f}")
print(f"  All Active (ATR Buff + TS + VIX):  ${df['All_Active_Value'].iloc[-1]:,.2f}")
print(f"  TQQQ Buy & Hold:                   ${df['TQQQ_BuyHold_Value'].iloc[-1]:,.2f}")
print(f"  NDX Buy & Hold:                    ${df['NDX_BuyHold_Value'].iloc[-1]:,.2f}")
