"""
產生網站（GitHub Pages）要讀的資料檔，放在 docs/data/：
- index.json            有哪些日期的報告
- days/YYYY-MM-DD.json  每天的報告：燈號、大盤速覽、強勢族群、推薦、觀察名單（依原因分組）
- stocks/代號.json       個股頁：K 線、投信外資買賣超、被推薦紀錄、模擬交易、基本面
網頁本身（HTML、CSS、JS）也放在 docs/，不需要伺服器。
"""
import json
import math
import os

import pandas as pd

from core import config, data_finmind, notify

try:
    import yfinance as yf
except ImportError:
    yf = None

SITE_DIR = os.path.join(config.BASE_DIR, "docs", "data")

# 觀察名單分組：(代碼, 標題, 一句話說明為什麼先別買)
GROUPS = [
    ("near", "差一點上榜", "投信有買，力道排在第 6～10 名。明天可能擠進前 5。"),
    ("chase", "漲太快，等回檔", "離 20 日均線超過 10%。測試中這種股票有一半中途跌超過 10%，買了很難抱住。"),
    ("margin", "融資太高", "融資使用率 20% 以上，代表很多散戶借錢買，容易暴漲暴跌。"),
    ("loss", "近 4 季有虧損", "只要有一季賠錢就先不碰。營運不穩的公司，消息一變股價容易大跌。"),
    ("cash", "帳面賺錢，現金沒進來", "營業現金流是負的：東西賣了，錢還沒收回來，或庫存越堆越多。不一定是壞公司，但風險比較高。"),
    ("notice", "交易所列為注意股", "最近漲跌或成交量異常，交易所公告提醒。這時候進場很容易買在情緒最高點。"),
    ("punish", "交易所處置中", "交易所限制交易方式，代表之前漲跌太過頭。"),
    ("ky", "KY 股", "外國公司來台上市，資訊比較難查證，過去爆雷的比例較高。"),
    ("nodata", "資料不足", "營收、獲利或股價資料不夠，沒辦法檢查。"),
    ("weak", "投信有買，但力道較弱", "排在第 11 名以後。投信只是小量買，參考價值較低。"),
]


def _group_of(p):
    first = str(p.get("reason") or "").split("；")[0]
    rank = p.get("rank")
    if first.startswith("排名"):
        return "near" if rank and rank <= 10 else "weak"
    for key, word in [("chase", "離 20 日均線"), ("margin", "融資"), ("loss", "虧損"), ("cash", "現金流"),
                      ("notice", "注意股"), ("punish", "處置"), ("ky", "KY"), ("nodata", "不足")]:
        if word in first:
            return key
    return "weak"


def _clean(v):
    """轉成 JSON 可用的值（NaN → None、numpy → Python）"""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)


def _day_change(chips, today):
    days = sorted(d for d in chips["date"].unique() if d <= pd.Timestamp(today.date()))
    if len(days) < 2:
        return {}
    a = chips[(chips["date"] == days[-2]) & (chips["price_ok"] == 1)].set_index("stock_id")["close"]
    b = chips[(chips["date"] == days[-1]) & (chips["price_ok"] == 1)].set_index("stock_id")["close"]
    common = a.index.intersection(b.index)
    return {sid: round((b[sid] / a[sid] - 1) * 100, 2) for sid in common if a[sid] > 0}


def _ohlcv(sid, chips):
    """K 線資料：Yahoo 一年（還原除權息），抓不到就用證交所行情"""
    rows = []
    if yf is not None:
        try:
            h = yf.Ticker(f"{sid}.TW").history(period="1y", auto_adjust=True)
            if h is not None and len(h) >= 20:
                h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
                rows = [[d.strftime("%Y-%m-%d"), round(r.Open, 2), round(r.High, 2), round(r.Low, 2), round(r.Close, 2), int(r.Volume)]
                        for d, r in h.iterrows() if r.Close == r.Close]
        except Exception:
            rows = []
    c = chips[(chips["stock_id"] == sid) & (chips["price_ok"] == 1)].sort_values("date")
    have = {r[0] for r in rows}
    for _, r in c.iterrows():          # 補上 Yahoo 還沒有的最新幾天（或 Yahoo 抓不到時全部用證交所）
        d = r["date"].strftime("%Y-%m-%d")
        if d not in have and (not rows or d > rows[-1][0]):
            rows.append([d, r["open"], r["high"], r["low"], r["close"], int(r["volume"])])
    return rows


def _monthly(sid):
    """月 K：Yahoo 近 5 年月線（還原除權息）"""
    if yf is None:
        return []
    try:
        h = yf.Ticker(f"{sid}.TW").history(period="5y", interval="1mo", auto_adjust=True)
    except Exception:
        return []
    if h is None or h.empty:
        return []
    h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
    return [[d.strftime("%Y-%m-%d"), round(r.Open, 2), round(r.High, 2), round(r.Low, 2), round(r.Close, 2), int(r.Volume)]
            for d, r in h.iterrows() if r.Close == r.Close]


