"""
HTML 報表生成模組
生成類似 chengwaye.com 風格的深色主題靜態 HTML 頁面
支援上市 / 上櫃 / 創新板 / 興櫃 分頁顯示
每張卡片含可展開的歷年同期營收柱狀圖
"""

import os
import json
import logging
from datetime import datetime

import pandas as pd

from config import OUTPUT_DIR
from analyzer import format_revenue

logger = logging.getLogger(__name__)

MARKET_MAP = {
    "sii": {"name": "上市", "key": "sii"},
    "otc": {"name": "上櫃", "key": "otc"},
    "tib": {"name": "創新板", "key": "tib"},
    "emerging": {"name": "興櫃", "key": "emerging"},
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>營收創同期新高 - {year}/{month:02d}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", sans-serif;
    line-height: 1.6;
    min-height: 100vh;
}}

.container {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}}

header {{
    text-align: center;
    padding: 40px 20px 30px;
}}

header h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 8px;
}}

header .subtitle {{
    color: #8b949e;
    font-size: 0.95rem;
}}

header .date-nav {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 20px;
    margin-top: 16px;
}}

header .date-info {{
    font-size: 1.3rem;
    font-weight: 600;
    color: #58a6ff;
}}

.nav-btn {{
    color: #8b949e;
    text-decoration: none;
    font-size: 0.9rem;
    padding: 6px 16px;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
}}

.nav-btn:hover {{
    color: #58a6ff;
    border-color: #58a6ff;
    background: #161b22;
}}

header .update-time {{
    color: #6e7681;
    font-size: 0.8rem;
    margin-top: 4px;
}}

.summary {{
    display: flex;
    justify-content: center;
    gap: 40px;
    margin: 20px 0 30px;
    flex-wrap: wrap;
}}

.summary-item {{
    text-align: center;
}}

.summary-item .number {{
    font-size: 2rem;
    font-weight: 700;
    color: #f85149;
}}

.summary-item .label {{
    font-size: 0.85rem;
    color: #8b949e;
}}

/* ===== 市場分頁 Tab ===== */
.market-tabs {{
    display: flex;
    justify-content: center;
    gap: 0;
    margin: 0 0 30px;
    border-bottom: 2px solid #21262d;
    flex-wrap: wrap;
}}

.market-tab {{
    padding: 12px 24px;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 600;
    color: #8b949e;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
    user-select: none;
}}

.market-tab:hover {{
    color: #e6edf3;
    background: #161b22;
}}

.market-tab.active {{
    color: #58a6ff;
    border-bottom-color: #58a6ff;
}}

.market-tab .tab-count {{
    display: inline-block;
    background: #21262d;
    color: #8b949e;
    border-radius: 10px;
    padding: 1px 8px;
    font-size: 0.75rem;
    margin-left: 6px;
    font-weight: 500;
}}

.market-tab.active .tab-count {{
    background: #58a6ff33;
    color: #58a6ff;
}}

.market-panel {{
    display: none;
}}

.market-panel.active {{
    display: block;
}}

/* ===== 產業區塊 ===== */
.industry-section {{
    background: #161b22;
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
    border: 1px solid #21262d;
}}

.industry-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    background: #1c2128;
    border-bottom: 1px solid #21262d;
}}

.industry-header h2 {{
    font-size: 1.1rem;
    font-weight: 600;
}}

.industry-count {{
    color: #8b949e;
    font-size: 0.9rem;
}}

.stock-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
    padding: 16px;
}}

.stock-card {{
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 16px;
    transition: border-color 0.2s;
}}

.stock-card:hover {{
    border-color: #58a6ff;
}}

.stock-card .top-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8px;
}}

.stock-info {{
    display: flex;
    align-items: baseline;
    gap: 8px;
}}

.stock-name {{
    font-weight: 600;
    font-size: 1rem;
}}

.stock-id {{
    color: #8b949e;
    font-size: 0.85rem;
}}

.revenue-value {{
    font-size: 1.3rem;
    font-weight: 700;
    color: #f85149;
}}

.stock-card .pct-change {{
    color: #f85149;
    font-size: 0.85rem;
}}

.stock-card .pct-change.negative {{
    color: #3fb950;
}}

