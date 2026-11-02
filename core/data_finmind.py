"""
FinMind 基本面：月營收、EPS、營業現金流。只查當天候選股，並快取在 data/fundamentals/。
- 月營收：有新月份才重抓
- EPS、現金流：每 30 天重抓一次
"""
import json
import os
from datetime import datetime, timedelta

import requests

from core import config

API = "https://api.finmindtrade.com/api/v4/data"
_limit_hit = False


def _fetch(dataset, sid, start):
    global _limit_hit
    if _limit_hit:
        return None
    params = {"dataset": dataset, "data_id": sid, "start_date": start}
    if config.FINMIND_TOKEN:
        params["token"] = config.FINMIND_TOKEN
    try:
        js = requests.get(API, params=params, timeout=30).json()
    except Exception as e:
        print(f"   ⚠️ FinMind {sid} {dataset} 失敗：{e}")
        return None
    if "upper limit" in str(js.get("msg", "")):
        print("   ⏳ FinMind 達到每小時查詢上限，本次改用快取資料")
        _limit_hit = True
        return None
    return js.get("data", [])


def _path(sid):
    return os.path.join(config.FUND_DIR, f"{sid}.json")


def _load(sid):
    try:
        with open(_path(sid), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(sid, d):
    os.makedirs(config.FUND_DIR, exist_ok=True)
    with open(_path(sid), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def _expected_revenue_key(today):
    """依法規，上月營收最晚在每月 10 日前公布。FinMind 的日期是「公布月份的 1 號」。"""
    first = today.replace(day=1)
    if today.day < 11:
        first = (first - timedelta(days=1)).replace(day=1)
    return first.strftime("%Y-%m-%d")


def _quarterly_from_ytd(rows):
    """現金流量表是「年初累計」，換算成單季數字"""
    by = {r["date"]: r["value"] for r in rows}
    out = []
    for d in sorted(by):
        y, m = d[:4], d[5:7]
        prev = {"06": f"{y}-03-31", "09": f"{y}-06-30", "12": f"{y}-09-30"}.get(m)
        if prev is None:
            out.append((d, by[d]))
        elif prev in by:
            out.append((d, by[d] - by[prev]))
    return out


def get_fundamentals(sid, today):
    c = _load(sid)
    today_s = today.strftime("%Y-%m-%d")
    start2y = (today - timedelta(days=800)).strftime("%Y-%m-%d")

    # 月營收
    rev = c.get("revenue", [])
    latest_key = rev[-1][0] if rev else ""
    if latest_key < _expected_revenue_key(today) and c.get("rev_checked") != today_s:
        data = _fetch("TaiwanStockMonthRevenue", sid, start2y)
        if data is not None:
            rev = sorted([[r["date"], r["revenue"], r.get("revenue_year"), r.get("revenue_month")] for r in data])
            c["revenue"] = rev
            c["rev_checked"] = today_s

    # EPS、營業現金流
    q_at = c.get("q_fetched", "")
    if not q_at or (today - datetime.strptime(q_at, "%Y-%m-%d")).days >= config.FUND_REFRESH_DAYS:
        fs = _fetch("TaiwanStockFinancialStatements", sid, start2y)
        cf = _fetch("TaiwanStockCashFlowsStatement", sid, start2y)
        if fs is not None and cf is not None:
            c["eps"] = sorted([[r["date"], r["value"]] for r in fs if r.get("type") == "EPS"])
            c["cf"] = _quarterly_from_ytd([r for r in cf if r.get("type") == "CashFlowsFromOperatingActivities"])
            c["q_fetched"] = today_s
    _save(sid, c)
    return summarize(c, sid)


# 金融股（銀行、保險、證券）：存放款、投資買賣都算在營業活動裡，營業現金流正負不代表經營好壞，不檢查
FINANCE_EXTRA = {"5876", "5880", "6005", "6024"}


def is_finance(sid):
    return sid.startswith("28") or sid in FINANCE_EXTRA


def summarize(c, sid=""):
    out = {"rev_yoy": None, "rev_label": "", "eps4": None, "cf_ttm": None, "ok": None, "reason": ""}
    rev = c.get("revenue", [])
    if len(rev) >= 13:
        last, prev = rev[-1], rev[-13]
        if prev[1]:
            out["rev_yoy"] = round((last[1] / prev[1] - 1) * 100, 1)
            out["rev_label"] = f"{last[3]}月" if last[3] else ""
    eps = c.get("eps", [])
    cf = c.get("cf", [])
    if len(eps) >= 4:
        out["eps4"] = [e[1] for e in eps[-4:]]
    if len(cf) >= 4:
        out["cf_ttm"] = sum(v for _, v in cf[-4:])
    # 避雷判斷
    if out["eps4"] is None or out["cf_ttm"] is None:
        out["ok"], out["reason"] = None, "基本面資料不足"
    elif min(out["eps4"]) <= 0:
        out["ok"], out["reason"] = False, "近 4 季有虧損"
    elif out["cf_ttm"] <= 0 and not is_finance(sid):
        out["ok"], out["reason"] = False, "營業現金流為負"
    else:
        out["ok"] = True
    return out
