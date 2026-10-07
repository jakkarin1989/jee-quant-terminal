import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ใส่ค่าที่ได้จาก LINE Developers และ LINE OA ของบูม
CHANNEL_ACCESS_TOKEN = "08RD13L8FSynZSWO3clrebrxRN1mWT1+rpKF7AcjLagQdIkHqlwIOyQs5mZED0m6o3QKGF6mJExoKaNepAq/somIqAJB558Beo1jJE4GVArOi4WKfOpwdTGkHZN9HNqHx3eoHbaodtB/2KwLOk/01wdB04t89/1O/w1cDnyilFU="
USER_ID = "U9cea9111fc52675942e9f2bdc46c5228"  # สังเกตว่าจะขึ้นต้นด้วยตัว 'U...'

def send_line_push_message(message: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[X] ส่ง LINE ไม่สำเร็จ: {str(e)}")
        return False

def load_watchlist(filename="watchlist.txt"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            symbols = [line.strip().upper() for line in f if line.strip()]
        return symbols
    except FileNotFoundError:
        return ["ARM", "NVDA", "AMD"]

def scan_and_alert():
    watchlist = load_watchlist("watchlist.txt")
    capital = 50000.0
    risk_pct = 0.015

    print(f"[*] กำลังสแกนหุ้น {len(watchlist)} ตัว ประจำรอบ {datetime.now().strftime('%Y-%m-%d %H:%M')}...")
    
    for symbol in watchlist:
        try:
            import yfinance as yf
            end_str = datetime.now().strftime("%Y-%m-%d")
            start_str = (datetime.now() - timedelta(days=150)).strftime("%Y-%m-%d")
            
            df = yf.download(symbol, start=start_str, end=end_str, interval="1d", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0].lower() for col in df.columns]
            else:
                df.columns = [col.lower() for col in df.columns]

            curr_price = float(df['close'].iloc[-1])
            prev_high = float(df['high'].iloc[-20:-1].max())  # แนวต้าน 20 วันล่าสุด
            ema_9 = float(df['close'].ewm(span=9).mean().iloc[-1])
            ema_21 = float(df['close'].ewm(span=21).mean().iloc[-1])
            sma_50 = float(df['close'].rolling(50).mean().iloc[-1])

            signal_type = None

            # 1. ตรวจสอบเงื่อนไข Breakout (ทะล แนวต้านเดิมขึ้นไปทำ High ใหม่)
            if curr_price > prev_high:
                signal_type = "🚀 BREAKOUT SETUP"
            
            # 2. ตรวจสอบเงื่อนไข Pullback (ย่อตัวลงมาแตะโซนเส้นค่าเฉลี่ย EMA 9/21 ในเทรนด์ขาขึ้น)
            elif curr_price > sma_50 and (abs(curr_price - ema_9) / ema_9 < 0.015 or abs(curr_price - ema_21) / ema_21 < 0.015):
                signal_type = "📉 PULLBACK SETUP"
            
            # 3. ตรวจสอบเงื่อนไข Buy the Dip (ย่อลึกแต่ยังเกาะโครงสร้างหลักแล้วเริ่มมีแรงซื้อกลับ)
            elif curr_price > sma_50 and df['close'].iloc[-1] > df['open'].iloc[-1] and df['close'].iloc[-2] < df['open'].iloc[-2]:
                signal_type = "🛒 BUY THE DIP SETUP"

            if signal_type:
                current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # ประมาณการคำนวณหน้าตักคร่าวๆ ตามวินัย
                position_value = capital * 0.20 # ตัวอย่างสัดส่วนต่อไม้

                msg = (
                    f"🚨 [{signal_type}]\n"
                    f"📅 เวลา: {current_time_str}\n"
                    f"📌 หุ้น: {symbol}\n"
                    f"💰 ราคาปัจจุบัน: ${curr_price:,.2f}\n"
                    f"💵 มูลค่าไม้พอร์ต: ${position_value:,.2f}\n"
                    f"🛡️ วินัยคุมหน้าตัก: ล็อกความเสี่ยง คุมสภาพคล่อง\n"
                    f"⚠️ หมายเหตุ: ปล่อยรันเทรนด์ยาว ออกสถานะเมื่อโครงสร้างพังหรือเจอสัญญาณขายเท่านั้น"
                )
                send_line_push_message(msg)
                print(f"[✓] ส่งสัญญาณ {symbol} ({signal_type}) เข้า LINE เรียบร้อยค่ะ")
        except Exception as e:
            print(f"[X] ผิดพลาดในการสแกน {symbol}: {str(e)}")

if __name__ == '__main__':
    scan_and_alert()