.stock-card .detail-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 6px;
}}

.stock-card .revenue-label {{
    color: #8b949e;
    font-size: 0.8rem;
}}

.tag {{
    display: inline-block;
    background: #f8514922;
    color: #f85149;
    border: 1px solid #f8514944;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.75rem;
    font-weight: 600;
}}

.exceed-tag {{
    background: #f0883e22;
    color: #f0883e;
    border-color: #f0883e44;
    font-size: 0.75rem;
    padding: 2px 6px;
    border-radius: 4px;
}}

.card-links {{
    display: flex;
    gap: 8px;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #21262d;
}}

.card-link {{
    flex: 1;
    text-align: center;
    padding: 5px 8px;
    font-size: 0.75rem;
    color: #8b949e;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-decoration: none;
    transition: all 0.2s;
}}

.card-link:hover {{
    color: #58a6ff;
    border-color: #58a6ff;
}}

/* ===== 柱狀圖 (MoM 雙柱) ===== */
.chart-toggle {{
    margin-top: 10px;
    border-top: 1px solid #21262d;
}}

.chart-toggle summary {{
    cursor: pointer;
    padding: 8px 0 4px;
    font-size: 0.8rem;
    color: #58a6ff;
    user-select: none;
    list-style: none;
}}

.chart-toggle summary::-webkit-details-marker {{
    display: none;
}}

.chart-toggle summary::before {{
    content: "\\25B6  ";
    font-size: 0.65rem;
    transition: transform 0.2s;
    display: inline-block;
}}

.chart-toggle[open] summary::before {{
    transform: rotate(90deg);
}}

.mini-chart {{
    display: flex;
    align-items: flex-end;
    gap: 2px;
    padding: 12px 2px 4px;
    height: 160px;
}}

.chart-group {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 100%;
    min-width: 0;
}}

.chart-bars-pair {{
    display: flex;
    align-items: flex-end;
    gap: 1px;
    flex: 1;
    width: 100%;
    justify-content: center;
}}

.chart-bar {{
    width: 45%;
    max-width: 14px;
    border-radius: 2px 2px 0 0;
    transition: height 0.3s;
    min-height: 2px;
}}

.chart-bar.prev {{
    background: #58a6ff;
}}

.chart-bar.curr {{
    background: #f0883e;
}}

.chart-bar.curr.is-target {{
    background: #f0883e;
    box-shadow: 0 0 4px #f0883e88;
}}

.chart-month-label {{
    font-size: 0.55rem;
    color: #6e7681;
    margin-top: 3px;
    white-space: nowrap;
    text-align: center;
}}

.chart-month-label.is-target {{
    color: #f0883e;
    font-weight: 600;
}}

.chart-legend {{
    display: flex;
    justify-content: center;
    gap: 16px;
    margin-top: 8px;
    padding-bottom: 4px;
}}

.chart-legend span {{
    font-size: 0.7rem;
    color: #8b949e;
    display: flex;
    align-items: center;
    gap: 4px;
}}

.legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
}}

