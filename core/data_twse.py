"""
證交所資料：三大法人買賣超（T86）、每日收盤行情（MI_INDEX）、融資（MI_MARGN）、處置股（punish）、注意股（notice）。
所有數量單位都是「股」。
"""
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from core import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.twse.com.tw/",
}
BASE = "https://www.twse.com.tw/rwd/zh"
KEEP_ETFS = {"0050"}   # 除了一般公司股票，另外保留 0050 的行情（大盤燈號、成績單比較用）


def _num(x):
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "--", "X"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _get(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"   ⚠️ 連線失敗（第 {i + 1} 次）：{e}")
        time.sleep(config.TWSE_SLEEP * (i + 1))
    return None


def is_company(sid):
    """一般公司股票：4 碼數字、不以 0 開頭"""
    return len(sid) == 4 and sid.isdigit() and not sid.startswith("0")


def _find_table(js, must_have):
    """在新版回傳格式（tables）中，找出欄位包含指定文字的表格"""
    for t in js.get("tables", []) or []:
        fields = t.get("fields") or []
        if all(any(k in f for f in fields) for k in must_have):
            return t
    return None


def fetch_day(date):
    """抓取某一天的法人買賣超＋收盤行情。當天沒資料（休市或尚未公布）回傳 None。"""
    d = date.strftime("%Y%m%d")
    js = _get(f"{BASE}/fund/T86?date={d}&selectType=ALLBUT0999&response=json")
    if not js or js.get("stat") != "OK":
        return None
    f = js["fields"]
    i_f = f.index("外陸資買賣超股數(不含外資自營商)")
    i_t = f.index("投信買賣超股數")
    i_d = f.index("自營商買賣超股數")
    inst = {}
    for r in js["data"]:
        sid = r[0].strip()
        if is_company(sid) or sid in KEEP_ETFS:
            inst[sid] = (r[1].strip(), _num(r[i_f]), _num(r[i_t]), _num(r[i_d]))

    time.sleep(config.TWSE_SLEEP)
    mi = _get(f"{BASE}/afterTrading/MI_INDEX?date={d}&type=ALLBUT0999&response=json")
    t = _find_table(mi or {}, ["證券代號", "成交股數", "收盤價"])
    if t is None:
        print(f"   ⚠️ {d} 抓不到收盤行情，成交量與價格標示為缺漏")
    price = {}
    if t:
        f2 = t["fields"]
        ix = {k: f2.index(k) for k in ["證券代號", "證券名稱", "成交股數", "開盤價", "最高價", "最低價", "收盤價"]}
        for r in t["data"]:
            sid = str(r[ix["證券代號"]]).strip()
            if is_company(sid) or sid in KEEP_ETFS:
                price[sid] = (str(r[ix["證券名稱"]]).strip(), _num(r[ix["成交股數"]]), _num(r[ix["開盤價"]]),
                              _num(r[ix["最高價"]]), _num(r[ix["最低價"]]), _num(r[ix["收盤價"]]))

    rows = []
    for sid in set(inst) | set(price):
        name_i, fo, tr, de = inst.get(sid, ("", 0.0, 0.0, 0.0))
        name_p, vol, o, h, l, c = price.get(sid, ("", 0.0, 0.0, 0.0, 0.0, 0.0))
        rows.append({"date": date.strftime("%Y-%m-%d"), "stock_id": sid, "name": name_i or name_p,
                     "foreign": fo, "trust": tr, "dealer": de, "volume": vol,
                     "open": o, "high": h, "low": l, "close": c,
                     "price_ok": int(sid in price and c > 0)})
    return pd.DataFrame(rows)


def market_open_today(today):
    """用證交所即時系統確認今天有沒有開市。無法判斷時回傳 None。"""
    try:
        r = requests.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw",
                         headers=HEADERS, timeout=15)
        return r.json()["msgArray"][0]["d"] == today.strftime("%Y%m%d")
    except Exception:
        return None


