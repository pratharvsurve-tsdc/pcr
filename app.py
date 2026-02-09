import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time

# --- SAFETY SHIELD: Check for Matplotlib ---
try:
    import matplotlib
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

st.set_page_config(page_title="Live NSE PCR Tracker", layout="wide")

class NSELive:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/option-chain'
        }
        self.session = requests.Session()

    def get_data(self, symbol):
        # Initial request to establish cookies/session
        base_url = "https://www.nseindia.com"
        api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        
        try:
            self.session.get(base_url, headers=self.headers, timeout=5)
            response = self.session.get(api_url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                return None, f"NSE Server Error: {response.status_code}"
                
            data = response.json()
            
            if 'filtered' not in data or not data['filtered']['data']:
                return None, "No data found (Market likely closed or API restricted)"

            underlying = data['records']['underlyingValue']
            df_raw = pd.json_normalize(data['filtered']['data'])
            
            # Calculate distance from spot to find ATM
            df_raw['diff'] = abs(df_raw['strikePrice'] - underlying)
            atm_idx = df_raw['diff'].idxmin()
            
            # Get 5 strikes above and 5 below ATM (11 strikes total)
            subset = df_raw.iloc[max(0, atm_idx-5):atm_idx+6].copy()
            
            # Calculate PCR
            pe_oi_sum = subset['PE.openInterest'].sum()
            ce_oi_sum = subset['CE.openInterest'].sum()
            pcr = round(pe_oi_sum / ce_oi_sum, 2) if ce_oi_sum != 0 else 0
            
            display_df = subset[['strikePrice', 'CE.openInterest', 'PE.openInterest', 'CE.changeinOpenInterest', 'PE.changeinOpenInterest']]
            display_df.columns = ['Strike', 'Call OI', 'Put OI', 'Call OI Chg', 'Put OI Chg']
            
            return {
                "spot": underlying, 
                "atm_pcr": pcr, 
                "pe_total": pe_oi_sum, 
                "ce_total": ce_oi_sum, 
                "table": display_df
            }, None
            
        except Exception as e:
            return None, f"Connection Error: {str(e)}"

# --- ANALYZER LOGIC ---
def get_suggestion(pcr, history):
    if len(history) < 2:
        return "Establishing Trend...", "gray"
    
    prev_pcr = history.iloc[-2]['PCR']
    trend = "Rising" if pcr > prev_pcr else "Falling"
    
    if pcr > 1.3:
        return f"OVERBOUGHT ({trend} PCR). Caution on longs.", "red"
    elif pcr > 1.1 and trend == "Rising":
        return "BULLISH MOMENTUM. Support is strengthening.", "green"
    elif pcr < 0.7 and trend == "Falling":
        return "BEARISH MOMENTUM. Resistance is building.", "red"
    elif pcr < 0.6:
        return "OVERSOLD. Potential for short covering bounce.", "green"
    elif 0.9 <= pcr <= 1.1:
        return "NEUTRAL / SIDEWAYS. Wait for breakout.", "blue"
    else:
        return f"PCR: {pcr} | Trend: {trend}", "orange"

# --- APP SETUP ---
nse = NSELive()

with st.sidebar:
    st.header("📈 Market Controls")
    selected_index = st.selectbox("Select Index", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    refresh_speed = st.slider("Refresh Interval (Seconds)", 30, 300, 60)
    st.info("Note: NSE API may block frequent requests. Default is 60s.")

st.title(f"📊 Live {selected_index} PCR Analyzer")

# Initialize session state for history
if 'history' not in st.session_state:
    st.session_state.history = {idx: pd.DataFrame(columns=['Time', 'PCR']) for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]}

placeholder = st.empty()

while True:
    with placeholder.container():
        res, err = nse.get_data(selected_index)
        
        if err:
            st.error(f"⚠️ {err}")
            st.button("Retry Now")
            time.sleep(10)
            st.rerun()
        else:
            curr_time = time.strftime("%H:%M:%S")
            
            # Update history
            new_entry = pd.DataFrame({'Time': [curr_time], 'PCR': [res['atm_pcr']]})
            st.session_state.history[selected_index] = pd.concat(
                [st.session_state.history[selected_index], new_entry], 
                ignore_index=True
            ).tail(50)

            # AI Suggestion Box
            suggestion, color = get_suggestion(res['atm_pcr'], st.session_state.history[selected_index])
            st.info(f"**Market Sentiment:** {suggestion}")

            # Top Metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Spot Price", f"₹{res['spot']:,}")
            c2.metric("ATM PCR", res['atm_pcr'], delta=round(res['atm_pcr']-1.0, 2))
            c3.metric("Total Put OI", f"{res['pe_total']:,}")
            c4.metric("Total Call OI", f"{res['ce_total']:,}")

            st.divider()

            # Visualizations
            col_chart, col_bars = st.columns([2, 1])
            with col_chart:
                st.subheader("Intraday PCR Trend")
                fig = go.Figure(go.Scatter(
                    x=st.session_state.history[selected_index]['Time'], 
                    y=st.session_state.history[selected_index]['PCR'],
                    mode='lines+markers', 
                    line=dict(color='#00d1b2', width=3)
                ))
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
                
            with col_bars:
                st.subheader("OI Pulse")
                st.bar_chart(data=pd.DataFrame(
                    {'OI': [res['pe_total'], res['ce_total']]}, 
                    index=['Puts (Support)', 'Calls (Resist)']
                ))

            # Live Data Table
            st.subheader("ATM Option Chain (Live)")
            if HAS_MATPLOTLIB:
                st.dataframe(
                    res['table'].style.background_gradient(subset=['Put OI Chg', 'Call OI Chg'], cmap='RdYlGn'), 
                    use_container_width=True, 
                    hide_index=True
                )
            else:
                st.dataframe(res['table'], use_container_width=True, hide_index=True)

    time.sleep(refresh_speed)
    st.rerun()
