#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把營收月報頁的配色換成全站基準 (CBAS 那一套)。

為什麼是「字串級 patch」而不是重建
------------------------------------
`rebuild_all.py` 讀的是 data/all_revenue_full.csv,而那個檔停在 **2026-03**
(1,819 筆 / 最後修改 4/1),但 output/ 底下的月檔已經到 2026-07 ——
用它重建會把 04~07 這幾個月的資料洗掉。這是專案記憶裡明載的地雷。

所以沿用 patch_xq_export.py 已經證明可行的模式:直接對既有 HTML 做字串替換,
只碰顏色值,一個資料位元組都不動。

安全設計
--------
- **idempotent**:檔案裡若已出現新色盤的 --bg (#0a0e17) 就跳過,重跑不會壞。
- **只替換顏色**:對映表全部是 6 碼 hex / rgba 前三數,不碰 class、屬性、數值。
  (XQ .dsl 匯出綁死了一整串 DOM 契約 —— data-sid / .stock-card / .market-panel.active /
   inline style.display 等等 —— 只改顏色完全不會踩到。)
- **每個檔案改完立刻驗**:卡片數、股票代號集合、股名集合必須與改前完全相同,
  任何一項對不上就還原該檔並中止。
- 預設 dry-run,要加 --write 才會真的寫檔。

用法:
    python patch_theme.py              # 只報告,不寫檔
    python patch_theme.py --write      # 實際套用
    python patch_theme.py --write --only 2026_07.html
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'output')

# GitHub-dark → CBAS 基準色
HEX6 = {
    '#0d1117': '#0a0e17',   # 頁底
    '#161b22': '#11161f',   # 卡片
    '#1c2128': '#161c28',   # 第二層
    '#21262d': '#161c28',   # 第二層
    '#30363d': '#1d2632',   # 邊框
    '#e6edf3': '#e6ecf5',   # 主文
    '#c9d1d9': '#e6ecf5',   # 主文(次)
    '#8b949e': '#8a96aa',   # 次要文字
    '#6e7681': '#5b6779',   # 說明文字
    '#58a6ff': '#5fa8ff',   # accent 藍
    '#79bbff': '#7cb8ff',   # accent 藍(亮)
    '#3fb950': '#4dd4ac',   # 綠(正向) → teal
    '#56d364': '#5fe0bc',   # 綠(亮)
    '#f85149': '#f06d8a',   # 紅(負向) → rose
    '#f0883e': '#ff8c42',   # 橘
    '#f5a664': '#ffa15e',   # 橘(亮)
    '#d2a8ff': '#a487f7',   # 紫 → violet
}
RGBA = {
    '88,166,255': '95,168,255',
    '22,27,34':   '17,22,31',
    '13,17,23':   '10,14,23',
    '63,185,80':  '77,212,172',
    '248,81,73':  '240,109,138',
}
MARKER = '#0a0e17'          # 出現這個就代表已經套過


def patch_text(s: str) -> tuple[str, int]:
    n = 0
    for old, new in HEX6.items():
        # 允許 8 碼形式 (#RRGGBBAA,顏色帶透明度) —— 例如 #58a6ff33、#58a6ff15。
        # 這裡要精準:後面接「剛好 2 個 hex 字元且再後面不是 hex」才當成 alpha,
        # 否則會誤吃到別的色碼。純 6 碼的情況則要求後面不能是 hex 字元。
        # (?<!&) 是關鍵防呆:HTML 數字實體長得像色碼 —— 例如 📥 是 &#128229;,
        # 少了這個 lookbehind 就會把 &#128229; 改成 &#2f9e7f; 讓 emoji 變亂碼。
        pat = re.compile(r'(?<!&)' + re.escape(old) + r'(?:([0-9a-fA-F]{2})(?![0-9a-fA-F]))?(?![0-9a-fA-F])', re.I)
        hits = len(pat.findall(s))
        if hits:
            s = pat.sub(lambda m: new + (m.group(1) or ''), s)
            n += hits
    for old, new in RGBA.items():
        a, b, c = [x.strip() for x in old.split(',')]
        # 允許逗號後面有沒有空白兩種寫法
        pat = re.compile(r'rgba?\(\s*%s\s*,\s*%s\s*,\s*%s\s*' % (a, b, c))
        hits = len(pat.findall(s))
        if hits:
            s = pat.sub(lambda m: m.group(0).replace(a, new.split(',')[0], 1)
                                            .replace(b, new.split(',')[1], 1)
                                            .replace(c, new.split(',')[2], 1), s)
            n += hits
    return s, n


def fingerprint(s: str) -> dict:
    """抓出「資料」的指紋 —— 改完必須完全一致,否則代表動到不該動的東西。"""
    return {
        'cards': len(re.findall(r'class="stock-card"', s)),
        'sids': tuple(sorted(re.findall(r'data-sid="(\d+)"', s))),
        'snames': tuple(sorted(re.findall(r'data-sname="([^"]*)"', s))),
        'markets': tuple(sorted(re.findall(r'data-market="([^"]*)"', s))),
        'nums': tuple(re.findall(r'>([+-]?\d[\d,]*\.?\d*)%<', s))[:4000],
        # HTML 數字實體長得像色碼,曾經真的被誤改過 (📥 &#128229; → &#2f9e7f;)
        'entities': tuple(sorted(re.findall(r'&#[0-9a-zA-Z]+;', s))),
        'emoji': tuple(re.findall(r'[🌀-🫿]', s)),
    }


def process(path: str, write: bool) -> str:
    raw = io.open(path, encoding='utf-8').read()
    if MARKER in raw:
        return 'skip  (已套用過)'
    before = fingerprint(raw)
    new, n = patch_text(raw)
    if n == 0:
        return 'skip  (沒有可替換的顏色)'
    after = fingerprint(new)
    for k in before:
        if before[k] != after[k]:
            return 'ABORT ★ 資料指紋不符: %s (改前 %r / 改後 %r)' % (
                k, str(before[k])[:60], str(after[k])[:60])
    if write:
        tmp = path + '.tmp'
        io.open(tmp, 'w', encoding='utf-8', newline='').write(new)
        os.replace(tmp, path)
    return 'OK    替換 %5d 處 · 卡片 %d 張 · 代號 %d 個%s' % (
        n, before['cards'], len(before['sids']), '' if write else '  (dry-run,未寫檔)')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='實際寫檔(預設只報告)')
    ap.add_argument('--only', help='只處理指定檔名')
    ap.add_argument('--gen', action='store_true', help='同時處理產生器 html_generator.py / html_realtime.py')
    a = ap.parse_args()

    targets = []
    if os.path.isdir(OUT):
        for f in sorted(os.listdir(OUT)):
            if f.endswith('.html') and (not a.only or f == a.only):
                targets.append(os.path.join(OUT, f))
    if a.gen:
        for f in ('html_generator.py', 'html_realtime.py'):
            p = os.path.join(HERE, f)
            if os.path.exists(p):
                targets.append(p)

    if not targets:
        print('沒有可處理的檔案'); return 1

    bad = 0
    for p in targets:
        r = process(p, a.write)
        if r.startswith('ABORT'):
            bad += 1
        print('  %-22s %s' % (os.path.basename(p), r))
    print()
    print('%s%d 個檔案' % ('(dry-run) ' if not a.write else '', len(targets)))
    if bad:
        print('★ 有 %d 個檔案指紋不符,沒有寫入' % bad)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
