import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time
import random
import base64

# --- SAFETY SHIELD: Matplotlib ---
try:
    import matplotlib
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

st.set_page_config(page_title="Pro PCR Intel + Alerts", layout="wide")

# --- AUDIO ALERT FUNCTION ---
def play_sound():
    # Simple beep sound using base64 encoded audio
    audio_html = """
    <audio autoplay>
      <source src="https://www.soundjay.com/buttons/beep-01a.mp3" type="audio/mpeg">
    </audio>
    """
    st.components.v1.html(audio_html, height=0)

class NSEPro:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/option-chain'
        }
        self.session = requests.Session()

    def get_mock_data(self, symbol):
        prices = {"NIFTY": 23500, "BANKNIFTY": 51200, "FINNIFTY": 23200, "MIDCPNIFTY": 12800}
        spot = prices.get(symbol, 20000)
        interval = 50 if symbol != "BANKNIFTY" else 100
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
            if 'filtered' not in data: return None, "Market Closed"
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

# --- APP SETUP ---
nse = NSEPro()
with st.sidebar:
    st.header("⚙️ Controls")
    sim_mode = st.toggle("Simulation Mode", value=True)
    enable_audio = st.toggle("Enable Audio Alerts", value=True)
    selected_index = st.selectbox("Index", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    refresh_speed = st.slider("Refresh (Sec)", 5, 300, 10 if sim_mode else 60)

st.title("🛡️ Pro Option Intel: Signal Desk")

if 'history' not in st.session_state:
    st.session_state.history = {idx: pd.DataFrame(columns=['Time', 'PCR']) for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]}
if 'last_signal' not in st.session_state:
    st.session_state.last_signal = None

placeholder = st.empty()

while True:
    with placeholder.container():
        res, err = nse.get_mock_data(selected_index) if sim_mode else nse.get_live_data(selected_index)
        if not res:
            res, _ = nse.get_mock_data(selected_index)
            st.caption("Using Offline Simulation Data")

        curr_time = time.strftime("%H:%M:%S")
        pcr = res['atm_pcr']
        new_entry = pd.DataFrame({'Time': [curr_time], 'PCR': [pcr]})
        st.session_state.history[selected_index] = pd.concat([st.session_state.history[selected_index], new_entry], ignore_index=True).tail(50)

        # --- SIGNAL ANALYZER ---
        signal = "NEUTRAL"
        if pcr >= 1.4: signal = "STRONG BULLISH (Overbought)"
        elif pcr <= 0.6: signal = "STRONG BEARISH (Oversold)"
        elif pcr > 1.15: signal = "BULLISH BIAS"
        elif pcr < 0.85: signal = "BEARISH BIAS"

        # --- ALERT TRIGGER ---
        if signal != st.session_state.last_signal and "STRONG" in signal:
            if enable_audio: play_sound()
            st.toast(f"🚨 SIGNAL ALERT: {signal}", icon="🔥")
            st.session_state.last_signal = signal

        # Display Signal Box
        sig_color = "green" if "BULLISH" in signal else "red" if "BEARISH" in signal else "blue"
        st.markdown(f"""<div style="padding:15px; border-radius:10px; background-color:{sig_color}; color:white; text-align:center;">
            <h2 style="margin:0;">{signal}</h2>
            <p style="margin:0;">PCR: {pcr} | Momentum: {"Rising" if len(st.session_state.history[selected_index]) > 1 and pcr > st.session_state.history[selected_index].iloc[-2]['PCR'] else "Falling"}</p>
        </div>""", unsafe_allow_html=True)

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot Price", f"₹{res['spot']}")
        c2.metric("Current PCR", pcr, delta=round(pcr-1.0, 2))
        c3.metric("Support (PE OI)", f"{res['pe_total']:,}")
        c4.metric("Resistance (CE OI)", f"{res['ce_total']:,}")

        col_chart, col_bars = st.columns([2, 1])
        with col_chart:
            fig = go.Figure(go.Scatter(x=st.session_state.history[selected_index]['Time'], y=st.session_state.history[selected_index]['PCR'], mode='lines+markers', line=dict(color='#00ffcc')))
            fig.update_layout(template="plotly_dark", height=300, title="Intraday PCR Movement")
            st.plotly_chart(fig, use_container_width=True)
            
        with col_bars:
            st.subheader("OI Pulse")
            st.bar_chart(data=pd.DataFrame({'OI': [res['pe_total'], res['ce_total']]}, index=['Puts', 'Calls']))

        st.subheader("ATM Option Chain Details")
        if HAS_MATPLOTLIB:
            st.dataframe(res['table'].style.background_gradient(subset=['Put OI Chg', 'Call OI Chg'], cmap='RdYlGn'), use_container_width=True, hide_index=True)
        else:
            st.dataframe(res['table'], use_container_width=True, hide_index=True)

    time.sleep(refresh_speed)
    st.rerun()
