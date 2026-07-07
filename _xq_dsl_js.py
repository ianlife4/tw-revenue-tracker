"""
營收頁「匯出 XQ .dsl」的單一來源 (button + JS + CSS)。

- html_generator.py 透過 {xq_export_button} / {xq_export_js} placeholder 注入 (產生新月報)
- patch_xq_export.py 匯入後字串級升級既有 output/*.html (CSV → .dsl)

.dsl = XQ 原生 CFB / OLE2 格式。匯入 XQ 時會「取代」同名商品組合,
不像 CSV 是 append → 不會累積重複資料。組合名固定「營收」。

CFB writer (_DSL_BUILDER_JS) 直接移植自 worker/worker.js 的法說會版
(已用 Python olefile round-trip 驗證: tiny / medium / large 皆通),
唯一差異是組合名 Big5: 法說 AA 6B BB A1 → 營收 C0 E7 A6 AC。
_DSL_BUILDER_JS 為「可獨立執行」的純函式區塊,方便用 Node 單測。
"""

# 「營收」Big5 = C0 E7 A6 AC ('營收'.encode('big5'))
# CFB / OLE2 writer — 純函式,無外部相依 (DOM 無關),可在 Node 直接測
_DSL_BUILDER_JS = r"""
// ---- XQ .dsl (CFB / OLE2) builder ----
var SEC = 512, MINI = 64, MINI_CUTOFF = 4096;
var FREE = 0xFFFFFFFF, EOC = 0xFFFFFFFE, FATSECT = 0xFFFFFFFD;
// 「營收」Big5 = C0 E7 A6 AC (TextEncoder 不支援 Big5,直接寫死)
var GROUP_BIG5 = new Uint8Array([0xC0, 0xE7, 0xA6, 0xAC]);

function asciiBytes(s){
  var o = new Uint8Array(s.length);
  for (var i = 0; i < s.length; i++) o[i] = s.charCodeAt(i) & 0xFF;
  return o;
}
function concatBytes(arrs){
  var total = 0;
  for (var i = 0; i < arrs.length; i++) total += arrs[i].length;
  var out = new Uint8Array(total), off = 0;
  for (var j = 0; j < arrs.length; j++) { out.set(arrs[j], off); off += arrs[j].length; }
  return out;
}
function newGuid(){
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID().toUpperCase();
  var hex = '0123456789ABCDEF', g = '';
  for (var i = 0; i < 32; i++) g += hex[Math.floor(Math.random()*16)];
  return g.slice(0,8)+'-'+g.slice(8,12)+'-'+g.slice(12,16)+'-'+g.slice(16,20)+'-'+g.slice(20,32);
}
function writeDirEntry(view, bytes, off, name, etype, color, left, right, child, startSec, size){
  // UTF-16-LE name + null terminator, in first 64 bytes
  var nameLen = (name.length + 1) * 2;
  for (var i = 0; i < name.length; i++) {
    var c = name.charCodeAt(i);
    bytes[off + i*2] = c & 0xFF;
    bytes[off + i*2 + 1] = (c >> 8) & 0xFF;
  }
  view.setUint16(off + 64, nameLen, true);
  bytes[off + 66] = etype;
  bytes[off + 67] = color;
  view.setInt32(off + 68, left, true);
  view.setInt32(off + 72, right, true);
  view.setInt32(off + 76, child, true);
  // CLSID (80-95), state (96-99), times (100-115): all zero, already
  view.setUint32(off + 116, startSec >>> 0, true);
  view.setUint32(off + 120, size >>> 0, true);  // lower 32
  view.setUint32(off + 124, 0, true);           // upper 32 (v3 unused)
}
function buildXqDsl(stocks){
  // FileContentSymbolList_0 content: "1," + GUID + ";" + big5(組合名) + ",{code}.TW,..."
  var guid = newGuid();
  var head = asciiBytes('1,' + guid + ';');
  // 字尾: 興櫃 .TE / 其餘 .TW (由呼叫端在 s.suffix 帶入)
  var tailStr = ',' + stocks.map(function(s){ return s.code + (s.suffix || '.TW'); }).join(',');
  var tail = asciiBytes(tailStr);
  var fcsl = concatBytes([head, GROUP_BIG5, tail]);
  var fcslLen = fcsl.length;
  var fcslInMini = fcslLen < MINI_CUTOFF;

  // Mini sectors used: _SSHeader_ (1) + FileHeadFileCount (1) + FCSL (if mini)
  var fcslMiniSecs = fcslInMini ? Math.ceil(fcslLen / MINI) : 0;
  var miniSecs = 2 + fcslMiniSecs;
  var miniStreamBytes = miniSecs * MINI;
  var miniStreamRegular = Math.ceil(miniStreamBytes / SEC);

  var fcslRegularSecs = fcslInMini ? 0 : Math.ceil(fcslLen / SEC);
  var miniStreamFirstSec = 3;
  var fcslFirstSec = fcslInMini ? -1 : miniStreamFirstSec + miniStreamRegular;
  var totalSecs = 3 + miniStreamRegular + fcslRegularSecs;
  var fileSize = (1 + totalSecs) * SEC;

  var buf = new Uint8Array(fileSize);
  var view = new DataView(buf.buffer);

  // --- Header (0..511) ---
  buf.set([0xD0,0xCF,0x11,0xE0,0xA1,0xB1,0x1A,0xE1], 0);
  view.setUint16(24, 0x003E, true);
  view.setUint16(26, 0x0003, true);
  view.setUint16(28, 0xFFFE, true);
  view.setUint16(30, 9, true);
  view.setUint16(32, 6, true);
  view.setUint32(40, 0, true);
  view.setUint32(44, 1, true);                // num_fat_sectors
  view.setUint32(48, 1, true);                // first_dir_sector
  view.setUint32(56, MINI_CUTOFF, true);
  view.setUint32(60, 2, true);                // first_mini_fat_sector
  view.setUint32(64, 1, true);                // num_mini_fat_sectors
  view.setUint32(68, FREE, true);             // no DIFAT
  view.setUint32(76, 0, true);                // DIFAT[0] = FAT at sector 0
  for (var k = 1; k < 109; k++) view.setUint32(76 + k*4, FREE, true);

  // --- FAT (sector 0 -> file 0x200) ---
  var fatOff = SEC;
  for (var i = 0; i < 128; i++) view.setUint32(fatOff + i*4, FREE, true);
  view.setUint32(fatOff + 0*4, FATSECT, true);
  view.setUint32(fatOff + 1*4, EOC, true);
  view.setUint32(fatOff + 2*4, EOC, true);
  for (var i2 = 0; i2 < miniStreamRegular; i2++) {
    var cur = 3 + i2;
    view.setUint32(fatOff + cur*4, i2 === miniStreamRegular - 1 ? EOC : cur + 1, true);
  }
  if (!fcslInMini) {
    for (var i3 = 0; i3 < fcslRegularSecs; i3++) {
      var c2 = fcslFirstSec + i3;
      view.setUint32(fatOff + c2*4, i3 === fcslRegularSecs - 1 ? EOC : c2 + 1, true);
    }
  }

  // --- Directory (sector 1 -> file 0x400) ---
  var dirOff = SEC * 2;
  // BST: Root.child = idx 2 (FileHeadFileCount), L = _SSHeader_(1), R = FCSL(3)
  writeDirEntry(view, buf, dirOff + 0*128, 'Root Entry', 5, 0, -1, -1, 2, miniStreamFirstSec, miniSecs * MINI);
  writeDirEntry(view, buf, dirOff + 1*128, '_SSHeader_', 2, 0, -1, -1, -1, 0, 36);
  writeDirEntry(view, buf, dirOff + 2*128, 'FileHeadFileCount', 2, 1, 1, 3, -1, 1, 4);
  var fcslStart = fcslInMini ? 2 : fcslFirstSec;
  writeDirEntry(view, buf, dirOff + 3*128, 'FileContentSymbolList_0', 2, 0, -1, -1, -1, fcslStart, fcslLen);

  // --- Mini FAT (sector 2 -> file 0x600) ---
  var mfatOff = SEC * 3;
  for (var m = 0; m < 128; m++) view.setUint32(mfatOff + m*4, FREE, true);
  view.setUint32(mfatOff + 0*4, EOC, true);
  view.setUint32(mfatOff + 1*4, EOC, true);
  if (fcslInMini) {
    for (var n = 0; n < fcslMiniSecs; n++) {
      var mc = 2 + n;
      view.setUint32(mfatOff + mc*4, n === fcslMiniSecs - 1 ? EOC : mc + 1, true);
    }
  }

  // --- Mini stream (regular sector 3+) ---
  var miniStreamOff = SEC * (1 + miniStreamFirstSec);
  // _SSHeader_ at mini sec 0: 00 00 00 00 Test + zeros (36B)
  buf[miniStreamOff + 4] = 0x54; buf[miniStreamOff + 5] = 0x65;
  buf[miniStreamOff + 6] = 0x73; buf[miniStreamOff + 7] = 0x74;
  // FileHeadFileCount at mini sec 1: uint32 LE = 1
  buf[miniStreamOff + MINI] = 1;
  // FCSL at mini sec 2+ if mini
  if (fcslInMini) buf.set(fcsl, miniStreamOff + 2 * MINI);

  // --- FCSL regular sectors ---
  if (!fcslInMini) buf.set(fcsl, SEC * (1 + fcslFirstSec));

  return buf;
}
"""

