"""
每日主程式：抓資料 → 大盤燈號 → 選股 → 紀錄 → LINE 群發
每個交易日由 Google Apps Script 約 16:30 觸發；資料還沒公布會每 10 分鐘重試，最多到 17:30。當天已經產生過報告就直接結束。
用法：
  python run_daily.py              正常執行
  DRY_RUN=1 python run_daily.py    只預覽 LINE 訊息，不發送
  FORCE=1 python run_daily.py      今天已經跑過也重跑
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from core import config, data_twse, market, market_summary, notify, screener, site, tracker

TW = timezone(timedelta(hours=8))


def main():
    today = datetime.now(TW).replace(tzinfo=None)
    if os.environ.get("TODAY"):                       # 測試用：指定日期
        today = datetime.strptime(os.environ["TODAY"], "%Y-%m-%d")
    print(f"=== 每日選股 {today:%Y-%m-%d %H:%M} ===")
    prefix = "dryrun_" if config.DRY_RUN else ""      # 預覽模式另存檔名，不會擋掉正式執行
    report_path = os.path.join(config.REPORT_DIR, f"{prefix}{today:%Y-%m-%d}.json")
    if os.path.exists(report_path) and os.environ.get("FORCE") != "1" and not config.DRY_RUN:
        print("✅ 今天的報告已經產生過，結束。")
        return
    if today.weekday() >= 5:
        print("📅 週末休市，結束。")
        return

    if not os.environ.get("TODAY") and data_twse.market_open_today(today) is False:
        print("📅 證交所確認今天休市，結束。")
        return

    print("\n① 更新法人與行情資料")
    chips, has_today = data_twse.update_chips(today)
    # 資料還沒公布：每 10 分鐘再檢查一次，最多等到 17:30
    while not has_today and not os.environ.get("TODAY") and (datetime.now(TW).hour, datetime.now(TW).minute) < (17, 30):
        print(f"⏳ {datetime.now(TW):%H:%M} 證交所今天的資料還沒公布，10 分鐘後再試…")
        time.sleep(600)
        chips, has_today = data_twse.update_chips(today)
    if not has_today:
        print("📅 今天沒有資料（休市），結束。")
        return

    print("\n② 大盤紅綠燈")
    light = market.get_light(today, chips)
    print(f"   {light['emoji']} {light['text']}")

    print("\n③ 融資與處置股")
    margin, margin_date = data_twse.fetch_margin(today)
    punish = data_twse.fetch_punish(today)
    notice = data_twse.fetch_notice(today)
    print(f"   融資資料日期：{margin_date}｜處置股 {len(punish)} 檔｜注意股 {len(notice)} 檔")

    print("\n④ 篩選與排序")
    cands = screener.chip_candidates(chips, today)
    n_both = int(cands["foreign_together"].sum()) if not cands.empty else 0
    print(f"   候選 {len(cands)} 檔（其中外資投信同買 {n_both} 檔）")
    picks = screener.evaluate(cands, chips, today, light, margin, punish, notice) if not cands.empty else None
    if picks is not None and not picks.empty:
        for _, p in picks[picks["status"] == "top"].iterrows():
            print(f"   ⭐ {p['stock_id']} {p['name']}  投信佔量 {p['trust5_ratio'] * 100:.1f}%  連買 {p['trust_days']} 天")

    print("\n⑤ 紀錄與模擬帳戶")
    tracker.append_picks(picks)
    due_today, trades = tracker.update_trades(chips, today, picks, light)
    card = tracker.scorecard(trades, today)

    print("\n⑥ LINE 推播")
    text = notify.build_message(today, light, picks, card, due_today)
    sent = notify.broadcast(text)

    os.makedirs(config.REPORT_DIR, exist_ok=True)
    report = {"date": f"{today:%Y-%m-%d}", "light": light, "margin_date": margin_date,
              "picks": [] if picks is None else json.loads(picks.to_json(orient="records", force_ascii=False)),
              "due_today": due_today, "scorecard": card, "message": text, "sent": sent}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n💾 報告已存：{report_path}")

    print("\n⑦ 更新網站資料")
    try:                                              # 網站出錯不影響選股與 LINE
        mk = market_summary.fetch_market(today)
        ind = market_summary.industry_map(today)
        sectors = market_summary.sector_leaders(mk, chips, today, ind)
        mk_brief = {k: v for k, v in (mk or {}).items() if k != "sectors"} or None
        site.build(today, light, picks, chips, trades, mk_brief, sectors, official=not config.DRY_RUN, ind_map=ind,
                   all_sectors=(mk or {}).get("sectors"))
    except Exception as e:
        print(f"   ⚠️ 網站資料更新失敗（不影響選股）：{e}")


if __name__ == "__main__":
    sys.exit(main())
