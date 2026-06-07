"""
升級 output/ 既有 HTML 的 XQ 匯出: 舊版 CSV → 新版 .dsl (XQ 原生 CFB/OLE2)。

- 不重新渲染、不碰資料,純字串級替換 → 保留各月份既有資料 (rebuild_all 會用到
  舊的 all_revenue_full.csv,會把近月新資料洗掉,所以既有檔一律用本工具升級)。
- 按鈕 / JS 來源同 html_generator.py: 共用模組 _xq_dsl_js。
- 冪等: 已是 .dsl 的檔 (含 buildXqDsl) 會 skip。

重跑: python patch_xq_export.py
"""
import os
import re
import glob

from _xq_dsl_js import EXPORT_BUTTON_HTML, EXPORT_JS, EXPORT_CSS

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 舊 CSV 按鈕 (id 不變, 只換 label/title) — 整顆 <button ...>...</button>
RE_BUTTON = re.compile(r'<button class="export-btn" id="exportXqCsv".*?</button>', re.DOTALL)
# 舊 CSV IIFE: 從註解 header 到 IIFE 結尾 })(); (其後接 </script>)
RE_CSV_IIFE = re.compile(r"// XQ 自選股 CSV 匯出.*?\}\)\(\);(?=\s*</script>)", re.DOTALL)
# 新版標記 (冪等判斷)
DSL_MARKER = "buildXqDsl"


def patch_one(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    if DSL_MARKER in html:
        return "skip"  # 已是 .dsl 版

    changed = False

    # 升級既有 CSV 按鈕 + IIFE
    if 'id="exportXqCsv"' in html and RE_CSV_IIFE.search(html):
        html, nb = RE_BUTTON.subn(lambda m: EXPORT_BUTTON_HTML, html, count=1)
        html, nj = RE_CSV_IIFE.subn(lambda m: EXPORT_JS, html, count=1)
        if nb and nj:
            changed = True
        else:
            return f"partial(btn={nb},js={nj})"
    else:
        # 從未加過匯出按鈕的檔 — 若有 .view-toggle 則 fresh inject
        if '<div class="view-toggle">' not in html:
            return "no-match"
        if "</style>" in html:
            html = html.replace("</style>", EXPORT_CSS + "\n</style>", 1)
        html = re.sub(
            r'(<div class="view-toggle">\s*)',
            lambda m: m.group(1) + EXPORT_BUTTON_HTML + "\n            ",
            html, count=1,
        )
        if "</script>" in html:
            html = html.replace("</script>", EXPORT_JS + "\n</script>", 1)
        changed = True

    if not changed:
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
