"""
即時營收 HTML 生成模組
參考 chengwaye.com/realtime-rev 風格
表格式、即時申報偵測、可排序/篩選
"""

import json
import logging
from datetime import datetime

import pandas as pd

from analyzer import format_revenue

logger = logging.getLogger(__name__)


def _fmt_revenue_million(val) -> str:
    """營收格式化為百萬 (M)"""
    if pd.isna(val) or val == 0:
        return "-"
    m = float(val) / 1_000_000
    if m >= 1000:
        return f"{m:,.1f}"
    elif m >= 100:
        return f"{m:,.1f}"
    elif m >= 10:
        return f"{m:,.2f}"
    else:
        return f"{m:,.2f}"


def _pct_html(val, reverse=False) -> str:
    """百分比 HTML (紅正綠負)"""
    if pd.isna(val) or val == 0:
        return '<span style="color:#6e7681">-</span>'
    v = float(val)
    if v > 0:
        color = "#f85149"
        return f'<span style="color:{color}">{v:.2f}%</span>'
    else:
        color = "#3fb950"
        return f'<span style="color:{color}">{v:.2f}%</span>'


def _build_chart_data(stock_id: str, full_df: pd.DataFrame, rev_year: int, rev_month: int) -> str:
    """為個股建立圖表所需的 JSON 數據"""
    if full_df is None or full_df.empty:
        return "[]"

    stock_data = full_df[full_df["stock_id"] == stock_id].copy()
    if stock_data.empty:
        return "[]"

    records = []
    for _, row in stock_data.iterrows():
        records.append({
            "year": int(row["revenue_year"]),
            "month": int(row["revenue_month"]),
            "revenue": float(row["revenue"]) if pd.notna(row["revenue"]) else 0,
        })

    return json.dumps(records, ensure_ascii=False)


def generate_realtime_page(state: dict, current_df: pd.DataFrame,
                           full_df: pd.DataFrame, rev_year: int, rev_month: int) -> str:
    """生成即時營收頁面"""

    now = datetime.now()
    period_str = f"{rev_year}/{rev_month:02d}"
    total_filed = state.get("total_filed", 0)
    last_check = state.get("last_check", "")
    last_new = state.get("last_new_filing", "尚無")
    is_monitoring = True  # 腳本執行中就是偵測中

    # 建立表格行
    rows_html = ""
    if not current_df.empty:
        # 依 first_seen 降序排列 (最新申報在上)
        df = current_df.copy()
        df["_sort_seen"] = pd.to_datetime(
            df["first_seen"].str.replace(r"^(\d{2})-(\d{2})", f"{rev_year}-\\1-\\2", regex=True),
            format="%Y-%m-%d %H:%M", errors="coerce"
        )
        df = df.sort_values("_sort_seen", ascending=False, na_position="last")

        for _, row in df.iterrows():
            sid = str(row.get("stock_id", ""))
            sname = str(row.get("stock_name", ""))
            first_seen = str(row.get("first_seen", ""))
            rev = row.get("revenue", 0)
            mom = row.get("mom_pct", 0)
            yoy = row.get("yoy_pct", 0)
            ytd_yoy = row.get("ytd_yoy_pct", 0)
            remark = row.get("remark", "")
            market = row.get("market", "")

            rev_m = _fmt_revenue_million(rev)
            mom_html = _pct_html(mom)
            yoy_html = _pct_html(yoy)
            ytd_html = _pct_html(ytd_yoy)

            # 備註
            remark_str = str(remark).strip() if pd.notna(remark) and str(remark).strip() != "-" else ""
            remark_attr = f' data-remark="{remark_str}"' if remark_str else ""

            # 市場標籤
            market_labels = {"sii": "上市", "otc": "上櫃", "tib": "創新板", "emerging": "興櫃"}
            market_label = market_labels.get(market, "")

            # 圖表數據
            chart_json = _build_chart_data(sid, full_df, rev_year, rev_month)

            # 營收原始值 (用於排序)
            rev_raw = float(rev) if pd.notna(rev) else 0
            yoy_raw = float(yoy) if pd.notna(yoy) else 0
            mom_raw = float(mom) if pd.notna(mom) else 0
            ytd_raw = float(ytd_yoy) if pd.notna(ytd_yoy) else 0

            rows_html += f"""
        <tr class="stock-row" data-sid="{sid}" data-sname="{sname}" data-rev="{rev_raw}"
            data-yoy="{yoy_raw}" data-mom="{mom_raw}" data-ytd="{ytd_raw}"
            data-seen="{first_seen}" data-market="{market}"{remark_attr}
            data-chart='{chart_json}'>
            <td class="col-id">{sid}</td>
            <td class="col-name">{sname} <span class="market-badge">{market_label}</span></td>
            <td class="col-seen">{first_seen}</td>
            <td class="col-rev">{rev_m}</td>
            <td class="col-pct">{mom_html}</td>
            <td class="col-pct">{yoy_html}</td>
            <td class="col-pct">{ytd_html}</td>
        </tr>"""

    # 監控狀態
    status_dot = "🟢" if is_monitoring else "⚪"
    status_text = "偵測中 ✓" if is_monitoring else "已停止"

    # 歷史月報連結 (當期的營收創同期新高報表)
    history_link = f"{rev_year}_{rev_month:02d}.html"

    html = REALTIME_TEMPLATE.format(
        period=period_str,
        total_filed=total_filed,
        last_check=last_check,
        last_new=last_new,
        status_dot=status_dot,
        status_text=status_text,
        update_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        rows=rows_html,
        compare_years=5,
        rev_year=rev_year,
        rev_month=rev_month,
        history_link=history_link,
    )
    return html


