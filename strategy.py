import pandas as pd
import numpy as np

class TechnicalStrategy:
    def __init__(self, cci_period: int = 20, min_bars_required: int = 80):
        self.cci_period = cci_period
        self.min_bars_required = min_bars_required

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.min_bars_required:
            raise ValueError(f"[Data Guard] ข้อมูลไม่พอ ({len(df)} แท่ง) ต้องการอย่างน้อย {self.min_bars_required} แท่ง")
            
        df = df.copy()
        
        df['ema9'] = df['close'].ewm(span=9, adjust=False, min_periods=1).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False, min_periods=1).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False, min_periods=1).mean()
        
        # ATR Standard
        high_low = df['high'] - df['low']
        high_cp = np.abs(df['high'] - df['close'].shift())
        low_cp = np.abs(df['low'] - df['close'].shift())
        df['tr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['atr'] = df['tr'].ewm(span=27, adjust=False, min_periods=1).mean()
        
        # CCI(20)
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma_tp = tp.rolling(window=self.cci_period, min_periods=1).mean()
        mad = tp.rolling(window=self.cci_period, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        df['cci'] = (tp - sma_tp) / (0.015 * mad)
        
        # Volume Ratio
        df['vol_sma20'] = df['volume'].rolling(window=20, min_periods=1).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma20']
        
        return df

    def check_signals(self, df_4h: pd.DataFrame, df_day: pd.DataFrame = None, has_position: bool = False, current_signal: str = "", entry_price: float = 0.0) -> dict:
        df_4h = self.calculate_indicators(df_4h)
        curr_4h = df_4h.iloc[-2]   # แท่งปิดล่าสุด
        prev_4h = df_4h.iloc[-3]   # แท่งก่อนหน้า 1
        prev2_4h = df_4h.iloc[-4]  # แท่งก่อนหน้า 2

        buy_signal = "NONE"
        buy_reason = ""
        sell_type = "NONE"
        sell_reason = ""

        # ==========================================
        # 1. สัญญาณขาย (Exit Rules)
        # ==========================================
        if has_position:
            total_range = curr_4h['high'] - curr_4h['low']
            upper_wick = curr_4h['high'] - max(curr_4h['open'], curr_4h['close'])
            is_green = curr_4h['close'] > curr_4h['open']
            prev_is_green = prev_4h['close'] > prev_4h['open']

            # คำนวณกำไรปัจจุบัน (%) จากราคาเข้าซื้อจริง
            profit_pct = 0.0
            if entry_price > 0:
                profit_pct = ((curr_4h['close'] - entry_price) / entry_price) * 100

            # กฎเหล็ก Diamond Hand สำหรับ G-Dip
            if current_signal == "BUY_G_DIP":
                if profit_pct >= 10.0:
                    # ถ้ากำไรเกิน 10% แล้ว อนุญาตให้ขายเมื่อเจอแท่งแดงแรกหรือไส้เทียนหมดแรง
                    if prev_is_green and not is_green:
                        sell_type = "SELL_G_DIP_TARGET_HIT"
                        sell_reason = f"G-Dip กำไรทะยาน {profit_pct:.2f}% (>=10%) เจอแท่งแดงหมดแรง -> ขายล็อกกำไรคำโต"
                    elif is_green and total_range > 0 and (upper_wick / total_range) >= 0.35:
                        sell_type = "SELL_G_DIP_EXHAUSTION"
                        sell_reason = f"G-Dip กำไรทะยาน {profit_pct:.2f}% (>=10%) เกิดไส้เทียนยาวหมดแรง -> ขายล็อกกำไร"
                else:
                    # ถ้ายังไม่ถึง 10% ห้ามขายเด็ดขาด (Diamond Hand ถือรันยาวข้ามแรงกระเพื่อม)
                    sell_type = "NONE"
                    sell_reason = f"G-Dip กำไรปัจจุบัน {profit_pct:.2f}% ยังไม่ถึงเป้า 10% -> ถือรันเทรนยาวห้ามขาย!"

            # กฎ Exit สำหรับสัญญาณอื่น (Breakout / Pullback)
            if sell_type == "NONE" and current_signal != "BUY_G_DIP":
                if prev_is_green and not is_green:
                    sell_type = "SELL_MOMENTUM_FADE"
                    sell_reason = f"แท่งเขียวหมดแรง พลิกปิดแดง -> ขายล็อกกำไร"
                elif is_green and total_range > 0 and (upper_wick / total_range) >= 0.35:
                    sell_type = "SELL_EXHAUSTION_WICK"
                    sell_reason = f"ชนแนวต้านเกิดไส้เทียนยาวหมดแรง -> ขายล็อกกำไร"
                elif curr_4h['close'] < curr_4h['ema200']:
                    sell_type = "SELL_EMA200_BROKEN"
                    sell_reason = f"TF 4H ปิดหลุด EMA200 -> ตัดขายจบเทรน"

        # ==========================================
        # 2. สัญญาณซื้อ (Entry Rules: G-Dip)
        # ==========================================
        else:
            recent_high_4h = df_4h['high'].iloc[-30:-2].max()
            curr_is_green = curr_4h['close'] > curr_4h['open']
            prev_is_green = prev_4h['close'] > prev_4h['open']

            # G-Dip: แดงสะสมรวม >= 5 แท่ง + CCI <= -100 + เกิดเขียว 2 แท่งยืนยัน
            if len(df_4h) >= 12:
                recent_window = df_4h.iloc[-10:-2]
                red_count = sum(recent_window['close'] < recent_window['open'])
                is_cci_oversold = (prev_4h['cci'] <= -100 or prev2_4h['cci'] <= -100)
                two_consecutive_greens = curr_is_green and prev_is_green

                if two_consecutive_greens and red_count >= 5 and is_cci_oversold:
                    buy_signal = "BUY_G_DIP"
                    buy_reason = f"Diamond G-Dip ช้อนซื้อ! แดงสะสม {red_count} แท่ง, CCI Oversold ({prev_4h['cci']:.1f}), เขียว 2 แท่งยืนยัน"

            # สัญญาณเสริมอื่นๆ
            if buy_signal == "NONE":
                if curr_4h['close'] > recent_high_4h and curr_is_green and curr_4h['vol_ratio'] >= 2.0:
                    buy_signal = "BUY_G_BREAKOUT"
                    buy_reason = f"Strict Breakout! ทะลุ High เดิม"
                elif curr_4h['low'] <= curr_4h['ema21'] and curr_4h['close'] > curr_4h['ema21'] and curr_4h['close'] > prev_4h['high']:
                    buy_signal = "BUY_G_PULLBACK"
                    buy_reason = f"Pullback รีเทสแนวรับ EMA21"

        return {
            "entry_signal": buy_signal,
            "entry_reason": buy_reason,
            "exit_type": sell_type,
            "exit_reason": sell_reason,
            "indicators_4h": {
                "close": curr_4h['close'],
                "ema9": curr_4h['ema9'],
                "ema21": curr_4h['ema21'],
                "ema200": curr_4h['ema200'],
                "cci": curr_4h['cci'],
                "vol_ratio": curr_4h['vol_ratio'],
                "atr": curr_4h['atr']
            }
        }