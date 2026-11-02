"""
LINE 推播：用「群發（broadcast）」，所有加機器人為好友的人都會收到，不需要知道 LINE ID。
DRY_RUN=1 時只印出訊息內容，不實際發送。
"""
from datetime import timedelta

import requests

from core import config

BROADCAST = "https://api.line.me/v2/bot/message/broadcast"
WEEKDAY = "一二三四五六日"


def _review_date(today):
    """推薦日 → 隔天買進 → 再 20 個交易日（以平日估算，遇到假日會晚幾天）"""
    d, n = today, 0
    while n < config.HOLD_DAYS + 1:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return f"{d.month}/{d.day}"


def _pct(x, digits=0):
    return f"{x * 100:+.{digits}f}%"


def build_message(today, light, picks, card, due_today):
    lines = [f"📅 {today.month}/{today.day}（{WEEKDAY[today.weekday()]}）今日選股",
             f"{light['emoji']} {light['text']}", ""]
    top = picks[picks["status"] == "top"] if picks is not None and not picks.empty else picks
    red = light["light"] == "red"
    if red:
        lines += ["以下僅供觀察，先不要買新的股票", "已經買的，照原本的日期繼續抱著就好", ""]
    if top is None or top.empty:
        lines += ["今天沒有符合條件的股票", ""]
    else:
        review = _review_date(today)
        for i, (_, p) in enumerate(top.iterrows(), 1):
            star = " ⭐" if p.get("strong") else ""
            lines.append(f"{i}. {p['stock_id']} {p['name']}{star}")
            px = f"約 {p['close']:.1f} 元" if p.get("close") else ""
            if red:
                lines.append(f"   👀 觀察就好，先不要買（今日收盤 {px.replace('約 ', '')}）")
            else:
                half = "（金額減半）" if p["size"] < 1 else ""
                lines.append(f"   👉 明天可買{half}，參考價{px}")
                lines.append(f"   ⏰ 抱到約 {review} 再檢視")
            info = [f"投信連買 {int(p['trust_days'])} 天"]
            if p.get("foreign_together"):
                info.append(f"外資同步買 {int(p['foreign_days'])} 天")
            if p.get("rev_yoy") is not None and p.get("rev_yoy") == p.get("rev_yoy"):
                lab = p.get("rev_label") or ""
                info.append(f"{lab}營收年增 {p['rev_yoy']:.0f}%" if p["rev_yoy"] >= 0 else f"{lab}營收年減 {abs(p['rev_yoy']):.0f}%")
            lines.append("   📊 " + "｜".join(info))
            if not red and p.get("swing") and p["swing"] == p["swing"]:
                lines.append(f"   ⚠️ 一個月內高低差約 {p['swing'] * 100:.0f}%，跌了先別慌")
            if p.get("margin_warn"):
                lines.append(f"   ⚠️ 融資偏高（{p['margin']:.0f}%），震盪較大")
            lines.append("")
    if due_today:
        lines.append("⏰ 到期提醒（持有滿 20 個交易日）")
        for t in due_today:
            lines.append(f"・{t['stock_id']} {t['name']}（{t['signal_date'][5:].replace('-', '/')} 推薦）{_pct(t['ret'], 1)}")
        lines += ["可以考慮賣出，或依自己的判斷繼續持有", ""]
    if card:
        lines.append(f"📈 成績單：近 30 天到期 {card['n']} 檔，平均 {_pct(card['avg'], 1)}"
                     f"（0050 同期 {_pct(card['bench'], 1)}），上漲 {card['wins']} 檔")
    n_watch = int((picks["status"] == "watch").sum()) if picks is not None and not picks.empty else 0
    if config.WEBSITE_URL:
        lines.append(f"🔍 觀察名單 {n_watch} 檔、K 線圖 👉 {config.WEBSITE_URL}")
    elif n_watch:
        lines.append(f"🔍 另有觀察名單 {n_watch} 檔")
    lines.append("※ 僅供參考，請自行判斷")
    return "\n".join(lines).strip()


def _split(text, limit=4800):
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            parts.append(cur.strip())
            cur = ""
        cur += block + "\n\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts[:5]          # LINE 一次最多 5 則


def broadcast(text):
    if config.DRY_RUN or not config.LINE_TOKEN:
        print("\n────── LINE 訊息預覽（未發送）──────\n" + text + "\n────────────────────────────")
        return False
    payload = {"messages": [{"type": "text", "text": t} for t in _split(text)]}
    headers = {"Authorization": f"Bearer {config.LINE_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(BROADCAST, headers=headers, json=payload, timeout=20)
    if r.status_code != 200:
        print(f"⚠️ LINE 發送失敗：{r.status_code} {r.text}")
        return False
    print("✅ LINE 已群發")
    return True