REALTIME_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>營收即時追蹤 - {period}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
    line-height: 1.6;
    min-height: 100vh;
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}}

/* ===== Header ===== */
header {{
    text-align: center;
    padding: 30px 20px 20px;
}}

header h1 {{
    font-size: 1.8rem;
    font-weight: 700;
    margin-bottom: 8px;
}}

.period-info {{
    color: #8b949e;
    font-size: 0.95rem;
    margin-bottom: 4px;
}}

.period-info .highlight {{
    color: #58a6ff;
    font-weight: 600;
}}

.monitor-status {{
    font-size: 0.85rem;
    color: #6e7681;
}}

.monitor-status .status-active {{
    color: #3fb950;
}}

.stats-bar {{
    display: flex;
    justify-content: center;
    gap: 30px;
    margin: 20px 0;
    flex-wrap: wrap;
}}

.stat-item {{
    text-align: center;
}}

.stat-item .stat-value {{
    font-size: 1.5rem;
    font-weight: 700;
    color: #f85149;
}}

.stat-item .stat-label {{
    font-size: 0.8rem;
    color: #8b949e;
}}

/* ===== 搜尋 + 篩選 ===== */
.filter-bar {{
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    margin: 20px 0;
    padding: 12px 16px;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
}}

.filter-group {{
    display: flex;
    align-items: center;
    gap: 6px;
}}

.filter-group label {{
    font-size: 0.8rem;
    color: #8b949e;
}}

.filter-group input[type="checkbox"] {{
    accent-color: #58a6ff;
}}

.filter-group input[type="number"] {{
    width: 60px;
    padding: 4px 8px;
    font-size: 0.8rem;
    color: #e6edf3;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
}}

.filter-group select {{
    padding: 4px 8px;
    font-size: 0.8rem;
    color: #e6edf3;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
}}

.search-input {{
    flex: 1;
    min-width: 160px;
    padding: 6px 12px;
    font-size: 0.85rem;
    color: #e6edf3;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    outline: none;
}}

.search-input:focus {{
    border-color: #58a6ff;
}}

.search-input::placeholder {{
    color: #6e7681;
}}

.filter-count {{
    font-size: 0.8rem;
    color: #8b949e;
}}

/* ===== 導航 ===== */
.nav-links {{
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-bottom: 20px;
}}

.nav-link {{
    color: #8b949e;
    text-decoration: none;
    font-size: 0.85rem;
    padding: 4px 12px;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
}}

.nav-link:hover {{
    color: #58a6ff;
    border-color: #58a6ff;
}}

.nav-link.active {{
    color: #58a6ff;
    border-color: #58a6ff;
    background: #58a6ff15;
}}

