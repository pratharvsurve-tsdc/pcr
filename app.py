import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import pytz

st.set_page_config(page_title="NSE Live PCR Intel", layout="wide")

# --- 1. MARKET STATUS CHECKER ---
def is_market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Check for Weekends
    if now.weekday() >= 5:  # 5 is Saturday, 6 is Sunday
        return False, "Market is Closed (Weekend)"

    # Check for 2026 NSE Holidays
    holidays_2026 = [
        "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28",
        "2026-06-26", "2026-09-14", "2026-10-02", "2026-10-20",
        "2026-11-10", "2026-11-24", "2026-12-25"
    ]
    if now.strftime("%Y-%m-%d") in holidays_2026:
        return False, "Market is Closed (NSE Holiday)"

    # Check for Timing (9:15 AM to 3:30 PM)
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if not (market_start <= now <= market_end):
        return False, "Market is Closed (Out of Trading Hours)"
    
    return True, "🟢 Market is Live"

# --- 2. DATA FETCHER ---
class NSELive:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/option-chain'
        }
        self.session = requests.Session()

    def get_data(self, symbol):
        base_url = "https://www.nseindia.com"
        api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        try:
            self.session.get(base_url, headers=self.headers, timeout=5)
            response = self.session.get(api_url, headers=self.headers, timeout=10)
            data = response.json()
            
            underlying = data['records']['underlyingValue']
            df_raw = pd.json_normalize(data['filtered']['data'])
            df_raw['diff'] = abs(df_raw['strikePrice'] - underlying)
            atm_idx = df_raw['diff'].idxmin()
            subset = df_raw.iloc[max(0, atm_idx-5):atm_idx+6].copy()
            
            pe_oi = subset['PE.openInterest'].sum()
            ce_oi = subset['CE.openInterest'].sum()
            pcr = round(pe_oi / ce_oi, 2) if ce_oi != 0 else 0
            
            table = subset[['strikePrice', 'CE.openInterest', 'PE.openInterest', 'CE.changeinOpenInterest', 'PE.changeinOpenInterest']]
            table.columns = ['Strike', 'Call OI', 'Put OI', 'Call OI Chg', 'Put OI Chg']
            
            return {"spot": underlying, "pcr": pcr, "pe": pe_oi, "ce": ce_oi, "table": table}, None
        except Exception as e:
            return None, str(e)

# --- 3. MAIN APP INTERFACE ---
is_open, status_msg = is_market_open()

if not is_open:
    st.error(f"### 🛑 {status_msg}")
    st.image("https://img.icons8.com/color/96/closed-sign.png") # Visual indicator
    st.info("The dashboard will automatically activate once the market opens at 09:15 AM IST.")
    if st.button("Refresh Status"):
        st.rerun()
else:
    # App logic runs only if market is open
    st.title("🚀 Smart PCR Intel")
    selected_index = st.sidebar.selectbox("Index", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    
    if 'history' not in st.session_state:
        st.session_state.history = pd.DataFrame(columns=['Time', 'PCR'])

    placeholder = st.empty()
    nse = NSELive()

    while True:
        with placeholder.container():
            res, err = nse.get_data(selected_index)
            if err:
                st.warning(f"Waiting for data... ({err})")
            else:
                # Top Metrics
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Spot", f"₹{res['spot']}")
                c2.metric("PCR", res['pcr'])
                c3.metric("Put OI", f"{res['pe']:,}")
                c4.metric("Call OI", f"{res['ce']:,}")

                # PCR Chart
                st.subheader("Intraday Trend")
                new_row = pd.DataFrame({'Time': [datetime.now().strftime("%H:%M")], 'PCR': [res['pcr']]})
                st.session_state.history = pd.concat([st.session_state.history, new_row]).tail(50)
                st.line_chart(st.session_state.history.set_index('Time'))

                # Option Chain
                st.subheader("ATM Option Chain")
                st.dataframe(res['table'], hide_index=True, use_container_width=True)

        time.sleep(60)
        # Final re-check of market status before rerunning loop
        is_open, _ = is_market_open()
        if not is_open: st.rerun()
