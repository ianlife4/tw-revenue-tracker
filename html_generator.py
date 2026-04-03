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

/* ===== 備註 ===== */
.remark-row {{
    margin-top: 8px;
    padding: 6px 10px;
    background: #1c2128;
    border-left: 3px solid #f0883e;
    border-radius: 0 4px 4px 0;
    font-size: 0.78rem;
    color: #d2a8ff;
    line-height: 1.5;
}}

.remark-icon {{
    color: #f0883e;
    margin-right: 4px;
}}

/* ===== T+1 歷史表現 ===== */
.t1-box {{
    margin-top: 10px;
    padding: 8px 10px;
    background: #1c2128;
    border-left: 3px solid #58a6ff;
    border-radius: 0 4px 4px 0;
    font-size: 0.78rem;
}}

.t1-title {{
    color: #58a6ff;
    font-weight: 600;
    margin-bottom: 4px;
}}

.t1-stats {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 4px;
}}

.t1-stats span {{
    color: #8b949e;
}}

.t1-detail {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 4px;
    padding-top: 4px;
    border-top: 1px solid #21262d;
}}

.t1-item {{
    font-family: "Consolas", "Monaco", monospace;
    font-size: 0.72rem;
    color: #8b949e;
    background: #0d1117;
    padding: 1px 6px;
    border-radius: 3px;
}}

/* ===== 推播提醒 ===== */
.alert-section {{
    margin: 20px 0;
    padding: 16px;
    background: linear-gradient(135deg, #1c1f2b 0%, #1a1e2e 100%);
    border: 1px solid #f0883e44;
    border-radius: 10px;
}}

.alert-title {{
    font-size: 1rem;
    font-weight: 700;
    color: #f0883e;
    margin-bottom: 12px;
}}

.alert-card {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 12px;
    background: #161b22;
    border-radius: 6px;
    margin-bottom: 8px;
    border-left: 3px solid #f0883e;
}}

.alert-card .alert-sid {{
    font-family: "Consolas", monospace;
    font-weight: 700;
    color: #58a6ff;
    min-width: 50px;
}}

.alert-card .alert-name {{
    font-weight: 600;
    min-width: 70px;
}}

.alert-card .alert-avg {{
    font-family: "Consolas", monospace;
    font-weight: 700;
    color: #f85149;
    min-width: 60px;
}}

