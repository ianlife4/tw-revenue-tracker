"""
一次性 patch: 為 output/ 既有 HTML 加上「匯出 XQ 自選股 CSV」按鈕。
- 注入 CSS (.export-btn)
- 在 .view-toggle 內第一個位置插入 <button id="exportXqCsv">
- 在 </script> 前插入 IIFE
重複執行安全 (做 idempotent 檢查)。
"""
import os
import re
import glob

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

EXPORT_CSS = """
/* ===== XQ 自選股匯出按鈕 ===== */
.export-btn {
    padding: 6px 14px;
    font-size: 0.8rem;
    color: #56d364;
    background: #161b22;
    border: 1px solid #56d36450;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
    margin-right: 8px;
    font-family: inherit;
}
.export-btn:hover {
    color: #fff;
    border-color: #56d364;
    background: #56d36420;
}
.export-btn:active {
    transform: translateY(1px);
}
.export-btn .count-badge {
    color: #8b949e;
    margin-left: 4px;
    font-size: 0.7rem;
}
"""

EXPORT_BUTTON_HTML = (
    '<button class="export-btn" id="exportXqCsv" type="button" '
    'title="匯出當前篩選結果為 XQ 自選股 CSV (代號.TW,股名)">'
    '&#128229; 匯出 XQ 自選股<span class="count-badge" id="exportCount"></span></button>'
)

EXPORT_JS = r"""
// XQ 自選股 CSV 匯出
(function() {
    var btn = document.getElementById('exportXqCsv');
    var countBadge = document.getElementById('exportCount');
    if (!btn) return;

    function getVisibleStocks() {
        var panel = document.querySelector('.market-panel.active');
        if (!panel) return [];
        var cards = panel.querySelectorAll('.stock-card');
        var seen = {};
        var list = [];
        for (var i = 0; i < cards.length; i++) {
            var c = cards[i];
            if (c.style.display === 'none') continue;
            var section = c.closest('.industry-section');
            if (section && section.style.display === 'none') continue;
            var sid = (c.dataset.sid || '').trim();
            var sname = (c.dataset.sname || '').trim();
            if (!sid || seen[sid]) continue;
            seen[sid] = 1;
            list.push({ sid: sid, sname: sname });
        }
        return list;
    }

    function getActiveMarketLabel() {
        var panel = document.querySelector('.market-panel.active');
        if (!panel) return 'all';
        return (panel.id || '').replace('panel-', '') || 'all';
    }

    function todayTw() {
        var d = new Date(Date.now() + 8 * 3600 * 1000);
        return d.toISOString().slice(0, 10);
    }

    function updateCount() {
        if (!countBadge) return;
        var n = getVisibleStocks().length;
        countBadge.textContent = n > 0 ? '(' + n + ')' : '';
    }

    btn.addEventListener('click', function() {
        var stocks = getVisibleStocks();
        if (stocks.length === 0) {
            alert('目前沒有可匯出的股票（請確認分頁與篩選條件）');
            return;
        }
        var lines = stocks.map(function(s) { return s.sid + '.TW,' + s.sname; });
        var BOM = String.fromCharCode(0xFEFF);
        var csv = BOM + lines.join('\r\n') + '\r\n';
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'XQ自選股_營收創新高_' + getActiveMarketLabel() + '_' + todayTw() + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function() { URL.revokeObjectURL(url); }, 100);
    });

    updateCount();

    document.addEventListener('click', function(e) {
        if (e.target.closest('.market-tab') || e.target.closest('.date-pill')) {
            setTimeout(updateCount, 60);
        }
    });
    var search = document.getElementById('stockSearch');
    if (search) {
        search.addEventListener('input', function() {
            setTimeout(updateCount, 60);
        });
    }
})();
"""


def patch_one(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    if "exportXqCsv" in html:
        return "skip"

    changed = False

    # 1. 注入 CSS — 放在 </style> 前
    if "</style>" in html:
        html = html.replace("</style>", EXPORT_CSS + "\n</style>", 1)
        changed = True

    # 2. 插入 button HTML — 在 view-toggle div 開頭
    pattern = re.compile(
        r'(<div class="view-toggle">\s*)',
        re.MULTILINE,
    )
    new_html, n = pattern.subn(r"\1" + EXPORT_BUTTON_HTML + "\n            ", html, count=1)
    if n > 0:
        html = new_html
        changed = True

    # 3. 插入 JS — 在 </script> 前
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
    stats = {"patched": 0, "skip": 0, "no-match": 0}
    for f in files:
        result = patch_one(f)
        stats[result] = stats.get(result, 0) + 1
        print(f"[{result:>9}] {os.path.basename(f)}")
    print("\n", stats)


if __name__ == "__main__":
    main()
