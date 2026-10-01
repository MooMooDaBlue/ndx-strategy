import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("Fetching 10 years of data...")
end_date = "2026-05-07"
start_date = "2016-01-01"
ndx = yf.download("^NDX", start=start_date, end=end_date, auto_adjust=True, progress=False)
tqqq = yf.download("TQQQ", start=start_date, end=end_date, auto_adjust=True, progress=False)
sqqq = yf.download("SQQQ", start=start_date, end=end_date, auto_adjust=True, progress=False)

if isinstance(ndx.columns, pd.MultiIndex):
    ndx.columns = ndx.columns.get_level_values(0)
    tqqq.columns = tqqq.columns.get_level_values(0)
    sqqq.columns = sqqq.columns.get_level_values(0)

df = pd.DataFrame(index=ndx.index)
df['ndx_close'] = ndx['Close']
df['ndx_low'] = ndx['Low']
df['ndx_high'] = ndx['High']
df['tqqq_close'] = tqqq['Close']
df['sqqq_close'] = sqqq['Close']
df = df.dropna()

df['sma50'] = df['ndx_close'].rolling(50).mean()
df['sma250'] = df['ndx_close'].rolling(250).mean()
df['sma20'] = df['ndx_close'].rolling(20).mean()

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

# AMD Accumulation over last 4 days
df['acc_low'] = df['ndx_low'].shift(1).rolling(4).min()
# Manipulation: sweeps low but closes above
df['amd_signal'] = (df['ndx_low'] < df['acc_low']) & (df['ndx_close'] > df['acc_low'])

def run_backtest(df, mode="original"):
    cash = 100000.0
    tqqq_shares = 0.0
    sqqq_shares = 0.0
    
    portfolio_value = []
    years = []
    position = "CASH"
    
    # Protected mode state tracking
    trim_active = False    # True while waiting for RSI reset after overbought trim
    prev_rsi = 50.0        # Track previous RSI for crossing detection
    
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
        s20 = row['sma20']
        rsi = row['rsi']
        
        above_250 = price >= s250
        above_50 = price >= s50
        below_50 = price < s50
        below_250 = price < s250
        
        signal = "CASH"
        in_buffer = (position == "CASH") and above_50 and (price <= s50 * 1.01)
        
        if mode == "original":
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

        elif mode == "amd":
            # Strategy 2: AMD Re-entry + 20SMA Trim
            if above_250 and above_50:
                if in_buffer: signal = "CASH"
                elif price < s20: 
                    signal = "TQQQ_50"
                    # If AMD triggers, re-enter full!
                    if row['amd_signal']:
                        signal = "TQQQ_100"
                elif rsi >= 75: signal = "TQQQ_30"
                else: signal = "TQQQ_100"
            elif above_250 and below_50: signal = "CASH"
            elif below_250 and below_50:
                if 35 <= rsi <= 55: signal = "SQQQ"
                else: signal = "CASH"
            elif below_250 and above_50:
                if in_buffer: signal = "CASH"
                elif rsi >= 50: signal = "TQQQ_30"
                else: signal = "CASH"

        elif mode == "protected":
            # Strategy 3: Original + RSI re-entry buffer + never-scale-up guard
            # After overbought trim (RSI>=75), stay at 30% until RSI crosses
            # above 60 from below — proving momentum has fully reset.
            # Never scale UP during an active trim (30% stays 30%, not 50%).
            
            # Check if RSI has reset: crossed above 60 from below
            rsi_reset = (prev_rsi < 60) and (rsi >= 60)
            if trim_active and rsi_reset:
                trim_active = False  # Momentum confirmed recovered
            
            if above_250 and above_50:
                if in_buffer:
                    signal = "CASH"
                elif rsi >= 75:
                    signal = "TQQQ_30"
                    trim_active = True  # Activate trim lock
                elif trim_active:
                    # Still waiting for RSI reset — stay at most conservative trim
                    # Bearish divergence during trim? Stay at 30% (don't scale up)
                    signal = "TQQQ_30"
                elif row['bearish_div']:
                    signal = "TQQQ_50"
                else:
                    signal = "TQQQ_100"
            elif above_250 and below_50:
                signal = "CASH"
                trim_active = False  # Exiting to cash clears trim state
            elif below_250 and below_50:
                trim_active = False
                if 35 <= rsi <= 55: signal = "SQQQ"
                else: signal = "CASH"
            elif below_250 and above_50:
                trim_active = False
                if in_buffer: signal = "CASH"
                elif rsi >= 50: signal = "TQQQ_30"
                else: signal = "CASH"
            
            prev_rsi = rsi
                
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

print("Running Original Strategy...")
y_orig, ret_orig = run_backtest(df, mode="original")
print("Running AMD + 20SMA Strategy...")
y_amd, ret_amd = run_backtest(df, mode="amd")
print("Running Protected Strategy (RSI re-entry buffer)...")
y_prot, ret_prot = run_backtest(df, mode="protected")

res = pd.DataFrame({
    'Orig_Value': y_orig, 
    'Orig_Return_%': ret_orig, 
    'AMD_Value': y_amd, 
    'AMD_Return_%': ret_amd,
    'Protected_Value': y_prot,
    'Protected_Return_%': ret_prot,
})

tqqq_bh_val = 100000.0 / df['tqqq_close'].iloc[250] * df['tqqq_close'].iloc[-1]
print("\n" + "=" * 100)
print(res.round(2).to_string())
print("=" * 100)
print(f"\nFinal Portfolio Value (Original):    ${y_orig.iloc[-1]:,.2f}")
print(f"Final Portfolio Value (AMD 20SMA):    ${y_amd.iloc[-1]:,.2f}")
print(f"Final Portfolio Value (Protected):    ${y_prot.iloc[-1]:,.2f}")
print(f"TQQQ Buy & Hold:                     ${tqqq_bh_val:,.2f}")
print(f"\nProtected vs Original diff:          ${y_prot.iloc[-1] - y_orig.iloc[-1]:+,.2f} ({(y_prot.iloc[-1]/y_orig.iloc[-1]-1)*100:+.2f}%)")

# Show when trim_active matters most — during drawdown years
print("\n--- Protected Strategy Logic ---")
print("After RSI >= 75 trim to 30%:")
print("  - Stay at 30% while RSI is falling (don't chase the dip)")
print("  - Only re-enter 100% when RSI crosses above 60 from below")
print("  - Bearish divergence during trim stays at 30% (never scale up)")
print("  - Exit to cash / regime change clears trim state")
