"""
tw_revenue_tracker 健康檢查 & 自動修復小幫手
用法:
    python doctor.py          # 檢查所有項目
    python doctor.py --fix    # 檢查並自動修復
    python doctor.py --push   # 檢查 + 修復 + commit & push
"""

import os
import sys
import json
import subprocess
import importlib
import re
from datetime import datetime

# Windows console UTF-8
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ── 工具 ──────────────────────────────────────────────

class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    INFO = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"

def ok(msg):   print(f"  {Colors.OK}✔{Colors.END} {msg}")
def warn(msg): print(f"  {Colors.WARN}⚠{Colors.END} {msg}")
def fail(msg): print(f"  {Colors.FAIL}✘{Colors.END} {msg}")
def info(msg): print(f"  {Colors.INFO}ℹ{Colors.END} {msg}")
def header(msg): print(f"\n{Colors.BOLD}【{msg}】{Colors.END}")

def run(cmd, capture=True, check=False):
    """執行 shell 指令"""
    r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, cwd=BASE_DIR)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{r.stderr}")
    return r

issues = []   # (level, category, message, fix_func_or_None)
fixed = []

def add_issue(level, cat, msg, fix=None):
    issues.append((level, cat, msg, fix))

# ── 1. Git 狀態 ──────────────────────────────────────

def check_git():
    header("Git 狀態")

    # 是否在 git repo 內
    r = run("git rev-parse --is-inside-work-tree")
    if r.returncode != 0:
        fail("不在 git repository 中")
        return
    ok("Git repository")

    # 當前分支
    branch = run("git branch --show-current").stdout.strip()
    info(f"分支: {branch}")

    # 未 push 的 commit
    r = run(f"git log origin/{branch}..HEAD --oneline")
    unpushed = [l for l in r.stdout.strip().split("\n") if l]
    if unpushed:
        warn(f"有 {len(unpushed)} 個 commit 未 push")
        for line in unpushed:
            info(f"  {line}")
        add_issue("warn", "git", f"{len(unpushed)} 個 commit 未 push",
                  lambda: run(f"git push origin {branch}", capture=False))
    else:
        ok("所有 commit 已 push")

    # 未 commit 的改動
    r = run("git status --porcelain")
    changes = [l for l in r.stdout.strip().split("\n") if l.strip()]
    modified = [l for l in changes if l.startswith(" M") or l.startswith("M ")]
    untracked = [l for l in changes if l.startswith("??")]

    if modified:
        warn(f"有 {len(modified)} 個檔案已修改未 commit")
        for line in modified:
            info(f"  {line.strip()}")
        # 判斷是否包含關鍵 py 檔
        critical_py = [l for l in modified if l.strip().endswith(".py")]
        if critical_py:
            fail("包含 .py 原始碼修改！CI 可能跑的是舊版本")
            add_issue("fail", "git", "關鍵 .py 檔案未 commit/push",
                      lambda: _auto_commit_and_push(branch))
    else:
        ok("工作目錄乾淨 (無未 commit 修改)")

    if untracked:
        info(f"{len(untracked)} 個未追蹤檔案 (通常不影響 CI)")


def _auto_commit_and_push(branch):
    """自動 commit 所有 .py + html + yml 改動並 push"""
    # 加入關鍵檔案
    run("git add *.py .github/workflows/*.yml", capture=False)
    run("git add -f data/monitor_state.json data/t1_cache.json", capture=False)
    run("git add -f output/", capture=False)

    r = run("git diff --staged --quiet")
    if r.returncode == 0:
        info("沒有需要 commit 的改動")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(f'git commit -m "fix: sync local changes to remote ({now})"', capture=False)
    run("git pull --rebase || true", capture=False)
    run(f"git push origin {branch}", capture=False)
    fixed.append("已 commit 並 push 所有改動")


# ── 2. Python import 檢查 ────────────────────────────