.legend-dot.prev {{ background: #58a6ff; }}
.legend-dot.curr {{ background: #f0883e; }}

/* ===== 檢視模式切換 ===== */
.view-toggle {{
    display: flex;
    justify-content: flex-end;
    margin-bottom: 16px;
    gap: 4px;
}}

.view-btn {{
    padding: 6px 14px;
    font-size: 0.8rem;
    color: #8b949e;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
}}

.view-btn:hover {{
    color: #e6edf3;
    border-color: #8b949e;
}}

.view-btn.active {{
    color: #58a6ff;
    border-color: #58a6ff;
    background: #58a6ff15;
}}

/* ===== 精簡模式 ===== */
body.compact .stock-grid {{
    grid-template-columns: 1fr;
    gap: 4px;
    padding: 8px;
}}

body.compact .stock-card {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 14px;
    border-radius: 4px;
}}

body.compact .stock-card .top-row {{
    display: contents;
    margin-bottom: 0;
}}

body.compact .stock-info {{
    min-width: 120px;
    gap: 6px;
}}

body.compact .stock-name {{
    font-size: 0.9rem;
}}

body.compact .stock-id {{
    font-size: 0.75rem;
}}

body.compact .revenue-value {{
    font-size: 1rem;
    min-width: 80px;
    text-align: right;
}}

body.compact .stock-card .detail-row {{
    margin-top: 0;
    gap: 4px;
}}

body.compact .stock-card .detail-row .revenue-label {{
    display: none;
}}

body.compact .stock-card .detail-row:nth-child(2),
body.compact .stock-card .detail-row:nth-child(3) {{
    display: none;
}}

body.compact .tag {{
    display: none;
}}

body.compact .card-links {{
    display: none;
}}

body.compact .chart-toggle {{
    display: none;
}}

body.compact .exceed-tag {{
    font-size: 0.7rem;
}}

body.compact .pct-change {{
    font-size: 0.8rem;
}}

body.compact .industry-header {{
    padding: 10px 16px;
}}

body.compact .industry-header h2 {{
    font-size: 0.95rem;
}}

/* compact 表頭列 */
.compact-header {{
    display: none;
}}

body.compact .compact-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 14px;
    font-size: 0.7rem;
    color: #6e7681;
    border-bottom: 1px solid #21262d;
    font-weight: 600;
}}

body.compact .compact-header .ch-name {{ min-width: 120px; }}
body.compact .compact-header .ch-rev {{ min-width: 80px; text-align: right; }}
body.compact .compact-header .ch-pct {{ min-width: 60px; text-align: right; }}

.empty-msg {{
    text-align: center;
    color: #8b949e;
    padding: 60px 20px;
    font-size: 1rem;
}}

footer {{
    text-align: center;
    padding: 40px 20px;
    color: #6e7681;
    font-size: 0.8rem;
}}

@media (max-width: 768px) {{
    .stock-grid {{
        grid-template-columns: 1fr;
    }}
    header h1 {{
        font-size: 1.5rem;
    }}
    .market-tab {{
        padding: 10px 14px;
        font-size: 0.85rem;
    }}
}}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>營收創同期新高</h1>
        <div class="subtitle">自動比對公開資訊觀測站每月營收資料，篩選創近 {compare_years} 年同期新高股票</div>
        <div class="date-nav">
            <a class="nav-btn" href="{prev_month_file}" title="上個月">&#9664; 前一月</a>
            <span class="date-info">{year}/{month:02d}</span>
            <a class="nav-btn" href="{next_month_file}" title="下個月">後一月 &#9654;</a>
        </div>
        <div class="update-time">{update_time} 更新</div>
    </header>

    <div class="summary">
        <div class="summary-item">
            <div class="number">{total_count}</div>
            <div class="label">創同期新高</div>
        </div>
        <div class="summary-item">
            <div class="number">{sii_count}</div>
            <div class="label">上市</div>
        </div>
        <div class="summary-item">
            <div class="number">{otc_count}</div>
            <div class="label">上櫃</div>
        </div>
        <div class="summary-item">
            <div class="number">{tib_count}</div>
            <div class="label">創新板</div>
        </div>
        <div class="summary-item">
            <div class="number">{emerging_count}</div>
            <div class="label">興櫃</div>
        </div>
        <div class="summary-item">
            <div class="number">{industry_count}</div>
            <div class="label">產業別</div>
        </div>
    </div>

    <!-- 市場分頁 -->
    <div class="market-tabs">
        <div class="market-tab active" data-market="all">全部 <span class="tab-count">{total_count}</span></div>
        <div class="market-tab" data-market="sii">上市 <span class="tab-count">{sii_count}</span></div>
        <div class="market-tab" data-market="otc">上櫃 <span class="tab-count">{otc_count}</span></div>
        <div class="market-tab" data-market="tib">創新板 <span class="tab-count">{tib_count}</span></div>
        <div class="market-tab" data-market="emerging">興櫃 <span class="tab-count">{emerging_count}</span></div>
    </div>

    <!-- 檢視模式切換 -->
    <div class="view-toggle">
        <div class="view-btn active" data-view="normal">&#9638; 標準</div>
        <div class="view-btn" data-view="compact">&#9776; 精簡</div>
    </div>

    <!-- 全部面板 -->
    <div class="market-panel active" id="panel-all">
        {all_sections}
    </div>

    <!-- 上市面板 -->
    <div class="market-panel" id="panel-sii">
        {sii_sections}
    </div>

    <!-- 上櫃面板 -->
    <div class="market-panel" id="panel-otc">
        {otc_sections}
    </div>

    <!-- 創新板面板 -->
    <div class="market-panel" id="panel-tib">
        {tib_sections}
    </div>

    <!-- 興櫃面板 -->
    <div class="market-panel" id="panel-emerging">
        {emerging_sections}
    </div>

</div>
<footer>
    資料來源：公開資訊觀測站 (MOPS) / FinMind | 僅供參考，不構成投資建議
</footer>

<script>
// 市場分頁切換
document.querySelectorAll('.market-tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
        document.querySelectorAll('.market-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.market-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('panel-' + tab.dataset.market).classList.add('active');
    }});
}});