/* ===== 表格 ===== */
.table-wrapper {{
    overflow-x: auto;
    border: 1px solid #21262d;
    border-radius: 8px;
    background: #161b22;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}}

thead th {{
    padding: 10px 14px;
    text-align: left;
    font-size: 0.78rem;
    color: #8b949e;
    font-weight: 600;
    border-bottom: 2px solid #21262d;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    transition: color 0.2s;
    position: sticky;
    top: 0;
    background: #161b22;
    z-index: 5;
}}

thead th:hover {{
    color: #e6edf3;
}}

thead th.sort-active {{
    color: #58a6ff;
    border-bottom-color: #58a6ff;
}}

thead th .sort-arrow {{
    font-size: 0.6rem;
    margin-left: 3px;
    opacity: 0.4;
}}

thead th.sort-active .sort-arrow {{
    opacity: 1;
}}

.col-rev, .col-pct {{
    text-align: right;
    padding-right: 14px;
}}

thead th.col-rev, thead th.col-pct {{
    text-align: right;
}}

tbody tr {{
    cursor: pointer;
    transition: background 0.12s;
}}

tbody tr:hover {{
    background: rgba(88,166,255,0.08);
}}

tbody tr:nth-child(even) {{
    background: rgba(22,27,34,0.5);
}}

tbody tr:nth-child(even):hover {{
    background: rgba(88,166,255,0.08);
}}

tbody tr.new-filing {{
    background: rgba(88,166,255,0.12);
}}

tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid #21262d10;
    white-space: nowrap;
}}

.col-id {{
    font-family: "Consolas", "Monaco", monospace;
    font-weight: 600;
    color: #58a6ff;
}}

.col-name {{
    font-weight: 500;
}}

.col-seen {{
    color: #8b949e;
    font-family: "Consolas", "Monaco", monospace;
    font-size: 0.78rem;
}}

.col-rev {{
    font-family: "Consolas", "Monaco", monospace;
    font-weight: 700;
    color: #f85149;
    font-size: 0.9rem;
}}

.col-pct {{
    font-family: "Consolas", "Monaco", monospace;
}}

.market-badge {{
    font-size: 0.65rem;
    color: #6e7681;
    background: #21262d;
    padding: 1px 5px;
    border-radius: 3px;
    margin-left: 4px;
}}

/* ===== 展開明細 ===== */
.detail-row td {{
    padding: 16px;
    background: #0d1117;
    border-bottom: 2px solid #21262d;
}}

.detail-content {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.detail-header {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.detail-header a {{
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
}}

.detail-header a:hover {{
    text-decoration: underline;
}}

.detail-links {{
    display: flex;
    gap: 8px;
}}

.detail-links a {{
    padding: 4px 10px;
    font-size: 0.75rem;
    color: #8b949e;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-decoration: none;
    transition: all 0.2s;
}}

.detail-links a:hover {{
    color: #58a6ff;
    border-color: #58a6ff;
}}

.remark-box {{
    padding: 6px 10px;
    background: #1c2128;
    border-left: 3px solid #f0883e;
    border-radius: 0 4px 4px 0;
    font-size: 0.78rem;
    color: #d2a8ff;
}}

/* ===== 歷史表格 ===== */
.history-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 0.8rem;
}}

.history-table th {{
    padding: 6px 12px;
    text-align: right;
    font-weight: 600;
    color: #8b949e;
    border-bottom: 1px solid #21262d;
    cursor: default;
}}

.history-table th:first-child {{
    text-align: left;
}}

.history-table td {{
    padding: 5px 12px;
    text-align: right;
    font-family: "Consolas", "Monaco", monospace;
    border-bottom: 1px solid #21262d10;
}}

.history-table td:first-child {{
    text-align: left;
    color: #8b949e;
}}

/* ===== 柱狀圖 ===== */
.mini-chart {{
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 100px;
    padding: 8px 0;
}}

.chart-bar-single {{
    flex: 1;
    min-width: 4px;
    max-width: 16px;
    border-radius: 2px 2px 0 0;
    background: #6e7681;
    min-height: 2px;
    transition: background 0.2s;
}}

.chart-bar-single.current {{
    background: #f0883e;
}}

