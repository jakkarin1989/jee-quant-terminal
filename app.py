import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
import time
import yfinance as yf

# --- ตั้งค่าหน้าจอแบบ Wide Mode ---
st.set_page_config(
    page_title="Jee Sovereign Quant Terminal (Dime Style)",
    page_icon="⚡",
    layout="wide"
)

# --- Custom CSS แต่ง UI สไตล์ Dime! ---
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #f3f4f6;
    }
    .dime-header-card {
        background: linear-gradient(135deg, #171b26 0%, #1f2937 100%);
        border: 1px solid #2a3447;
        padding: 24px;
        border-radius: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .dime-label {
        color: #9ca3af;
        font-size: 14px;
        font-weight: 500;
        margin-bottom: 6px;
    }
    .dime-main-value {
        color: #ffffff;
        font-size: 32px;
        font-weight: bold;
        letter-spacing: -0.5px;
    }
    .dime-sub-value-pos {
        color: #10b981;
        font-size: 14px;
        margin-top: 6px;
        font-weight: 500;
    }
    .dime-sub-value-neg {
        color: #ef4444;
        font-size: 14px;
        margin-top: 6px;
        font-weight: 500;
    }
    .dime-mini-card {
        background-color: #171b26;
        border: 1px solid #2a3447;
        padding: 16px;
        border-radius: 16px;
        margin-bottom: 15px;
    }
    .scrollable-log {
        background-color: #0b0e14;
        border: 1px solid #1f2937;
        border-radius: 12px;
        padding: 15px;
        height: 320px;
        overflow-y: auto;
        font-family: monospace;
        color: #10b981;
        font-size: 13px;
        line-height: 1.6;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #2a3447;
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = "positions.db"
WATCHLIST_FILE = "watchlist.txt"
INITIAL_CAPITAL = 1000.00  # ทุนเริ่มต้นตั้งต้น

def load_watchlist_from_file():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip().upper() for line in f if line.strip()]
                if lines:
                    return lines
        except:
            pass
    return ["NVDA", "TSLA", "AAPL", "MSFT", "MSTR", "ARM"]

WATCHLIST = load_watchlist_from_file()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS positions 
                 (symbol TEXT PRIMARY KEY, 
                  has_position INTEGER, 
                  order_status TEXT, 
                  shares INTEGER, 
                  entry_price REAL, 
                  stop_loss REAL, 
                  target_tp REAL,
                  order_id TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS account_info 
                 (id INTEGER PRIMARY KEY CHECK (id = 1), 
                  cash_balance REAL, 
                  buying_power REAL, 
                  net_liquidation REAL)''')
    
    c.execute('''INSERT OR IGNORE INTO account_info (id, cash_balance, buying_power, net_liquidation) 
                 VALUES (1, 1000.00, 4000.00, 1000.00)''')
    conn.commit()
    conn.close()

init_db()

def get_db_account_capital():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT cash_balance FROM account_info WHERE id=1")
        row = c.fetchone()
        conn.close()
        return float(row[0]) if row else 1000.00
    except:
        return 1000.00

def get_all_positions():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM positions", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

# Session State สำหรับเก็บประวัติ Log
if "log_lines" not in st.session_state:
    st.session_state.log_lines = [
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INIT] เริ่มต้นระบบมอนิเตอร์พอร์ตและสตรีมมิ่งราคาหุ้น..."
    ]

@st.cache_data(ttl=30)
def fetch_live_market_data(symbols):
    data = []
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym.strip())
            todays_data = ticker.history(period="2d")
            if not todays_data.empty:
                current_price = todays_data['Close'].iloc[-1]
                prev_price = todays_data['Close'].iloc[-2] if len(todays_data) > 1 else current_price
                change_pct = ((current_price - prev_price) / prev_price) * 100
            else:
                current_price = 0.0
                change_pct = 0.0
        except:
            current_price = 0.0
            change_pct = 0.0
            
        data.append({
            "Symbol": sym,
            "Live Price ($)": f"${current_price:,.3f}" if current_price > 0 else "N/A",
            "Change (%)": f"{change_pct:+.2f}%",
            "Timeframe": "TF 4h & Day",
            "Strategy": "EMA 9/21/50/200"
        })
    return pd.DataFrame(data)

# --- Sidebar ควบคุมระบบ ---
st.sidebar.markdown("### 🎛️ Terminal Control Center")
current_capital = get_db_account_capital()
account_capital = st.sidebar.number_input("Account Capital ($) [Webull Live]", value=float(current_capital), step=100.0)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📡 Watchlist File")
for sym in WATCHLIST:
    st.sidebar.markdown(f"🟢 **{sym}** : Connected")

if st.sidebar.button("🔄 รีเฟรชราคาและข้อมูลพอร์ต"):
    st.cache_data.clear()
    st.rerun()

# --- ส่วนหัวแดชบอร์ด ---
st.markdown("## 📊 สินทรัพย์ของฉัน & พอร์ตการลงทุน")
st.markdown("ระบบมอนิเตอร์พอร์ตและสตรีมมิ่งราคาหุ้นสไตล์ Dime! | Live Active")
st.divider()

# --- คำนวณ % การเติบโตของพอร์ตเทียบกับทุนเริ่มต้น ---
growth_amount = account_capital - INITIAL_CAPITAL
growth_pct = (growth_amount / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0
growth_class = "dime-sub-value-pos" if growth_pct >= 0 else "dime-sub-value-neg"
growth_sign = "+" if growth_pct >= 0 else ""

# --- การ์ดแสดงมูลค่าพอร์ตและ % เติบโต (สไตล์ Dime Header Card) ---
st.markdown(f"""
    <div class="dime-header-card">
        <div class="dime-label">มูลค่าทรัพย์สินทั้งหมด (Webull Live Feed)</div>
        <div class="dime-main-value">${account_capital:,.2f} USD</div>
        <div class="{growth_class}">
            {growth_sign}{growth_pct:.2f}% ({growth_sign}${growth_amount:,.2f} USD) เทียบกับทุนเริ่มต้น ${INITIAL_CAPITAL:,.2f}
        </div>
    </div>
""", unsafe_allow_html=True)

# --- ดึงข้อมูลตำแหน่งที่ถือหุ้นอยู่ (Active Positions) ---
df_positions = get_all_positions()
active_positions = df_positions[df_positions['has_position'] == 1] if not df_positions.empty and 'has_position' in df_positions.columns else pd.DataFrame()

# --- การ์ดย่อยสรุปสถานะ ---
col_sub1, col_sub2 = st.columns(2)
with col_sub1:
    holding_count = len(active_positions) if not active_positions.empty else 0
    st.markdown(f"""
        <div class="dime-mini-card">
            <div class="dime-label">📊 จำนวนหุ้นที่ถือครองอยู่จริง</div>
            <div style="font-size: 22px; font-weight: bold; color: #ffffff;">{holding_count} ตัว</div>
            <div style="color: #10b981; font-size: 12px; margin-top: 4px;">Active Positions in Portfolio</div>
        </div>
    """, unsafe_allow_html=True)
with col_sub2:
    st.markdown(f"""
        <div class="dime-mini-card">
            <div class="dime-label">🎯 จำนวนหุ้นใน Watchlist</div>
            <div style="font-size: 22px; font-weight: bold; color: #ffffff;">{len(WATCHLIST)} ตัว</div>
            <div style="color: #9ca3af; font-size: 12px; margin-top: 4px;">Streaming Feed Active</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Tabs หลัก ---
tab1, tab2, tab3 = st.tabs([
    "💼 หุ้นที่ถือครองอยู่ในพอร์ต (Active Positions)", 
    "📈 ราคาหุ้นใน Watchlist", 
    "🤖 บันทึกการทำงาน (Live Logs)"
])

with tab1:
    st.subheader("💼 รายชื่อหุ้นและสินทรัพย์ในพอร์ต (`Positions.db`)")
    df_all_pos = get_all_positions()
    if not df_all_pos.empty:
        st.dataframe(df_all_pos, use_container_width=True)
    else:
        st.warning("⚠️ ไม่พบข้อมูลตาราง positions ในฐานข้อมูล Positions.db")
        st.info("💡 พอร์ตปัจจุบันอยู่ในสถานะถือเงินสด (FLAT) ไม่มีหุ้นค้างในพอร์ต พร้อมรอสัญญาณเทรดตามระบบ Risk 1-2%")

with tab2:
    st.subheader("📈 ตารางราคาหุ้นเรียลไทม์จาก Watchlist")
    with st.spinner("กำลังดึงราคาตลาด..."):
        df_prices = fetch_live_market_data(WATCHLIST)
    st.dataframe(df_prices, use_container_width=True)

with tab3:
    st.subheader("🔍 Auto-Scanner & Live Feed Logs")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.log_lines.append(f"[{now_str}] [SCAN] ตรวจสอบราคา Watchlist ทั้ง {len(WATCHLIST)} ตัวเรียบร้อย")
    
    log_html = "<br>".join(st.session_state.log_lines[-40:])
    st.markdown(f'<div class="scrollable-log">{log_html}</div>', unsafe_allow_html=True)

# --- Auto Refresh ทุก 30 วินาที ---
time.sleep(30)
st.rerun()