// 檢視模式切換 (標準 / 精簡)
document.querySelectorAll('.view-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (btn.dataset.view === 'compact') {{
            document.body.classList.add('compact');
        }} else {{
            document.body.classList.remove('compact');
        }}
    }});
}});
</script>
</body>
</html>"""

INDUSTRY_SECTION_TEMPLATE = """
    <div class="industry-section">
        <div class="industry-header">
            <h2>{industry}</h2>
            <span class="industry-count">{count}檔</span>
        </div>
        <div class="compact-header">
            <span class="ch-name">股票</span>
            <span class="ch-rev">營收</span>
            <span class="ch-pct">年增率</span>
            <span class="ch-pct">月增率</span>
            <span class="ch-pct">超越同期</span>
        </div>
        <div class="stock-grid">
            {cards}
        </div>
    </div>"""

STOCK_CARD_TEMPLATE = """
            <div class="stock-card">
                <div class="top-row">
                    <div class="stock-info">
                        <span class="stock-name">{stock_name}</span>
                        <span class="stock-id">{stock_id}</span>
                    </div>
                    <div class="revenue-value">{revenue_display}</div>
                </div>
                <div class="detail-row">
                    <span class="revenue-label">當月營收</span>
                    <span class="tag">創同期新高</span>
                </div>
                <div class="detail-row">
                    <span class="revenue-label">公布日期</span>
                    <span style="color:#58a6ff;font-size:0.85rem;">{publish_date}</span>
                </div>
                <div class="detail-row">
                    <span class="revenue-label">年增率</span>
                    <span class="pct-change {yoy_class}">{yoy_display}</span>
                </div>
                <div class="detail-row">
                    <span class="revenue-label">月增率</span>
                    <span class="pct-change {mom_class}">{mom_display}</span>
                </div>
                <div class="detail-row">
                    <span class="revenue-label">超越歷史同期</span>
                    <span class="exceed-tag">+{exceed_pct}%</span>
                </div>
                <div class="card-links">
                    <a href="{revenue_url}" target="_blank" class="card-link">營收公告</a>
                    <a href="{goodinfo_url}" target="_blank" class="card-link">基本資料</a>
                    <a href="{verify_url}" target="_blank" class="card-link">查證</a>
                </div>
                {chart_html}
            </div>"""


def _build_chart_html(row: pd.Series, current_year: int, current_month: int = 0) -> str:
    """為單一股票生成近 12 個月 MoM 雙柱圖 HTML (前期 vs 本期)"""
    import json as _json

    monthly_json = row.get("monthly_json", "[]")
    if pd.isna(monthly_json) or not monthly_json:
        return ""

    try:
        monthly = _json.loads(monthly_json)
    except (ValueError, TypeError):
        return ""

    if len(monthly) < 2:
        return ""

    # 建立查詢表 {(year, month): revenue}
    rev_map = {}
    for m in monthly:
        key = (m.get("year", 0), m.get("month", 0))
        rev_map[key] = m.get("revenue", 0)

    # 產生近 12 個月的列表 (含當月)
    months_list = []
    y, mo = current_year, current_month
    for _ in range(12):
        months_list.append((y, mo))
        mo -= 1
        if mo == 0:
            mo = 12
            y -= 1
    months_list.reverse()

    # 找所有數值的最大值 (本期+前期)
    all_vals = []
    for (y, mo) in months_list:
        curr_val = rev_map.get((y, mo), 0)
        prev_val = rev_map.get((y - 1, mo), 0)
        if curr_val > 0:
            all_vals.append(curr_val)
        if prev_val > 0:
            all_vals.append(prev_val)

    if not all_vals:
        return ""

    max_rev = max(all_vals)
    if max_rev == 0:
        return ""

    bars_html = ""
    for (y, mo) in months_list:
        curr_val = rev_map.get((y, mo), 0)
        prev_val = rev_map.get((y - 1, mo), 0)

        curr_h = max((curr_val / max_rev) * 100, 2) if curr_val > 0 else 0
        prev_h = max((prev_val / max_rev) * 100, 2) if prev_val > 0 else 0

        is_target = (y == current_year and mo == current_month)
        target_class = "is-target" if is_target else ""
        label_class = "is-target" if is_target else ""

        label = f"{mo}"

        bars_html += f"""
            <div class="chart-group">
                <div class="chart-bars-pair">
                    <div class="chart-bar prev" style="height:{prev_h:.0f}%" title="前期 {format_revenue(prev_val)}"></div>
                    <div class="chart-bar curr {target_class}" style="height:{curr_h:.0f}%" title="本期 {format_revenue(curr_val)}"></div>
                </div>
                <span class="chart-month-label {label_class}">{label}</span>
            </div>"""

    legend = """
                    <div class="chart-legend">
                        <span><i class="legend-dot prev"></i>前期</span>
                        <span><i class="legend-dot curr"></i>本期</span>
                    </div>"""

    return f"""
                <details class="chart-toggle">
                    <summary>近 12 個月營收走勢</summary>
                    <div class="mini-chart">{bars_html}
                    </div>{legend}
                </details>"""


def _get_external_urls(sid: str, market: str, rev_year: int, rev_month: int) -> tuple[str, str, str]:
    """生成外部連結 URL

    Returns:
        (revenue_url, goodinfo_url, verify_url)
    """
    roc_year = rev_year - 1911

    # Goodinfo 基本資料
    goodinfo_url = f"https://goodinfo.tw/tw/StockDetail.asp?STOCK_ID={sid}"

    # 營收公告 - 使用 Goodinfo 月營收頁面 (MOPS 需要 POST 不支援直開)
    revenue_url = f"https://goodinfo.tw/tw/ShowK_ChartFlow.asp?RPT_CAT=IM_MONTH&STOCK_ID={sid}"

    # 查證 - 使用 MoneyDJ 個股頁面
    verify_url = f"https://concords.moneydj.com/z/zc/zca/zca_{sid}.djhtm"

    # 興櫃股票用 MoneyDJ 興櫃版面
    if market == "emerging":
        revenue_url = f"https://concords.moneydj.com/z/zu/zue/zuef/zuef_{sid}_0_2.djhtm"

    return revenue_url, goodinfo_url, verify_url


def _build_cards(df: pd.DataFrame, current_year: int = 0, current_month: int = 0) -> str:
    """為一組股票 DataFrame 生成卡片 HTML"""
    cards = ""
    for _, row in df.iterrows():
        yoy = row.get("yoy_pct", 0)
        mom = row.get("mom_pct", 0)
        exceed = row.get("exceed_pct", 0)

        yoy_val = float(yoy) if pd.notna(yoy) else 0
        mom_val = float(mom) if pd.notna(mom) else 0
        exceed_val = float(exceed) if pd.notna(exceed) else 0

        # 公布日期
        pub_date = row.get("date", "")
        if pd.notna(pub_date) and pub_date:
            pub_date = str(pub_date)[:10]
        else:
            pub_date = "N/A"

        # 生成外部連結
        sid = str(row.get("stock_id", ""))
        market = str(row.get("market", ""))
        rev_year = int(row.get("revenue_year", 0)) if pd.notna(row.get("revenue_year", None)) else 0
        rev_month = int(row.get("revenue_month", 0)) if pd.notna(row.get("revenue_month", None)) else 0

        revenue_url, goodinfo_url, verify_url = _get_external_urls(sid, market, rev_year, rev_month)

        # 柱狀圖
        chart_html = _build_chart_html(row, current_year, current_month) if current_year > 0 else ""

        cards += STOCK_CARD_TEMPLATE.format(
            stock_name=row.get("stock_name", ""),
            stock_id=sid,
            revenue_display=format_revenue(row.get("revenue", 0)),
            publish_date=pub_date,
            yoy_display=f"{yoy_val:+.2f}%" if yoy_val != 0 else "N/A",
            yoy_class="" if yoy_val >= 0 else "negative",
            mom_display=f"{mom_val:+.2f}%" if mom_val != 0 else "N/A",
            mom_class="" if mom_val >= 0 else "negative",
            exceed_pct=f"{exceed_val:.1f}",
            revenue_url=revenue_url,
            goodinfo_url=goodinfo_url,
            verify_url=verify_url,
            chart_html=chart_html,
        )
    return cards


def _build_industry_sections(df: pd.DataFrame, current_year: int = 0, current_month: int = 0) -> str:
    """依產業分組生成區塊 HTML"""
    if df.empty:
        return '<p class="empty-msg">本分類無營收創同期新高資料</p>'

    sections = ""
    grouped = df.groupby("industry")

    for industry, group in sorted(grouped, key=lambda x: -len(x[1])):
        cards = _build_cards(group, current_year, current_month)
        sections += INDUSTRY_SECTION_TEMPLATE.format(
            industry=industry,
            count=len(group),
            cards=cards,
        )
    return sections


def generate_html(df: pd.DataFrame, year: int, month: int, compare_years: int = 5) -> str:
    """生成 HTML 報表"""
    if df.empty:
        return _generate_empty_html(year, month, compare_years)

    # 各市場計數
    sii_count = len(df[df["market"] == "sii"]) if "market" in df.columns else 0
    otc_count = len(df[df["market"] == "otc"]) if "market" in df.columns else 0
    tib_count = len(df[df["market"] == "tib"]) if "market" in df.columns else 0
    emerging_count = len(df[df["market"] == "emerging"]) if "market" in df.columns else 0
    industries = df["industry"].nunique() if "industry" in df.columns else 0

    # 各面板的產業區塊
    all_sections = _build_industry_sections(df, year, month)
    sii_sections = _build_industry_sections(df[df["market"] == "sii"], year, month) if sii_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    otc_sections = _build_industry_sections(df[df["market"] == "otc"], year, month) if otc_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    tib_sections = _build_industry_sections(df[df["market"] == "tib"], year, month) if tib_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    emerging_sections = _build_industry_sections(df[df["market"] == "emerging"], year, month) if emerging_count > 0 else '<p class="empty-msg">本分類無資料</p>'

    # 計算上/下月檔名
    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
    prev_month_file = f"{prev_y}_{prev_m:02d}.html"
    next_month_file = f"{next_y}_{next_m:02d}.html"

    html = HTML_TEMPLATE.format(
        year=year,
        month=month,
        compare_years=compare_years,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_count=len(df),
        sii_count=sii_count,
        otc_count=otc_count,
        tib_count=tib_count,
        emerging_count=emerging_count,
        industry_count=industries,
        prev_month_file=prev_month_file,
        next_month_file=next_month_file,
        all_sections=all_sections,
        sii_sections=sii_sections,
        otc_sections=otc_sections,
        tib_sections=tib_sections,
        emerging_sections=emerging_sections,
    )
    return html


def _generate_empty_html(year: int, month: int, compare_years: int = 5) -> str:
    """無資料時的 HTML"""
    empty = '<p class="empty-msg">本期無營收創同期新高資料</p>'
    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
    return HTML_TEMPLATE.format(
        year=year,
        month=month,
        compare_years=compare_years,
        update_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_count=0,
        sii_count=0,
        otc_count=0,
        tib_count=0,
        emerging_count=0,
        industry_count=0,
        prev_month_file=f"{prev_y}_{prev_m:02d}.html",
        next_month_file=f"{next_y}_{next_m:02d}.html",
        all_sections=empty,
        sii_sections=empty,
        otc_sections=empty,
        tib_sections=empty,
        emerging_sections=empty,
    )


def save_html(html: str, filename: str = "index.html") -> str:
    """儲存 HTML 檔案"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"報表已輸出: {path}")
    return path
