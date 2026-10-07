import os
import requests
from dotenv import load_dotenv

load_dotenv()
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

class LineNotifier:
    def __init__(self):
        self.token = LINE_ACCESS_TOKEN
        self.url = "https://api.line.me/v2/bot/message/broadcast" # หรือใช้ Push Message URL

    def send_trade_alert(self, title: str, details: dict):
        """ ส่งข้อความแจ้งเตือนรูปการ์ดสรุปเข้า LINE """
        if not self.token:
            print("[Line Notifier] ไม่พบ LINE_ACCESS_TOKEN (ข้ามการส่งแจ้งเตือน)")
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # สร้างข้อความ Format สวยๆ อ่านง่ายบนมือถือ
        msg_text = f"🚨 [{title}]\n"
        for key, value in details.items():
            msg_text += f"• {key}: {value}\n"

        payload = {
            "messages": [
                {
                    "type": "text",
                    "text": msg_text.strip()
                }
            ]
        }

        try:
            res = requests.post(self.url, headers=headers, json=payload, timeout=5)
            if res.status_code == 200:
                print("[✓] LINE Notification Sent Successfully!")
            else:
                print(f"[X] LINE Alert Failed: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"[X] LINE Notification Error: {str(e)}")

if __name__ == '__main__':
    # ทดสอบส่งแจ้งเตือน
    notifier = LineNotifier()
    notifier.send_trade_alert("BUY ORDER CONFIRMED", {
        "Symbol": "NVDA",
        "Signal": "BUY_EARLY_REVERSAL",
        "Entry Price": "$129.50",
        "Position Size": "120 Shares ($15,540)",
        "Stop Loss": "$124.00",
        "Target TP": "$140.50"
    })