"""
大盤速覽與類股漲跌（給網站用）
- 證交所 MI_INDEX：加權指數、成交金額、上漲下跌家數、各類股指數漲跌
- FinMind TaiwanStockInfo：每檔股票屬於哪個產業（每 30 天更新一次）
"""
import json
import os
import re
from datetime import datetime

import pandas as pd
import requests

from core import config
from core.data_twse import BASE, _find_table, _get, _num, is_company

INFO_FILE = os.path.join(config.DATA_DIR, "stock_industry.json")

# 這些是好幾個類股合起來的大分類，不列入族群排行
SKIP_INDEX = {"水泥窯製類指數", "塑膠化工類指數", "機電類指數", "電子工業類指數", "化學生技醫療類指數"}
# 產業名稱 → 類股指數名稱（名稱不一樣的）
IND_ALIAS = {"觀光事業": "觀光餐旅", "化學生技醫療": "生技醫療"}


def _base(name):
    """「半導體業」「水泥工業」→「半導體」「水泥」；「半導體類指數」→「半導體」"""
    name = IND_ALIAS.get(name, name)
    name = re.sub(r"類指數$", "", name)
    for suf in ("工業", "事業", "業"):
        if name.endswith(suf) and len(name) > len(suf) + 1:
            return name[: -len(suf)]
    return name


def _sign(cell):
    return -1 if "-" in re.sub(r"<[^>]+>", "", str(cell)) else 1


def fetch_market(date):
    """當天大盤速覽與各類股指數漲跌。抓不到回傳 None。"""
    js = _get(f"{BASE}/afterTrading/MI_INDEX?date={date:%Y%m%d}&type=ALLBUT0999&response=json")
    if not js or js.get("stat") != "OK":
        return None
    out = {"date": date.strftime("%Y-%m-%d"), "taiex": None, "taiex_chg": None, "taiex_pct": None,
           "value": None, "up": None, "down": None, "sectors": []}
    idx = _find_table(js, ["指數", "收盤指數", "漲跌百分比(%)"])
    if idx:
        for r in idx["data"]:
            name = str(r[0]).strip()
            pct = None if str(r[4]).strip() in ("--", "") else _num(r[4])   # 百分比本身已帶正負號
            if name == "發行量加權股價指數":
                out["taiex"] = _num(r[1])
                out["taiex_chg"] = _num(r[3]) * _sign(r[2])
                out["taiex_pct"] = pct
            elif name.endswith("類指數") and pct is not None and name not in SKIP_INDEX:
                out["sectors"].append({"name": _base(name[:-3]), "pct": pct})
    stat = _find_table(js, ["成交統計", "成交金額(元)"])
    if stat:
        for r in stat["data"]:
            if str(r[0]).startswith("證券合計"):
                out["value"] = _num(r[1])
    ud = _find_table(js, ["類型", "整體市場", "股票"])
    if ud:
        for r in ud["data"]:
            n = int(_num(str(r[2]).split("(")[0]))
            if str(r[0]).startswith("上漲"):
                out["up"] = n
            elif str(r[0]).startswith("下跌"):
                out["down"] = n
    out["sectors"].sort(key=lambda s: s["pct"], reverse=True)
    return out


def industry_map(today):
    """股票代號 → 產業（基本名稱，跟類股指數對得起來）。快取 30 天。"""
    try:
        with open(INFO_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        if (today - datetime.strptime(cache["fetched"], "%Y-%m-%d")).days < 30:
            return cache["map"]
    except Exception:
        cache = None
    try:
        params = {"dataset": "TaiwanStockInfo"}
        if config.FINMIND_TOKEN:
            params["token"] = config.FINMIND_TOKEN
        data = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=30).json().get("data", [])
    except Exception as e:
        print(f"   ⚠️ 產業分類抓取失敗：{e}")
        return cache["map"] if cache else {}
    m = {}
    for r in data:
        sid, ind = r.get("stock_id", ""), r.get("industry_category", "")
        if r.get("type") != "twse" or not is_company(sid) or ind in ("電子工業", "存託憑證", "創新板股票", "創新版股票", ""):
            continue
        m.setdefault(sid, _base(ind))
    if m:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(INFO_FILE, "w", encoding="utf-8") as f:
            json.dump({"fetched": today.strftime("%Y-%m-%d"), "map": m}, f, ensure_ascii=False)
    return m


def sector_leaders(market, chips, today, ind_map, top_n=5, leaders=3, min_value=1e8):
    """漲最多的前 N 個類股（只列真的有上漲的），每個類股附上當天漲最多的幾檔（成交金額 ≥ 1 億）"""
    if not market or not market["sectors"]:
        return []
    market = dict(market, sectors=[s for s in market["sectors"] if s["pct"] > 0])
    days = sorted(d for d in chips["date"].unique() if d <= pd.Timestamp(today.date()))
    if len(days) < 2:
        return [dict(s, leaders=[]) for s in market["sectors"][:top_n]]
    d0, d1 = days[-2], days[-1]
    a = chips[(chips["date"] == d0) & (chips["price_ok"] == 1)].set_index("stock_id")["close"]
    b = chips[(chips["date"] == d1) & (chips["price_ok"] == 1)].set_index("stock_id")
    out = []
    for s in market["sectors"][:top_n]:
        rows = []
        for sid, r in b.iterrows():
            if ind_map.get(sid) != s["name"] or sid not in a.index or a[sid] <= 0:
                continue
            if r["volume"] * r["close"] < min_value:
                continue
            p = float(r["close"] / a[sid] - 1)
            if p > 0:                                  # 領漲股只列真的有上漲的
                rows.append((p, sid, r["name"]))
        rows.sort(reverse=True)
        out.append(dict(s, leaders=[{"id": sid, "name": nm, "pct": round(p * 100, 2)} for p, sid, nm in rows[:leaders]]))
    return out