.chart-bar-single:hover {{
    background: #79bbff;
}}

.chart-labels {{
    display: flex;
    gap: 2px;
    font-size: 0.5rem;
    color: #6e7681;
}}

.chart-labels span {{
    flex: 1;
    text-align: center;
    min-width: 4px;
    max-width: 16px;
}}

footer {{
    text-align: center;
    padding: 30px 20px;
    color: #6e7681;
    font-size: 0.75rem;
}}

@media (max-width: 768px) {{
    .filter-bar {{
        flex-direction: column;
        align-items: stretch;
    }}
    .filter-group {{
        flex-wrap: wrap;
    }}
    table {{
        font-size: 0.78rem;
    }}
    thead th, tbody td {{
        padding: 7px 8px;
    }}
    .market-badge {{
        display: none;
    }}
}}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>營收即時追蹤</h1>
        <div class="period-info">
            營收期間：<span class="highlight">{period}</span> |
            已申報 <span class="highlight">{total_filed}</span> 家
        </div>
        <div class="monitor-status">
            最新申報：{last_new} ·
            <span class="status-active">{status_text}</span>
            · 最後偵測：{last_check}
        </div>
    </header>

    <div class="nav-links">
        <a href="index.html" class="nav-link active">即時申報</a>
        <a href="{history_link}" class="nav-link">歷史月報</a>
    </div>

    <div class="filter-bar">
        <input type="text" class="search-input" id="searchInput"
               placeholder="搜尋代號或名稱" autocomplete="off">
        <div class="filter-group">
            <input type="checkbox" id="filterYoy">
            <label for="filterYoy">YoY</label>
            <select id="filterYoyDir"><option value=">">&gt;</option><option value="<">&lt;</option></select>
            <input type="number" id="filterYoyVal" value="30">
            <label>%</label>
        </div>
        <div class="filter-group">
            <input type="checkbox" id="filterMom">
            <label for="filterMom">MoM</label>
            <select id="filterMomDir"><option value=">">&gt;</option><option value="<">&lt;</option></select>
            <input type="number" id="filterMomVal" value="20">
            <label>%</label>
        </div>
        <span class="filter-count" id="filterCount"></span>
    </div>

    <div class="table-wrapper">
        <table id="mainTable">
            <thead>
                <tr>
                    <th data-sort="sid" class="col-id">代號 <span class="sort-arrow">▲</span></th>
                    <th data-sort="name">名稱 <span class="sort-arrow">▲</span></th>
                    <th data-sort="seen" class="sort-active">偵測時間 <span class="sort-arrow">▼</span></th>
                    <th data-sort="rev" class="col-rev">營收(M) <span class="sort-arrow">▲</span></th>
                    <th data-sort="mom" class="col-pct">MoM% <span class="sort-arrow">▲</span></th>
                    <th data-sort="yoy" class="col-pct">YoY% <span class="sort-arrow">▲</span></th>
                    <th data-sort="ytd" class="col-pct">累計YoY% <span class="sort-arrow">▲</span></th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {rows}
            </tbody>
        </table>
    </div>
</div>

<footer>
    資料來源：公開資訊觀測站 (MOPS) | 系統每 5 分鐘偵測 | 僅供參考，不構成投資建議<br>
    最後更新：{update_time}
</footer>