def check_imports():
    header("Python Import 檢查")

    # 檢查 monitor.py 用到的所有 import 是否都能解析
    critical_imports = [
        ("config", ["DATA_DIR", "OUTPUT_DIR", "HEADERS", "HISTORY_YEARS", "get_current_period"]),
        ("analyzer", ["format_revenue", "find_revenue_new_highs"]),
        ("html_generator", ["save_html", "generate_html"]),
        ("html_realtime", ["generate_realtime_page"]),
        ("t1_analysis", ["generate_prefiling_alerts", "generate_early_alerts",
                         "analyze_all_period_highs"]),
    ]

    for module_name, funcs in critical_imports:
        try:
            mod = importlib.import_module(module_name)
            missing = [f for f in funcs if not hasattr(mod, f)]
            if missing:
                fail(f"{module_name}: 缺少 {', '.join(missing)}")
                add_issue("fail", "import", f"{module_name} 缺少函式: {', '.join(missing)}")
            else:
                ok(f"{module_name}: {', '.join(funcs)}")
        except Exception as e:
            fail(f"{module_name}: import 失敗 — {e}")
            add_issue("fail", "import", f"{module_name} 無法 import: {e}")

    # 檢查 requirements.txt 的套件
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(req_file):
        with open(req_file) as f:
            reqs = [l.strip().split(">=")[0].split("==")[0]
                    for l in f if l.strip() and not l.startswith("#")]
        for pkg in reqs:
            try:
                importlib.import_module(pkg.replace("-", "_"))
                ok(f"pip: {pkg}")
            except ImportError:
                fail(f"pip: {pkg} 未安裝")
                add_issue("fail", "pip", f"{pkg} 未安裝",
                          lambda p=pkg: run(f"pip install {p}", capture=False))
    else:
        fail("requirements.txt 不存在")
        add_issue("fail", "pip", "requirements.txt 不存在")


# ── 3. 資料檔案完整性 ────────────────────────────────

