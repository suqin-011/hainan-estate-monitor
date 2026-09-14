# -*- coding: utf-8 -*-
"""
海南楼市 · 飞书监控机器人
抓各政府网站栏目页 → 对比上次快照 → 有新公告就推送到飞书群。

用法：python monitor.py
依赖：pip install requests beautifulsoup4
环境变量：FEISHU_WEBHOOK（飞书群自定义机器人 webhook 地址）
"""
import json
import os
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

STATE_FILE = "state.json"
SOURCES_FILE = "sources.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 标题命中这些关键词之一，才算「值得盯」的公告
KEYWORDS = [
    "公告", "公示", "通知", "意见", "批复", "出让", "挂牌", "成交",
    "征收", "规划", "控规", "控制性", "补偿", "拆迁", "预售", "安居",
    "保障", "招生", "学区", "入学", "房价", "统计", "月报", "季报",
    "年报", "建设", "项目", "地块", "用地", "方案", "调整", "结果",
]


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_titles(name, url):
    """抓一个栏目页，返回 [(标题, 链接), ...]，最新在前。抓不到返回 []"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"[跳过] {name} 抓取失败: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if len(title) < 8 or len(title) > 80:
            continue
        if not any(k in title for k in KEYWORDS):
            continue
        if title in seen:
            continue
        seen.add(title)
        href = urljoin(url, a["href"])
        items.append({"title": title, "url": href})
    # 列表通常按时间从新到旧排，取前 12 条足够
    return items[:12]


def build_message(new_items):
    lines = ["🏠 海南楼市监控 · 发现 %d 条更新" % len(new_items), ""]
    for it in new_items:
        lines.append("【%s】%s" % (it["name"], it["title"]))
        lines.append("  %s" % it["url"])
        lines.append("")
    return "\n".join(lines).strip()


def send_feishu(text):
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook:
        print("[提示] 未配置 FEISHU_WEBHOOK，跳过推送")
        return False
    payload = {"msg_type": "text", "content": {"text": text}}
    try:
        r = requests.post(webhook, json=payload, timeout=15)
        print("飞书返回:", r.status_code, r.text[:200])
        return r.status_code == 200
    except Exception as e:
        print("飞书推送失败:", e)
        return False


def main():
    sources = load_sources()
    state = load_state()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_items = []
    first_run = False
    changed = False

    for src in sources:
        key = src["name"]
        titles = fetch_titles(src["name"], src["url"])
        if not titles:
            continue
        old_titles = state.get(key, [])
        if not old_titles:
            # 首次：只记住现状，不推送，避免刷屏
            first_run = True
            state[key] = [t["title"] for t in titles]
            changed = True
            continue
        for t in titles:
            if t["title"] not in old_titles:
                new_items.append({"name": src["name"], "title": t["title"], "url": t["url"]})
        state[key] = [t["title"] for t in titles]
        changed = True

    if changed:
        save_state(state)

    if new_items:
        text = build_message(new_items)
        print(text)
        send_feishu(text)
    elif first_run:
        print("首次运行，已记住当前内容，之后有更新会推送")
        send_feishu("🏠 海南楼市监控已上线：已记住各站当前内容，之后有新增会推到这里。")
    else:
        print("[%s] 无新增" % now)


if __name__ == "__main__":
    main()