<script>
// ===== 排序 =====
(function() {{
    const table = document.getElementById('mainTable');
    const tbody = document.getElementById('tableBody');
    const headers = table.querySelectorAll('thead th[data-sort]');
    let currentSort = 'seen';
    let sortAsc = false;

    const sortMap = {{
        sid: r => r.dataset.sid,
        name: r => r.dataset.sname,
        seen: r => r.dataset.seen,
        rev: r => parseFloat(r.dataset.rev) || 0,
        mom: r => parseFloat(r.dataset.mom) || -9999,
        yoy: r => parseFloat(r.dataset.yoy) || -9999,
        ytd: r => parseFloat(r.dataset.ytd) || -9999,
    }};

    headers.forEach(th => {{
        th.addEventListener('click', () => {{
            const key = th.dataset.sort;
            if (currentSort === key) {{
                sortAsc = !sortAsc;
            }} else {{
                currentSort = key;
                sortAsc = (key === 'sid' || key === 'name');
            }}

            headers.forEach(h => {{
                h.classList.remove('sort-active');
                h.querySelector('.sort-arrow').textContent = '▲';
            }});
            th.classList.add('sort-active');
            th.querySelector('.sort-arrow').textContent = sortAsc ? '▲' : '▼';

            doSort();
        }});
    }});

    function doSort() {{
        const rows = Array.from(tbody.querySelectorAll('.stock-row'));
        const fn = sortMap[currentSort];
        if (!fn) return;

        rows.sort((a, b) => {{
            let va = fn(a), vb = fn(b);
            if (typeof va === 'string') {{
                return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            }}
            return sortAsc ? (va - vb) : (vb - va);
        }});

        rows.forEach(r => tbody.appendChild(r));
    }}
    window._doSort = doSort;
}})();

// ===== 搜尋 + 篩選 =====
(function() {{
    const searchInput = document.getElementById('searchInput');
    const filterYoy = document.getElementById('filterYoy');
    const filterYoyDir = document.getElementById('filterYoyDir');
    const filterYoyVal = document.getElementById('filterYoyVal');
    const filterMom = document.getElementById('filterMom');
    const filterMomDir = document.getElementById('filterMomDir');
    const filterMomVal = document.getElementById('filterMomVal');
    const filterCount = document.getElementById('filterCount');

    function applyFilters() {{
        const q = searchInput.value.trim().toLowerCase();
        const yoyOn = filterYoy.checked;
        const yoyDir = filterYoyDir.value;
        const yoyTh = parseFloat(filterYoyVal.value) || 0;
        const momOn = filterMom.checked;
        const momDir = filterMomDir.value;
        const momTh = parseFloat(filterMomVal.value) || 0;

        const rows = document.querySelectorAll('.stock-row');
        let shown = 0;

        rows.forEach(row => {{
            let show = true;

            // 搜尋
            if (q) {{
                const sid = (row.dataset.sid || '').toLowerCase();
                const sname = (row.dataset.sname || '').toLowerCase();
                if (!sid.includes(q) && !sname.includes(q)) show = false;
            }}

            // YoY 篩選
            if (show && yoyOn) {{
                const yoy = parseFloat(row.dataset.yoy) || 0;
                if (yoyDir === '>' && yoy <= yoyTh) show = false;
                if (yoyDir === '<' && yoy >= yoyTh) show = false;
            }}

            // MoM 篩選
            if (show && momOn) {{
                const mom = parseFloat(row.dataset.mom) || 0;
                if (momDir === '>' && mom <= momTh) show = false;
                if (momDir === '<' && mom >= momTh) show = false;
            }}

            row.style.display = show ? '' : 'none';
            if (show) shown++;
        }});

        filterCount.textContent = shown + ' / ' + rows.length + ' 筆';
    }}

    searchInput.addEventListener('input', applyFilters);
    [filterYoy, filterMom].forEach(cb => cb.addEventListener('change', applyFilters));
    [filterYoyDir, filterMomDir].forEach(sel => sel.addEventListener('change', applyFilters));
    [filterYoyVal, filterMomVal].forEach(inp => inp.addEventListener('input', applyFilters));

    // 初始顯示
    applyFilters();
}})();