# 完整匯出 IIFE (DOM 讀取 + 觸發下載) — 注入到 </script> 之前
EXPORT_JS = (
    r"""
// XQ 自選股 .dsl 匯出 (XQ 原生 CFB/OLE2,組合名「營收」)
// xq-export-v2: 興櫃(emerging)字尾 .TE / 公發(pub)不匯出 / 其餘 .TW
// 取「當前可見」股票 — 尊重市場 tab + 日期 pill + 搜尋
// .dsl 匯入 XQ 會「取代」同名商品組合,不像 CSV 是 append 累積重複
(function() {
    var btn = document.getElementById('exportXqCsv');
    var countBadge = document.getElementById('exportCount');
    if (!btn) return;

    function getVisibleStocks() {
        var panel = document.querySelector('.market-panel.active');
        if (!panel) return [];
        var activeMarket = (panel.id || '').replace('panel-', '') || 'all';
        var cards = panel.querySelectorAll('.stock-card');
        var seen = {};
        var list = [];
        for (var i = 0; i < cards.length; i++) {
            var c = cards[i];
            // 過濾掉被 inline display:none 隱藏的卡片 (date filter / search)
            if (c.style.display === 'none') continue;
            // 過濾掉被 filter class 隱藏的卡片 (YoY+MoM / 股票期貨 / 可轉債 / 日期屬性)
            if (c.classList.contains('growth-filtered')) continue;
            if (c.classList.contains('futures-filtered')) continue;
            if (c.classList.contains('cb-filtered')) continue;
            if (c.getAttribute('data-date-hidden')) continue;
            if (c.getAttribute('data-search-hidden')) continue;
            // 過濾掉父層產業區塊被隱藏的卡片
            var section = c.closest('.industry-section');
            if (section && section.style.display === 'none') continue;
            var sid = (c.dataset.sid || '').trim();
            var sname = (c.dataset.sname || '').trim();
            if (!sid || seen[sid]) continue;
            // 市場: 優先卡片自身 data-market;舊檔無此屬性時,非「全部」面板退回當前面板
            var market = (c.dataset.market || '').trim();
            if (!market && activeMarket !== 'all') market = activeMarket;
            // 公發 (pub) 不匯出
            if (market === 'pub') continue;
            seen[sid] = 1;
            // 興櫃 (emerging) 用 .TE,其餘 (上市/上櫃/創新板) 用 .TW
            var suffix = (market === 'emerging') ? '.TE' : '.TW';
            list.push({ sid: sid, sname: sname, suffix: suffix });
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
"""
    + _DSL_BUILDER_JS
    + r"""
    btn.addEventListener('click', function() {
        var stocks = getVisibleStocks();
        if (stocks.length === 0) {
            alert('目前沒有可匯出的股票（請確認分頁與篩選條件）');
            return;
        }
        var dslStocks = stocks.map(function(s) { return { code: s.sid, suffix: s.suffix }; });
        var dsl = buildXqDsl(dslStocks);
        var blob = new Blob([dsl], { type: 'application/octet-stream' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'XQ自選股_營收_' + getActiveMarketLabel() + '_' + todayTw() + '.dsl';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function() { URL.revokeObjectURL(url); }, 100);
    });

    // 初次計算
    updateCount();

    // filter 變動時即時更新數量
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
    // chip filter (YoY+MoM / 股期 / CB) 變動時更新
    ['growthFilter', 'futuresFilter', 'cbFilter'].forEach(function(id) {
        var cb = document.getElementById(id);
        if (cb) cb.addEventListener('change', function() {
            setTimeout(updateCount, 60);
        });
    });
})();
"""
)

# 按鈕 — 維持 id="exportXqCsv" / 邊章 id="exportCount" (沿用既有 .export-btn CSS 與 JS 綁定)
EXPORT_BUTTON_HTML = (
    '<button class="export-btn" id="exportXqCsv" type="button" '
    'title="匯出當前篩選結果為 XQ 原生 .dsl 檔（組合名「營收」，匯入 XQ 會取代同名商品組合，不會 append 累積重複）">'
    '&#128229; 匯出 XQ .dsl<span class="count-badge" id="exportCount"></span>'
    '<span style="font-size:0.62rem;opacity:0.55;margin-left:4px;">v3</span></button>'
)

# .export-btn 樣式 — html_generator 模板內已有;patch 既有檔若缺則補
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
