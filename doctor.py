"""
tw_revenue_tracker 健康檢查 & 自動修復小幫手
用法:
    python doctor.py          # 檢查所有項目
    python doctor.py --fix    # 檢查並自動修復
    python doctor.py --push   # 檢查 + 修復 + commit & push
    python doctor.py --ci     # CI 模式: 預檢 import + data，失敗就報錯
    python doctor.py --ci-diagnose  # CI 失敗後診斷: 分析錯誤原因
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

IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

# ── 工具 ──────────────────────────────────────────────

class Colors:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    INFO = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"

def ok(msg):   print(f"  {Colors.OK}[OK]{Colors.END} {msg}")
def warn(msg): print(f"  {Colors.WARN}[WARN]{Colors.END} {msg}")
def fail(msg): print(f"  {Colors.FAIL}[FAIL]{Colors.END} {msg}")
def info(msg): print(f"  {Colors.INFO}[INFO]{Colors.END} {msg}")
def header(msg): print(f"\n{Colors.BOLD}=== {msg} ==={Colors.END}")

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
    header("Git")

    # 是否在 git repo 內
    r = run("git rev-parse --is-inside-work-tree")
    if r.returncode != 0:
        fail("not in git repository")
        return
    ok("Git repository")

    # 當前分支
    branch = run("git branch --show-current").stdout.strip()
    info(f"branch: {branch}")

    # 未 push 的 commit
    r = run(f"git log origin/{branch}..HEAD --oneline")
    unpushed = [l for l in r.stdout.strip().split("\n") if l]
    if unpushed:
        warn(f"{len(unpushed)} commits not pushed")
        for line in unpushed:
            info(f"  {line}")
        add_issue("warn", "git", f"{len(unpushed)} commits not pushed",
                  lambda: run(f"git push origin {branch}", capture=False))
    else:
        ok("all commits pushed")

    # 未 commit 的改動
    r = run("git status --porcelain")
    changes = [l for l in r.stdout.strip().split("\n") if l.strip()]
    modified = [l for l in changes if l.startswith(" M") or l.startswith("M ")]
    untracked = [l for l in changes if l.startswith("??")]

    if modified:
        warn(f"{len(modified)} files modified (not committed)")
        for line in modified:
            info(f"  {line.strip()}")
        critical_py = [l for l in modified if l.strip().endswith(".py")]
        if critical_py:
            fail(".py source modified! CI runs old version")
            add_issue("fail", "git", ".py files not committed/pushed",
                      lambda: _auto_commit_and_push(branch))
    else:
        ok("working directory clean")

    if untracked:
        info(f"{len(untracked)} untracked files")


def _auto_commit_and_push(branch):
    """自動 commit 所有 .py + html + yml 改動並 push"""
    run("git add *.py .github/workflows/*.yml", capture=False)
    run("git add -f data/monitor_state.json data/t1_cache.json", capture=False)
    run("git add -f output/", capture=False)

    r = run("git diff --staged --quiet")
    if r.returncode == 0:
        info("nothing to commit")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(f'git commit -m "fix: sync local changes to remote ({now})"', capture=False)
    run("git pull --rebase || true", capture=False)
    run(f"git push origin {branch}", capture=False)
    fixed.append("committed and pushed all changes")


# ── 2. Python import 檢查 ────────────────────────────

def check_imports():
    header("Python Imports")

    critical_imports = [
        ("config", ["DATA_DIR", "OUTPUT_DIR", "HEADERS", "HISTORY_YEARS", "get_current_period"]),
        ("analyzer", ["format_revenue", "find_revenue_new_highs"]),
        ("html_generator", ["save_html", "generate_html"]),
        ("html_realtime", ["generate_realtime_page"]),
        ("t1_analysis", ["generate_prefiling_alerts", "generate_early_alerts",
                         "analyze_all_period_highs"]),
    ]

    all_ok = True
    for module_name, funcs in critical_imports:
        try:
            mod = importlib.import_module(module_name)
            missing = [f for f in funcs if not hasattr(mod, f)]
            if missing:
                fail(f"{module_name}: missing {', '.join(missing)}")
                add_issue("fail", "import", f"{module_name} missing: {', '.join(missing)}")
                all_ok = False
            else:
                ok(f"{module_name}: {', '.join(funcs)}")
        except Exception as e:
            fail(f"{module_name}: import error - {e}")
            add_issue("fail", "import", f"{module_name} import failed: {e}")
            all_ok = False

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
                fail(f"pip: {pkg} not installed")
                add_issue("fail", "pip", f"{pkg} not installed",
                          lambda p=pkg: run(f"pip install {p}", capture=False))
                all_ok = False
    else:
        fail("requirements.txt missing")
        add_issue("fail", "pip", "requirements.txt missing")
        all_ok = False

    return all_ok


# ── 3. 資料檔案完整性 ────────────────────────────────

def check_data():
    header("Data Files")

    data_dir = os.path.join(BASE_DIR, "data")
    all_ok = True

    if not os.path.isdir(data_dir):
        fail("data/ directory missing")
        add_issue("fail", "data", "data/ missing",
                  lambda: os.makedirs(data_dir, exist_ok=True))
        return False
    ok("data/ exists")

    # 主要營收歷史檔
    csv_file = os.path.join(data_dir, "all_revenue_mops.csv")
    if os.path.exists(csv_file):
        size_mb = os.path.getsize(csv_file) / (1024 * 1024)
        ok(f"all_revenue_mops.csv ({size_mb:.1f} MB)")
        if size_mb < 1:
            warn("file too small, data may be incomplete")
    else:
        warn("all_revenue_mops.csv missing (historical data)")

    # monitor_state.json
    state_file = os.path.join(data_dir, "monitor_state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        n = state.get("total_filed", 0)
        period = f"{state.get('period_year')}/{state.get('period_month', 0):02d}"
        last = state.get("last_check", "N/A")
        ok(f"monitor_state.json - period {period}, filed {n}, last check {last}")
    else:
        info("monitor_state.json not found (will be created on first run)")

    # t1_cache.json
    cache_file = os.path.join(data_dir, "t1_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        ok(f"t1_cache.json ({len(cache)} entries)")
    else:
        info("t1_cache.json not found (run build_prefiling_cache.py to create)")

    # output 目錄
    out_dir = os.path.join(BASE_DIR, "output")
    if os.path.isdir(out_dir):
        htmls = [f for f in os.listdir(out_dir) if f.endswith(".html")]
        ok(f"output/ ({len(htmls)} HTML files)")
    else:
        warn("output/ missing")
        add_issue("warn", "data", "output/ missing",
                  lambda: os.makedirs(out_dir, exist_ok=True))

    return all_ok


# ── 4. CI 狀態 ────────────────────────────────────────

def check_ci():
    header("GitHub Actions CI")

    r = run("gh run list --limit 5 --json status,conclusion,name,createdAt,databaseId")
    if r.returncode != 0:
        warn("cannot get CI status (gh CLI not available)")
        return

    try:
        runs = json.loads(r.stdout)
    except json.JSONDecodeError:
        warn("cannot parse CI response")
        return

    if not runs:
        info("no CI runs found")
        return

    latest = runs[0]
    status = latest.get("conclusion") or latest.get("status")
    created = latest.get("createdAt", "")[:16].replace("T", " ")

    if status == "success":
        ok(f"latest CI: success ({created})")
    elif status == "failure":
        fail(f"latest CI: FAILED ({created})")
        run_id = latest.get("databaseId")
        if run_id:
            log = run(f"gh run view {run_id} --log 2>/dev/null")
            errors = [l for l in log.stdout.split("\n")
                      if "Error" in l or "error" in l or "Traceback" in l
                      or "ImportError" in l or "ModuleNotFoundError" in l]
            if errors:
                info("error summary:")
                for e in errors[-5:]:
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', e)
                    clean = re.sub(r'^\S+\s+\S+\s+\S+\s+', '', clean).strip()
                    if clean:
                        info(f"  {clean}")

        fail_count = sum(1 for r in runs if r.get("conclusion") == "failure")
        if fail_count >= 3:
            fail(f"{fail_count} consecutive failures!")
            add_issue("fail", "ci", f"CI {fail_count} consecutive failures")
    else:
        info(f"latest CI: {status} ({created})")


# ── 5. Workflow YAML 檢查 ─────────────────────────────

def check_workflow():
    header("Workflow Config")

    yml = os.path.join(BASE_DIR, ".github", "workflows", "monitor.yml")
    if not os.path.exists(yml):
        fail("monitor.yml missing")
        add_issue("fail", "workflow", "monitor.yml missing")
        return
    ok("monitor.yml exists")

    with open(yml, "r", encoding="utf-8") as f:
        content = f.read()

    if "git add -f" in content:
        ok("git add -f (bypasses .gitignore)")
    elif "git add" in content:
        warn("git add without -f, data/ in .gitignore may be skipped")
        add_issue("warn", "workflow", "git add should use -f")

    if "git pull" in content:
        ok("git pull before push (prevents conflicts)")
    else:
        warn("should add git pull --rebase before push")

    cron_match = re.search(r"cron:\s*'(.+?)'", content)
    if cron_match:
        info(f"cron: {cron_match.group(1)}")


# ── 6. 本地 vs Remote 同步 ────────────────────────────

def check_sync():
    header("Local vs Remote Sync")

    r = run("git diff --name-only origin/main")
    if r.returncode != 0:
        warn("cannot compare (no remote)")
        return

    diff_files = [f for f in r.stdout.strip().split("\n") if f.strip()]
    if not diff_files:
        ok("local and remote in sync")
        return

    py_files = [f for f in diff_files if f.endswith(".py")]
    yml_files = [f for f in diff_files if f.endswith(".yml")]
    other = [f for f in diff_files if f not in py_files and f not in yml_files]

    if py_files:
        fail(f"{len(py_files)} .py files out of sync (CI uses old version)")
        for f in py_files:
            info(f"  {f}")
        add_issue("fail", "sync", "Python source not synced to remote",
                  lambda: _auto_commit_and_push("main"))
    if yml_files:
        warn(f"{len(yml_files)} workflow files out of sync")
    if other:
        info(f"{len(other)} other files out of sync")


# ── 7. 快速執行測試 ──────────────────────────────────

def check_monitor_dry():
    header("monitor.py Dry Run")

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
        ok(f"monitor.py loads OK (period {period})")
        return True
    else:
        err = output.split("|")[1] if "|" in output else output
        fail(f"monitor.py load failed: {err}")
        add_issue("fail", "runtime", f"monitor.py error: {err}")
        return False


# ── CI 模式 ──────────────────────────────────────────

def ci_precheck():
    """CI 預檢: 在 monitor.py 之前跑，確保 import 和資料都沒問題"""
    print(f"\n{Colors.BOLD}{'='*50}")
    print(f"  Doctor Pre-Check (CI)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*50}{Colors.END}")

    imports_ok = check_imports()
    data_ok = check_data()
    monitor_ok = check_monitor_dry()

    if imports_ok and monitor_ok:
        ok("Pre-check passed, safe to run monitor.py")
        return 0
    else:
        fail("Pre-check FAILED, monitor.py will likely crash")
        header("Issue Summary")
        for lv, cat, msg, _ in issues:
            if lv == "fail":
                fail(f"[{cat}] {msg}")
        return 1


def ci_diagnose(error_log: str = ""):
    """CI 失敗後診斷: 分析錯誤原因，給出修復建議"""
    print(f"\n{Colors.BOLD}{'='*50}")
    print(f"  Doctor Diagnosis (CI Post-Failure)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*50}{Colors.END}")

    check_imports()
    check_data()
    check_monitor_dry()

    header("Diagnosis")

    if not issues:
        info("No issues found in post-mortem check")
        info("The error may be transient (network, MOPS downtime)")
        return

    for lv, cat, msg, fix_fn in issues:
        if lv == "fail":
            fail(f"[{cat}] {msg}")
        else:
            warn(f"[{cat}] {msg}")

    # CI 環境下的自動修復 (僅限安裝套件)
    pip_issues = [(lv, c, m, fn) for lv, c, m, fn in issues
                  if c == "pip" and fn is not None]
    if pip_issues:
        header("Auto-Fix (CI)")
        for lv, cat, msg, fn in pip_issues:
            info(f"fixing: {msg}")
            try:
                fn()
                ok(f"fixed: {msg}")
            except Exception as e:
                fail(f"fix failed: {e}")

    # 產生 GitHub Actions 錯誤摘要
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        summary_path = os.environ["GITHUB_STEP_SUMMARY"]
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n## Doctor Diagnosis\n\n")
            for lv, cat, msg, _ in issues:
                icon = "x" if lv == "fail" else "warning"
                f.write(f"- :{icon}: **[{cat}]** {msg}\n")
            f.write("\n")


# ── 主程式 (本地模式) ─────────────────────────────────

def main():
    # CI 模式
    if "--ci" in sys.argv:
        return ci_precheck()
    if "--ci-diagnose" in sys.argv:
        ci_diagnose()
        return 1

    print(f"\n{Colors.BOLD}{'='*50}")
    print(f"  Revenue Tracker Health Check")
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
    header("Summary")
    fails = [(c, m) for lv, c, m, _ in issues if lv == "fail"]
    warns = [(c, m) for lv, c, m, _ in issues if lv == "warn"]

    if not fails and not warns:
        print(f"\n  {Colors.OK}All checks passed!{Colors.END}\n")
        return 0

    if fails:
        print(f"\n  {Colors.FAIL}{len(fails)} critical issue(s):{Colors.END}")
        for cat, msg in fails:
            print(f"     [{cat}] {msg}")
    if warns:
        print(f"\n  {Colors.WARN}{len(warns)} warning(s):{Colors.END}")
        for cat, msg in warns:
            print(f"     [{cat}] {msg}")

    # 自動修復
    if do_fix or do_push:
        header("Auto-Fix")
        fixable = [(lv, c, m, fn) for lv, c, m, fn in issues if fn is not None]
        if not fixable:
            info("nothing to auto-fix")
        else:
            for lv, cat, msg, fn in fixable:
                info(f"fixing: [{cat}] {msg}")
                try:
                    fn()
                    ok(f"fixed: {msg}")
                    fixed.append(msg)
                except Exception as e:
                    fail(f"fix failed: {e}")

        if fixed:
            print(f"\n  {Colors.OK}Fixed {len(fixed)} issue(s){Colors.END}")
            for f in fixed:
                print(f"    - {f}")
    else:
        if any(fn for _, _, _, fn in issues if fn):
            print(f"\n  {Colors.INFO}Run: python doctor.py --fix   (auto-fix)")
            print(f"  Run: python doctor.py --push  (fix + push to GitHub){Colors.END}")

    print()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
