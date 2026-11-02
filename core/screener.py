"""
篩選與排序
  ① 候選：A 外資＋投信同買 3 天，或 B 投信連買 4 天（同買的在推播加註「外資同步買」）
  ② 避雷：近 4 季 EPS 為正、近 4 季營業現金流為正、非處置股、非注意股、非 KY 股
     （全額交割股多為虧損或財報延遲，已被 EPS／現金流條件排除）
  ③ 風險：離 20 日均線 ≤ 10%、融資使用率 < 20%
  ④ 排序：投信 5 日買超佔成交量，前 5 名推薦，其餘列觀察名單
"""
import pandas as pd

from core import config, data_finmind, data_price
from core.data_twse import is_company


def chip_candidates(chips, today):
    dates = sorted(chips["date"].unique())
    dates = [d for d in dates if d <= pd.Timestamp(today.date())][-40:]
    if len(dates) < config.PATTERN_B_DAYS:
        return pd.DataFrame()
    sub = chips[chips["date"].isin(dates) & chips["stock_id"].map(is_company)]
    T = sub.pivot(index="date", columns="stock_id", values="trust").reindex(dates).fillna(0)
    F = sub.pivot(index="date", columns="stock_id", values="foreign").reindex(dates).fillna(0)
    V = sub.pivot(index="date", columns="stock_id", values="volume").reindex(dates).fillna(0)
    names = sub.sort_values("date").groupby("stock_id")["name"].last()

    def streak(col):
        n = 0
        for v in col[::-1]:
            if v > 0:
                n += 1
            else:
                break
        return n

    a = config.PATTERN_A_DAYS
    rows = []
    for sid in T.columns:
        t, f = T[sid].to_numpy(), F[sid].to_numpy()
        A = (t[-a:] > 0).all() and (f[-a:] > 0).all()
        B = (t[-config.PATTERN_B_DAYS:] > 0).all()
        if not (A or B):
            continue
        w = config.TRUST_WINDOW
        vol5 = V[sid].to_numpy()[-w:].sum()
        rows.append({"stock_id": sid, "name": names.get(sid, ""),
                     "cat": ("A" if A else "") + ("B" if B else ""),
                     "trust_days": streak(t), "foreign_days": streak(f),
                     "trust5_ratio": float(t[-w:].sum() / vol5) if vol5 > 0 else 0.0,
                     "trust_today": float(t[-1]), "foreign_together": bool(A)})
    return pd.DataFrame(rows)


def evaluate(cands, chips, today, light, margin, punish, notice=None):
    notice = notice or set()
    out = []
    for _, c in cands.iterrows():
        r = c.to_dict()
        r["date"] = today.strftime("%Y-%m-%d")
        reasons = []
        sid = r["stock_id"]
        f = data_finmind.get_fundamentals(sid, today)
        r.update({"rev_yoy": f["rev_yoy"], "rev_label": f["rev_label"], "fund_ok": f["ok"]})
        if f["ok"] is not True:
            reasons.append(f["reason"])
        if sid in punish:
            reasons.append("處置股")
        if sid in notice:
            reasons.append("注意股")
        if config.EXCLUDE_KY and "KY" in str(r["name"]).upper():
            reasons.append("KY 股")
        h = data_price.stock_history(sid, chips)
        p = data_price.price_features(h) if not h.empty else {"close": None, "bias": None, "swing": None}
        r.update({"close": p["close"], "bias": p["bias"], "swing": p["swing"]})
        if p["bias"] is None:
            reasons.append("價格資料不足")
        elif p["bias"] > config.MAX_BIAS:
            reasons.append(f"離 20 日均線 {p['bias'] * 100:.0f}%，等回檔")
        m = margin.get(sid)
        r["margin"] = m
        if m is not None and m >= config.MARGIN_EXCLUDE:
            reasons.append(f"融資 {m:.0f}%，震盪大")
        r["strong"] = bool(r["trust5_ratio"] >= config.STRONG_TRUST_RATIO or r["trust_days"] >= config.STRONG_TRUST_DAYS)
        r["margin_warn"] = bool(m is not None and config.MARGIN_WARN <= m < config.MARGIN_EXCLUDE)
        r["reason"] = "；".join(reasons)
        r["status"] = "eligible" if not reasons else "watch"
        out.append(r)

    df = pd.DataFrame(out)
    if df.empty:
        return df
    elig = df[df["status"] == "eligible"].sort_values("trust5_ratio", ascending=False)
    df["rank"] = float("nan")
    for i, idx in enumerate(elig.index, 1):
        df.loc[idx, "rank"] = i
        if i <= config.TOP_N:
            df.loc[idx, "status"] = "top"
        else:
            df.loc[idx, "status"] = "watch"
            df.loc[idx, "reason"] = f"排名第 {i}，買超力道較弱"
    # 建議金額：大盤燈號 × 融資警示
    df["size"] = 0.0
    top = df["status"] == "top"
    df.loc[top, "size"] = light["size"] * df.loc[top, "margin_warn"].map(lambda w: 0.5 if w else 1.0)
    order = {"top": 0, "watch": 1}
    df["_o"] = df["status"].map(order)
    df = df.sort_values(["_o", "rank", "trust5_ratio"], ascending=[True, True, False]).drop(columns="_o")
    return df.reset_index(drop=True)