.alert-card .alert-msg {{
    font-size: 0.78rem;
    color: #8b949e;
    flex: 1;
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

/* ===== 柱狀圖 Tooltip ===== */
.chart-tooltip {{
    position: absolute;
    background: #1c2128;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 0.75rem;
    color: #e6edf3;
    pointer-events: none;
    z-index: 100;
    white-space: nowrap;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    line-height: 1.6;
    opacity: 0;
    transition: opacity 0.15s;
}}

.chart-tooltip.visible {{
    opacity: 1;
}}

.chart-tooltip .tt-month {{
    font-weight: 600;
    color: #58a6ff;
    margin-bottom: 2px;
}}

.chart-tooltip .tt-row {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
}}

.chart-tooltip .tt-label {{
    color: #8b949e;
}}

.chart-tooltip .tt-val {{
    font-weight: 600;
}}

.chart-tooltip .tt-val.prev {{ color: #58a6ff; }}
.chart-tooltip .tt-val.curr {{ color: #f0883e; }}
.chart-tooltip .tt-val.yoy-pos {{ color: #f85149; }}
.chart-tooltip .tt-val.yoy-neg {{ color: #3fb950; }}

.mini-chart {{
    position: relative;
}}

.chart-group {{
    cursor: pointer;
}}

.chart-group:hover .chart-bar.prev {{
    background: #79bbff;
}}

.chart-group:hover .chart-bar.curr {{
    background: #f5a664;
}}

/* ===== 日期篩選 + 工具列 ===== */
.toolbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 16px;
}}

.date-filter {{
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
}}

.date-filter .date-label {{
    color: #6e7681;
    font-size: 0.8rem;
    margin-right: 4px;
}}

.date-pill {{
    padding: 4px 10px;
    font-size: 0.75rem;
    color: #8b949e;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
    white-space: nowrap;
}}

.date-pill:hover {{
    color: #e6edf3;
    border-color: #8b949e;
}}

.date-pill.active {{
    color: #f0883e;
    border-color: #f0883e;
    background: #f0883e15;
}}

/* 排序模式下隱藏產業分組標題 */
body.sort-mode .industry-header {{
    display: none;
}}

body.sort-mode .industry-section {{
    background: transparent;
    border: none;
    margin-bottom: 0;
}}

body.sort-mode .stock-grid {{
    padding: 0;
}}

/* ===== 搜尋列 ===== */
.search-bar {{
    display: flex;
    justify-content: center;
    margin-bottom: 20px;
}}

.search-bar input {{
    width: 100%;
    max-width: 480px;
    padding: 10px 16px 10px 40px;
    font-size: 0.95rem;
    color: #e6edf3;
    background: #161b22 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%238b949e' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85zm-5.242.156a5 5 0 1 1 0-10 5 5 0 0 1 0 10z'/%3E%3C/svg%3E") no-repeat 12px center;
    border: 1px solid #30363d;
    border-radius: 8px;
    outline: none;
    transition: border-color 0.2s;
}}

.search-bar input::placeholder {{
    color: #6e7681;
}}

.search-bar input:focus {{
    border-color: #58a6ff;
    background-color: #0d1117;
}}

.search-result-info {{
    text-align: center;
    color: #8b949e;
    font-size: 0.85rem;
    margin: -10px 0 16px;
    display: none;
}}

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

/* ===== 精簡模式 (表格風格) ===== */
body.compact .stock-grid {{
    display: table;
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    padding: 0;
}}

body.compact .stock-card {{
    display: table-row;
    padding: 0;
    border-radius: 0;
    border: none;
    background: transparent;
    cursor: pointer;
    transition: background 0.15s;
}}

body.compact .stock-card:hover {{
    background: rgba(88,166,255,0.08);
    border-color: transparent;
}}

body.compact .stock-card .top-row {{
    display: contents;
}}

body.compact .stock-info {{
    display: table-cell;
    padding: 8px 12px;
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

body.compact .stock-name {{
    font-size: 0.88rem;
    color: #58a6ff;
}}

body.compact .stock-id {{
    font-size: 0.75rem;
    color: #6e7681;
    margin-left: 6px;
}}

body.compact .revenue-value {{
    display: table-cell;
    padding: 8px 12px;
    vertical-align: middle;
    text-align: right;
    font-size: 0.95rem;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

body.compact .stock-card .detail-row {{
    display: none;
}}

body.compact .stock-card .detail-row:nth-child(4),
body.compact .stock-card .detail-row:nth-child(5),
body.compact .stock-card .detail-row:nth-child(6) {{
    display: table-cell;
    padding: 8px 10px;
    vertical-align: middle;
    text-align: right;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

body.compact .stock-card .detail-row .revenue-label {{
    display: none;
}}

body.compact .pct-change {{
    font-size: 0.85rem;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
}}

body.compact .exceed-tag {{
    font-size: 0.8rem;
    font-family: "Consolas", "Monaco", "Courier New", monospace;
    background: transparent;
    border: none;
    padding: 0;
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

body.compact .remark-row {{
    display: none;
}}

/* compact T+1: 作為表格欄位顯示 */
body.compact .t1-box {{
    display: table-cell;
    padding: 4px 10px;
    vertical-align: middle;
    margin: 0;
    border-left: none;
    border-radius: 0;
    background: transparent;
    overflow: hidden;
}}

body.compact .t1-title {{
    font-size: 0.72rem;
    margin-bottom: 2px;
}}

body.compact .t1-stats {{
    gap: 8px;
    margin-bottom: 2px;
    font-size: 0.72rem;
}}

body.compact .t1-detail {{
    gap: 4px;
    margin-top: 2px;
    padding-top: 2px;
}}

body.compact .t1-item {{
    font-size: 0.65rem;
    padding: 0px 4px;
}}

/* compact 展開狀態 */
body.compact .stock-card.expanded {{
    display: table-row;
    background: #161b22;
}}

body.compact .stock-card.expanded + .expanded-detail {{
    display: table-row;
}}

.expanded-detail {{
    display: none;
}}

/* 展開行內的元素恢復顯示 */
.expanded-detail-row .chart-toggle {{
    display: block !important;
}}

.expanded-detail-row .t1-box {{
    display: block !important;
    max-width: 100%;
    background: #1c2128;
    border-left: 3px solid #58a6ff;
    border-radius: 0 4px 4px 0;
    padding: 8px 10px;
}}

.expanded-detail-row .remark-row {{
    display: block !important;
}}

.expanded-detail-row .card-links {{
    display: flex !important;
}}

body.compact .industry-header {{
    padding: 10px 16px;
}}

body.compact .industry-header h2 {{
    font-size: 0.95rem;
}}

/* compact 表頭列 (可點排序) */
.compact-header {{
    display: none;
}}

body.compact .compact-header {{
    display: table-row;
    font-size: 0.72rem;
    color: #6e7681;
    font-weight: 600;
    background: #161b22;
}}

body.compact .compact-header .ch-col {{
    display: table-cell;
    padding: 8px 12px;
    cursor: pointer;
    user-select: none;
    transition: color 0.2s;
    white-space: nowrap;
    border-bottom: 2px solid #21262d;
    vertical-align: middle;
}}

body.compact .compact-header .ch-name {{ width: 12%; }}
body.compact .compact-header .ch-rev {{ width: 11%; }}
body.compact .compact-header .ch-yoy {{ width: 9%; }}
body.compact .compact-header .ch-mom {{ width: 9%; }}
body.compact .compact-header .ch-exceed {{ width: 9%; }}
body.compact .compact-header .ch-t1 {{ width: auto; }}

body.compact .compact-header .ch-col:not(.ch-name) {{
    text-align: right;
    padding-right: 10px;
}}

body.compact .compact-header .ch-col:hover {{
    color: #e6edf3;
}}

body.compact .compact-header .ch-col.sort-active {{
    color: #58a6ff;
    border-bottom-color: #58a6ff;
}}

body.compact .compact-header .ch-col .sort-arrow {{
    font-size: 0.6rem;
    margin-left: 2px;
    opacity: 0.4;
}}

body.compact .compact-header .ch-col.sort-active .sort-arrow {{
    opacity: 1;
}}

/* 行間交替色 */
body.compact .stock-card:nth-child(even) {{
    background: rgba(22,27,34,0.5);
}}

body.compact .stock-card:nth-child(even):hover {{
    background: rgba(88,166,255,0.08);
}}

@media (max-width: 768px) {{
    body.compact .stock-info {{
        padding: 6px 8px;
    }}
    body.compact .revenue-value {{
        padding: 6px 8px;
        font-size: 0.82rem;
    }}
    body.compact .stock-card .detail-row:nth-child(4),
    body.compact .stock-card .detail-row:nth-child(5),
    body.compact .stock-card .detail-row:nth-child(6) {{
        padding: 6px 6px;
    }}
    body.compact .pct-change {{
        font-size: 0.78rem;
    }}
    body.compact .compact-header .ch-col {{
        padding: 6px 8px;
        font-size: 0.65rem;
    }}
}}

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
        <div style="margin-top:12px"><a href="index.html" style="color:#58a6ff;text-decoration:none;font-size:0.85rem;padding:4px 12px;border:1px solid #30363d;border-radius:6px;">← 即時申報</a></div>
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

    <!-- 搜尋 -->
    <div class="search-bar">
        <input type="text" id="stockSearch" placeholder="搜尋股票代號或名稱 (例: 2330 或 台積電)" autocomplete="off">
    </div>
    <div class="search-result-info" id="searchResultInfo"></div>

    <!-- 工具列 -->
    <div class="toolbar">
        {date_filter_html}
        <div class="view-toggle">
            <div class="view-btn active" data-view="normal">&#9638; 標準</div>
            <div class="view-btn" data-view="compact">&#9776; 精簡</div>
        </div>
    </div>

    {alert_html}

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

// ===== 排序 (點 compact 表頭欄位) + 日期篩選 =====
(function() {{
    let currentSort = null;
    let sortAsc = false;
    const attrMap = {{ rev: 'data-rev', yoy: 'data-yoy', mom: 'data-mom', exceed: 'data-exceed' }};

    // 點擊 compact 表頭排序
    document.addEventListener('click', function(e) {{
        const col = e.target.closest('.ch-col[data-sort]');
        if (!col) return;

        const sortKey = col.dataset.sort;
        if (currentSort === sortKey) {{
            sortAsc = !sortAsc;
        }} else {{
            currentSort = sortKey;
            sortAsc = false;
        }}

        // 更新所有表頭的箭頭顯示
        document.querySelectorAll('.ch-col[data-sort]').forEach(c => {{
            c.classList.remove('sort-active');
            const arrow = c.querySelector('.sort-arrow');
            if (arrow) arrow.textContent = '▼';
        }});
        // 點到的那欄 + 同 data-sort 的所有表頭都高亮
        document.querySelectorAll('.ch-col[data-sort="' + sortKey + '"]').forEach(c => {{
            c.classList.add('sort-active');
            const arrow = c.querySelector('.sort-arrow');
            if (arrow) arrow.textContent = sortAsc ? '▲' : '▼';
        }});

        doSort(sortKey, sortAsc);
    }});

    function doSort(sortKey, asc) {{
        const attr = attrMap[sortKey];
        if (!attr) return;

        document.body.classList.add('sort-mode');

        // 對當前可見的 panel 排序
        document.querySelectorAll('.market-panel').forEach(panel => {{
            const grids = panel.querySelectorAll('.stock-grid');
            grids.forEach(grid => {{
                const cards = Array.from(grid.querySelectorAll('.stock-card'));
                if (cards.length === 0) return;

                cards.sort((a, b) => {{
                    const va = parseFloat(a.getAttribute(attr));
                    const vb = parseFloat(b.getAttribute(attr));
                    const na = isNaN(va) ? -Infinity : va;
                    const nb = isNaN(vb) ? -Infinity : vb;
                    return asc ? (na - nb) : (nb - na);
                }});

                cards.forEach(c => grid.appendChild(c));
            }});
        }});

        applyDateFilter();
        applySearch();
    }}

    // ===== 日期篩選 =====
    let currentDate = 'all';

    document.addEventListener('click', function(e) {{
        const pill = e.target.closest('.date-pill');
        if (!pill) return;

        document.querySelectorAll('.date-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        currentDate = pill.dataset.date;
        applyDateFilter();
    }});

    function applyDateFilter() {{
        const cards = document.querySelectorAll('.stock-card');
        cards.forEach(card => {{
            if (currentDate === 'all') {{
                card.removeAttribute('data-date-hidden');
                if (!card.getAttribute('data-search-hidden')) {{
                    card.style.display = '';
                }}
            }} else {{
                const cardDate = card.dataset.filingDate || card.dataset.date || '';
                if (cardDate === currentDate || cardDate.startsWith(currentDate)) {{
                    card.removeAttribute('data-date-hidden');
                    if (!card.getAttribute('data-search-hidden')) {{
                        card.style.display = '';
                    }}
                }} else {{
                    card.setAttribute('data-date-hidden', '1');
                    card.style.display = 'none';
                }}
            }}
        }});
        updateSectionVisibility();
    }}

    function updateSectionVisibility() {{
        document.querySelectorAll('.industry-section').forEach(section => {{
            const visible = section.querySelectorAll('.stock-card:not([style*="display: none"])');
            section.style.display = visible.length > 0 ? '' : 'none';
        }});
    }}

    function applySearch() {{
        const input = document.getElementById('stockSearch');
        if (input && input.value.trim()) {{
            input.dispatchEvent(new Event('input'));
        }}
    }}

    window._applyDateFilter = applyDateFilter;
}})();

// ===== 精簡模式點擊展開卡片 =====
(function() {{
    let expandedRow = null;

    document.addEventListener('click', function(e) {{
        if (!document.body.classList.contains('compact')) return;
        if (e.target.closest('a') || e.target.closest('summary') || e.target.closest('.ch-col')) return;

        const card = e.target.closest('.stock-card');
        if (!card) return;

        // 移除之前的展開行
        const oldDetail = document.querySelector('.expanded-detail-row');
        if (oldDetail) {{
            oldDetail.remove();
            if (expandedRow === card) {{
                card.classList.remove('expanded');
                expandedRow = null;
                return;
            }}
        }}
        if (expandedRow) expandedRow.classList.remove('expanded');

        // 建立展開行
        card.classList.add('expanded');
        expandedRow = card;

        const detail = document.createElement('tr');
        detail.className = 'expanded-detail-row';
        const td = document.createElement('td');
        td.colSpan = 7;
        td.style.padding = '12px 16px';
        td.style.background = '#161b22';
        td.style.borderTop = '1px solid #21262d';
        td.style.borderBottom = '1px solid #21262d';

        // 複製原始卡片的詳細內容
        const remark = card.querySelector('.remark-row');
        const t1box = card.querySelector('.t1-box');
        const chart = card.querySelector('.chart-toggle');
        const links = card.querySelector('.card-links');

        let html = '';
        if (remark) html += '<div style="margin-bottom:10px">' + remark.outerHTML + '</div>';
        if (t1box) html += '<div style="margin-bottom:10px">' + t1box.outerHTML + '</div>';
        if (links) {{
            html += '<div style="display:flex;gap:8px;margin-bottom:10px">';
            links.querySelectorAll('a').forEach(a => {{
                html += '<a href="' + a.href + '" target="_blank" class="card-link">' + a.textContent + '</a>';
            }});
            html += '</div>';
        }}
        if (chart) html += chart.outerHTML;

        td.innerHTML = html;
        detail.appendChild(td);

        // 插入到卡片後面
        card.parentNode.insertBefore(detail, card.nextSibling);

        // 開啟 details
        const det = detail.querySelector('details');
        if (det) det.open = true;
    }});
}})();

// 個股搜尋
(function() {{
    const searchInput = document.getElementById('stockSearch');
    const searchInfo = document.getElementById('searchResultInfo');
    let debounceTimer;

    searchInput.addEventListener('input', function() {{
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => filterCards(this.value.trim()), 150);
    }});

    // 按 Esc 清除搜尋
    searchInput.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            this.value = '';
            filterCards('');
            this.blur();
        }}
    }});

    function filterCards(query) {{
        const cards = document.querySelectorAll('.stock-card');
        const sections = document.querySelectorAll('.industry-section');

        if (!query) {{
            // 清除搜尋
            cards.forEach(c => {{
                c.removeAttribute('data-search-hidden');
                if (!c.getAttribute('data-date-hidden')) {{
                    c.style.display = '';
                }}
            }});
            sections.forEach(s => s.style.display = '');
            searchInfo.style.display = 'none';
            if (window._applyDateFilter) window._applyDateFilter();
            return;
        }}

        const q = query.toLowerCase();
        let matchCount = 0;

        cards.forEach(card => {{
            const sid = (card.dataset.sid || '').toLowerCase();
            const sname = (card.dataset.sname || '').toLowerCase();
            const match = sid.includes(q) || sname.includes(q);
            if (match) {{
                card.removeAttribute('data-search-hidden');
                if (!card.getAttribute('data-date-hidden')) {{
                    card.style.display = '';
                    matchCount++;
                }}
            }} else {{
                card.setAttribute('data-search-hidden', '1');
                card.style.display = 'none';
            }}
        }});

        // 隱藏空的產業區塊
        sections.forEach(section => {{
            const visibleCards = section.querySelectorAll('.stock-card:not([style*="display: none"])');
            section.style.display = visibleCards.length > 0 ? '' : 'none';
        }});

        // 顯示搜尋結果數
        searchInfo.style.display = 'block';
        if (matchCount > 0) {{
            searchInfo.textContent = '找到 ' + matchCount + ' 檔符合「' + query + '」';
            searchInfo.style.color = '#8b949e';
        }} else {{
            searchInfo.textContent = '找不到「' + query + '」相關股票';
            searchInfo.style.color = '#f85149';
        }}
    }}
}})();

// 柱狀圖 Tooltip (hover + touch)
(function() {{
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    document.body.appendChild(tooltip);

    let activeGroup = null;

    function showTooltip(group, x, y) {{
        const month = group.dataset.month || '';
        const prev = group.dataset.prev || 'N/A';
        const curr = group.dataset.curr || 'N/A';
        const yoy = group.dataset.yoy || 'N/A';

        const yoyNum = parseFloat(yoy);
        const yoyClass = isNaN(yoyNum) ? '' : (yoyNum >= 0 ? 'yoy-pos' : 'yoy-neg');

        tooltip.innerHTML =
            '<div class="tt-month">' + month + '</div>' +
            '<div class="tt-row"><span class="tt-label">本期</span><span class="tt-val curr">' + curr + '</span></div>' +
            '<div class="tt-row"><span class="tt-label">前期</span><span class="tt-val prev">' + prev + '</span></div>' +
            '<div class="tt-row"><span class="tt-label">年增</span><span class="tt-val ' + yoyClass + '">' + yoy + '</span></div>';

        // 定位: 優先顯示在上方
        tooltip.style.display = 'block';
        tooltip.classList.add('visible');

        const rect = group.getBoundingClientRect();
        const ttRect = tooltip.getBoundingClientRect();
        let left = rect.left + rect.width / 2 - ttRect.width / 2;
        let top = rect.top - ttRect.height - 8;

        // 邊界修正
        if (left < 4) left = 4;
        if (left + ttRect.width > window.innerWidth - 4) left = window.innerWidth - ttRect.width - 4;
        if (top < 4) top = rect.bottom + 8;

        tooltip.style.left = left + window.scrollX + 'px';
        tooltip.style.top = top + window.scrollY + 'px';

        activeGroup = group;
    }}

    function hideTooltip() {{
        tooltip.classList.remove('visible');
        activeGroup = null;
    }}

    // Desktop: hover
    document.addEventListener('mouseover', function(e) {{
        const group = e.target.closest('.chart-group');
        if (group) {{
            showTooltip(group);
        }}
    }});

    document.addEventListener('mouseout', function(e) {{
        const group = e.target.closest('.chart-group');
        if (group) {{
            const related = e.relatedTarget;
            if (!group.contains(related)) {{
                hideTooltip();
            }}
        }}
    }});

    // Mobile: touch
    document.addEventListener('touchstart', function(e) {{
        const group = e.target.closest('.chart-group');
        if (group) {{
            e.preventDefault();
            if (activeGroup === group) {{
                hideTooltip();
            }} else {{
                showTooltip(group);
            }}
        }} else if (!e.target.closest('.chart-tooltip')) {{
            hideTooltip();
        }}
    }}, {{ passive: false }});
}})();
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
            <span class="ch-col ch-name">股票</span>
            <span class="ch-col ch-rev" data-sort="rev">營收(百萬) <span class="sort-arrow">▼</span></span>
            <span class="ch-col ch-yoy" data-sort="yoy">YoY% <span class="sort-arrow">▼</span></span>
            <span class="ch-col ch-mom" data-sort="mom">MoM% <span class="sort-arrow">▼</span></span>
            <span class="ch-col ch-exceed" data-sort="exceed">超越同期 <span class="sort-arrow">▼</span></span>
            <span class="ch-col ch-t1">T+1 歷史</span>
        </div>
        <div class="stock-grid">
            {cards}
        </div>
    </div>"""

STOCK_CARD_TEMPLATE = """
            <div class="stock-card" data-sid="{stock_id}" data-sname="{stock_name}" data-rev="{revenue_raw}" data-yoy="{yoy_raw}" data-mom="{mom_raw}" data-exceed="{exceed_raw}" data-date="{publish_date}" data-filing-date="{filing_date}">
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
                {date_row_html}
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
                {remark_html}
                {t1_html}
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

        # YoY: (本期 - 前期) / 前期 * 100
        if curr_val > 0 and prev_val > 0:
            yoy_val = (curr_val - prev_val) / prev_val * 100
            yoy_str = f"{yoy_val:+.1f}%"
        else:
            yoy_str = "N/A"

        label = f"{mo}"

        bars_html += f"""
            <div class="chart-group" data-month="{y}/{mo:02d}" data-prev="{format_revenue(prev_val)}" data-curr="{format_revenue(curr_val)}" data-yoy="{yoy_str}">
                <div class="chart-bars-pair">
                    <div class="chart-bar prev" style="height:{prev_h:.0f}%"></div>
                    <div class="chart-bar curr {target_class}" style="height:{curr_h:.0f}%"></div>
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

        # 公布日期 (MOPS CSV 只有出表日期，非個股公告日)
        pub_date = row.get("date", "")
        if pd.notna(pub_date) and pub_date:
            pub_date = str(pub_date)[:10]
        else:
            pub_date = ""

        # 生成外部連結
        sid = str(row.get("stock_id", ""))
        market = str(row.get("market", ""))
        rev_year = int(row.get("revenue_year", 0)) if pd.notna(row.get("revenue_year", None)) else 0
        rev_month = int(row.get("revenue_month", 0)) if pd.notna(row.get("revenue_month", None)) else 0

        revenue_url, goodinfo_url, verify_url = _get_external_urls(sid, market, rev_year, rev_month)

        # 柱狀圖
        chart_html = _build_chart_html(row, current_year, current_month) if current_year > 0 else ""

        revenue_raw = float(row.get("revenue", 0)) if pd.notna(row.get("revenue", 0)) else 0

        # 備註 (MOPS 營收變動原因)
        remark = row.get("remark", "")
        if pd.notna(remark) and str(remark).strip() and str(remark).strip() != "-":
            remark_text = str(remark).strip()
            remark_html = f'<div class="remark-row"><span class="remark-icon">&#9432;</span> {remark_text}</div>'
        else:
            remark_html = ""

        # 申報日期行 — 優先用 first_seen (精確)，否則用 publish_date
        first_seen = row.get("first_seen", "")
        if pd.notna(first_seen) and str(first_seen).strip():
            filing_display = str(first_seen).strip()
            # first_seen format: "04-01 22:45" → extract date part "4/1"
            try:
                parts = filing_display.split(" ")[0].split("-")
                filing_short = f"{int(parts[0])}/{int(parts[1])}"
            except (ValueError, IndexError):
                filing_short = filing_display
        elif pub_date:
            filing_display = pub_date
            try:
                parts = str(pub_date).replace("-", "/").split("/")
                filing_short = f"{int(parts[-2])}/{int(parts[-1])}"
            except (ValueError, IndexError):
                filing_short = pub_date
        else:
            filing_display = ""
            filing_short = ""

        date_row_html = ""
        if filing_display:
            date_row_html = f"""<div class="detail-row">
                    <span class="revenue-label">申報時間</span>
                    <span style="color:#58a6ff;font-size:0.85rem;">{filing_display}</span>
                </div>"""

        # T+1 歷史表現
        t1_html = ""
        t1_count = int(row.get("t1_count", 0)) if pd.notna(row.get("t1_count", 0)) else 0
        if t1_count > 0:
            t1_avg = float(row.get("t1_avg", 0))
            t1_hit = float(row.get("t1_hit_rate", 0))
            t1_max = float(row.get("t1_max", 0))
            avg_color = "#f85149" if t1_avg >= 0 else "#3fb950"
            t1_html = f'''<div class="t1-box">
                    <div class="t1-title">📊 T+1 歷史表現 ({t1_count}次創新高)</div>
                    <div class="t1-stats">
                        <span>平均 <b style="color:{avg_color}">{t1_avg:+.1f}%</b></span>
                        <span>最高 <b style="color:#f85149">{t1_max:+.1f}%</b></span>
                        <span>正報酬率 <b>{t1_hit:.0f}%</b></span>
                    </div>'''
            # 歷史明細
            try:
                import json as _j
                details = _j.loads(row.get("t1_detail_json", "[]"))
                if details:
                    t1_html += '<div class="t1-detail">'
                    for d in details:
                        pct = d.get("t1_pct", 0)
                        color = "#f85149" if pct >= 0 else "#3fb950"
                        t1_html += (f'<span class="t1-item">'
                                    f'{d.get("year")}/{d.get("month"):02d} '
                                    f'<b style="color:{color}">{pct:+.1f}%</b></span>')
                    t1_html += '</div>'
            except Exception:
                pass
            t1_html += '</div>'

        cards += STOCK_CARD_TEMPLATE.format(
            stock_name=row.get("stock_name", ""),
            stock_id=sid,
            revenue_display=format_revenue(row.get("revenue", 0)),
            revenue_raw=revenue_raw,
            yoy_raw=yoy_val,
            mom_raw=mom_val,
            exceed_raw=exceed_val,
            publish_date=pub_date,
            date_row_html=date_row_html,
            filing_date=filing_short,
            yoy_display=f"{yoy_val:+.2f}%" if yoy_val != 0 else "N/A",
            yoy_class="" if yoy_val >= 0 else "negative",
            mom_display=f"{mom_val:+.2f}%" if mom_val != 0 else "N/A",
            mom_class="" if mom_val >= 0 else "negative",
            exceed_pct=f"{exceed_val:.1f}",
            remark_html=remark_html,
            t1_html=t1_html,
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


def _build_date_pills(df: pd.DataFrame) -> str:
    """從資料中提取申報日期（first_seen），生成日期 pill 按鈕"""
    # 優先用 first_seen，否則用 date / publish_date
    if "first_seen" in df.columns:
        # first_seen format: "04-01 22:45" → extract "04-01"
        dates = df["first_seen"].dropna().astype(str).str.strip()
        dates = dates[dates != ""].str[:5]  # "04-01"
    elif "date" in df.columns or "publish_date" in df.columns:
        date_col = "publish_date" if "publish_date" in df.columns else "date"
        dates = df[date_col].dropna().astype(str).str.strip()
        dates = dates[dates != ""].str[:10]
    else:
        return ""

    # 統計每個日期的筆數
    date_counts = dates.value_counts().sort_index()
    if date_counts.empty:
        return ""

    pills = ""
    for date_str, count in date_counts.items():
        # "04-01" → "4/1"
        display = date_str
        try:
            parts = str(date_str).replace("-", "/").replace("/", "-").split("-")
            if len(parts) >= 2:
                m = int(parts[0]) if len(parts[0]) <= 2 else int(parts[-2])
                d = int(parts[1]) if len(parts[0]) <= 2 else int(parts[-1])
                display = f"{m}/{d}"
        except (ValueError, IndexError):
            pass
        pills += f'<div class="date-pill" data-date="{date_str}">{display} <span style="font-size:0.65rem;color:#6e7681">({count})</span></div>\n            '

    return pills


def generate_html(df: pd.DataFrame, year: int, month: int, compare_years: int = 5,
                   early_alerts: list = None) -> str:
    """生成 HTML 報表"""
    if df.empty:
        return _generate_empty_html(year, month, compare_years)

    # 各市場計數
    sii_count = len(df[df["market"] == "sii"]) if "market" in df.columns else 0
    otc_count = len(df[df["market"] == "otc"]) if "market" in df.columns else 0
    tib_count = len(df[df["market"] == "tib"]) if "market" in df.columns else 0
    emerging_count = len(df[df["market"] == "emerging"]) if "market" in df.columns else 0
    industries = df["industry"].nunique() if "industry" in df.columns else 0

    # 永遠顯示申報日期 (有 first_seen 就用)
    show_date = "first_seen" in df.columns
    if not show_date and "date" in df.columns:
        unique_dates = df["date"].dropna().astype(str).str.strip().unique()
        unique_dates = [d for d in unique_dates if d and d != "N/A"]
        show_date = len(unique_dates) > 1
    df._show_date = show_date

    # 各面板的產業區塊
    all_sections = _build_industry_sections(df, year, month)

    def _market_sections(market_key):
        sub = df[df["market"] == market_key].copy()
        if sub.empty:
            return '<p class="empty-msg">本分類無資料</p>'
        sub._show_date = show_date
        return _build_industry_sections(sub, year, month)

    sii_sections = _market_sections("sii") if sii_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    otc_sections = _market_sections("otc") if otc_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    tib_sections = _market_sections("tib") if tib_count > 0 else '<p class="empty-msg">本分類無資料</p>'
    emerging_sections = _market_sections("emerging") if emerging_count > 0 else '<p class="empty-msg">本分類無資料</p>'

    # 生成申報日期 pills
    date_pills = _build_date_pills(df)

    # 計算上/下月檔名
    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
    prev_month_file = f"{prev_y}_{prev_m:02d}.html"
    next_month_file = f"{next_y}_{next_m:02d}.html"

    # 日期篩選區塊 (只有多日期時才顯示)
    if date_pills:
        date_filter_html = f"""<div class="date-filter">
            <span class="date-label">📅 申報日</span>
            <div class="date-pill active" data-date="all">全部</div>
            {date_pills}
        </div>"""
    else:
        date_filter_html = ""

    # 推播提醒區塊
    alert_html = ""
    if early_alerts:
        alert_cards = ""
        for a in early_alerts:
            alert_cards += f"""<div class="alert-card">
                <span class="alert-sid">{a['stock_id']}</span>
                <span class="alert-name">{a['stock_name']}</span>
                <span class="alert-avg">T+1 avg {a['avg_t1']:+.1f}%</span>
                <span class="alert-msg">{a['alert_msg']}</span>
            </div>\n"""
        alert_html = f"""<div class="alert-section">
            <div class="alert-title">🔔 T-1 推播提醒：過去創新高後 T+1 容易大漲</div>
            {alert_cards}
        </div>"""

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
        date_filter_html=date_filter_html,
        alert_html=alert_html,
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
        date_filter_html="",
        alert_html="",
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
