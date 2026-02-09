import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time
import random

# --- SAFETY SHIELD: Check for Matplotlib ---
try:
    import matplotlib
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

st.set_page_config(page_title="Pro PCR Intel", layout="wide")

class NSEPro:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/option-chain'
        }
        self.session = requests.Session()

    def get_mock_data(self, symbol):
        prices = {"NIFTY": 25600, "BANKNIFTY": 52400, "FINNIFTY": 23800, "MIDCPNIFTY": 13200, "NIFTYNXT50": 78000}
        intervals = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25, "NIFTYNXT50": 100}
        spot = prices.get(symbol, 20000)
        interval = intervals.get(symbol, 50)
        strikes = [spot + (i * interval) for i in range(-5, 6)]
        df = pd.DataFrame({
            'Strike': strikes,
            'Call OI': [random.randint(5000, 25000) for _ in strikes],
            'Put OI': [random.randint(5000, 25000) for _ in strikes],
            'Call OI Chg': [random.randint(-500, 1000) for _ in strikes],
            'Put OI Chg': [random.randint(-500, 1000) for _ in strikes]
        })
        pcr = round(df['Put OI'].sum() / df['Call OI'].sum(), 2)
        return {"spot": spot, "atm_pcr": pcr, "pe_total": df['Put OI'].sum(), "ce_total": df['Call OI'].sum(), "table": df}, None

    def get_live_data(self, symbol):
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        try:
            self.session.get("https://www.nseindia.com", headers=self.headers, timeout=5)
            response = self.session.get(url, headers=self.headers, timeout=10)
            data = response.json()
            if 'filtered' not in data or not data['filtered']['data']:
                return None, "Market Closed"
            underlying = data['records']['underlyingValue']
            df_raw = pd.json_normalize(data['filtered']['data'])
            df_raw['diff'] = abs(df_raw['strikePrice'] - underlying)
            atm_idx = df_raw['diff'].idxmin()
            subset = df_raw.iloc[max(0, atm_idx-5):atm_idx+6].copy()
            pcr = round(subset['PE.openInterest'].sum() / subset['CE.openInterest'].sum(), 2)
            display_df = subset[['strikePrice', 'CE.openInterest', 'PE.openInterest', 'CE.changeinOpenInterest', 'PE.changeinOpenInterest']]
            display_df.columns = ['Strike', 'Call OI', 'Put OI', 'Call OI Chg', 'Put OI Chg']
            return {"spot": underlying, "atm_pcr": pcr, "pe_total": subset['PE.openInterest'].sum(), "ce_total": subset['CE.openInterest'].sum(), "table": display_df}, None
        except Exception as e:
            return None, str(e)

# --- ANALYZER LOGIC ---
def get_suggestion(pcr, history):
    if len(history) < 2:
        return "Analyzing Momentum...", "gray"
    
    prev_pcr = history.iloc[-2]['PCR']
    trend = "Rising" if pcr > prev_pcr else "Falling"
    
    if pcr > 1.3:
        return f"OVERBOUGHT ({trend} PCR). Look for reversal or trail SL.", "red"
    elif pcr > 1.1 and trend == "Rising":
        return "STRONG BULLISH. Dip buying preferred.", "green"
    elif pcr < 0.7 and trend == "Falling":
        return "STRONG BEARISH. Sell on rise preferred.", "red"
    elif pcr < 0.6:
        return "OVERSOLD. Potential bounce back zone.", "green"
    elif 0.9 <= pcr <= 1.1:
        return "NEUTRAL. Market in consolidation.", "blue"
    else:
        return f"MOMENTUM: {trend}. Wait for clarity.", "orange"

# --- APP SETUP ---
nse = NSEPro()
with st.sidebar:
    st.header("⚙️ Controls")
    sim_mode = st.toggle("Simulation Mode", value=True)
    selected_index = st.selectbox("Index", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    refresh_speed = st.slider("Refresh (Sec)", 5, 300, 10 if sim_mode else 60)

st.title("🚀 Smart PCR Intel & Suggestion Engine")

if 'history' not in st.session_state:
    st.session_state.history = {idx: pd.DataFrame(columns=['Time', 'PCR']) for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]}

placeholder = st.empty()

while True:
    with placeholder.container():
        res, err = nse.get_mock_data(selected_index) if sim_mode else nse.get_live_data(selected_index)
        if not res:
            res, _ = nse.get_mock_data(selected_index)
            status_text = "🟠 SIMULATED (Market Closed)"
        else:
            status_text = "🟢 LIVE DATA"

        curr_time = time.strftime("%H:%M:%S")
        new_entry = pd.DataFrame({'Time': [curr_time], 'PCR': [res['atm_pcr']]})
        st.session_state.history[selected_index] = pd.concat([st.session_state.history[selected_index], new_entry], ignore_index=True).tail(50)

        # --- AI SUGGESTION BOX ---
        suggestion, color = get_suggestion(res['atm_pcr'], st.session_state.history[selected_index])
        st.info(f"**AI ANALYZER:** {suggestion}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot Price", f"₹{res['spot']}")
        c2.metric("PCR", res['atm_pcr'], delta=round(res['atm_pcr']-1.0, 2))
        c3.metric("Put OI", f"{res['pe_total']:,}")
        c4.metric("Call OI", f"{res['ce_total']:,}")

        # Charts Section
        st.divider()
        col_chart, col_bars = st.columns([2, 1])
        with col_chart:
            st.subheader("PCR Momentum History")
            fig = go.Figure(go.Scatter(x=st.session_state.history[selected_index]['Time'], 
                                     y=st.session_state.history[selected_index]['PCR'],
                                     mode='lines+markers', line=dict(color='#2ecc71', width=3)))
            fig.update_layout(template="plotly_dark", height=300)
            st.plotly_chart(fig, use_container_width=True)
            
        with col_bars:
            st.subheader("Support vs Resistance")
            st.bar_chart(data=pd.DataFrame({'OI': [res['pe_total'], res['ce_total']]}, index=['Puts', 'Calls']))

        st.subheader("Live Option Chain (ATM)")
        if HAS_MATPLOTLIB:
            st.dataframe(res['table'].style.background_gradient(subset=['Put OI Chg', 'Call OI Chg'], cmap='RdYlGn'), use_container_width=True, hide_index=True)
        else:
            st.dataframe(res['table'], use_container_width=True, hide_index=True)

    time.sleep(refresh_speed)
    st.rerun()
