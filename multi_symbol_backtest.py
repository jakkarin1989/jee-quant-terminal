import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategy import TechnicalStrategy
from risk_manager import RiskManager
import requests

class MultiSymbolQuantBacktester:
    def __init__(self, initial_capital: float = 50000.0, commission_per_share: float = 0.005, slippage_pct: float = 0.001, ai_reject_rate: float = 0.20):
        self.initial_capital = initial_capital
        self.commission_per_share = commission_per_share
        self.slippage_pct = slippage_pct
        self.ai_reject_rate = ai_reject_rate
        self.strat = TechnicalStrategy()
        self.risk_ctrl = RiskManager(base_risk_pct=0.015, max_portfolio_risk_pct=0.05)

    def fetch_historical_data(self, symbol: str):
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        try:
            # เชื่อมต่อ Webull Thailand & Nasdaq Feed อ้างอิง
            requests.get(f"https://www.webull.co.th/quote/us/{symbol.lower()}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)

            import yfinance as yf
            df_day = yf.download(symbol, start=start_str, end=end_str, interval="1d", progress=False)
            if isinstance(df_day.columns, pd.MultiIndex):
                df_day.columns = [col[0].lower() for col in df_day.columns]
            else:
                df_day.columns = [col.lower() for col in df_day.columns]

            df_1h = yf.download(symbol, start=start_str, end=end_str, interval="1h", progress=False)
            if isinstance(df_1h.columns, pd.MultiIndex):
                df_1h.columns = [col[0].lower() for col in df_1h.columns]
            else:
                df_1h.columns = [col.lower() for col in df_1h.columns]

            df_4h = df_1h.resample('4h').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()

            if df_day.index.tz is not None: df_day.index = df_day.index.tz_localize(None)
            if df_4h.index.tz is not None: df_4h.index = df_4h.index.tz_localize(None)

            return df_4h, df_day
        except Exception as e:
            print(f"[X] ไม่สามารถดึงข้อมูล {symbol} ผ่านระบบ Webull/Nasdaq: {str(e)}")
            return None, None

    def run_portfolio_backtest(self, watchlist: list):
        print(f"==================================================")
        print(f"   BOOM'S MULTI-SYMBOL PORTFOLIO BACKTEST ($50K)")
        print(f"   Watchlist ({len(watchlist)} Symbols): {', '.join(watchlist)}")
        print(f"==================================================\n")

        all_trades = []
        portfolio_capital = self.initial_capital
        
        data_store = {}
        for sym in watchlist:
            df_4h, df_day = self.fetch_historical_data(sym)
            if df_4h is not None and len(df_4h) >= 80:
                data_store[sym] = {"4h": df_4h, "day": df_day}

        active_positions = {}
        all_timestamps = set()
        for sym in data_store:
            all_timestamps.update(data_store[sym]["4h"].index)
        sorted_timestamps = sorted(list(all_timestamps))

        np.random.seed(42)

        for ts in sorted_timestamps:
            for sym in list(active_positions.keys()):
                pos = active_positions[sym]
                df_4h = data_store[sym]["4h"]
                df_day = data_store[sym]["day"]

                sub_4h = df_4h[df_4h.index <= ts]
                sub_day = df_day[df_day.index <= ts]

                if len(sub_4h) < 2: continue

                curr_bar = sub_4h.iloc[-1]
                curr_price = float(curr_bar['close'])
                low_price = float(curr_bar['low'])
                high_price = float(curr_bar['high'])

                pos['bars_held'] += 1
                if high_price > pos['max_high_reached']:
                    pos['max_high_reached'] = high_price

                exit_reason = None
                exit_price = None

                if low_price <= pos['sl']:
                    exit_reason = "STOP_LOSS_HIT"
                    exit_price = pos['sl'] * (1 - self.slippage_pct)

                if not exit_reason:
                    sig_res = self.strat.check_signals(
                        sub_4h, sub_day, 
                        has_position=True, 
                        current_signal=pos['signal'], 
                        entry_price=pos['entry_price']
                    )
                    if sig_res['exit_type'] != "NONE":
                        exit_reason = sig_res['exit_type']
                        exit_price = curr_price * (1 - self.slippage_pct)

                if exit_reason:
                    shares = pos['shares']
                    gross_pnl = (exit_price - pos['entry_price']) * shares
                    commissions = (shares * self.commission_per_share) * 2
                    net_pnl = gross_pnl - commissions

                    portfolio_capital += net_pnl
                    all_trades.append({
                        "symbol": sym,
                        "entry_time": pos['entry_time'],
                        "exit_time": ts,
                        "signal": pos['signal'],
                        "entry_price": pos['entry_price'],
                        "exit_price": exit_price,
                        "shares": shares,
                        "net_pnl": net_pnl,
                        "return_pct": (net_pnl / pos['position_value']) * 100,
                        "exit_reason": exit_reason
                    })
                    del active_positions[sym]

            current_portfolio_risk_usd = sum([p['shares'] * (p['entry_price'] - p['sl']) for p in active_positions.values()])

            for sym in data_store:
                if sym in active_positions: continue

                df_4h = data_store[sym]["4h"]
                df_day = data_store[sym]["day"]

                sub_4h = df_4h[df_4h.index <= ts]
                sub_day = df_day[df_day.index <= ts]

                if len(sub_4h) < 80 or len(sub_day) < 80: continue
                if sub_4h.index[-1] != ts: continue

                curr_bar = sub_4h.iloc[-2]
                sig_res = self.strat.check_signals(sub_4h, sub_day, has_position=False)
                entry_signal = sig_res['entry_signal']

                if entry_signal != "NONE":
                    if np.random.rand() < self.ai_reject_rate:
                        continue

                    atr_val = sig_res['indicators_4h']['atr']
                    recent_high_4h = float(sub_4h['high'].iloc[-30:-2].max())
                    
                    if entry_signal == "BUY_G_BREAKOUT":
                        entry_price = recent_high_4h * 1.001
                    else:
                        entry_price = float(curr_bar['close'])

                    sl_price = self.risk_ctrl.find_structural_stop_loss(sub_4h, entry_price=entry_price, atr_val=atr_val, signal_type=entry_signal)
                    sizing = self.risk_ctrl.calculate_position_size(portfolio_capital, entry_price, sl_price, df_4h=sub_4h, current_portfolio_risk_usd=current_portfolio_risk_usd)

                    if sizing['status'] == "APPROVED":
                        shares = sizing['shares']
                        entry_with_slippage = entry_price * (1 + self.slippage_pct)

                        active_positions[sym] = {
                            "entry_time": ts,
                            "signal": entry_signal,
                            "entry_price": entry_with_slippage,
                            "sl": sl_price,
                            "atr": atr_val,
                            "shares": shares,
                            "position_value": shares * entry_with_slippage,
                            "max_high_reached": entry_with_slippage,
                            "bars_held": 0
                        }
                        current_portfolio_risk_usd += shares * (entry_with_slippage - sl_price)

        self.display_portfolio_report(all_trades, portfolio_capital)

    def display_portfolio_report(self, trades: list, final_capital: float):
        if not trades:
            print("\n[!] ไม่พบรายการเทรดตลอดช่วงทดสอบบน Portfolio")
            return

        df_trades = pd.DataFrame(trades)
        total_trades = len(df_trades)
        wins = df_trades[df_trades['net_pnl'] > 0]
        losses = df_trades[df_trades['net_pnl'] <= 0]

        win_rate = (len(wins) / total_trades) * 100
        total_pnl = df_trades['net_pnl'].sum()
        total_return_pct = (total_pnl / self.initial_capital) * 100

        print("\n==================================================")
        print(f"   PORTFOLIO PERFORMANCE REPORT (Webull/Nasdaq Feed)")
        print("==================================================")
        print(f" เงินทุนเริ่มต้น       : ${self.initial_capital:,.2f}")
        print(f" เงินทุนสุทธิสุดท้าย    : ${final_capital:,.2f}")
        print(f" กำไร/ขาดทุน สุทธิ     : ${total_pnl:,.2f} ({total_return_pct:+.2f}%)")
        print(f" จำนวนไม้ทั้งหมด       : {total_trades} ไม้")
        print(f" อัตราการชนะ (Win Rate): {win_rate:.2f}%")
        print("==================================================\n")

if __name__ == '__main__':
    WATCHLIST = ["ARM", "IREN", "SNDK", "AMD", "AVGO", "PLTR", "TSLA", "META", "GOOGL", "INTC"]
    backtester = MultiSymbolQuantBacktester(initial_capital=50000.0)
    backtester.run_portfolio_backtest(WATCHLIST)