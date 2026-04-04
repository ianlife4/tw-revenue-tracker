"""
直接修補現有 HTML 檔案的 CSS 和結構，不重新產生資料。
修正項目：
1. compact-header 欄位加上 ch-yoy/ch-mom/ch-beat class（對齊用）
2. CSS 加入固定欄寬
3. 月份選擇器取代舊的 date-info span
"""
import os
import re
import glob

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def get_available_months():
    available = set()
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".html") and "_" in f and f != "index.html" and ".bak" not in f:
            parts = f.replace(".html", "").split("_")
            if len(parts) == 2:
                try:
                    available.add((int(parts[0]), int(parts[1])))
                except ValueError:
                    pass
    return available


def build_month_picker_html(current_year, current_month, available):
    years = sorted(set(y for y, m in available), reverse=True)
    parts = []
    for yr in years:
        parts.append(f'<div class="month-dropdown-year">{yr}</div>')
        parts.append('<div class="month-dropdown-grid">')
        for mo in range(1, 13):
            fname = f"{yr}_{mo:02d}.html"
            if (yr, mo) in available:
                active = " active" if yr == current_year and mo == current_month else ""
                parts.append(f'<a class="month-dropdown-item{active}" href="{fname}">{mo}月</a>')
            else:
                parts.append(f'<span class="month-dropdown-item disabled">{mo}月</span>')
        parts.append('</div>')
    return "\n".join(parts)


MONTH_PICKER_CSS = """
/* Month Picker */
.month-picker-wrap { position: relative; display: inline-block; }
.month-picker-btn { font-size: 1.3rem; font-weight: 600; color: #58a6ff; cursor: pointer; padding: 4px 12px; border-radius: 6px; transition: background 0.2s; user-select: none; }
.month-picker-btn:hover { background: rgba(88,166,255,0.1); }
.month-picker-btn::after { content: " \\25BE"; font-size: 0.8rem; }
.month-dropdown { display: none; position: absolute; top: 110%; left: 50%; transform: translateX(-50%); background: #1c2128; border: 1px solid #30363d; border-radius: 10px; padding: 12px; z-index: 999; min-width: 220px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
.month-dropdown.show { display: block; }
.month-dropdown-year { color: #8b949e; font-size: 0.8rem; font-weight: 600; padding: 6px 8px 4px; border-bottom: 1px solid #21262d; margin-bottom: 4px; }
.month-dropdown-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.month-dropdown-item { display: block; padding: 6px 4px; text-align: center; color: #c9d1d9; text-decoration: none; border-radius: 6px; font-size: 0.85rem; transition: all 0.15s; }
.month-dropdown-item:hover { background: rgba(88,166,255,0.15); color: #58a6ff; }
.month-dropdown-item.active { background: #58a6ff; color: #0d1117; font-weight: 600; }
.month-dropdown-item.disabled { color: #30363d; pointer-events: none; }
"""

MONTH_PICKER_JS = """
// Month Picker toggle
(function() {
    var btn = document.getElementById('monthPickerBtn');
    var dd = document.getElementById('monthDropdown');
    if (!btn || !dd) return;
    btn.addEventListener('click', function(e) { e.stopPropagation(); dd.classList.toggle('show'); });
    document.addEventListener('click', function(e) { if (!e.target.closest('.month-picker-wrap')) dd.classList.remove('show'); });
})();
"""

COMPACT_CSS_FIX = """
/* Compact column fix (v2) */
body.compact .stock-grid { display: table !important; width: 100% !important; table-layout: fixed !important; }
body.compact .compact-header .ch-name { width: 14%; }
body.compact .compact-header .ch-rev { width: 18%; }
body.compact .compact-header .ch-yoy { width: 14%; }
body.compact .compact-header .ch-mom { width: 14%; }
body.compact .compact-header .ch-beat { width: 14%; }
body.compact .compact-header .ch-col:not(.ch-name) { text-align: right; padding-right: 10px; }
body.compact .stock-card > .card-name { width: 14%; }
body.compact .stock-card > .compact-rev { width: 18%; text-align: right; padding-right: 10px; }
body.compact .stock-card > .compact-yoy { width: 14%; text-align: right; padding-right: 10px; }
body.compact .stock-card > .compact-mom { width: 14%; text-align: right; padding-right: 10px; }
body.compact .stock-card > .compact-exceed { width: 14%; text-align: right; padding-right: 10px; }
"""


def patch_html(filepath, available_months):
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    fname = os.path.basename(filepath)
    parts = fname.replace(".html", "").split("_")
    if len(parts) != 2:
        return False
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        return False

    original = html

    # 1. Add ch-yoy, ch-mom, ch-beat classes to compact-header columns
    html = html.replace('class="ch-col" data-sort="yoy"', 'class="ch-col ch-yoy" data-sort="yoy"')
    html = html.replace('class="ch-col" data-sort="mom"', 'class="ch-col ch-mom" data-sort="mom"')
    html = html.replace('class="ch-col" data-sort="exceed"', 'class="ch-col ch-beat" data-sort="exceed"')

    # 2. Add compact CSS fix (only if not already present)
    # Remove old v1 if present
    if 'Compact mode column alignment fix' in html:
        html = re.sub(r'/\* Compact mode column alignment fix \*/.*?background: transparent; \}\s*', '', html, flags=re.DOTALL)
    if 'Compact column fix (v2)' not in html:
        html = html.replace('</style>', COMPACT_CSS_FIX + '\n</style>', 1)

    # 3. Add month picker CSS
    if '.month-picker-wrap {' not in html:
        html = html.replace('</style>', MONTH_PICKER_CSS + '\n</style>', 1)

    # 4. Replace <span class="date-info"> with month picker dropdown
    old_nav = re.search(r'<span class="date-info">\d+/\d+</span>', html)
    if old_nav:
        picker_inner = build_month_picker_html(year, month, available_months)
        new_nav = (
            f'<div class="month-picker-wrap">\n'
            f'                <span class="month-picker-btn" id="monthPickerBtn">{year}/{month:02d}</span>\n'
            f'                <div class="month-dropdown" id="monthDropdown">\n'
            f'                    {picker_inner}\n'
            f'                </div>\n'
            f'            </div>'
        )
        html = html[:old_nav.start()] + new_nav + html[old_nav.end():]

    # 5. Add month picker JS (if we have the button but no JS handler)
    if 'id="monthPickerBtn"' in html and '// Month Picker toggle' not in html:
        # Remove old incomplete JS if present
        html = re.sub(r'// Month Picker\n.*?}\)\(\);\s*', '', html, flags=re.DOTALL)
        if '</script>' in html:
            last = html.rfind('</script>')
            html = html[:last] + '\n' + MONTH_PICKER_JS + '\n' + html[last:]

    modified = html != original
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
    return modified


def main():
    available = get_available_months()
    print(f"Available: {sorted(available)}")

    patched = 0
    for fpath in sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.html"))):
        fname = os.path.basename(fpath)
        if fname == "index.html" or ".bak" in fname:
            continue
        result = patch_html(fpath, available)
        status = "PATCHED" if result else "ok"
        print(f"  {fname}: {status}")
        if result:
            patched += 1

    print(f"\nDone: {patched} files patched")


if __name__ == "__main__":
    main()