def load_chips():
    if os.path.exists(config.CHIPS_FILE):
        df = pd.read_csv(config.CHIPS_FILE, dtype={"stock_id": str})
        df["date"] = pd.to_datetime(df["date"])
        return df
    return pd.DataFrame()


def update_chips(today):
    """補齊到今天的法人＋行情資料。回傳 (完整資料, 今天是否有資料)"""
    old = load_chips()
    if old.empty:
        start = today - timedelta(days=config.BACKFILL_DAYS)
        print(f"🚀 第一次執行：補抓 {start:%Y-%m-%d} 起的資料（約需幾分鐘）")
    else:
        start = old["date"].max() + timedelta(days=1)
    new = []
    d = start
    while d.date() <= today.date():
        if d.weekday() < 5:
            day = fetch_day(d)
            if day is not None and not day.empty:
                new.append(day)
                print(f"   ✅ {d:%Y-%m-%d}：{len(day)} 檔")
            time.sleep(config.TWSE_SLEEP)
        d += timedelta(days=1)
    if new:
        add = pd.concat(new, ignore_index=True)
        add["date"] = pd.to_datetime(add["date"])
        df = pd.concat([old, add], ignore_index=True) if not old.empty else add
        df = df.drop_duplicates(["date", "stock_id"], keep="last").sort_values(["date", "stock_id"])
        keep = sorted(df["date"].unique())[-config.CHIPS_KEEP_DAYS:]
        df = df[df["date"].isin(keep)]
        os.makedirs(config.DATA_DIR, exist_ok=True)
        df.to_csv(config.CHIPS_FILE, index=False, encoding="utf-8-sig")
    else:
        df = old
    has_today = (not df.empty) and df["date"].max().date() == today.date()
    return df, has_today


def fetch_margin(today, look_back=6):
    """融資使用率（%）＝ 融資今日餘額 ÷ 次一營業日限額。當天尚未公布就往前找最近一天。"""
    for k in range(look_back):
        d = today - timedelta(days=k)
        if d.weekday() >= 5:
            continue
        js = _get(f"{BASE}/marginTrading/MI_MARGN?date={d:%Y%m%d}&selectType=ALL&response=json")
        t = _find_table(js or {}, ["代號", "今日餘額", "次一營業日限額"])
        if t:
            f = t["fields"]
            i_bal = f.index("今日餘額")           # 第一次出現的是融資
            i_lim = f.index("次一營業日限額")
            out = {}
            for r in t["data"]:
                sid = str(r[0]).strip()
                lim = _num(r[i_lim])
                if lim > 0:
                    out[sid] = round(_num(r[i_bal]) / lim * 100, 1)
            return out, d.strftime("%Y-%m-%d")
        time.sleep(config.TWSE_SLEEP)
    return {}, None


def _roc(s):
    y, m, d = s.strip().split("/")
    return datetime(int(y) + 1911, int(m), int(d))


def fetch_punish(today):
    """目前處置中（或即將開始處置）的股票代號"""
    start = (today - timedelta(days=30)).strftime("%Y%m%d")
    js = _get(f"{BASE}/announcement/punish?startDate={start}&endDate={today:%Y%m%d}&response=json")
    out = set()
    if not js or js.get("stat") != "OK":
        return out
    f = js["fields"]
    i_id, i_rng = f.index("證券代號"), f.index("處置起迄時間")
    for r in js["data"]:
        try:
            a, b = str(r[i_rng]).split("～")
            if _roc(b).date() >= today.date():
                out.add(str(r[i_id]).strip())
        except Exception:
            continue
    return out


def fetch_notice(today):
    """最近幾天被公布為「注意有價證券」的股票代號"""
    start = (today - timedelta(days=config.NOTICE_LOOKBACK_DAYS)).strftime("%Y%m%d")
    js = _get(f"{BASE}/announcement/notice?startDate={start}&endDate={today:%Y%m%d}&response=json")
    out = set()
    if not js or js.get("stat") != "OK":
        return out
    i_id = js["fields"].index("證券代號")
    for r in js.get("data", []):
        sid = str(r[i_id]).strip()
        if is_company(sid):
            out.add(sid)
    return out