def build(today, light, picks, chips, trades, market, sectors, official=True, ind_map=None, all_sectors=None):
    ind_map = ind_map or {}
    hot = {s["name"] for s in (sectors or [])}
    if picks is None or picks.empty:
        picks = pd.DataFrame(columns=["stock_id", "status"])
    date = today.strftime("%Y-%m-%d")
    chg = _day_change(chips, today)
    review = notify._review_date(today)

    top = []
    for _, p in picks[picks["status"] == "top"].iterrows():
        size = round(float(p["size"]), 2)
        top.append({k: _clean(v) for k, v in {
            "id": p["stock_id"], "name": p["name"], "close": p.get("close"), "chg": chg.get(p["stock_id"]),
            "industry": ind_map.get(p["stock_id"], ""), "hot": ind_map.get(p["stock_id"]) in hot,
            "size": size, "size_label": {1.0: "", 0.5: "金額減半", 0.25: "金額 1/4"}.get(size, ""),
            "review": review, "trust_days": int(p["trust_days"]), "trust5": round(float(p["trust5_ratio"]) * 100, 1),
            "foreign_together": bool(p.get("foreign_together")), "foreign_days": int(p.get("foreign_days") or 0),
            "rev_label": p.get("rev_label") or "", "rev_yoy": p.get("rev_yoy"), "swing": p.get("swing"),
            "bias": p.get("bias"), "margin": p.get("margin"), "margin_warn": bool(p.get("margin_warn")),
            "strong": bool(p.get("strong")),
        }.items()})

    groups = {k: [] for k, _, _ in GROUPS}
    for _, p in picks[picks["status"] == "watch"].iterrows():
        d = p.to_dict()
        rank = d.get("rank")
        d["rank"] = int(rank) if rank == rank and rank is not None else None
        groups[_group_of(d)].append({"id": d["stock_id"], "name": d["name"], "rank": d["rank"],
                                     "reason": d.get("reason") or "", "chg": chg.get(d["stock_id"])})
    watch = [{"key": k, "title": t, "lesson": l, "items": groups[k]} for k, t, l in GROUPS if groups[k]]

    day = {"date": date, "official": official, "light": {k: _clean(v) for k, v in light.items()},
           "market": market, "sectors": sectors, "all_sectors": all_sectors or [], "picks": top, "watch": watch}
    _write(os.path.join(SITE_DIR, "days", f"{date}.json"), day)

    # 日期清單：正式報告優先；只有預覽報告的日期也列出（標示預覽）
    idx_path = os.path.join(SITE_DIR, "index.json")
    try:
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
    except Exception:
        idx = {"dates": []}
    dates = {d["date"]: d for d in idx["dates"]}
    if official or date not in dates or not dates[date].get("official"):
        dates[date] = {"date": date, "official": official, "light": light["light"], "n_picks": len(top)}
    idx["dates"] = sorted(dates.values(), key=lambda d: d["date"], reverse=True)
    idx["latest"] = idx["dates"][0]["date"]
    _write(idx_path, idx)

    # 個股資料：今天的推薦＋觀察名單＋模擬帳戶持有中的股票
    ids = set(picks["stock_id"]) if not picks.empty else set()
    if trades is not None and not trades.empty:
        ids |= set(trades.loc[trades["status"].isin(["pending", "open"]), "stock_id"])
    log = pd.read_csv(config.PICKS_LOG, dtype={"stock_id": str}) if os.path.exists(config.PICKS_LOG) else pd.DataFrame()
    print(f"   🌐 網站資料：{len(top)} 檔推薦、{len(ids)} 檔個股頁")
    for sid in sorted(ids):
        _write_stock(sid, chips, log, trades, picks, ind_map.get(sid, ""))


def _write_stock(sid, chips, log, trades, picks, industry=""):
    c = chips[chips["stock_id"] == sid].sort_values("date")
    name = c["name"].dropna().iloc[-1] if not c.empty else sid
    # 每天：日期、投信、外資、成交股數（算「近 5 日買超佔成交量」用）
    flows = [[d.strftime("%Y-%m-%d"), int(t), int(f), int(v)] for d, t, f, v in zip(c["date"], c["trust"], c["foreign"], c["volume"])]
    hist = []
    if not log.empty:
        for _, r in log[log["stock_id"] == sid].sort_values("date").iterrows():
            hist.append({"date": r["date"], "status": r["status"], "reason": _clean(r.get("reason")) or "",
                         "rank": _clean(r.get("rank"))})
    tr = []
    if trades is not None and not trades.empty:
        for _, t in trades[trades["stock_id"] == sid].iterrows():
            tr.append({k: _clean(t.get(k)) for k in ["signal_date", "status", "entry_date", "entry_price",
                                                       "exit_date", "exit_price", "ret", "bench_ret", "size"]})
    fund = data_finmind.summarize(data_finmind._load(sid), sid)
    p = picks[picks["stock_id"] == sid]
    latest = {k: _clean(p.iloc[0].get(k)) for k in ["status", "reason", "bias", "swing", "margin", "trust_days",
                                                      "trust5_ratio", "foreign_days"]} if not p.empty else {}
    _write(os.path.join(SITE_DIR, "stocks", f"{sid}.json"), {
        "id": sid, "name": name, "industry": industry, "ohlcv": _ohlcv(sid, chips), "ohlcv_m": _monthly(sid), "flows": flows, "history": hist,
        "trades": tr, "latest": latest,
        "fund": {"rev_yoy": _clean(fund["rev_yoy"]), "rev_label": fund["rev_label"],
                 "eps4": fund["eps4"], "cf_ttm": _clean(fund["cf_ttm"])},
    })
