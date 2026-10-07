import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class SentimentAnalysisSchema(BaseModel):
    status: str = Field(description="PASS หรือ REJECT เท่านั้น")
    sentiment: str = Field(description="BULLISH, BEARISH, หรือ NEUTRAL")
    reason: str = Field(description="เหตุผลสรุปสั้นๆ 1 ประโยค")

class GeminiMarketScanner:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("[Error] กรุณาใส่ GEMINI_API_KEY ในไฟล์ .env ก่อนรันนะคะ")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def analyze_news_sentiment(self, symbol: str, news_text: str) -> dict:
        prompt = f"วิเคราะห์ข่าวของหุ้น {symbol}: {news_text}"
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SentimentAnalysisSchema,
                    temperature=0.1
                )
            )
            return json.loads(response.text)
                
        except Exception as e:
            return {"status": "REJECT", "sentiment": "NEUTRAL", "reason": f"ข้อผิดพลาดระบบ AI ({str(e)})"}