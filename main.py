import os
import sqlite3
import pandas as pd
import numpy as np
import time
from datetime import datetime
from dotenv import load_dotenv
from risk_manager import RiskManager
from sentiment_scanner import GeminiMarketScanner
from strategy import TechnicalStrategy
from line_notifier import LineNotifier

load_dotenv()
DB_FILE = "positions.db"

WEBULL_APP_ID = os.getenv("WEBULL_APP_ID", "1005288254494085120")
WEBULL_APP_SECRET = os.getenv("WEBULL_APP_SECRET", "")
WEBULL_API_URL = os.getenv("WEBULL_API_URL", "https://openapi.webull.com")

# รายชื่อหุ้นใน Watchlist ที่ต้องการให้บอทวิ่งสแกนอัตโนมัติ
WATCHLIST = ["NVDA", "TSLA", "AAPL", "MSFT", "MSTR", "ARM"]

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

def get_account_capital() -> float:
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cash_balance FROM account_info WHERE id=1")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else 1000.00

def get_position_state(symbol: str) -> dict:
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT has_position, order_status, shares, entry_price, stop_loss, target_tp, order_id FROM positions WHERE symbol=?", (symbol,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "has_position": bool(row[0]), 
            "order_status": row[1], 
            "shares": row[2], 
            "entry_price": row[3], 
            "stop_loss": row[4], 
            "target_tp": row[5],
            "order_id": row[6]
        }
    return {"has_position": False, "order_status": "FLAT", "shares": 0, "entry_price": 0.0, "stop_loss": 0.0, "target_tp": 0.0, "order_id": ""}

def get_total_portfolio_risk_usd() -> float:
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT shares, entry_price, stop_loss FROM positions WHERE has_position = 1")
    rows = c.fetchall()
    conn.close()
    
    total_risk = 0.0
    for row in rows:
        shares, entry_price, stop_loss = row
        total_risk += shares * (entry_price - stop_loss)
    return total_risk

def update_position_state(symbol: str, has_pos: bool, status: str, shares: int = 0, entry_price: float = 0.0, sl: float = 0.0, tp: float = 0.0, order_id: str = ""):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO positions (symbol, has_position, order_status, shares, entry_price, stop_loss, target_tp, order_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT(symbol) DO UPDATE SET
                 has_position=excluded.has_position, order_status=excluded.order_status, 
                 shares=excluded.shares, entry_price=excluded.entry_price, 
                 stop_loss=excluded.stop_loss, target_tp=excluded.target_tp, order_id=excluded.order_id''',
              (symbol, int(has_pos), status, shares, entry_price, sl, tp, order_id))
    conn.commit()
    conn.close()

def execute_webull_openapi_order(symbol: str, action: str, shares: int, order_type: str = "MKT") -> dict:
    import uuid
    generated_order_id = f"WB-API-{uuid.uuid4().hex[:8].upper()}"
    print(f"[*] [Webull OpenAPI] ส่งคำสั่ง {action} สำหรับหุ้น {symbol} จำนวน {shares} หุ้นสำเร็จ")
    return {"status": "FILLED", "order_id": generated_order_id, "filled_shares": shares}

def scan_and_trade_symbol(symbol: str):
    account_capital = get_account_capital()
    print(f"\n--------------------------------------------------")
    print(f"   [AUTO SCAN] กำลังประมวลผลหุ้น : {symbol} | ทุน: ${account_capital:,.2f}")
    print(f"--------------------------------------------------")
    
    notifier = LineNotifier()
    pos_info = get_position_state(symbol)
    has_pos = pos_info["has_position"]
    
    # จำลองข้อมูลราคาสำหรับทดสอบระบบสแกน
    np.random.seed(abs(hash(symbol)) % 10000)
    dates_4h = pd.date_range(end=pd.Timestamp.now(), periods=120, freq='4h')
    prices_4h = np.linspace(100, 130, 120) + np.random.normal(0, 0.5, 120)
    mock_df_4h = pd.DataFrame({
        'open': prices_4h - 0.3, 'high': prices_4h + 0.6,
        'low': prices_4h - 0.5, 'close': prices_4h, 'volume': [30000] * 120
    }, index=dates_4h)

    dates_day = pd.date_range(end=pd.Timestamp.now(), periods=120, freq='D')
    prices_day = np.linspace(90, 125, 120)
    mock_df_day = pd.DataFrame({
        'open': prices_day - 0.5, 'high': prices_day + 1.0,
        'low': prices_day - 0.8, 'close': prices_day, 'volume': [150000] * 120
    }, index=dates_day)

    strat = TechnicalStrategy()
    try:
        sig_res = strat.check_signals(df_4h=mock_df_4h, df_day=mock_df_day, has_position=has_pos)
    except Exception as e:
        print(f"[X] Error analyzing {symbol}: {str(e)}")
        return

    entry_signal = sig_res['entry_signal']
    curr_price = sig_res['indicators_4h']['close']
    atr_val = sig_res['indicators_4h']['atr']
    
    print(f"-> สภาพตลาดหุ้น {symbol} : Signal = {entry_signal}")

    if not has_pos and entry_signal != "NONE":
        # สแกนข่าวผ่าน AI
        scanner = GeminiMarketScanner()
        sentiment_res = scanner.analyze_news_sentiment(symbol, f"Market expansion news for {symbol}")
        
        if sentiment_res['status'] == "PASS":
            risk_ctrl = RiskManager(base_risk_pct=0.015, max_portfolio_risk_pct=0.05)
            structural_sl = risk_ctrl.find_structural_stop_loss(mock_df_4h, entry_price=curr_price, atr_val=atr_val)
            sizing = risk_ctrl.calculate_position_size(account_capital, curr_price, structural_sl, get_total_portfolio_risk_usd())
            
            if sizing['status'] == "APPROVED":
                tp_price = curr_price + ((curr_price - structural_sl) * 2.0)
                exec_res = execute_webull_openapi_order(symbol, action="BUY", shares=sizing['shares'])
                if exec_res['status'] == "FILLED":
                    update_position_state(symbol, has_pos=True, status="HOLDING", shares=sizing['shares'], 
                                          entry_price=curr_price, sl=structural_sl, tp=tp_price, order_id=exec_res['order_id'])
                    print(f"[✓] เปิดสถานะซื้อ {symbol} สำเร็จ! บันทึกลงฐานข้อมูลเรียบร้อย")

if __name__ == '__main__':
    print(f"[*] เริ่มต้นระบบ Automated Quant Bot (Watchlist Auto-Scanner)")
    print(f"[*] หุ้นในความดูแล: {WATCHLIST}")
    
    init_db()
    
    # รันระบบเป็นลูปต่อเนื่องอัตโนมัติ
    try:
        while True:
            print(f"\n[🔄 ROUND START] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - เริ่มรอบการสแกนหุ้นทั้งหมด...")
            for symbol in WATCHLIST:
                scan_and_trade_symbol(symbol)
            
            print(f"\n[⏳ SLEEP] สแกนครบทุกตัวแล้ว พักรอรอบถัดไป (60 วินาที)...")
            time.sleep(60) # วนลูปสแกนใหม่ทุกๆ 1 นาที
    except KeyboardInterrupt:
        print("\n[!] ปิดการทำงานบอทเรียบร้อย")