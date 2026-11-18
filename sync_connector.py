# -*- coding: utf-8 -*-
"""第一步：把发布包里的浏览器连接器同步到仓库 main 分支。

双击就能跑（推荐双击 1-sync-connector.bat）。只做连接器这一件事：
  1. 读本包 browser-extension/manifest.json，确认是 1.4.8，并且和主程序
     内嵌的连接器版本一致；不一致就停住，绝不把错的版本推上去。
  2. 找到本地仓库（脚本目录本身是仓库就用它，否则用脚本目录下的
     Page-Operations-Monitor 子目录，没有就自动 clone），切到 main
     分支并拉取最新代码。
  3. 把本包的 browser-extension/ 整个拷进仓库（只动这一个目录，
     仓库里别的文件一个不动），有变化就提交“更新浏览器连接器 1.4.8”
     并推送到 main；没变化就直接告诉你已经是最新，不提交。
  4. 跑完这一步，再双击 publish.bat 发主程序，云端打出的包里嵌的
     才是新连接器 1.4.8。

安全与防呆：
  - 只提交 browser-extension/ 这一个目录，别处未提交的改动不会被带上去。
  - 仓库里 browser-extension/ 下已有未提交的改动时先停住，让你先处理。
  - 推送先走本机存好的 git 凭据，认证失败时再用 Token 重试；
    Token 只读不写，绝不打印、绝不写进代码与文件。
  - 只检查不动手：python sync_connector.py --dry-run。

用法：python sync_connector.py [--repo 仓库目录] [--branch main] [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OWNER = "bstbuku-ship-it"
REPO = "Page-Operations-Monitor"
REPO_URL = f"https://github.com/{OWNER}/{REPO}"
CONNECTOR_VERSION = "1.4.8"

TOKEN_ENV_NAMES = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT", "GIT_TOKEN")


def fail(msg):
    print("错误：" + msg, file=sys.stderr)
    raise SystemExit(1)


def run(cmd, cwd, check=True, secret_values=()):
    shown = " ".join(str(c) for c in cmd)
    for s in secret_values:
        if s:
            shown = shown.replace(s, "***")
    print("> " + shown)
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=str(cwd),
                           capture_output=True, text=True, errors="replace")
    except FileNotFoundError:
        fail(f"找不到命令 {cmd[0]}。请先安装 Git（https://git-scm.com），装好再双击运行。")
    if check and r.returncode != 0:
        fail(f"命令失败（退出码 {r.returncode}）：{shown}\n{r.stdout}{r.stderr}")
    return r


def resolve_token():
    """Return (token, source). Token value is never printed anywhere."""
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, f"环境变量 {name}"
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True,
                           text=True, errors="replace", timeout=30)
    except (FileNotFoundError, OSError):
        r = None
    if r is not None and r.returncode == 0:
        value = r.stdout.strip()
        if value.startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")):
            return value, "gh CLI 已保存的登录（gh auth login）"
    return "", ""


def current_branch(repo: Path) -> str:
    r = run(["git", "symbolic-ref", "--short", "HEAD"], repo, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def ensure_repo(repo: Path, branch: str):
    """Clone the public repo if needed, else fast-forward the local clone."""
    if (repo / ".git").is_dir():
        r = run(["git", "config", "--get", "remote.origin.url"], repo, check=False)
        url = r.stdout.strip()
        if url and "Page-Operations-Monitor" not in url:
            fail(f"该目录的 git 远程地址不是本项目：{url}\n请换一个目录，或删掉它让脚本重新 clone。")
        if current_branch(repo) != branch:
            run(["git", "checkout", branch], repo)
        print("正在拉取最新代码…")
        run(["git", "pull", "--ff-only", "origin", branch], repo)
        return
    if repo.exists() and any(repo.iterdir()):
        fail(f"目录 {repo} 非空且不是 git 仓库，无法 clone。请清空它或用 --repo 指定已有仓库。")
    print(f"本地没有仓库，正在 clone：{REPO_URL}")
    run(["git", "clone", REPO_URL, str(repo)], cwd=repo.parent)
    if current_branch(repo) != branch:
        run(["git", "checkout", branch], repo)


def ensure_identity(repo: Path):
    """Fresh clones often lack user.name/user.email; ask once when interactive."""
    for key, label in (("user.name", "提交者姓名"), ("user.email", "提交者邮箱")):
        r = run(["git", "config", "--get", key], repo, check=False)
        if r.returncode == 0 and r.stdout.strip():
            continue
        if sys.stdin.isatty():
            value = input(f"{label}（git {key}，仅保存在本仓库配置里）：").strip()
        else:
            value = ""
        if not value:
            fail(f"git 没有配置 {key}。请先在仓库里跑 git config {key} \"…\" 再运行。")
        run(["git", "config", key, value], repo)


def push(repo: Path, branch: str, token: str):
    """Plain push first (stored credentials); on auth failure retry with the token."""
    r = run(["git", "push", "origin", branch], repo, check=False)
    if r.returncode == 0:
        return
    out = r.stdout + r.stderr
    if token and any(k in out.lower() for k in ("auth", "permission", "403", "401", "denied")):
        cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        r2 = run(["git", "-c", f"http.extraHeader=AUTHORIZATION: basic {cred}",
                  "push", "origin", branch], repo, check=False, secret_values=(cred,))
        if r2.returncode == 0:
            return
        out += r2.stdout + r2.stderr
    fail("推送失败。请检查 git 凭据（Windows 凭据管理器里存的 GitHub 登录）或 Token 是否有效。\n" + out)


def main():
    ap = argparse.ArgumentParser(description="把发布包的浏览器连接器同步到仓库 main 分支（发布第一步）")
    ap.add_argument("--repo", default=None, help="本地仓库目录；不填则用脚本目录下的仓库、没有就自动 clone")
    ap.add_argument("--branch", default="main", help="推送分支（默认 main）")
    ap.add_argument("--dry-run", action="store_true", help="只检查，不拷贝、不提交、不推送")
    args = ap.parse_args()

    package = Path(__file__).resolve().parent
    ext_src = package / "browser-extension"
    manifest_path = ext_src / "manifest.json"
    if not manifest_path.is_file():
        fail("发布包里找不到 browser-extension/manifest.json，请用完整的发布包再跑。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = str(manifest.get("version", ""))
    if version != CONNECTOR_VERSION:
        fail(f"本包连接器版本是 {version}，不是 {CONNECTOR_VERSION}，已停住。请用正确的发布包再跑。")
    main_py = package / "Page_Operations_Monitor.py"
    if main_py.is_file():
        m = re.search(r"BUNDLED_CONNECTOR_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                      main_py.read_text(encoding="utf-8-sig"))
        if m and m.group(1) != version:
            fail(f"主程序内嵌连接器是 {m.group(1)}，和本包 browser-extension/ 的 {version} 不一致，已停住。")
    print(f"本包连接器版本：{version}，和主程序内嵌版本一致。")

    if args.repo:
        repo = Path(args.repo).resolve()
    elif (package / ".git").is_dir():
        repo = package
    else:
        repo = package / REPO
    print(f"仓库目录：{repo}")
    print(f"发布包目录：{package}")

    if args.dry_run:
        print("dry-run：只检查，不拷贝、不提交、不推送。")
        if (repo / ".git").is_dir():
            r = run(["git", "status", "--porcelain", "--", "browser-extension"], repo, check=False)
            print("仓库连接器目录当前状态：" + (r.stdout.strip() or "（干净）"))
        print(f"dry-run 完成：待同步连接器 {version}。")
        return 0

    ensure_repo(repo, args.branch)
    # 提交身份先确认好（没配好就停在这里），再动文件：否则拷完才发现
    # 没法提交，下次跑又会被下面的未提交改动检查挡住。
    ensure_identity(repo)
    # 仓库里连接器目录下已有未提交的改动时：如果是上次跑到一半拷好
    # 但没提交的（内容和本包完全一致），就继续提交；是用户自己的
    # 改动就先停住，让他先处理，别悄悄盖掉。
    r = run(["git", "status", "--porcelain", "--", "browser-extension"], repo, check=False)
    if r.stdout.strip():
        ext_dst_pre = repo / "browser-extension"
        _same = (ext_dst_pre.is_dir()
                 and sorted(p.relative_to(ext_dst_pre).as_posix() for p in ext_dst_pre.rglob("*") if p.is_file())
                 == sorted(p.relative_to(ext_src).as_posix() for p in ext_src.rglob("*") if p.is_file())
                 and all((ext_dst_pre / p.relative_to(ext_src).as_posix()).read_bytes() == p.read_bytes()
                         for p in ext_src.rglob("*") if p.is_file()))
        if _same:
            print("检测到上次已拷好但没提交的连接器，继续提交。")
        else:
            fail("仓库里 browser-extension/ 下有未提交的改动，先提交或撤销它们再跑：\n" + r.stdout)
    ext_dst = repo / "browser-extension"
    before = None
    if (ext_dst / "manifest.json").is_file():
        before = json.loads((ext_dst / "manifest.json").read_text(encoding="utf-8")).get("version")
    if ext_dst.exists():
        shutil.rmtree(ext_dst)
    shutil.copytree(ext_src, ext_dst)
    print(f"已拷贝 browser-extension/（仓库里原来是 {before}，现在是 {version}）。")

    r = run(["git", "status", "--porcelain", "--", "browser-extension"], repo, check=False)
    if not r.stdout.strip():
        print(f"仓库里的连接器已经是 {version}，无需提交。")
        _ahead = run(["git", "rev-list", "--count", f"origin/{args.branch}..HEAD"], repo, check=False)
        if _ahead.returncode == 0 and int(_ahead.stdout.strip() or "0") > 0:
            print("本地还有没推送的提交，现在推送。")
            token, token_source = resolve_token()
            if token_source:
                print(f"推送凭据：已找到（来源：{token_source}，值不会被打印）")
            push(repo, args.branch, token)
            print(f"已推送：{run(['git', 'rev-parse', 'HEAD'], repo).stdout.strip()}")
        print("第一步完成：可以直接双击 publish.bat 发主程序了。")
        return 0
    run(["git", "add", "--", "browser-extension"], repo)
    run(["git", "commit", "-m", f"更新浏览器连接器 {version}"], repo)
    token, token_source = resolve_token()
    if token_source:
        print(f"推送凭据：已找到（来源：{token_source}，值不会被打印）")
    push(repo, args.branch, token)
    head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    print(f"已推送：{head}")
    print(f"第一步完成：仓库 main 分支上的连接器已是 {version}。")
    print("第二步：双击 publish.bat 发主程序，云端打出的包里嵌的才是新连接器。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
