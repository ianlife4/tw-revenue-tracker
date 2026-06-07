"""
升級 output/ 既有 HTML 的 XQ 匯出 → 最新版 (v2)。

v2 = XQ 原生 .dsl (CFB/OLE2) + 興櫃(emerging)字尾 .TE + 公發(pub)不匯出。
能從以下任一舊版升級 (字串級替換,不重新渲染、不碰資料):
  - 舊 CSV 版 (`// XQ 自選股 CSV 匯出`)
  - v1 .dsl 版 (`// XQ 自選股 .dsl 匯出`,全部 .TW、未排除公發)

同時為既有 .stock-card 注入 data-market (從各市場分頁 panel-sii/.../pub 推導
sid→market),讓「全部」分頁也能正確判斷興櫃 / 排除公發。

按鈕 / JS 來源同 html_generator.py: 共用模組 _xq_dsl_js。冪等 (已是 v2 就 skip)。
重跑: python patch_xq_export.py
"""
import os
import re
import glob

from _xq_dsl_js import EXPORT_BUTTON_HTML, EXPORT_JS, EXPORT_CSS

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

EXPORT_VERSION = "xq-export-v2"  # 出現在 EXPORT_JS 註解,用來判斷是否已是最新版

# 匯出按鈕 (id 固定,label 可能是 CSV 或 .dsl 版) — 整顆 <button ...>...</button>
RE_BUTTON = re.compile(r'<button class="export-btn" id="exportXqCsv".*?</button>', re.DOTALL)
# 匯出 IIFE: 從註解 header (CSV 或 .dsl 版) 到 IIFE 結尾 })(); (其後接 </script>)
RE_EXPORT_IIFE = re.compile(
    r"// XQ 自選股 (?:CSV|\.dsl) 匯出[\s\S]*?\}\)\(\);(?=\s*</script>)", re.DOTALL
)
RE_CARD_OPEN = re.compile(r'<div class="stock-card" data-sid="(\d+)"')
RE_CARD_HAS_MARKET = re.compile(r'<div class="stock-card"[^>]*\bdata-market=')

PANEL_ORDER = ["all", "sii", "otc", "tib", "emerging", "pub"]
MARKET_PANELS = ["sii", "otc", "tib", "emerging", "pub"]


def inject_card_market(html: str) -> str:
    """從各市場分頁推導 sid→market,為每張 .stock-card 注入 data-market。"""
    if RE_CARD_HAS_MARKET.search(html):
        return html  # 已注入
    pos = {m: html.find('id="panel-%s"' % m) for m in PANEL_ORDER}
    sid2mkt = {}
    for m in MARKET_PANELS:
        s = pos.get(m, -1)
        if s == -1:
            continue
        later = [p for p in pos.values() if p > s]
        e = min(later) if later else len(html)
        for sid in re.findall(r'data-sid="(\d+)"', html[s:e]):
            sid2mkt.setdefault(sid, m)
    if not sid2mkt:
        return html

    def repl(mo):
        sid = mo.group(1)
        return '<div class="stock-card" data-sid="%s" data-market="%s"' % (sid, sid2mkt.get(sid, ""))

    return RE_CARD_OPEN.sub(repl, html)


def patch_one(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # 已是 v2 (有版本標記 + 卡片已帶 data-market) → skip
    if EXPORT_VERSION in html and RE_CARD_HAS_MARKET.search(html):
        return "skip"

    has_btn = 'id="exportXqCsv"' in html
    has_iife = bool(RE_EXPORT_IIFE.search(html))

    if has_btn and has_iife:
        html = inject_card_market(html)
        html, nb = RE_BUTTON.subn(lambda m: EXPORT_BUTTON_HTML, html, count=1)
        html, nj = RE_EXPORT_IIFE.subn(lambda m: EXPORT_JS, html, count=1)
        if not (nb and nj):
            return f"partial(btn={nb},js={nj})"
    elif '<div class="view-toggle">' in html:
        # 從未加過匯出按鈕的檔 — fresh inject
        html = inject_card_market(html)
        if "</style>" in html:
            html = html.replace("</style>", EXPORT_CSS + "\n</style>", 1)
        html = re.sub(
            r'(<div class="view-toggle">\s*)',
            lambda m: m.group(1) + EXPORT_BUTTON_HTML + "\n            ",
            html, count=1,
        )
        if "</script>" in html:
            html = html.replace("</script>", EXPORT_JS + "\n</script>", 1)
    else:
        return "no-match"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return "patched"


def main():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.html")))
    files = [f for f in files if ".bak" not in f]
    if not files:
        print("output/ 內找不到 HTML")
        return
    stats = {}
    for f in files:
        result = patch_one(f)
        stats[result] = stats.get(result, 0) + 1
        print(f"[{result:>9}] {os.path.basename(f)}")
    print("\n", stats)


if __name__ == "__main__":
    main()
