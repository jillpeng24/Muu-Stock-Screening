"""
股價：優先用 Yahoo（已還原除權息），抓不到就用證交所行情（chips_history）備援。
含分割斷層修正：台股有漲跌幅限制，單日變成 1.8 倍以上或 55% 以下只可能是分割／減資。
"""
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:      # 本機測試沒裝也能跑（會改用備援資料）
    yf = None


def fix_splits(df):
    df = df.copy()
    c = df["close"].to_numpy()
    for i in range(1, len(c)):
        if c[i] <= 0 or c[i - 1] <= 0:
            continue
        x = c[i - 1] / c[i]
        if x >= 1.8 or x <= 1 / 1.8:
            n = round(x) if x >= 1 else 1 / round(1 / x)
            ratio = n if abs(x / n - 1) < 0.05 else x
            df.iloc[:i, df.columns.get_indexer(["high", "low", "close"])] /= ratio
            c = df["close"].to_numpy()
    return df


def yahoo(symbol, period="6mo"):
    if yf is None:
        return pd.DataFrame()
    try:
        h = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    except Exception:
        return pd.DataFrame()
    if h is None or h.empty:
        return pd.DataFrame()
    h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    return pd.DataFrame({"high": h["High"], "low": h["Low"], "close": h["Close"]}).dropna()


def from_chips(chips, sid):
    d = chips[(chips["stock_id"] == sid) & (chips["price_ok"] == 1)]
    if d.empty:
        return pd.DataFrame()
    return d.set_index("date")[["high", "low", "close"]].sort_index()


def stock_history(sid, chips):
    h = yahoo(f"{sid}.TW")
    if len(h) < 25:
        h = from_chips(chips, sid)
    if h.empty:
        return h
    h = fix_splits(h)
    # 用證交所當天收盤補上 Yahoo 可能還沒更新的最新一天
    last = chips[(chips["stock_id"] == sid) & (chips["price_ok"] == 1)].sort_values("date").tail(1)
    if not last.empty:
        d = last["date"].iloc[0]
        if d > h.index.max():
            h.loc[d] = [last["high"].iloc[0], last["low"].iloc[0], last["close"].iloc[0]]
    return h.sort_index()


def price_features(h):
    """離 20 日均線多遠、一個月內的高低差（過去 60 天平均）"""
    if len(h) < 21:
        return {"close": float(h["close"].iloc[-1]) if len(h) else None, "bias": None, "swing": None}
    c = h["close"]
    ma20 = c.rolling(20).mean()
    rng = (h["high"].rolling(20).max() / h["low"].rolling(20).min() - 1).tail(60)
    return {"close": float(c.iloc[-1]),
            "ma20": float(ma20.iloc[-1]),
            "bias": float(c.iloc[-1] / ma20.iloc[-1] - 1),
            "swing": float(np.nanmean(rng)) if rng.notna().any() else None}
