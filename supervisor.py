"""
營收追蹤器監督系統 (supervisor.py)
============================================

定期檢查系統健康狀態，發現異常立即推播 TG 告警

檢查項目:
1. CSV 資料新鮮度 - 當期/上期資料是否在合理時間內更新
2. CSV 完整度 - 申報期結束後資料是否齊全 (>1500 筆)
3. HTML 檔案存在 + 最近修改時間
4. monitor_state period 是否符合當前日曆月
5. CI 最近執行狀態 (是否連續失敗)
6. 申報期內 (1~12 日) 申報數是否合理增長
7. 各市場分布是否齊全 (sii/otc/tib/emerging/pub)

使用方式:
  python supervisor.py                      # 一次性檢查並印出報告
  python supervisor.py --tg                 # 異常時發 TG 通知 (需設環境變數)
  python supervisor.py --json               # 輸出 JSON 供 CI 解析
  python supervisor.py --strict             # 任何 warning 也視為失敗 (exit 1)

環境變數 (TG 通知):
  TELEGRAM_BOT_TOKEN  -- TG bot token
  TELEGRAM_CHAT_ID    -- 收件 chat id
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

# Windows cp950 fix
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
TW_TZ = timezone(timedelta(hours=8))


class Issue:
    """單一檢查項目的結果"""

    def __init__(self, level: str, key: str, msg: str, details: dict = None):
        self.level = level  # "ok", "warn", "error"
        self.key = key
        self.msg = msg
        self.details = details or {}

    def __repr__(self):
        icon = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(self.level, "?")
        return f"{icon} [{self.key}] {self.msg}"


def check_csv_freshness() -> list[Issue]:
    """CSV 資料新鮮度檢查"""
    issues = []
    csv_path = DATA_DIR / "all_revenue_mops.csv"
    if not csv_path.exists():
        return [Issue("error", "csv_missing", "all_revenue_mops.csv 不存在")]

    now = datetime.now(TW_TZ)
    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime, TW_TZ)
    hours_since = (now - mtime).total_seconds() / 3600

    if hours_since > 26:
        issues.append(Issue(
            "error", "csv_stale",
            f"CSV 檔案已 {hours_since:.1f} 小時未更新 (期望 < 26h)",
            {"hours": hours_since, "mtime": mtime.isoformat()},
        ))
    elif hours_since > 13:
        issues.append(Issue(
            "warn", "csv_warming",
            f"CSV 檔案 {hours_since:.1f} 小時未更新",
            {"hours": hours_since},
        ))
    else:
        issues.append(Issue("ok", "csv_fresh", f"CSV 新鮮 ({hours_since:.1f}h)"))

    return issues


def check_period_alignment() -> list[Issue]:
    """monitor_state 的 period 是否符合當前日曆月"""
    issues = []
    state_path = DATA_DIR / "monitor_state.json"
    if not state_path.exists():
        return [Issue("error", "state_missing", "monitor_state.json 不存在")]

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    now = datetime.now(TW_TZ)
    # 報告月份 = 當前月 - 1
    expected_y = now.year if now.month > 1 else now.year - 1
    expected_m = now.month - 1 if now.month > 1 else 12

    state_y = state.get("period_year")
    state_m = state.get("period_month")

    if state_y != expected_y or state_m != expected_m:
        issues.append(Issue(
            "error", "period_mismatch",
            f"period 不對齊：state={state_y}/{state_m:02d}, "
            f"應為 {expected_y}/{expected_m:02d}",
            {"state": f"{state_y}/{state_m}", "expected": f"{expected_y}/{expected_m}"},
        ))
    else:
        issues.append(Issue("ok", "period_aligned", f"period 正常 ({state_y}/{state_m:02d})"))

    # 申報數合理性
    total = state.get("total_filed", 0)
    last_check = state.get("last_check", "")
    if total < 100 and now.day > 10:
        issues.append(Issue(
            "warn", "low_filings",
            f"當期申報數 {total} 偏低 (今天 {now.day} 日)",
            {"total_filed": total},
        ))
    else:
        issues.append(Issue("ok", "filings_count", f"申報數 {total} (last_check={last_check})"))

    return issues


def check_data_completeness() -> list[Issue]:
    """檢查近月資料完整度"""
    issues = []
    csv_path = DATA_DIR / "all_revenue_mops.csv"
    if not csv_path.exists():
        return []

    df = pd.read_csv(csv_path, dtype={"stock_id": str})
    now = datetime.now(TW_TZ)

    # 上 3 個月的資料完整度
    months_to_check = []
    y, m = now.year, now.month
    for _ in range(3):
        if m == 1:
            m, y = 12, y - 1
        else:
            m -= 1
        months_to_check.append((y, m))

    for y, m in months_to_check:
        grp = df[(df["revenue_year"] == y) & (df["revenue_month"] == m)]
        cnt = len(grp)
        markets = grp["market"].value_counts().to_dict()
        missing_markets = [k for k in ["sii", "otc", "emerging", "pub"] if markets.get(k, 0) == 0]

        # 該月該完成 (今天 > 該月的次月 15 日)
        deadline_passed = (now.year, now.month) > (y, m) and (
            now.year > y or (now.year == y and now.month > m + 1) or (now.day > 15)
        )

        if cnt < 1500 and deadline_passed:
            issues.append(Issue(
                "error", f"incomplete_{y}_{m:02d}",
                f"{y}/{m:02d} 只有 {cnt} 筆 (期望 >1500), 申報期已過",
                {"count": cnt, "markets": markets},
            ))
        elif cnt < 1500:
            issues.append(Issue(
                "warn", f"early_{y}_{m:02d}",
                f"{y}/{m:02d} 目前 {cnt} 筆 (申報期未截止)",
                {"count": cnt},
            ))
        elif missing_markets:
            issues.append(Issue(
                "warn", f"missing_market_{y}_{m:02d}",
                f"{y}/{m:02d} 缺少市場: {missing_markets}",
                {"markets": markets},
            ))
        else:
            issues.append(Issue("ok", f"complete_{y}_{m:02d}", f"{y}/{m:02d} 完整 ({cnt} 筆)"))

    return issues


def check_html_freshness() -> list[Issue]:
    """HTML 檔案新鮮度"""
    issues = []
    now = datetime.now(TW_TZ)

    # 報告月份
    expected_y = now.year if now.month > 1 else now.year - 1
    expected_m = now.month - 1 if now.month > 1 else 12
    expected_file = OUTPUT_DIR / f"{expected_y}_{expected_m:02d}.html"

    if not expected_file.exists():
        issues.append(Issue(
            "error", "html_missing",
            f"{expected_file.name} 不存在",
        ))
        return issues

    mtime = datetime.fromtimestamp(expected_file.stat().st_mtime, TW_TZ)
    hours_since = (now - mtime).total_seconds() / 3600

    if hours_since > 26:
        issues.append(Issue(
            "warn", "html_stale",
            f"{expected_file.name} 已 {hours_since:.1f}h 未更新",
            {"hours": hours_since},
        ))
    else:
        issues.append(Issue("ok", "html_fresh", f"{expected_file.name} ({hours_since:.1f}h)"))

    # index.html
    index_file = OUTPUT_DIR / "index.html"
    if index_file.exists():
        mtime = datetime.fromtimestamp(index_file.stat().st_mtime, TW_TZ)
        hours_since = (now - mtime).total_seconds() / 3600
        if hours_since > 26:
            issues.append(Issue(
                "warn", "index_stale",
                f"index.html 已 {hours_since:.1f}h 未更新",
                {"hours": hours_since},
            ))

    return issues


def check_ci_history() -> list[Issue]:
    """檢查 GitHub Actions 最近執行狀態"""
    import subprocess
    issues = []
    try:
        # 用 gh 取最近 5 次執行
        result = subprocess.run(
            ["gh", "run", "list", "--workflow=monitor.yml", "--limit=5", "--json", "status,conclusion,createdAt"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return [Issue("warn", "ci_check_failed", "無法執行 gh CLI")]

        runs = json.loads(result.stdout) if result.stdout else []
        if not runs:
            return [Issue("warn", "no_ci_runs", "近期無 CI 執行紀錄")]

        # 最近 1 次
        latest = runs[0]
        latest_status = latest.get("conclusion") or latest.get("status")
        latest_time = latest.get("createdAt", "")
        try:
            run_time = datetime.fromisoformat(latest_time.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_since = (now - run_time).total_seconds() / 3600
        except Exception:
            hours_since = -1

        if latest_status == "failure":
            issues.append(Issue(
                "error", "ci_failed",
                f"最近 CI 執行失敗 ({hours_since:.1f}h 前)",
            ))
        elif hours_since > 26:
            issues.append(Issue(
                "warn", "ci_no_recent_run",
                f"CI 已 {hours_since:.1f}h 未執行",
            ))
        else:
            issues.append(Issue("ok", "ci_running", f"CI 正常 (最近 {hours_since:.1f}h 前 {latest_status})"))

        # 連續失敗檢查
        last_3 = [r.get("conclusion") for r in runs[:3]]
        if last_3.count("failure") >= 2:
            issues.append(Issue(
                "error", "ci_consecutive_failures",
                f"近 3 次 CI 有 {last_3.count('failure')} 次失敗",
                {"recent": last_3},
            ))
    except Exception as e:
        issues.append(Issue("warn", "ci_check_error", f"CI 檢查錯誤: {e}"))

    return issues


def run_all_checks() -> list[Issue]:
    """執行所有檢查"""
    all_issues = []
    all_issues.extend(check_csv_freshness())
    all_issues.extend(check_period_alignment())
    all_issues.extend(check_data_completeness())
    all_issues.extend(check_html_freshness())
    all_issues.extend(check_ci_history())
    return all_issues


def format_report(issues: list[Issue]) -> str:
    """格式化檢查報告"""
    lines = [
        f"=== 營收追蹤器健康檢查 ({datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M')}) ===",
        "",
    ]
    errors = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    oks = [i for i in issues if i.level == "ok"]

    if errors:
        lines.append("❌ 嚴重問題:")
        for i in errors:
            lines.append(f"  • {i.msg}")
        lines.append("")

    if warns:
        lines.append("⚠️ 警告:")
        for i in warns:
            lines.append(f"  • {i.msg}")
        lines.append("")

    if oks and not errors and not warns:
        lines.append("✅ 全部正常:")
        for i in oks:
            lines.append(f"  • {i.msg}")
    elif oks:
        lines.append(f"✅ 正常: {len(oks)} 項")

    lines.append("")
    lines.append(f"總結: {len(errors)} 嚴重 / {len(warns)} 警告 / {len(oks)} 正常")
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """發送 TG 通知"""
    import requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("TG 環境變數未設定，跳過通知")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"TG 發送失敗: {e}")
        return False


def main():
    use_tg = "--tg" in sys.argv
    use_json = "--json" in sys.argv
    strict = "--strict" in sys.argv

    issues = run_all_checks()
    errors = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]

    if use_json:
        out = {
            "ts": datetime.now(TW_TZ).isoformat(),
            "errors": [{"key": i.key, "msg": i.msg, "details": i.details} for i in errors],
            "warns": [{"key": i.key, "msg": i.msg, "details": i.details} for i in warns],
            "ok_count": sum(1 for i in issues if i.level == "ok"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        report = format_report(issues)
        print(report)

    # TG 通知 (只在有問題時)
    if use_tg and (errors or (strict and warns)):
        report = format_report(issues)
        tg_msg = f"<b>🚨 營收追蹤器告警</b>\n\n<pre>{report}</pre>"
        send_telegram(tg_msg)
        logger.info("已發送 TG 告警")

    # Exit code
    if errors:
        sys.exit(2)
    if strict and warns:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
