import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("Fetching ^NDX data to build synthetic TQQQ/SQQQ for 2005-2016...")
start_date = "2005-01-01"
end_date = "2016-01-01"

ndx = yf.download("^NDX", start=start_date, end=end_date, auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex):
    ndx.columns = ndx.columns.get_level_values(0)

df = pd.DataFrame(index=ndx.index)
df['ndx_close'] = ndx['Close']

df['ndx_pct'] = df['ndx_close'].pct_change()
df['tqqq_pct'] = df['ndx_pct'] * 3.0
df['sqqq_pct'] = df['ndx_pct'] * -3.0

# Start synthetic prices at arbitrary $10.00
df['tqqq_close'] = 10.0 * (1 + df['tqqq_pct']).cumprod()
df['sqqq_close'] = 10.0 * (1 + df['sqqq_pct']).cumprod()
df['tqqq_close'] = df['tqqq_close'].fillna(10.0)
df['sqqq_close'] = df['sqqq_close'].fillna(10.0)
df = df.dropna()

df['sma50'] = df['ndx_close'].rolling(50).mean()
df['sma250'] = df['ndx_close'].rolling(250).mean()

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

def run_backtest(df):
    cash = 100000.0
    tqqq_shares = 0.0
    sqqq_shares = 0.0
    
    portfolio_value = []
    years = []
    position = "CASH"
    
    # 250 rows to account for 2005 buildup of 250-day SMA, effectively starting Jan 2006
    for i in range(250, len(df)):
        row = df.iloc[i]
        
        tqqq_price = row['tqqq_close']
        sqqq_price = row['sqqq_close']
        total_val = cash + tqqq_shares * tqqq_price + sqqq_shares * sqqq_price
        
        portfolio_value.append(total_val)
        years.append(df.index[i].year)
        
        price = row['ndx_close']
        s50 = row['sma50']
        s250 = row['sma250']
        rsi = row['rsi']
        
        above_250 = price >= s250
        above_50 = price >= s50
        below_50 = price < s50
        below_250 = price < s250
        
        signal = "CASH"
        in_buffer = (position == "CASH") and above_50 and (price <= s50 * 1.01)
        
        if above_250 and above_50:
            if in_buffer: signal = "CASH"
            elif rsi >= 75: signal = "TQQQ_30"
            elif row['bearish_div']: signal = "TQQQ_50"
            else: signal = "TQQQ_100"
        elif above_250 and below_50: signal = "CASH"
        elif below_250 and below_50:
            if 35 <= rsi <= 55: signal = "SQQQ"
            else: signal = "CASH"
        elif below_250 and above_50:
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
            
    res_df = pd.DataFrame({'Year': years, 'Value': portfolio_value})
    yearly = res_df.groupby('Year')['Value'].last()
    yearly_ret = yearly.pct_change() * 100
    yearly_ret.iloc[0] = (yearly.iloc[0] / 100000.0 - 1) * 100
    return yearly, yearly_ret

y_orig, ret_orig = run_backtest(df)

res = pd.DataFrame({
    'Orig_Value': y_orig, 
    'Orig_Return_%': ret_orig, 
})

# Calculate synthetic TQQQ buy & hold from Jan 2006 to end of 2015
tqqq_bh_val = 100000.0 / df['tqqq_close'].iloc[250] * df['tqqq_close'].iloc[-1]

print(res.round(2).to_string())
print(f"\nFinal Portfolio Value (Original): ${y_orig.iloc[-1]:,.2f}")
print(f"Synthetic TQQQ Buy & Hold: ${tqqq_bh_val:,.2f}")
