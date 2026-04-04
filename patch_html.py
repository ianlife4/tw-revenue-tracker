"""
直接修補現有 HTML 檔案的 CSS 和結構，不重新產生資料。
修正項目：
1. compact-header 移進 stock-grid 內（對齊修正）
2. CSS 欄寬修正
3. 月份選擇器取代舊的日期顯示
4. 交替行底色修正
"""
import os
import re
import glob

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def get_available_months():
    """掃描 output 目錄取得可用月份"""
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
    """生成月份選擇器下拉 HTML"""
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
.month-picker-wrap {
    position: relative;
    display: inline-block;
}
.month-picker-btn {
    font-size: 1.3rem;
    font-weight: 600;
    color: #58a6ff;
    cursor: pointer;
    padding: 4px 12px;
    border-radius: 6px;
    transition: background 0.2s;
    user-select: none;
}
.month-picker-btn:hover {
    background: rgba(88,166,255,0.1);
}
.month-picker-btn::after {
    content: " ▾";
    font-size: 0.8rem;
}
.month-dropdown {
    display: none;
    position: absolute;
    top: 110%;
    left: 50%;
    transform: translateX(-50%);
    background: #1c2128;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 12px;
    z-index: 999;
    min-width: 220px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.month-dropdown.show {
    display: block;
}
.month-dropdown-year {
    color: #8b949e;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 6px 8px 4px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 4px;
}
.month-dropdown-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
}
.month-dropdown-item {
    display: block;
    padding: 6px 4px;
    text-align: center;
    color: #c9d1d9;
    text-decoration: none;
    border-radius: 6px;
    font-size: 0.85rem;
    transition: all 0.15s;
}
.month-dropdown-item:hover {
    background: rgba(88,166,255,0.15);
    color: #58a6ff;
}
.month-dropdown-item.active {
    background: #58a6ff;
    color: #0d1117;
    font-weight: 600;
}
.month-dropdown-item.disabled {
    color: #30363d;
    pointer-events: none;
}
"""

MONTH_PICKER_JS = """
// Month Picker
(function() {
    var btn = document.getElementById('monthPickerBtn');
    var dd = document.getElementById('monthDropdown');
    if (!btn || !dd) return;
    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        dd.classList.toggle('show');
    });
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.month-picker-wrap')) {
            dd.classList.remove('show');
        }
    });
})();
"""

# CSS fixes for compact mode column alignment
COMPACT_CSS_FIX = """
/* Compact mode column alignment fix */
body.compact .stock-grid {
    display: table !important;
    width: 100% !important;
    table-layout: fixed !important;
}
body.compact .compact-header {
    display: table-row;
}
body.compact .compact-header .ch-col {
    display: table-cell;
    padding: 8px 12px;
}
body.compact .compact-header .ch-name { width: 14%; }
body.compact .compact-header .ch-rev { width: 18%; text-align: right; padding-right: 10px; }
body.compact .compact-header .ch-col:not(.ch-name):not(.ch-rev) { text-align: right; padding-right: 10px; }
body.compact .stock-card {
    display: table-row !important;
}
body.compact .stock-card > .card-name,
body.compact .stock-card > .compact-rev,
body.compact .stock-card > .compact-yoy,
body.compact .stock-card > .compact-mom,
body.compact .stock-card > .compact-exceed,
body.compact .stock-card > .t1-box {
    display: table-cell !important;
    vertical-align: middle !important;
}
body.compact .stock-card:nth-child(odd) { background: rgba(22,27,34,0.5); }
body.compact .stock-card:nth-child(odd):hover { background: rgba(88,166,255,0.08); }
body.compact .stock-card:nth-child(even) { background: transparent; }
"""


def patch_html(filepath, available_months):
    """修補單個 HTML 檔案"""
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

    modified = False

    # 1. Move compact-header inside stock-grid
    # Old: </div>\n        <div class="compact-header">...\n        </div>\n        <div class="stock-grid">
    # New: </div>\n        <div class="stock-grid">\n            <div class="compact-header">...
    pattern = r'(<div class="compact-header">.*?</div>)\s*(<div class="stock-grid">)'
    if re.search(pattern, html, re.DOTALL):
        html = re.sub(pattern, r'\2\n            \1', html, flags=re.DOTALL)
        modified = True

    # 2. Add month picker CSS before </style>
    if 'month-picker-wrap' not in html:
        html = html.replace('</style>', MONTH_PICKER_CSS + '\n</style>', 1)
        modified = True

    # 3. Add compact CSS fix before </style>
    if 'column alignment fix' not in html:
        html = html.replace('</style>', COMPACT_CSS_FIX + '\n</style>', 1)
        modified = True

    # 4. Replace date-nav span with month picker
    picker_html = build_month_picker_html(year, month, available_months)
    old_nav = re.search(
        r'<span class="date-info">\d+/\d+</span>',
        html
    )
    if old_nav and 'month-picker-wrap' not in html:
        new_nav = f'''<div class="month-picker-wrap">
                <span class="month-picker-btn" id="monthPickerBtn">{year}/{month:02d}</span>
                <div class="month-dropdown" id="monthDropdown">
                    {picker_html}
                </div>
            </div>'''
        html = html[:old_nav.start()] + new_nav + html[old_nav.end():]
        modified = True

    # 5. Add month picker JS before </script> (last one)
    if 'monthPickerBtn' not in html and '</script>' in html:
        last_script_end = html.rfind('</script>')
        html = html[:last_script_end] + '\n' + MONTH_PICKER_JS + '\n' + html[last_script_end:]
        modified = True

    # 6. Remove alert-section if present
    alert_pattern = r'<div class="alert-section">.*?</div>\s*</div>\s*</div>'
    if re.search(alert_pattern, html, re.DOTALL):
        html = re.sub(alert_pattern, '', html, flags=re.DOTALL)
        modified = True

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

    return modified


def main():
    available = get_available_months()
    print(f"可用月份: {sorted(available)}")

    html_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.html")))
    for fpath in html_files:
        fname = os.path.basename(fpath)
        if fname == "index.html" or ".bak" in fname:
            continue
        result = patch_html(fpath, available)
        status = "✅ patched" if result else "⏭ no change"
        print(f"  {fname}: {status}")

    # Also patch index.html
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    if os.path.exists(index_path):
        # index.html is a copy of the latest month - patch it too
        result = patch_html(index_path, available)
        print(f"  index.html: {'✅ patched' if result else '⏭ no change'}")

    print("\n✅ 全部修補完成")


if __name__ == "__main__":
    main()