// ===== 點擊展開 =====
(function() {{
    const tbody = document.getElementById('tableBody');
    let expandedRow = null;
    let detailRow = null;

    tbody.addEventListener('click', function(e) {{
        if (e.target.closest('a')) return;
        const row = e.target.closest('.stock-row');
        if (!row) return;

        // 關閉舊的
        if (detailRow) {{
            detailRow.remove();
            detailRow = null;
        }}
        if (expandedRow === row) {{
            expandedRow = null;
            return;
        }}
        expandedRow = row;

        const sid = row.dataset.sid;
        const sname = row.dataset.sname;
        const remark = row.dataset.remark || '';
        const chartData = row.dataset.chart || '[]';

        // 建立明細行
        const tr = document.createElement('tr');
        tr.className = 'detail-row';
        const td = document.createElement('td');
        td.colSpan = 7;

        let html = '<div class="detail-content">';

        // 標題 + 連結
        html += '<div class="detail-header">';
        html += '<a href="https://goodinfo.tw/tw/ShowK_ChartFlow.asp?RPT_CAT=IM_MONTH&STOCK_ID=' + sid + '" target="_blank">' + sid + ' ' + sname + ' 歷史營收</a>';
        html += '<div class="detail-links">';
        html += '<a href="https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID=' + sid + '" target="_blank">基本資料</a>';
        html += '<a href="https://concords.moneydj.com/z/zc/zca/zca_' + sid + '.djhtm" target="_blank">查證</a>';
        html += '</div></div>';

        // 備註
        if (remark) {{
            html += '<div class="remark-box">ℹ ' + remark + '</div>';
        }}

        // 圖表 + 歷史表格
        try {{
            const data = JSON.parse(chartData);
            if (data.length > 0) {{
                // 依 year, month 排序
                data.sort((a, b) => a.year * 100 + a.month - b.year * 100 - b.month);
                const maxRev = Math.max(...data.map(d => d.revenue));

                if (maxRev > 0) {{
                    // 柱狀圖
                    html += '<div class="mini-chart">';
                    data.forEach(d => {{
                        const h = Math.max((d.revenue / maxRev) * 100, 2);
                        const isCurrent = (d.year === {rev_year} && d.month === {rev_month});
                        const cls = isCurrent ? 'chart-bar-single current' : 'chart-bar-single';
                        const title = d.year + '/' + d.month + ': ' + (d.revenue / 1000000).toFixed(1) + 'M';
                        html += '<div class="' + cls + '" style="height:' + h + '%" title="' + title + '"></div>';
                    }});
                    html += '</div>';

                    // 月份標籤
                    html += '<div class="chart-labels">';
                    data.forEach(d => {{
                        const yr = d.month === 1 ? d.year : '';
                        html += '<span>' + (yr || d.month) + '</span>';
                    }});
                    html += '</div>';

                    // 歷史表格 (最近12個月)
                    const recent = data.slice(-12).reverse();
                    html += '<table class="history-table"><thead><tr>';
                    html += '<th>年月</th><th>營收(百萬)</th><th>MoM%</th><th>YoY%</th>';
                    html += '</tr></thead><tbody>';
                    for (let i = 0; i < recent.length; i++) {{
                        const d = recent[i];
                        const revM = (d.revenue / 1000000).toFixed(1);
                        // 計算 MoM
                        const prevIdx = data.indexOf(d) - 1;
                        let momStr = '-';
                        if (prevIdx >= 0 && data[prevIdx].revenue > 0) {{
                            const momV = ((d.revenue - data[prevIdx].revenue) / data[prevIdx].revenue * 100);
                            const mColor = momV >= 0 ? '#f85149' : '#3fb950';
                            momStr = '<span style="color:' + mColor + '">' + momV.toFixed(1) + '%</span>';
                        }}
                        // 計算 YoY
                        let yoyStr = '-';
                        const sameMonthPrev = data.find(x => x.year === d.year - 1 && x.month === d.month);
                        if (sameMonthPrev && sameMonthPrev.revenue > 0) {{
                            const yoyV = ((d.revenue - sameMonthPrev.revenue) / sameMonthPrev.revenue * 100);
                            const yColor = yoyV >= 0 ? '#f85149' : '#3fb950';
                            yoyStr = '<span style="color:' + yColor + '">' + yoyV.toFixed(1) + '%</span>';
                        }}
                        html += '<tr><td>' + d.year + '/' + String(d.month).padStart(2, '0') + '</td>';
                        html += '<td style="font-family:Consolas,monospace">' + parseFloat(revM).toLocaleString('en', {{minimumFractionDigits:1}}) + '</td>';
                        html += '<td>' + momStr + '</td><td>' + yoyStr + '</td></tr>';
                    }}
                    html += '</tbody></table>';
                }}
            }}
        }} catch(err) {{}}

        html += '</div>';
        td.innerHTML = html;
        tr.appendChild(td);
        row.parentNode.insertBefore(tr, row.nextSibling);
        detailRow = tr;
    }});
}})();
</script>
</body>
</html>"""
