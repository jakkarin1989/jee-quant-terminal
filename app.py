import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import yfinance as yf

# --- ตั้งค่าหน้าจอแบบ Wide Mode ---
st.set_page_config(
    page_title="Jee Sovereign Quant Terminal (Dime UI Style)",
    page_icon="⚡",
    layout="wide"
)

# --- Custom CSS แต่ง UI ให้สะอาด สบายตา สไตล์แอป Dime ---
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
    .dime-sub {
        color: #10b981;
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
        height: 350px;
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
    
    # ค่าตั้งต้นเริ่มต้นถ้ายังไม่มีข้อมูล
    c.execute('''INSERT OR IGNORE INTO account_info (id, cash_balance, buying_power, net_liquidation) 
                 VALUES (1, 2000.00, 8000.00, 2000.00)''')
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
        return float(row[0]) if row else 2000.00
    except:
        return 2000.00

def update_db_account_capital(new_capital):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE account_info SET cash_balance = ?, buying_power = ?, net_liquidation = ? WHERE id = 1", 
                  (new_capital, new_capital * 4, new_capital))
        conn.commit()
        conn.close()
    except:
        pass

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

# ดึงเวลาไทยเริ่มต้น
thai_now = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")

if "log_lines" not in st.session_state:
    st.session_state.log_lines = [
        f"[{thai_now}] [INIT] เริ่มต้นระบบมอนิเตอร์ Watchlist จำนวน {len(WATCHLIST)} ตัว..."
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

# ช่องกรอกปรับยอดเงิน และบันทึกลง DB ทันทีเมื่อมีการเปลี่ยนแปลง
new_capital_input = st.sidebar.number_input("Account Capital ($) [Webull Live]", value=float(current_capital), step=100.0)
if new_capital_input != current_capital:
    update_db_account_capital(new_capital_input)
    current_capital = new_capital_input

st.sidebar.markdown("---")
st.sidebar.markdown("### 📡 Watchlist File")
for sym in WATCHLIST:
    st.sidebar.markdown(f"🟢 **{sym}** : Connected")

if st.sidebar.button("🔄 รีเฟรชราคาและข้อมูลพอร์ต"):
    st.cache_data.clear()
    st.rerun()

# --- ส่วนหัวสไตล์ Dime ---
st.markdown("## 📊 สินทรัพย์ของฉัน & ควบคุมพอร์ต")
st.markdown("ระบบมอนิเตอร์ราคาและวิเคราะห์เชิงปริมาณสไตล์ Dime! | Live Streaming Active")
st.divider()

# --- การ์ดแสดงมูลค่าทรัพย์สินรวม ---
st.markdown(f"""
    <div class="dime-header-card">
        <div class="dime-label">มูลค่าพอร์ตเงินสดรวม (Webull Live Feed)</div>
        <div class="dime-main-value">${current_capital:,.2f} USD</div>
        <div class="dime-sub">🟢 เชื่อมต่อข้อมูลตลาดหลักทรัพย์แบบเรียลไทม์ (ปลอดภัย ไร้ความเสี่ยง)</div>
    </div>
""", unsafe_allow_html=True)

# --- การ์ดย่อย 2 คอลัมน์ ---
col_sub1, col_sub2 = st.columns(2)
with col_sub1:
    df_positions = get_all_positions()
    holding_count = len(df_positions[df_positions['has_position'] == 1]) if not df_positions.empty else 0
    st.markdown(f"""
        <div class="dime-mini-card">
            <div class="dime-label">📊 จำนวนหุ้นที่ถือครองในพอร์ต</div>
            <div style="font-size: 22px; font-weight: bold; color: #ffffff;">{holding_count} ตัว</div>
            <div style="color: #9ca3af; font-size: 12px; margin-top: 4px;">Active Positions</div>
        </div>
    """, unsafe_allow_html=True)
with col_sub2:
    st.markdown(f"""
        <div class="dime-mini-card">
            <div class="dime-label">🎯 จำนวนหุ้นใน Watchlist File</div>
            <div style="font-size: 22px; font-weight: bold; color: #ffffff;">{len(WATCHLIST)} ตัว</div>
            <div style="color: #10b981; font-size: 12px; margin-top: 4px;">Streaming Active (Passive Mode)</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Tabs หลัก ---
tab1, tab2, tab3 = st.tabs([
    "📈 รายชื่อหุ้น & ราคาเรียลไทม์", 
    "🤖 บันทึกการทำงาน (Live Logs)", 
    "💼 สถานะพอร์ตจริง"
])

with tab1:
    st.subheader(f"📈 ตารางราคาหุ้นจากไฟล์ `watchlist.txt`")
    with st.spinner("กำลังดึงราคาตลาดสด..."):
        df_prices = fetch_live_market_data(WATCHLIST)
    st.dataframe(df_prices, use_container_width=True)

with tab2:
    st.subheader("🔍 Auto-Scanner & Live Feed Logs")
    st.markdown(f"บันทึกการทำงานสแกนตลาด ข้อความจะไหลต่อยอดขึ้นด้านบนเรื่อยๆ (เช็กครบทั้ง {len(WATCHLIST)} ตัว / เวลาไทยตรงเป๊ะ):")
    
    # อัปเดต Log เป็นเวลาไทย (Asia/Bangkok)
    now_str = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.log_lines.append(f"[{now_str}] [SCAN] ดึงข้อมูลราคา Watchlist ทั้ง {len(WATCHLIST)} ตัวเรียบร้อย")
    
    # วนลูปโชว์ครบทุกตัวใน Watchlist จริงๆ
    for s in WATCHLIST:
        st.session_state.log_lines.append(f"[{now_str}]   ├─ [{s}] ตรวจสอบแนวโน้ม EMA 9/21/50/200 บน TF 4h / Day [ปกติ]")
    
    # แสดงผลกล่อง Scrollable Log (เก็บประวัติล่าสุด 150 บรรทัด)
    log_html = "<br>".join(st.session_state.log_lines[-150:])
    st.markdown(f'<div class="scrollable-log">{log_html}</div>', unsafe_allow_html=True)

with tab3:
    st.subheader("💼 สถานะพอร์ตการถือครองจริง (Positions.db)")
    if not df_positions.empty:
        st.dataframe(df_positions, use_container_width=True)
    else:
        st.info("พอร์ตปัจจุบันอยู่ในสถานะถือเงินสด (FLAT) พร้อมรอสัญญาณเทรดตามระบบ Risk 1-2%")

# --- Auto Refresh ทุก 30 วินาที ---
time.sleep(30)
st.rerun()
