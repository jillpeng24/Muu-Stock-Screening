"""
紀錄與成績單
- picks_log.csv：每天所有候選股（推薦、觀察）都記下來，永久保存
- sim_trades.csv：模擬帳戶。照規則「假裝買賣」：推薦隔天收盤買進，持有 20 個交易日後收盤賣出
  黃燈金額減半、紅燈不買；同一檔還在持有中就不重複買
"""
import os

import pandas as pd

from core import config, data_price

TRADE_COLS = ["signal_date", "stock_id", "name", "size", "light", "status",
              "entry_date", "entry_price", "exit_date", "exit_price", "ret", "bench_ret"]


def append_picks(df):
    if df is None or df.empty:
        return
    keep = ["date", "stock_id", "name", "status", "rank", "cat", "trust_days", "trust5_ratio", "foreign_days", "foreign_together",
            "strong", "rev_yoy", "fund_ok", "close", "bias", "swing", "margin", "margin_warn", "size", "reason"]
    d = df[[c for c in keep if c in df.columns]]
    if os.path.exists(config.PICKS_LOG):
        old = pd.read_csv(config.PICKS_LOG, dtype={"stock_id": str})
        old = old[old["date"] != d["date"].iloc[0]]          # 同一天重跑就覆蓋
        d = pd.concat([old, d], ignore_index=True)
    d.to_csv(config.PICKS_LOG, index=False, encoding="utf-8-sig")


def _load_trades():
    if os.path.exists(config.TRADES_FILE):
        tr = pd.read_csv(config.TRADES_FILE, dtype=str, keep_default_na=False)
        tr = tr.reindex(columns=TRADE_COLS).astype(object)
        for c in ["size", "entry_price", "exit_price", "ret", "bench_ret"]:
            tr[c] = pd.to_numeric(tr[c], errors="coerce").astype(object)
        return tr
    return pd.DataFrame(columns=TRADE_COLS, dtype=object)


def _close_on(chips, sid, date):
    r = chips[(chips["stock_id"] == sid) & (chips["date"] == pd.Timestamp(date)) & (chips["price_ok"] == 1)]
    return float(r["close"].iloc[0]) if not r.empty else None


def _adj_return(sid, d0, d1, fallback):
    """用 Yahoo 還原股價計算報酬（含除權息）；抓不到就用證交所收盤價"""
    h = data_price.yahoo(f"{sid}.TW", period="1y")
    try:
        return float(h.loc[pd.Timestamp(d1), "close"] / h.loc[pd.Timestamp(d0), "close"] - 1)
    except Exception:
        return fallback


def update_trades(chips, today, picks, light):
    """回傳 (今天到期的交易清單, 全部交易)"""
    tr = _load_trades()
    days = [d for d in sorted(chips["date"].unique()) if d <= pd.Timestamp(today.date())]
    idx = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(days)}
    today_s = today.strftime("%Y-%m-%d")
    due_today = []

    for i, t in tr.iterrows():
        # 1) 待買進：推薦日的下一個交易日收盤買進
        if t["status"] == "pending" and t["signal_date"] in idx:
            k = idx[t["signal_date"]] + 1
            if k < len(days):
                d = days[k].strftime("%Y-%m-%d")
                px = _close_on(chips, t["stock_id"], d)
                if px:
                    tr.loc[i, ["status", "entry_date", "entry_price"]] = ["open", d, px]
        # 2) 持有中：滿 20 個交易日賣出
        t = tr.loc[i]
        if t["status"] == "open" and t["entry_date"] in idx:
            k = idx[t["entry_date"]] + config.HOLD_DAYS
            if k < len(days):
                d = days[k].strftime("%Y-%m-%d")
                px = _close_on(chips, t["stock_id"], d)
                if px:
                    raw = px / float(t["entry_price"]) - 1
                    b0, b1 = _close_on(chips, "0050", t["entry_date"]), _close_on(chips, "0050", d)
                    tr.loc[i, ["status", "exit_date", "exit_price"]] = ["closed", d, px]
                    tr.loc[i, "ret"] = round(_adj_return(t["stock_id"], t["entry_date"], d, raw), 4)
                    tr.loc[i, "bench_ret"] = round(_adj_return("0050", t["entry_date"], d, (b1 / b0 - 1) if b0 and b1 else None) or 0, 4)
                    if d == today_s:
                        due_today.append(tr.loc[i].to_dict())

    # 3) 今天的新推薦 → 待買進（紅燈不買、持有中不重複買）
    held = set(tr.loc[tr["status"].isin(["pending", "open"]), "stock_id"])
    if picks is not None and not picks.empty:
        for _, p in picks[(picks["status"] == "top") & (picks["size"] > 0)].iterrows():
            if p["stock_id"] in held or ((tr["signal_date"] == today_s) & (tr["stock_id"] == p["stock_id"])).any():
                continue
            tr.loc[len(tr)] = {"signal_date": today_s, "stock_id": p["stock_id"], "name": p["name"],
                               "size": p["size"], "light": light["light"], "status": "pending"}
    tr.to_csv(config.TRADES_FILE, index=False, encoding="utf-8-sig")
    return due_today, tr


def scorecard(tr, today, lookback_days=30):
    """近 30 天到期的模擬交易成績"""
    c = tr[tr["status"] == "closed"].copy()
    if c.empty:
        return None
    c["exit_date"] = pd.to_datetime(c["exit_date"])
    recent = c[c["exit_date"] >= pd.Timestamp(today.date()) - pd.Timedelta(days=lookback_days)]
    if recent.empty:
        return None
    return {"n": len(recent), "avg": float(recent["ret"].mean()), "bench": float(recent["bench_ret"].mean()),
            "wins": int((recent["ret"] > 0).sum()),
            "all_n": len(c), "all_avg": float(c["ret"].mean()), "all_bench": float(c["bench_ret"].mean())}
