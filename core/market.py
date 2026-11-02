"""
大盤紅綠燈
  🟢 綠燈：0050 週收盤在 20 週均線之上 → 正常布局
  🟡 黃燈：0050 跌破 20 週均線，但美股仍在 200 日均線之上 → 新買進金額減半
  🔴 紅燈：0050 跌破 20 週均線，且美股也跌破 200 日均線 → 暫停新買進
台股以「最近一個完整週」的週收盤判斷（測試時是每週五檢查一次）。
"""
import os

import pandas as pd

from core import config, data_price

LIGHTS = {
    "green": ("🟢", "大盤綠燈：可正常布局"),
    "yellow": ("🟡", "大盤黃燈：台股轉弱，新買進金額減半"),
    "red": ("🔴", "大盤紅燈：台美股都轉弱，暫停買進新股票"),
}


def _tw_weekly(today, chips):
    h = data_price.yahoo("0050.TW", period="2y")
    if len(h) < 120:
        h = data_price.from_chips(chips, "0050")
    if h.empty:
        return None
    h = data_price.fix_splits(h)
    h = h[h.index <= pd.Timestamp(today.date())]
    w = h["close"].resample("W-FRI").last().dropna()
    # 本週還沒結束（今天不是週五）就不採用本週
    if today.weekday() < 4 and len(w) and w.index[-1] >= pd.Timestamp(today.date()):
        w = w.iloc[:-1]
    if len(w) < config.TW_TREND_WEEKS:
        return None
    ma = w.rolling(config.TW_TREND_WEEKS).mean()
    return {"week": w.index[-1].strftime("%Y-%m-%d"), "close": float(w.iloc[-1]), "ma": float(ma.iloc[-1]),
            "ok": bool(w.iloc[-1] > ma.iloc[-1])}


def _us_trend():
    h = data_price.yahoo("^GSPC", period="2y")
    if len(h) < config.US_TREND_DAYS:
        return None
    ma = h["close"].rolling(config.US_TREND_DAYS).mean()
    return {"date": h.index[-1].strftime("%Y-%m-%d"), "close": float(h["close"].iloc[-1]),
            "ma": float(ma.iloc[-1]), "ok": bool(h["close"].iloc[-1] > ma.iloc[-1])}


def get_light(today, chips):
    tw, us = _tw_weekly(today, chips), _us_trend()
    note = ""
    if tw is None:
        light, note = "green", "（台股資料不足，暫以綠燈處理）"
    elif tw["ok"]:
        light = "green"
        if us is not None and not us["ok"]:
            note = "（美股已跌破 200 日均線，留意）"
    else:
        light = "red" if (us is not None and not us["ok"]) else "yellow"
    emoji, text = LIGHTS[light]
    res = {"date": today.strftime("%Y-%m-%d"), "light": light, "emoji": emoji, "text": text + note,
           "tw_week": tw["week"] if tw else "", "tw_close": tw["close"] if tw else None,
           "tw_ma20w": tw["ma"] if tw else None, "us_close": us["close"] if us else None,
           "us_ma200": us["ma"] if us else None,
           "size": {"green": 1.0, "yellow": 0.5, "red": 0.0}[light]}
    _save(res)
    return res


def _save(res):
    row = pd.DataFrame([{k: v for k, v in res.items() if k != "size"}])
    if os.path.exists(config.MARKET_FILE):
        old = pd.read_csv(config.MARKET_FILE, dtype=str)
        row = pd.concat([old[old["date"] != res["date"]], row.astype(str)], ignore_index=True)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    row.to_csv(config.MARKET_FILE, index=False, encoding="utf-8-sig")
