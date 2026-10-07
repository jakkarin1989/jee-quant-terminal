import pandas as pd
import numpy as np

class RiskManager:
    def __init__(self, base_risk_pct: float = 0.015, max_portfolio_risk_pct: float = 0.05):
        self.base_risk_pct = base_risk_pct
        self.max_portfolio_risk_pct = max_portfolio_risk_pct

    def calculate_growth_velocity_multiplier(self, df_4h: pd.DataFrame) -> float:
        if len(df_4h) < 20: return 1.0
        recent = df_4h.tail(10)
        price_slope = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0]
        if price_slope > 0.05: return 1.25
        elif price_slope < 0.01: return 0.75
        return 1.0

    def find_structural_stop_loss(self, df: pd.DataFrame, entry_price: float, atr_val: float, signal_type: str = "GENERAL") -> float:
        # หากเป็น G-Dip ให้ใช้จุดต่ำสุด (Lowest Low) ของช่วง 5 แท่งแดงที่ผ่านมา เป็นจุดตัดขาดทุน
        if signal_type == "BUY_G_DIP":
            red_streak_low = float(df['low'].iloc[-8:-3].min())
            return red_streak_low - (atr_val * 0.1)

        recent_bars = df.tail(5).iloc[:-1]
        if signal_type in ["BUY_G_BREAKOUT", "BUY_G_PULLBACK"]:
            tight_sl = float(recent_bars['low'].iloc[-1]) - (atr_val * 0.2)
            if tight_sl < entry_price: return float(tight_sl)

        return float(entry_price - (atr_val * 1.5))

    def calculate_position_size(self, capital: float, entry_price: float, stop_loss: float, df_4h: pd.DataFrame = None, current_portfolio_risk_usd: float = 0.0) -> dict:
        try:
            if entry_price <= stop_loss:
                return {"shares": 0, "risk_amount_usd": 0.0, "position_value": 0.0, "status": "REJECTED_INVALID_SL"}

            velocity_multiplier = 1.0
            if df_4h is not None:
                velocity_multiplier = self.calculate_growth_velocity_multiplier(df_4h)

            adjusted_risk_pct = self.base_risk_pct * velocity_multiplier
            this_trade_risk = capital * adjusted_risk_pct
            
            risk_per_share = entry_price - stop_loss
            risk_shares = int(this_trade_risk // risk_per_share)
            max_capital_shares = int(capital // entry_price)
            shares = min(risk_shares, max_capital_shares)
            
            if shares <= 0:
                return {"shares": 0, "risk_amount_usd": 0.0, "position_value": 0.0, "status": "REJECTED_TOO_SMALL"}

            return {
                "shares": shares,
                "risk_amount_usd": shares * risk_per_share,
                "position_value": shares * entry_price,
                "growth_multiplier": velocity_multiplier,
                "status": "APPROVED"
            }
        except Exception as e:
            return {"shares": 0, "risk_amount_usd": 0.0, "position_value": 0.0, "status": f"ERROR_{str(e)}"}