def check_data():
    header("資料檔案")

    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.isdir(data_dir):
        fail("data/ 目錄不存在")
        add_issue("fail", "data", "data/ 目錄不存在",
                  lambda: os.makedirs(data_dir, exist_ok=True))
        return
    ok("data/ 目錄存在")

    # 主要營收歷史檔
    csv_file = os.path.join(data_dir, "all_revenue_mops.csv")
    if os.path.exists(csv_file):
        size_mb = os.path.getsize(csv_file) / (1024 * 1024)
        ok(f"all_revenue_mops.csv ({size_mb:.1f} MB)")
        if size_mb < 1:
            warn("檔案太小，可能資料不完整")
    else:
        fail("all_revenue_mops.csv 不存在 (歷史營收資料)")
        add_issue("fail", "data", "缺少歷史營收資料 all_revenue_mops.csv")

    # monitor_state.json
    state_file = os.path.join(data_dir, "monitor_state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        n = state.get("total_filed", 0)
        period = f"{state.get('period_year')}/{state.get('period_month', 0):02d}"
        last = state.get("last_check", "未知")
        ok(f"monitor_state.json — 期間 {period}, 已申報 {n} 家, 最後偵測 {last}")
    else:
        warn("monitor_state.json 不存在 (首次執行會自動建立)")

    # t1_cache.json
    cache_file = os.path.join(data_dir, "t1_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        ok(f"t1_cache.json ({len(cache)} 筆)")
    else:
        warn("t1_cache.json 不存在 (可用 build_prefiling_cache.py 建立)")

    # output 目錄
    out_dir = os.path.join(BASE_DIR, "output")
    if os.path.isdir(out_dir):
        htmls = [f for f in os.listdir(out_dir) if f.endswith(".html")]
        ok(f"output/ 目錄 ({len(htmls)} 個 HTML)")
    else:
        warn("output/ 目錄不存在")
        add_issue("warn", "data", "output/ 目錄不存在",
                  lambda: os.makedirs(out_dir, exist_ok=True))


# ── 4. CI 狀態 ────────────────────────────────────────

def check_ci():
    header("GitHub Actions CI")

    r = run("gh run list --limit 5 --json status,conclusion,name,createdAt,databaseId")
    if r.returncode != 0:
        warn("無法取得 CI 狀態 (gh CLI 未登入或未安裝)")
        return

    try:
        runs = json.loads(r.stdout)
    except json.JSONDecodeError:
        warn("無法解析 CI 回應")
        return

    if not runs:
        info("沒有 CI 執行紀錄")
        return

    latest = runs[0]
    status = latest.get("conclusion") or latest.get("status")
    created = latest.get("createdAt", "")[:16].replace("T", " ")

    if status == "success":
        ok(f"最近 CI: ✔ 成功 ({created})")
    elif status == "failure":
        fail(f"最近 CI: ✘ 失敗 ({created})")
        # 取得失敗原因
        run_id = latest.get("databaseId")
        if run_id:
            log = run(f"gh run view {run_id} --log 2>/dev/null")
            # 找 error 行
            errors = [l for l in log.stdout.split("\n")
                      if "Error" in l or "error" in l or "Traceback" in l
                      or "ImportError" in l or "ModuleNotFoundError" in l]
            if errors:
                info("錯誤摘要:")
                for e in errors[-5:]:
                    # 清理 ANSI 和時間戳
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', e)
                    clean = re.sub(r'^\S+\s+\S+\s+\S+\s+', '', clean).strip()
                    if clean:
                        info(f"  {clean}")

        # 統計連續失敗次數
        fail_count = sum(1 for r in runs if r.get("conclusion") == "failure")
        if fail_count >= 3:
            fail(f"連續 {fail_count} 次失敗！需要修復")
            add_issue("fail", "ci", f"CI 連續 {fail_count} 次失敗")
    else:
        info(f"最近 CI: {status} ({created})")


# ── 5. Workflow YAML 檢查 ─────────────────────────────

def check_workflow():
    header("Workflow 設定")

    yml = os.path.join(BASE_DIR, ".github", "workflows", "monitor.yml")
    if not os.path.exists(yml):
        fail("monitor.yml 不存在")
        add_issue("fail", "workflow", "monitor.yml 不存在")
        return
    ok("monitor.yml 存在")

    with open(yml, "r", encoding="utf-8") as f:
        content = f.read()

    # 檢查 git add -f (避免 .gitignore 問題)
    if "git add -f" in content:
        ok("使用 git add -f (繞過 .gitignore)")
    elif "git add" in content:
        warn("git add 未使用 -f，data/ 在 .gitignore 中可能被忽略")
        add_issue("warn", "workflow", "git add 應加 -f 繞過 .gitignore")

    # 檢查 pull --rebase
    if "git pull" in content:
        ok("commit 前有 git pull (避免推送衝突)")
    else:
        warn("建議加入 git pull --rebase 避免推送衝突")

    # 檢查 cron 排程
    cron_match = re.search(r"cron:\s*'(.+?)'", content)
    if cron_match:
        cron = cron_match.group(1)
        info(f"排程: {cron}")
    else:
        warn("未設定 cron 排程")


# ── 6. 本地 vs Remote 同步 ────────────────────────────

def check_sync():
    header("本地 vs Remote 同步")

    # 取得有差異的檔案
    r = run("git diff --name-only origin/main")
    if r.returncode != 0:
        warn("無法比對 (可能沒有 remote)")
        return

    diff_files = [f for f in r.stdout.strip().split("\n") if f.strip()]
    if not diff_files:
        ok("本地與 remote 完全同步")
        return

    py_files = [f for f in diff_files if f.endswith(".py")]
    yml_files = [f for f in diff_files if f.endswith(".yml")]
    other = [f for f in diff_files if f not in py_files and f not in yml_files]

    if py_files:
        fail(f"{len(py_files)} 個 .py 檔案與 remote 不同步 (CI 用舊版)")
        for f in py_files:
            info(f"  {f}")
        add_issue("fail", "sync", "Python 原始碼未同步到 remote",
                  lambda: _auto_commit_and_push("main"))
    if yml_files:
        warn(f"{len(yml_files)} 個 workflow 檔案不同步")
        for f in yml_files:
            info(f"  {f}")
    if other:
        info(f"{len(other)} 個其他檔案不同步 (通常不影響 CI)")


# ── 7. 快速執行測試 ──────────────────────────────────

def check_monitor_dry():
    header("monitor.py 快速驗證")

    # 只測試 import 和基本初始化，不實際跑爬蟲
    test_script = os.path.join(BASE_DIR, "_doctor_test.py")
    with open(test_script, "w", encoding="utf-8") as f:
        f.write(f"""
import sys, os
os.chdir(r'{BASE_DIR}')
sys.path.insert(0, r'{BASE_DIR}')
try:
    from monitor import load_state, generate_realtime_html, generate_period_high_report
    from config import get_current_period
    y, m = get_current_period()
    print(f"OK|{{y}}/{{m:02d}}")
except Exception as e:
    print(f"FAIL|{{type(e).__name__}}: {{e}}")
""")
    r = run(f'python "{test_script}"')
    output = (r.stdout.strip() + r.stderr.strip()).strip()
    try:
        os.remove(test_script)
    except OSError:
        pass
    if output.startswith("OK|"):
        period = output.split("|")[1]
        ok(f"monitor.py 可正常載入 (期間 {period})")
    else:
        err = output.split("|")[1] if "|" in output else output
        fail(f"monitor.py 載入失敗: {err}")
        add_issue("fail", "runtime", f"monitor.py 執行錯誤: {err}")


# ── 主程式 ────────────────────────────────────────────

def main():
    print(f"\n{Colors.BOLD}{'='*50}")
    print(f"  營收追蹤系統 健康檢查 🩺")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}{Colors.END}")

    do_fix = "--fix" in sys.argv or "--push" in sys.argv
    do_push = "--push" in sys.argv

    # 執行所有檢查
    check_git()
    check_sync()
    check_imports()
    check_data()
    check_ci()
    check_workflow()
    check_monitor_dry()

    # 彙總
    header("診斷結果")
    fails = [(c, m) for lv, c, m, _ in issues if lv == "fail"]
    warns = [(c, m) for lv, c, m, _ in issues if lv == "warn"]

    if not fails and not warns:
        print(f"\n  {Colors.OK}🎉 全部正常！{Colors.END}\n")
        return 0

    if fails:
        print(f"\n  {Colors.FAIL}❌ {len(fails)} 個嚴重問題:{Colors.END}")
        for cat, msg in fails:
            print(f"     [{cat}] {msg}")
    if warns:
        print(f"\n  {Colors.WARN}⚠ {len(warns)} 個警告:{Colors.END}")
        for cat, msg in warns:
            print(f"     [{cat}] {msg}")

    # 自動修復
    if do_fix or do_push:
        header("自動修復")
        fixable = [(lv, c, m, fn) for lv, c, m, fn in issues if fn is not None]
        if not fixable:
            info("沒有可自動修復的項目")
        else:
            for lv, cat, msg, fn in fixable:
                info(f"修復: [{cat}] {msg}")
                try:
                    fn()
                    ok(f"已修復: {msg}")
                    fixed.append(msg)
                except Exception as e:
                    fail(f"修復失敗: {e}")

        if fixed:
            print(f"\n  {Colors.OK}✔ 已修復 {len(fixed)} 個問題{Colors.END}")
            for f in fixed:
                print(f"    - {f}")
    else:
        if any(fn for _, _, _, fn in issues if fn):
            print(f"\n  {Colors.INFO}💡 執行 python doctor.py --fix 自動修復")
            print(f"  💡 執行 python doctor.py --push 修復並推送到 GitHub{Colors.END}")

    print()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
