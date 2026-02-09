import streamlit as st
import pandas as pd
from curl_cffi import requests
import time
import random
from datetime import datetime
import pytz

# --- 1. CONFIG & STYLING ---
st.set_page_config(page_title="NSE Bulletproof PCR", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stMetric { background-color: #1f2937; padding: 15px; border-radius: 10px; border: 1px solid #374151; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ADVANCED STEALTH ENGINE ---
class NSEAntiBlockFetcher:
    def __init__(self):
        self.session = requests.Session(impersonate="chrome120")
        self.base_url = "https://www.nseindia.com"
        # Common Chrome User-Agents to rotate
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]

    def fetch_data(self, symbol):
        try:
            # Update User-Agent randomly for each full fetch cycle
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.nseindia.com/option-chain",
            }

            # --- THE 3-STEP HANDSHAKE ---
            # Step 1: Visit Home Page
            self.session.get(self.base_url, headers=headers, timeout=10)
            
            # Step 2: Human-like delay (NSE detects instant API calls as bots)
            time.sleep(random.uniform(2.0, 3.5)) 
            
            # Step 3: Call the API
            api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            response = self.session.get(api_url, headers=headers, timeout=15)
            
            if response.status_code == 401 or response.status_code == 403:
                return None, "NSE denied access. Your IP is likely temporarily blocked."

            data = response.json()
            
            if 'records' not in data:
                return None, "Throttled: NSE sent an empty response. Try a Mobile Hotspot."

            # --- DATA PROCESSING ---
            underlying = data['records']['underlyingValue']
            df = pd.json_normalize(data['filtered']['data'])
            
            pe_oi = df['PE.openInterest'].sum()
            ce_oi = df['CE.openInterest'].sum()
            pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else 0

            # Table Logic
            df['diff'] = abs(df['strikePrice'] - underlying)
            atm_idx = df['diff'].idxmin()
            subset = df.iloc[max(0, atm_idx-5):atm_idx+6].copy()
            
            table = subset[['strikePrice', 'CE.openInterest', 'PE.openInterest', 'CE.changeinOpenInterest', 'PE.changeinOpenInterest']]
            table.columns = ['Strike', 'Call OI', 'Put OI', 'Call Chg', 'Put Chg']

            return {"spot": underlying, "pcr": pcr, "pe": pe_oi, "ce": ce_oi, "table": table}, None

        except Exception as e:
            return None, f"Network Error: {str(e)}"

# --- 3. UI INTERFACE ---
st.title("🛡️ NSE Pro PCR Intel")

with st.sidebar:
    st.header("Dashboard Settings")
    selected_index = st.selectbox("Market Index", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    # Increase refresh time to avoid getting blocked again
    refresh_rate = st.slider("Refresh Rate (Seconds)", 60, 300, 120) 
    st.info("💡 Note: Refreshing too fast (<60s) will lead to IP blocking.")

if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Time', 'PCR'])

placeholder = st.empty()
fetcher = NSEAntiBlockFetcher()

# --- 4. DATA LOOP ---
while True:
    with st.spinner("Executing Stealth Handshake..."):
        res, err = fetcher.fetch_data(selected_index)
    
    if not err:
        curr_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%H:%M:%S")
        with placeholder.container():
            st.caption(f"Last Sync: {curr_time} | Connection: Stable")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Spot", f"₹{res['spot']:,}")
            m2.metric("PCR", res['pcr'], delta=round(res['pcr']-1.0, 2))
            m3.metric("Put OI", f"{res['pe']:,}")
            m4.metric("Call OI", f"{res['ce']:,}")

            new_row = pd.DataFrame({'Time': [curr_time], 'PCR': [res['pcr']]})
            st.session_state.history = pd.concat([st.session_state.history, new_row]).tail(50)
            st.line_chart(st.session_state.history.set_index('Time'))
            st.dataframe(res['table'], hide_index=True, use_container_width=True)
    else:
        st.error(f"⚠️ {err}")
        st.warning("REMEDY: 1. Turn off Wi-Fi. 2. Use Mobile Hotspot. 3. Set refresh to 120s.")
        time.sleep(20)

    time.sleep(refresh_rate)
    st.rerun()
