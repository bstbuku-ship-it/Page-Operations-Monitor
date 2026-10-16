# -*- coding: utf-8 -*-
"""Page Operations Monitor 1.5.0 -- automatic multi-Chrome Connector edition.
Run .py / .pyw; install PyQt6 Pillow (no connector network dependency).
Unpack extension/ in Chrome. It connects automatically. Select only when several browsers are online.
No remote-debugging switch, no cookie export, no unattended launch of the old default browser.
Version-independent single-instance activation. Closing to tray is silent.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
import os
import re
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
import hashlib
import html
import json
import zipfile
import shutil
import subprocess
import sys
import io
import math
import random
import uuid
import logging
from datetime import timedelta
from urllib.parse import urljoin
import platform
import urllib.request
import urllib.error
import ssl
import base64
import shlex

APP_TITLE = "专业监控工具"
APP_VERSION = "1.5.0"
APP_BUILD = "professional-portable-deployer-ui-v150-20261016"
DEFAULT_INTERVAL_MINUTES = 120
DEFAULT_PAGE_GAP_SECONDS = 8  # compatibility for callers using a fixed interval
DEFAULT_ROUND_JITTER_MIN = 15
DEFAULT_ROUND_JITTER_MAX = 25
DEFAULT_PAGE_GAP_MIN = 6
DEFAULT_PAGE_GAP_MAX = 9
DEFAULT_SHOW_BROWSER = False
APP_USER_MODEL_ID = "bstbuku.PageOperationsMonitor.Desktop"
FACEBOOK_HOME = "https://www.facebook.com/"
PAGE_LOAD_TIMEOUT_MS = 45000


def ensure_private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise RuntimeError("数据目录不能是符号链接")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def portable_install_root() -> Path | None:
    """Application directory for explicit green/portable deployment only."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        root = Path(sys.executable).resolve().parent
        return root if (root / "portable.mode").is_file() else None
    except OSError:
        return None


def app_data_dir() -> Path:
    override = os.environ.get("FBPM_DATA_DIR", "").strip()
    if override:
        return ensure_private_directory(Path(override).expanduser())
    portable = portable_install_root()
    if portable is not None:
        return ensure_private_directory(portable / "data")
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "FBGrowthRadar"
    else:
        base = Path.home() / ".fb_growth_radar"
    return base

DATA_DIR = app_data_dir()
DB_PATH = DATA_DIR / "fb_growth_radar_v1.db"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
AVATAR_DIR = DATA_DIR / "avatars"


def monitor_profile_dir() -> Path:
    """The one application-owned browser profile; never scans or opens daily Chrome accounts."""
    return BROWSER_PROFILE_DIR








def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_count(v) -> str:
    return "—" if v is None else f"{int(v):,}"


def format_compact_count(v) -> str:
    """Compact follower number for cards; exact value remains in the tooltip."""
    if v is None:
        return "—"
    n = int(v)
    if abs(n) < 7000:
        return f"{n:,}"
    text = f"{n / 10000.0:.1f}".rstrip("0").rstrip(".")
    return text + "W"


def format_delta(v) -> str:
    return "—" if v is None else (f"+{int(v):,}" if v > 0 else f"{int(v):,}")


def compact_elapsed(ts, now=None, approximate=False) -> str:
    if not ts:
        return "—"
    now = time.time() if now is None else float(now)
    seconds = max(0.0, now - float(ts))
    mark = "≈" if approximate else ""
    if seconds < 3600:
        return f"{mark}{max(1, int(seconds // 60))}M"
    hours = seconds / 3600.0
    if hours < 100:
        return f"{mark}{hours:.1f}H"
    return f"{mark}{hours / 24.0:.1f}D"


def local_time_label(value: str, with_date=True) -> str:
    if not value:
        return "—"
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo:
            d = d.astimezone()
        return d.strftime("%m-%d %H:%M" if with_date else "%H:%M")
    except (ValueError, TypeError):
        return value[:16].replace("T", " ")


def safe_csv_cell(value):
    if isinstance(value, str):
        probe = value.lstrip("\ufeff \t\r\n\v\f")
        if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


@dataclass
class PasteParseResult:
    ids: list[str]
    rejected: list[str]
    duplicates: int = 0


# Real 谷歌表格 copies contain tabs/newlines; some copied data contains
# Markdown / terminal table decorations as well.
BORDERS = "│┃┆┇┊┋╎╏┌┐└┘├┤┬┴┼─━═║╔╗╚╝╠╣╦╩╬┏┓┗┛┣┫┳┻╋"
INVISIBLE = ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060", "\u00ad")
HEADERS = {"id", "pageid", "page_id", "facebookid", "facebookpageid", "专业id", "专页id", "主页id", "编号", "主页编号", "facebook主页", "name", "page", "主页名称", "专页名称"}


def _facebook_id_from_url(raw: str) -> str | None:
    candidate = raw.strip().strip("<>[]{}()\"'“”‘’.,;，；")
    if "facebook.com" not in candidate.lower() and "fb.com" not in candidate.lower():
        return None
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        url = urlsplit(candidate)
        host = (url.hostname or "").lower()
        if not (host in ("facebook.com", "fb.com") or host.endswith(".facebook.com") or host.endswith(".fb.com")):
            return None
        qs = parse_qs(url.query)
        for key in ("id", "page_id"):
            for val in qs.get(key, []):
                if re.fullmatch(r"\d{5,25}", val):
                    return val
        segments = [x for x in url.path.split("/") if x]
        if segments and re.fullmatch(r"\d{5,25}", segments[-1]):
            return segments[-1]
    except ValueError:
        pass
    return None


def normalize_page_ids(text: str) -> PasteParseResult:
    """Parse IDs pasted from Sheets, Excel, ASCII / Markdown tables and URLs.

    Never convert floating-point or exponential notation to an ID.  When Sheets
    has rounded a 15-digit number, the lost digits cannot be recovered.
    """
    if not text:
        return PasteParseResult([], [])
    source = unicodedata.normalize("NFKC", str(text))
    for char in INVISIBLE:
        source = source.replace(char, "")
    source = source.replace("\u00a0", " ").replace("\u3000", " ")
    source = source.translate(str.maketrans({c: "|" for c in BORDERS}))
    ids, seen, rejected, duplicates = [], set(), [], 0

    def add(token: str):
        nonlocal duplicates
        if token in seen:
            duplicates += 1
        else:
            ids.append(token)
            seen.add(token)

    def process(raw: str):
        token = raw.strip().strip("\"“”‘’`")
        while token.startswith(("'", "’", "＇")):
            token = token[1:].strip()
        token = token.strip("\"“”‘’`")
        if not token or token in {"-", "--", ":-", "—", "…"}:
            return
        if re.fullmatch(r"[-+=:|_ ]{3,}", token):
            return
        if re.fullmatch(r"=[\"']?\d+[\"']?", token):
            token = re.sub(r"[^0-9]", "", token)
        if "facebook.com" in token.lower() or "fb.com" in token.lower():
            found = _facebook_id_from_url(token)
            if found:
                add(found)
            else:
                rejected.append(raw.strip()[:100])
            return
        if re.search(r"(?:\d+\.?\d*)[Ee][+-]?\d+", token):
            rejected.append(raw.strip()[:100] + "（科学计数法无法保证精确）")
            return
        if re.fullmatch(r"\d{1,3}(?:[,，]\d{3})+", token):
            token = token.replace(",", "").replace("，", "")
        if re.fullmatch(r"\d{5,25}", token):
            add(token)
        elif re.fullmatch(r"\d+", token):
            rejected.append(raw.strip()[:100] + "（长度不像 主页编号）")
        elif any(ch.isdigit() for ch in token):
            rejected.append(raw.strip()[:100])
        elif re.sub(r"[\s_-]+", "", token.lower()) not in HEADERS:
            # Other columns of a spreadsheet (e.g. page name) are safely skipped.
            return

    # Split first on actual pasted rows/cells. Comma splitting is handled per
    # cell to distinguish thousands separators from comma-separated ID lists.
    for cell in re.split(r"[\r\n\t|;；]+", source):
        cell = cell.strip()
        if not cell or re.fullmatch(r"[-+:_= ]{3,}", cell):
            continue
        if "facebook.com" in cell.lower() or "fb.com" in cell.lower():
            for part in re.split(r"\s+", cell):
                process(part)
            continue
        # Multiple IDs on the same line, including from multi-cell paste.
        if re.fullmatch(r"\d{1,3}(?:[,，]\d{3})+", cell):
            process(cell)
            continue
        for part in re.split(r"[,，\s]+", cell):
            process(part)
    return PasteParseResult(ids, rejected, duplicates)


# ---------- Facebook text extraction (legacy parser preserved + safer patterns) ----------

def parse_human_number(raw):
    s = str(raw).strip().lower().replace("\u00a0", " ").replace("，", ",")
    suffixes = [
        (r"\s*(?:k|千|rb|ribu|mil)$", 1000),
        (r"\s*(?:m|million|millions|millón|millones|mio\.?|jt)$", 1_000_000),
        (r"\s*(?:b|billion|billions)$", 1_000_000_000),
        (r"\s*万$", 10_000),
        (r"\s*亿$", 100_000_000),
    ]
    multiplier = 1
    for pat, factor in suffixes:
        if re.search(pat, s, re.I):
            multiplier = factor
            s = re.sub(pat, "", s, flags=re.I).strip()
            break
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        raise ValueError("未识别到数字")
    if multiplier == 1:
        return int(re.sub(r"[.,]", "", s)), False
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in s:
        s = s.replace(",", "." if len(s.split(",")[-1]) <= 2 else "")
    elif "." in s and len(s.split(".")[-1]) > 2:
        s = s.replace(".", "")
    return int(round(float(s) * multiplier)), True


FOLLOWER_PATTERNS = [
    r"(?P<num>[0-9][0-9.,\s]*(?:[KkMmBb])?)\s+(?:followers?|Follower)",
    r"(?P<num>[0-9][0-9.,\s]*(?:万|亿|[KkMm])?)\s*(?:位)?粉丝",
    r"(?P<num>[0-9][0-9.,\s]*(?:rb|ribu|jt|[KkMm])?)\s+(?:pengikut)",
    r"(?P<num>[0-9][0-9.,\s]*(?:mil|millones?|[KkMm])?)\s+(?:seguidores?)",
    r"(?P<num>[0-9][0-9.,\s]*(?:k|m|millions?)?)\s+(?:abonnés?)",
    r"(?P<num>[0-9][0-9.,\s]*(?:mila|milioni?|[KkMm])?)\s+(?:follower)",
    r"(?P<num>[0-9][0-9.,\s]*(?:bin|milyon|[KkMm])?)\s+(?:takipçi)",
]


def extract_followers_from_text(text: str):
    candidates = []
    for pattern in FOLLOWER_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            try:
                count, approx = parse_human_number(match.group("num"))
            except (ValueError, OverflowError):
                continue
            if 0 <= count <= 10_000_000_000:
                candidates.append((match.start(), count, approx, match.group(0).strip()))
    if not candidates:
        raise RuntimeError("页面未识别到粉丝数。可能需要登录、等待加载，或 脸书页面格式发生了变化。")
    # Prefer the first follower count in the page's heading region.  All results
    # are tentative; the UI shows approximations explicitly.
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2], candidates[0][3]


def clean_page_name(raw):
    if not raw:return ""
    text=str(raw)
    for _ in range(3):
        decoded=html.unescape(text)
        if decoded==text:break
        text=decoded
    text=re.sub(r"\s+", " ", text).strip()
    text=re.sub(r"^\(\d+\)\s*", "", text).strip()
    text=re.sub(r"\s*[|\-–—·]\s*Facebook\s*$", "", text, flags=re.I).strip()
    text=re.sub(r"\s*\|\s*Meta\s*$", "", text, flags=re.I).strip()
    text=re.sub(r"\s*[|\-–—·]\s*(?:Home|Posts|About|Photos|Videos|Reels|主页|首页|帖子|关于|照片|视频|短视频)\s*$",
                "", text, flags=re.I).strip()
    return text if len(text)<=180 else ""


# Name extractor from the supplied reference.zip / facebook_follower_tracker_v6.py.
# Identity-source order and filtering retained; integrated after follower-text parsing.
GENERIC_UI_NAMES = {
    "facebook", "meta", "home", "首页", "主页", "通知", "消息", "菜单", "搜索", "好友", "视频", "游戏", "群组",
    "动态消息", "动态", "创建", "更多", "个人主页", "设置", "设置和隐私", "帮助和支持", "查看全部", "通知中心",
    "赞", "点赞", "关注", "已关注", "正在关注", "发消息", "简介", "关于", "帖子", "照片", "短视频", "提及", "点评", "社区",
    "直播", "分享", "管理", "切换", "搜索 facebook", "notifications", "notification", "menu", "search", "friends",
    "watch", "marketplace", "groups", "gaming", "messenger", "messages", "settings", "like", "liked", "follow",
    "following", "message", "about", "posts", "photos", "videos", "reels", "mentions", "reviews", "community", "live",
    "share", "log in", "login", "sign up", "register", "详细信息", "详情", "更多信息", "专页详情", "页面详情",
    "个人资料详情", "个人资料详细信息", "公开详情", "基本信息", "信息", "介绍", "联系方式", "details", "detail",
    "page details", "profile details", "public details", "more information", "additional information", "contact info", "information",
    "facebook - log in or sign up", "facebook – log in or sign up", "facebook - 登录或注册", "facebook – 登录或注册",
    "全部", "所有", "全部内容", "查看全部", "显示全部", "全部帖子", "全部动态", "all", "all posts",
    "see all", "show all", "overview", "timeline", "精选", "筛选", "排序", "最近", "最相关", "热门",
    "查看所有照片", "查看全部照片", "所有照片", "see all photos", "view all photos", "all photos",
    "posts by", "more", "更多内容", "管理帖子", "筛选条件",
}

BAD_NAME_FRAGMENTS = [
    "followers", "follower", "粉丝", "pengikut", "seguidores", "abonn", "following", "likes", "people like this",
    "people follow this", "登录", "注册", "log in", "sign up", "notification", "通知中心", "详细信息", "个人资料详细信息",
    "公开详情", "page details", "profile details", "查看所有照片", "查看全部照片", "see all photos", "view all photos",
]

# Facebook 的页头区域同时会出现“关注 360 人 / 关注 0 人 / 1 人关注”等统计或操作文字。
# 这些文字字体较大，旧版本有时会把它们误判成专页名称。
STAT_OR_ACTION_PATTERNS = [
    r"^(?:已?关注|正在关注|关注了|关注中)\s*[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?$",
    r"^[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?\s*(?:已?关注|正在关注|关注中)$",
    r"^(?:following|followed by)\s*[0-9][0-9.,\sKkMmBb]*\s*(?:people|persons?)?$",
    r"^[0-9][0-9.,\sKkMmBb]*\s*(?:people\s+)?following$",
    r"^[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|people|persons?)$",
    r"^(?:赞|点赞|likes?)\s*[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?$",
]


def looks_like_stat_or_action(value: str) -> bool:
    s = clean_page_name(value)
    if not s:
        return True
    compact = re.sub(r"\s+", " ", s).strip()
    for pat in STAT_OR_ACTION_PATTERNS:
        if re.fullmatch(pat, compact, flags=re.I):
            return True

    # 只要包含明显的数字统计 + UI 关键词，也不要作为名称。
    has_number = bool(re.search(r"[0-9０-９]", compact))
    if has_number and re.search(
        r"(?:关注|正在关注|已关注|粉丝|点赞|赞|followers?|following|likes?|people\s+follow)",
        compact,
        flags=re.I,
    ):
        return True
    return False


def looks_like_page_name(value, page_id=""):
    s = clean_page_name(value)
    if not s:
        return False
    low = s.lower().strip()
    if low in {x.lower() for x in GENERIC_UI_NAMES}:
        return False
    if any(x in low for x in BAD_NAME_FRAGMENTS):
        return False
    if looks_like_stat_or_action(s):
        return False
    if page_id and s == str(page_id):
        return False
    if re.search(r"https?://|www\.", low):
        return False
    if re.fullmatch(r"[\d\s.,:+\-/%万亿千kmb]+", low, flags=re.I):
        return False
    if not re.search(r"[A-Za-z\u00C0-\u024F\u4e00-\u9fff\u3040-\u30ff\u0E00-\u0E7F]", s):
        return False
    return True

def _meta_content(page, selector):
    try:
        return page.locator(selector).first.get_attribute("content", timeout=1200) or ""
    except Exception:
        return ""


def _clean_profile_alt(raw):
    s = clean_page_name(raw)
    if not s:
        return ""
    suffixes = [
        r"'s\s+profile\s+picture$", r"profile\s+picture$", r"'s\s+profile\s+photo$",
        r"profile\s+photo$", r"的头像$", r"的大头贴$", r"的个人头像$", r"头像$",
        r"foto de perfil$", r"photo de profil$", r"profilbild$", r"immagine del profilo$",
    ]
    for pat in suffixes:
        s = re.sub(pat, "", s, flags=re.I).strip()
    return clean_page_name(s)


def _strict_h1_candidates(page):
    """Return visible h1 text outside navigation/tab/dialog chrome, top first."""
    try:
        rows = page.locator("h1").evaluate_all(
            r"""
            (els) => {
              const out = [];
              for (const el of els) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight * 2) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                out.push({text, top:r.top, left:r.left, fs:parseFloat(st.fontSize || '0') || 0});
              }
              out.sort((a,b) => (a.top-b.top) || (b.fs-a.fs) || (a.left-b.left));
              return out.slice(0, 20);
            }
            """
        )
        return rows or []
    except Exception:
        return []


def _profile_alt_candidates(page):
    try:
        rows = page.locator('img[alt]').evaluate_all(
            r"""
            (els) => {
              const out = [];
              for (const el of els.slice(0, 300)) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 28 || r.height < 28 || r.bottom < 0 || r.top > 1200) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="menu"],[role="dialog"]')) continue;
                const alt = (el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim();
                if (!alt || alt.length > 220) continue;
                const isProfile = /(?:'s\s+profile\s+(?:picture|photo)|profile\s+(?:picture|photo)|的头像|的大头贴|的个人头像|头像|foto de perfil|photo de profil|profilbild|immagine del profilo)$/i.test(alt);
                if (!isProfile) continue;
                out.push({text:alt, top:r.top, size:Math.max(r.width, r.height)});
              }
              out.sort((a,b) => (a.top-b.top) || (b.size-a.size));
              return out.slice(0, 30);
            }
            """
        )
        return rows or []
    except Exception:
        return []


def _self_link_candidates(page, page_id):
    try:
        return page.locator('a[href]').evaluate_all(
            r"""
            (els, pageId) => {
              const out = [];
              const id = String(pageId || '');
              const cur = new URL(location.href);
              const curPath = cur.pathname.replace(/\/+$/, '');
              for (const el of els.slice(0, 1200)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1100) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                let u; try { u = new URL(el.href, location.href); } catch (_) { continue; }
                const path = u.pathname.replace(/\/+$/, '');
                const idHit = id && (path === '/' + id || path.startsWith('/' + id + '/'));
                const profileId = id && u.searchParams.get('id') === id;
                const samePath = curPath && path === curPath;
                if (!(idHit || profileId || samePath)) continue;
                out.push({
                  text,
                  top:r.top,
                  fs:parseFloat(st.fontSize || '0') || 0,
                  fw:parseInt(st.fontWeight || '400', 10) || 400,
                  strong:idHit || profileId
                });
              }
              out.sort((a,b) => (Number(b.strong)-Number(a.strong)) || (a.top-b.top) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 60);
            }
            """,
            str(page_id or ""),
        ) or []
    except Exception:
        return []


def _near_follower_candidates(page, matched_text):
    """Find visible text just above/alongside the actual follower-count element."""
    if not matched_text:
        return []
    try:
        return page.locator('body').evaluate(
            r"""
            (body, needle) => {
              needle = String(needle || '').replace(/\s+/g, ' ').trim();
              if (!needle) return [];
              const all = Array.from(document.querySelectorAll('a,span,div'));
              const hits = [];
              for (const el of all.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 220) continue;
                if (!(text === needle || text.includes(needle))) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1400) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                hits.push({el, r});
              }
              if (!hits.length) return [];
              hits.sort((a,b) => (a.r.top-b.r.top) || (a.r.left-b.r.left));
              const target = hits[0].r;
              const out = [];
              const candidates = Array.from(document.querySelectorAll('h1,h2,[role="heading"],a,span,strong'));
              for (const el of candidates.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2) continue;
                if (r.top < target.top - 320 || r.top > target.bottom + 90) continue;
                if (Math.abs(r.left - target.left) > 900) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180 || text === needle) continue;
                const fs = parseFloat(st.fontSize || '0') || 0;
                const fw = parseInt(st.fontWeight || '400', 10) || 400;
                const distance = Math.max(0, target.top - r.bottom);
                out.push({text, distance, fs, fw, top:r.top});
              }
              out.sort((a,b) => (a.distance-b.distance) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 80);
            }
            """,
            str(matched_text),
        ) or []
    except Exception:
        return []


def _wait_for_page_identity(page, timeout_ms=7000):
    """Give Facebook SPA a little time to replace generic chrome with Page identity."""
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        for row in _strict_h1_candidates(page):
            name = clean_page_name((row or {}).get("text", ""))
            if looks_like_page_name(name):
                return
        try:
            title = clean_page_name(page.title())
            if looks_like_page_name(title):
                return
        except Exception:
            pass
        try:
            page.wait_for_timeout(350)
        except Exception:
            break


def extract_page_name(page, body_text, page_id="", matched_text=""):
    """Extract the Page display name using identity-specific DOM before generic text.

    The old versions used a broad largest-text heuristic. Facebook UI words such as
    “通知”, “详细信息”, “关注 360 人”, and “全部” can be large too, so this version
    only trusts identity-bearing locations first and heavily filters navigation text.
    """
    _wait_for_page_identity(page, timeout_ms=4500)

    # 1) Facebook Pages normally expose the display name as a visible top-level h1.
    # Take the first valid h1 outside navigation/tab/dialog chrome.
    for row in _strict_h1_candidates(page):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 2) The profile image accessible name is highly specific to the Page identity.
    for row in _profile_alt_candidates(page):
        name = _clean_profile_alt((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 3) A link that points back to the current numeric Page identity.
    for row in _self_link_candidates(page, page_id):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 4) Open Graph/document metadata. These are useful but can remain generic in SPA views.
    for raw in [
        _meta_content(page, 'meta[property="og:title"]'),
        _meta_content(page, 'meta[name="twitter:title"]'),
    ]:
        name = clean_page_name(raw)
        if looks_like_page_name(name, page_id):
            return name
    try:
        name = clean_page_name(page.title())
        if looks_like_page_name(name, page_id):
            return name
    except Exception:
        pass

    # 5) Only search text physically near the follower count that we actually parsed.
    for row in _near_follower_candidates(page, matched_text):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 6) Last resort: visible heading roles outside navigation. No generic large-text scan.
    try:
        rows = page.locator('[role="heading"]').evaluate_all(
            r"""
            (els) => {
              const out=[];
              for (const el of els.slice(0, 250)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r=el.getBoundingClientRect(), st=getComputedStyle(el);
                if (!r || r.width<2 || r.height<2 || r.bottom<0 || r.top>1200) continue;
                if (st.visibility==='hidden' || st.display==='none' || Number(st.opacity||1)===0) continue;
                const text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
                if (!text || text.length>180) continue;
                const level = Number(el.getAttribute('aria-level') || 99);
                out.push({text, level, top:r.top, fs:parseFloat(st.fontSize||'0')||0});
              }
              out.sort((a,b)=>(a.level-b.level)||(a.top-b.top)||(b.fs-a.fs));
              return out.slice(0,80);
            }
            """
        )
        for row in rows or []:
            name = clean_page_name((row or {}).get("text", ""))
            if looks_like_page_name(name, page_id):
                return name
    except Exception:
        pass

    return ""




def should_alert(current: int, previous: dict | None, current_ts: float,
                 current_approx: bool, interval_seconds: int, threshold: int) -> bool:
    """Avoid false alerts after missing samples or with rounded follower numbers."""
    if previous is None or current_approx or previous.get("approx"):
        return False
    elapsed = current_ts - float(previous.get("ts") or 0)
    if elapsed < 60 or elapsed > max(300, 2.5 * interval_seconds):
        return False
    return current - int(previous["count"]) >= threshold


def normalize_name(value, pid=""):
    """Reject generated placeholders and decode HTML without turning an ID into a name."""
    name = clean_page_name(value or "")
    for _ in range(2):
        decoded = html.unescape(name)
        if decoded == name:
            break
        name = decoded
    name = re.sub(r"\s+", " ", name).strip()
    banned = {"名称待获取", "待获取", "facebook", "log in to facebook", "登录 facebook",
              "登录或注册", "登录或註冊", "此内容目前无法显示", "content isn't available",
              "this content isn't available right now", "this page isn't available right now",
              "page not found", "content not found", "log in or sign up", "log into facebook",
              "内容不可用", "此内容暂时无法显示", "这个页面暂时无法显示"}
    if name.casefold() in {x.casefold() for x in banned}:
        return ""
    if re.fullmatch(r"(?:主页|公共主页|專頁|专页|page)\s*[:：#]?\s*[\d\W]+", name, re.I):
        return ""
    if name.isdigit() or (pid and name == str(pid)):
        return ""
    return name[:180] if looks_like_page_name(name,pid) else ""


def display_name(row):
    return (str(row.get("custom_name") or "").strip()
            or normalize_name(row.get("page_name"), row.get("page_id"))
            or "名称待获取")


def is_true(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "none")
    return bool(value)


def _bounded_int(value, default, low, high):
    try:
        value = int(value)
    except (ValueError, TypeError, OverflowError):
        value = default
    return max(low, min(high, value))


def inspection_timing(settings):
    """One source of defaults/ranges for both UI locations and runtime scheduling."""
    return (
        _bounded_int(settings.value("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                     DEFAULT_INTERVAL_MINUTES, 5, 1440),
        _bounded_int(settings.value("page_gap_seconds", DEFAULT_PAGE_GAP_SECONDS),
                     DEFAULT_PAGE_GAP_SECONDS, 0, 120),
    )


def normalize_random_timing(minutes, jitter_min, jitter_max, gap_min, gap_max):
    """Five persisted values; jitter is a magnitude with a randomly chosen sign."""
    minutes = _bounded_int(minutes, DEFAULT_INTERVAL_MINUTES, 5, 1440)
    low = _bounded_int(jitter_min, DEFAULT_ROUND_JITTER_MIN, 0, minutes-1)
    high = _bounded_int(jitter_max, DEFAULT_ROUND_JITTER_MAX, 0, minutes-1)
    g0 = _bounded_int(gap_min, DEFAULT_PAGE_GAP_MIN, 0, 120)
    g1 = _bounded_int(gap_max, DEFAULT_PAGE_GAP_MAX, 0, 120)
    return (minutes, min(low, high), max(low, high), min(g0, g1), max(g0, g1))


def random_inspection_timing(settings):
    return normalize_random_timing(
        settings.value("interval_minutes", DEFAULT_INTERVAL_MINUTES),
        settings.value("round_jitter_min_minutes", DEFAULT_ROUND_JITTER_MIN),
        settings.value("round_jitter_max_minutes", DEFAULT_ROUND_JITTER_MAX),
        settings.value("page_gap_min_seconds", DEFAULT_PAGE_GAP_MIN),
        settings.value("page_gap_max_seconds", DEFAULT_PAGE_GAP_MAX))


def save_random_timing(settings, values):
    values = normalize_random_timing(*values)
    for key, value in zip(("interval_minutes", "round_jitter_min_minutes",
                          "round_jitter_max_minutes", "page_gap_min_seconds",
                          "page_gap_max_seconds"), values):
        settings.setValue(key, value)
    # Keep legacy settings readable to older tooling; actual scheduling uses both bounds.
    settings.setValue("page_gap_seconds", int(round((values[3]+values[4])/2)))
    return values


def migrate_random_preferences(settings):
    """Never reset explicit startup consent; retain deliberately customized old page gaps."""
    marker = "migrations/random_timing_130"
    if not settings.contains("page_gap_min_seconds"):
        old = _bounded_int(settings.value("page_gap_seconds", 8), 8, 0, 120)
        bounds = (6, 9) if old == 8 else (old, old)
        settings.setValue("page_gap_min_seconds", bounds[0])
        settings.setValue("page_gap_max_seconds", bounds[1])
    if not settings.contains("silent_to_tray"):
        settings.setValue("silent_to_tray", int(is_true(settings.value("min_to_tray", 1), True)))
    save_random_timing(settings, random_inspection_timing(settings))
    settings.setValue(marker, 1)
    settings.sync()


def sample_round_minutes(values, rng=None):
    minutes, low, high, _, _ = normalize_random_timing(*values)
    rng = rng or random
    if high == 0:
        return minutes
    delta = rng.randint(low, high)
    return minutes + rng.choice((-1, 1))*delta


def plan_next_round(values, started_at, now=None, rng=None):
    """Draw once per scheduled round. Preserve the existing start-to-start cadence."""
    now = time.time() if now is None else float(now)
    minutes = sample_round_minutes(values, rng)
    start = float(started_at) if started_at is not None else now
    delay = max(30.0, start + minutes*60.0 - now)
    return minutes, now + delay, max(1000, int(round(delay*1000)))


def inspection_stamp_label(value):
    if not value:
        return "\u2014"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone().strftime("%m/%d %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        return "\u2014"


def latest_inspection_stamp(settings, rows):
    stored = settings.value("last_inspection_at", "")
    if inspection_stamp_label(stored) != "\u2014":
        return str(stored)
    candidates = []
    for row in rows:
        value = row.get("last_inspected_at")
        if inspection_stamp_label(value) != "\u2014":
            try:
                ts = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                candidates.append((ts, str(value)))
            except (ValueError, TypeError, OverflowError, OSError):
                pass
    return max(candidates)[1] if candidates else ""


def toast_position(parent_width, parent_height, width, height):
    """Bottom-center in logical pixels; never float near the screen middle."""
    return (max(12, (int(parent_width)-int(width))//2),
            max(12, int(parent_height)-int(height)-26))


def migrate_runtime_preferences(settings):
    """One-time reset of the OLD accidental autostart flag; never overwrite later explicit consent.

    Existing custom intervals survive. Old untouched 30min/3s defaults become 120min/8s.
    Removing selector keys does not delete any stored browser files or logins.
    """
    marker = "migrations/default_browser_191"
    first = not is_true(settings.value(marker, 0))
    if first:
        settings.setValue("start_auto", 0)
        if not settings.contains("interval_minutes") or str(settings.value("interval_minutes")) == "30":
            settings.setValue("interval_minutes", DEFAULT_INTERVAL_MINUTES)
        if not settings.contains("page_gap_seconds") or str(settings.value("page_gap_seconds")) == "3":
            settings.setValue("page_gap_seconds", DEFAULT_PAGE_GAP_SECONDS)
        settings.setValue(marker, 1)
    for key in ("monitor_account", "system_chrome_profile"):
        settings.remove(key)
    if not settings.contains("start_auto"):
        settings.setValue("start_auto", 0)
    if not settings.contains("show_browser"):
        settings.setValue("show_browser", int(DEFAULT_SHOW_BROWSER))
    minutes, gap = inspection_timing(settings)
    settings.setValue("interval_minutes", minutes)
    settings.setValue("page_gap_seconds", gap)
    settings.sync()
    return first


def configure_process_identity():
    """Use one stable taskbar identity for the app; bundled EXE icon is set at build time."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (OSError, AttributeError):
            pass


def asset_candidates(relative_path):
    """Support source, PyInstaller onedir/onefile and macOS bundles without cwd assumptions."""
    roots = [Path(__file__).resolve().parent]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        roots.insert(0, Path(bundled))
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        roots.extend([executable.parent, executable.parent.parent / "Resources"])
    seen = set()
    for root in roots:
        candidate = root / relative_path
        if str(candidate) not in seen:
            seen.add(str(candidate))
            yield candidate



def valid_post_ts(value, now=None):
    now = time.time() if now is None else float(now)
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if value > 100_000_000_000:
        value /= 1000.0
    if not math.isfinite(value) or value < 1_075_766_400 or value > now + 90:
        return None
    return min(now, value)


def elapsed_label(ts, now=None):
    if ts is None:
        return "待获取"
    now = time.time() if now is None else float(now)
    seconds = max(0, now - float(ts))
    if seconds < 60:
        return "不足1分钟"
    if seconds < 3600:
        return f"{int(seconds // 60)}分钟"
    hours = seconds / 3600
    if hours < 100:
        return f"{hours:.1f}小时"
    return f"{int(hours)}小时"


def post_view(row, now=None, interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
    """Read-only state; a stale/failed detection cannot become a new timeout alert."""
    now = time.time() if now is None else float(now)
    if not row.get("monitor_posts"):
        return dict(state="off", label="未监控", elapsed="未监控", elapsed_short="未监控", tooltip="未选择发帖时间监控", overdue=False)
    ts = valid_post_ts(row.get("last_post_ts"), now)
    checked = float(row.get("last_post_checked_ts") or 0)
    valid = row.get("post_result") == "ok" and checked > 0 and now - checked <= max(7200, interval_seconds * 2.5)
    if ts is None:
        label = "待获取" if not checked else "无法获取"
        return dict(state="unknown", label=label, elapsed=label, elapsed_short=label,
                    tooltip=row.get("post_error") or "尚未成功读取主页贴文时间", overdue=False)
    approximate = bool(row.get("post_precision_seconds", 1) > 1)
    timestamp = datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    checked_text = datetime.fromtimestamp(checked).astimezone().strftime("%m-%d %H:%M") if checked else "未核实"
    tooltip = f"贴文时间：{'约 ' if approximate else ''}{timestamp}\n检测时间：{checked_text}"
    tooltip += "\n来源：" + str(row.get("post_source") or "历史记录")
    age = max(0, now - ts)
    limit = max(1, int(row.get("post_limit_hours") or 24)) * 3600
    if not valid:
        return dict(state="unverified", label="待核实", elapsed=elapsed_label(ts, now), elapsed_short=compact_elapsed(ts, now, approximate),
                    tooltip=tooltip + "\n本次无法确认最新贴文；仅显示缓存，不据此产生新预警。\n" +
                    str(row.get("post_error") or "检测记录已过期"), overdue=False)
    state = "overdue" if age >= limit else "soon" if age >= limit * .8 else "ok"
    label = {"overdue": "发帖超时", "soon": "即将超时", "ok": "正常"}[state]
    return dict(state=state, label=label, elapsed=("约" if approximate else "") + elapsed_label(ts, now),
                elapsed_short=compact_elapsed(ts, now, approximate),
                tooltip=tooltip + f"\n超时标准：{int(limit / 3600)} 小时\n点击菜单可打开已读取的贴文。",
                overdue=state == "overdue")


def parse_post_time(raw, now=None):
    """Parse only explicit timestamps or unambiguous relative labels. No guessing m/d dates."""
    now = time.time() if now is None else float(now)
    text = html.unescape(str(raw or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}(?:\.\d+)?", text):
        ts = valid_post_ts(text, now)
        return (ts, 1) if ts is not None else None
    try:
        # Require a year in ISO values so arbitrary integers are not parsed as dates.
        if re.match(r"^\d{4}-\d\d-\d\d(?:T| )\d\d:\d\d", text):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            ts = valid_post_ts(dt.timestamp(), now)
            return (ts, 1) if ts is not None else None
    except (ValueError, OverflowError, OSError):
        pass
    lower = text.casefold().strip(" ·")
    if lower in {"just now", "刚刚", "剛剛"}:
        return now, 60
    m = re.fullmatch(r"(\d+)\s*(秒(?:钟)?|分鐘|分钟|小時|小时|天|seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)(?:\s*ago|前)?", lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        seconds = 86400 if unit in {"天", "day", "days", "d"} else 3600 if unit in {"小时", "小時","hour","hours","hr","hrs","h"} else 60 if unit in {"分钟","分鐘","minute","minutes","min","mins","m"} else 1
        ts = valid_post_ts(now - amount * seconds, now)
        return (ts, seconds) if ts is not None else None
    local = datetime.fromtimestamp(now).astimezone()
    if lower in {"昨天", "昨日", "yesterday"}:
        # Use the end of that day (lower bound on age) rather than inventing a clock time.
        dt = (local - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        return dt.timestamp(), 86400
    text = re.sub(r"\s*(?:星期|週|周)[一二三四五六日天]\s*", " ", text)
    m = re.fullmatch(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(上午|下午)?\s*(\d{1,2}):(\d\d))?", text)
    if m:
        year, month, day = map(int, m.group(1,2,3))
        try:
            hour = int(m.group(5) or 23)
            minute = int(m.group(6) or 59)
            if m.group(4) == "下午" and hour < 12: hour += 12
            if m.group(4) == "上午" and hour == 12: hour = 0
            dt = local.replace(year=year, month=month, day=day, hour=hour, minute=minute,
                               second=0 if m.group(5) else 59, microsecond=0)
            ts = valid_post_ts(dt.timestamp(), now)
            return (ts, 60 if m.group(5) else 86400) if ts is not None else None
        except ValueError:
            return None
    cleaned = re.sub(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+", "", text, flags=re.I)
    cleaned = re.sub(r"\s+at\s+", " ", cleaned, flags=re.I).replace("\u202f", " ")
    for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p", "%d %B %Y %H:%M",
                "%Y-%m-%d %H:%M", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            precision = 86400 if "%H" not in fmt and "%I" not in fmt else 60
            if precision == 86400:
                dt = dt.replace(hour=23, minute=59, second=59)
            ts = valid_post_ts(dt.timestamp(), now)
            if ts is not None:
                return ts, precision
        except (ValueError, OverflowError, OSError):
            pass
    return None


def choose_post_candidate(candidates, now=None):
    """Select the newest eligible timestamp, not the first (possibly pinned) post."""
    now = time.time() if now is None else float(now)
    usable = []
    for item in candidates:
        if item.get("excluded") or not item.get("authored"):
            continue
        parsed = parse_post_time(item.get("raw"), now)
        if parsed is None:
            continue
        ts, precision = parsed
        usable.append(dict(ts=ts, precision=precision, url=str(item.get("url") or ""),
                           source=str(item.get("source") or "主页贴文时间"), raw=str(item.get("raw"))))
    if not usable:
        return None
    grouped={}
    unlinked=[]
    for item in usable:
        if not item["url"]:unlinked.append(item)
        else:grouped.setdefault(item["url"],[]).append(item)
    preferred=list(unlinked)
    for items in grouped.values():
        resolution=min(x["precision"] for x in items)
        preferred.append(max((x for x in items if x["precision"]==resolution),key=lambda x:x["ts"]))
    return max(preferred,key=lambda p:p["ts"]) if preferred else None

class Store:
    def __init__(self,path=None):
        self.path=Path(path or DB_PATH)
        ensure_private_directory(self.path.parent)
        self.lock=threading.RLock();self.upgrade_backup=""
        if self.path.is_file():
            probe=sqlite3.connect(str(self.path))
            try:
                # One safety copy before removing the old history table, never a per-inspection snapshot.
                if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'").fetchone():
                    folder=ensure_private_directory(self.path.parent/"backups")
                    target=folder/("before_1_9_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6]+".db")
                    backup=sqlite3.connect(str(target))
                    try:probe.backup(backup)
                    finally:backup.close()
                    self.upgrade_backup=str(target)
            finally:probe.close()
        self._init_db()

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(str(self.path), timeout=25)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=25000")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _columns(conn, table):
        # Table names cannot be parameterized in SQLite PRAGMA statements.
        # Keep this helper future-safe by accepting identifiers only.
        table = str(table)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("数据库表名格式无效")
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def _init_db(self):
        with self.lock,self._connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pages (
                    page_id TEXT PRIMARY KEY,page_name TEXT NOT NULL DEFAULT '',
                    avatar_path TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    last_followers INTEGER,previous_followers INTEGER,last_collected_at TEXT,
                    status TEXT NOT NULL DEFAULT '待采集',approx INTEGER NOT NULL DEFAULT 0,
                    custom_name TEXT NOT NULL DEFAULT '',avatar_state TEXT NOT NULL DEFAULT '待获取'
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,page_id TEXT NOT NULL,
                    alerted_at TEXT NOT NULL,alerted_ts REAL NOT NULL,
                    current_count INTEGER NOT NULL,baseline_count INTEGER,
                    growth INTEGER NOT NULL,window_seconds INTEGER NOT NULL,
                    threshold INTEGER NOT NULL,acknowledged INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT,
                    total_pages INTEGER NOT NULL,success_count INTEGER NOT NULL DEFAULT 0,
                    fail_count INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE IF NOT EXISTS removed_pages(page_id TEXT PRIMARY KEY,removed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS post_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,page_id TEXT NOT NULL,
                    alerted_at TEXT NOT NULL,alerted_ts REAL NOT NULL,last_post_ts REAL NOT NULL,
                    limit_hours INTEGER NOT NULL,message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS follower_state (
                    page_id TEXT PRIMARY KEY,latest_ts REAL NOT NULL,latest_count INTEGER NOT NULL,
                    latest_approx INTEGER NOT NULL DEFAULT 0,prior_ts REAL,prior_count INTEGER,prior_approx INTEGER,
                    baseline_date TEXT NOT NULL,baseline_ts REAL NOT NULL,baseline_count INTEGER NOT NULL,
                    baseline_approx INTEGER NOT NULL DEFAULT 0,partial INTEGER NOT NULL DEFAULT 1,
                    yesterday_date TEXT NOT NULL DEFAULT '',yesterday_delta INTEGER,
                    yesterday_partial INTEGER NOT NULL DEFAULT 1,yesterday_approx INTEGER NOT NULL DEFAULT 0
                );
            """)
            previous=self._columns(c,"pages")
            columns={"custom_name":"TEXT NOT NULL DEFAULT ''","approx":"INTEGER NOT NULL DEFAULT 0",
                "avatar_state":"TEXT NOT NULL DEFAULT '待获取'",
                "monitor_growth":"INTEGER NOT NULL DEFAULT 0","monitor_posts":"INTEGER NOT NULL DEFAULT 0",
                "post_limit_hours":"INTEGER NOT NULL DEFAULT 24","sort_order":"INTEGER NOT NULL DEFAULT 0",
                "notes":"TEXT NOT NULL DEFAULT ''","last_inspected_at":"TEXT","metadata_checked_at":"TEXT",
                "last_post_ts":"REAL","last_post_checked_ts":"REAL","post_result":"TEXT NOT NULL DEFAULT 'pending'",
                "post_error":"TEXT NOT NULL DEFAULT ''","post_url":"TEXT NOT NULL DEFAULT ''",
                "post_source":"TEXT NOT NULL DEFAULT ''","post_precision_seconds":"INTEGER NOT NULL DEFAULT 1",
                "post_alert_key":"TEXT NOT NULL DEFAULT ''","growth_error":"TEXT NOT NULL DEFAULT ''",
                "name_error":"TEXT NOT NULL DEFAULT ''"}
            for name,typ in columns.items():
                if name not in previous:c.execute(f"ALTER TABLE pages ADD COLUMN {name} {typ}")
            follower_columns=self._columns(c,"follower_state")
            for name,typ in {
                "yesterday_date":"TEXT NOT NULL DEFAULT ''",
                "yesterday_delta":"INTEGER",
                "yesterday_partial":"INTEGER NOT NULL DEFAULT 1",
                "yesterday_approx":"INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in follower_columns:c.execute(f"ALTER TABLE follower_state ADD COLUMN {name} {typ}")
            if "monitor_growth" not in previous:c.execute("UPDATE pages SET monitor_growth=enabled")
            if "sort_order" not in previous:
                for order,row in enumerate(c.execute("SELECT page_id FROM pages ORDER BY created_at,page_id").fetchall(),1):
                    c.execute("UPDATE pages SET sort_order=? WHERE page_id=?",(order,row["page_id"]))
            self._migrate_snapshot_storage(c)
            for row in c.execute("SELECT page_id,page_name,custom_name FROM pages").fetchall():
                if not normalize_name(row["page_name"],row["page_id"]):
                    c.execute("UPDATE pages SET page_name='' WHERE page_id=?",(row["page_id"],))
                custom=row["custom_name"] or ""
                if re.fullmatch(r"(?:主页|公共主页|专页|Page)\s*[:：]?\s*[\d\W]+",custom,re.I):
                    c.execute("UPDATE pages SET custom_name='' WHERE page_id=?",(row["page_id"],))
            c.execute("CREATE INDEX IF NOT EXISTS idx_alert_page_ts ON alerts(page_id,alerted_ts)")
            c.execute("INSERT OR REPLACE INTO app_meta VALUES('schema','2.0')")


    def add_pages(self,ids,monitor_growth=True,monitor_posts=True,limit_hours=24):
        return self.import_ids(ids,"add",monitor_growth,monitor_posts,limit_hours)["added"]

    def replace_pages(self,ids):
        result=self.import_ids(ids,"replace",True,True,24)
        return result["total"]

    def list_pages(self, enabled_only=False):
        with self.lock,self._connect() as c:
            query="SELECT * FROM pages"
            if enabled_only: query+=" WHERE monitor_growth=1 OR monitor_posts=1"
            return [dict(r) for r in c.execute(query+" ORDER BY sort_order,page_id")]

    def page(self,pid):
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM pages WHERE page_id=?",(str(pid),)).fetchone()
            return dict(row) if row else None

    def rename_page(self,pid,name):
        name=str(name).strip()[:160]
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET custom_name=?,updated_at=? WHERE page_id=?",(name,now_iso(),str(pid)))

    def set_enabled(self,pid,enabled):
        # Compatibility API: pausing all modules / explicitly enabling both.
        self.update_config([pid],monitor_growth=bool(enabled),monitor_posts=bool(enabled))

    def delete_page(self,pid,delete_history=False):
        self.delete_ids([pid],delete_history)

    def update_status(self, pid: str, status: str):
        with self.lock, self._connect() as c:
            c.execute("UPDATE pages SET status=?,updated_at=? WHERE page_id=?", (str(status)[:180],now_iso(),pid))

    def update_metadata(self,pid,name="",avatar_path="",name_error=""):
        name=normalize_name(name,pid)
        avatar=str(avatar_path or "")
        if not avatar or not Path(avatar).is_file(): avatar=""
        with self.lock,self._connect() as c:
            if not c.execute("SELECT 1 FROM pages WHERE page_id=?",(str(pid),)).fetchone(): return False
            c.execute("""UPDATE pages SET
                page_name=CASE WHEN ?<>'' THEN ? ELSE page_name END,
                avatar_path=CASE WHEN ?<>'' THEN ? ELSE avatar_path END,
                avatar_state=CASE WHEN ?<>'' THEN '已获取' ELSE avatar_state END,
                metadata_checked_at=?,name_error=?,updated_at=? WHERE page_id=?""",
                (name,name,avatar,avatar,avatar,now_iso(),str(name_error)[:220] if not name else "",now_iso(),str(pid)))
        return bool(avatar or name)

    def mark_avatar_failed(self,pid:str,error:str):
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET avatar_state=?,updated_at=? WHERE page_id=?",
                      ("未识别头像："+str(error or '页面未提供可识别头像')[:120],now_iso(),pid))





    def dashboard_rows(self,window_seconds=None,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=time.time()
        with self.lock,self._connect() as c:
            states={r["page_id"]:dict(r) for r in c.execute("SELECT * FROM follower_state")}
        rows=self.list_pages()
        for row in rows:
            st=states.get(row["page_id"]);has=bool(st)
            delta=st["latest_count"]-st["prior_count"] if st and st["prior_count"] is not None else None
            reliable=bool(st and not st["latest_approx"] and not st["prior_approx"] and delta is not None)
            row.update(delta=delta,reliable=reliable,has_data=has,
                stale=not st or now-st["latest_ts"]>max(7200,2.5*interval_seconds))
        return rows

    def start_run(self, run_id, total):
        with self.lock, self._connect() as c:
            c.execute("INSERT INTO runs(run_id,started_at,total_pages) VALUES(?,?,?)", (run_id,now_iso(),int(total)))

    def finish_run(self, run_id, success, fail, status):
        with self.lock, self._connect() as c:
            c.execute("UPDATE runs SET finished_at=?,success_count=?,fail_count=?,status=? WHERE run_id=?",
                      (now_iso(),int(success),int(fail),status,run_id))

    def last_run(self):
        with self.lock, self._connect() as c:
            return c.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()

    def has_recent_alert(self, pid: str, seconds: int) -> bool:
        with self.lock, self._connect() as c:
            return bool(c.execute("SELECT 1 FROM alerts WHERE page_id=? AND alerted_ts>=? LIMIT 1", (pid,time.time()-seconds)).fetchone())

    def add_alert(self, pid: str, current: int, baseline: int, growth: int, window_seconds: int, threshold: int):
        with self.lock, self._connect() as c:
            cur=c.execute("""
                INSERT INTO alerts(page_id,alerted_at,alerted_ts,current_count,baseline_count,growth,
                                   window_seconds,threshold,acknowledged)
                VALUES(?,?,?,?,?,?,?,?,0)
            """, (pid,now_iso(),time.time(),current,baseline,growth,window_seconds,threshold))
            return int(cur.lastrowid)

    def checkpoint(self):
        """Flush SQLite WAL before migrating the live data directory."""
        with self.lock:
            con = sqlite3.connect(str(self.path), timeout=25)
            try:
                con.execute("PRAGMA wal_checkpoint(FULL)")
            finally:
                con.close()

    def unack_alert_count(self):
        with self.lock, self._connect() as c:
            return c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0]

    def alert_rows(self,limit=500):
        with self.lock,self._connect() as c:
            return [dict(r) for r in c.execute("""
                SELECT a.*,COALESCE(p.avatar_path,'') avatar_path,COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM alerts a LEFT JOIN pages p ON a.page_id=p.page_id ORDER BY a.id DESC LIMIT ?
            """,(int(limit),))]

    def acknowledge_all(self):
        with self.lock, self._connect() as c:
            c.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")


    def export_csv(self,path,kind="current"):
        if kind=="current":return self.export_manager_csv(path)
        if kind!="alerts":raise ValueError("历史快照功能已移除；只支持当前状态或通知导出")
        with open(path,"w",encoding="utf-8-sig",newline="") as f:
            writer=csv.writer(f);writer.writerow(["时间","专业ID","名称","类型","提醒","已读"])
            for row in self.combined_alerts(limit=10000):
                writer.writerow([safe_csv_cell(row.get(k,"")) for k in
                                 ("alerted_at","page_id","page_name","kind","message","acknowledged")])

    def backup(self,destination):
        destination=Path(destination)
        if destination.resolve()==self.path.resolve():raise ValueError("备份路径不能和当前数据库相同")
        with self.lock,self._connect() as source:
            target=sqlite3.connect(str(destination))
            try:source.backup(target)
            finally:target.close()

    def import_ids(self,ids,mode="add",monitor_growth=True,monitor_posts=True,limit_hours=24):
        if mode not in ("add","replace"):raise ValueError("导入方式无效")
        cleaned=list(dict.fromkeys(str(x).strip() for x in ids))
        if not cleaned or any(not re.fullmatch(r"[0-9]{5,25}",pid) for pid in cleaned):
            raise ValueError("请输入至少一个有效的 5 至 25 位数字主页 ID")
        hours=int(limit_hours)
        if not 1<=hours<=8760:raise ValueError("发帖标准须为 1 至 8760 小时")
        with self.lock,self._connect() as c:
            before={r[0] for r in c.execute("SELECT page_id FROM pages")}
            new=[pid for pid in cleaned if pid not in before]
            order=int(c.execute("SELECT COALESCE(MAX(sort_order),0) FROM pages").fetchone()[0])
            for offset,pid in enumerate(new,1):
                cache=AVATAR_DIR/f"{pid}.png"
                avatar=str(cache) if cache.is_file() else ""
                c.execute("""INSERT INTO pages(page_id,page_name,avatar_path,avatar_state,created_at,updated_at,
                           enabled,monitor_growth,monitor_posts,post_limit_hours,sort_order)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid,"",avatar,"已获取" if avatar else "待获取",now_iso(),now_iso(),
                     int(bool(monitor_growth or monitor_posts)),int(bool(monitor_growth)),int(bool(monitor_posts)),hours,order+offset))
                c.execute("DELETE FROM removed_pages WHERE page_id=?",(pid,))
            removed=before-set(cleaned) if mode=="replace" else set()
            for pid in removed:
                c.execute("DELETE FROM pages WHERE page_id=?",(pid,))
                c.execute("DELETE FROM follower_state WHERE page_id=?",(pid,))
                c.execute("INSERT OR REPLACE INTO removed_pages VALUES(?,?)",(pid,now_iso()))
            total=c.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        return {"added":len(new),"skipped":len(cleaned)-len(new),"removed":len(removed),"total":total}


    def update_config(self,ids,**fields):
        allowed={"monitor_growth","monitor_posts","post_limit_hours","sort_order","notes","custom_name"}
        if not fields or set(fields)-allowed: raise ValueError("配置字段无效")
        prepared={}
        for key,value in fields.items():
            if key in ("monitor_growth","monitor_posts"): prepared[key]=int(bool(value))
            elif key=="post_limit_hours":
                prepared[key]=int(value)
                if not 1<=prepared[key]<=8760: raise ValueError("发帖超时标准须为 1–8760 小时")
            elif key=="sort_order":
                prepared[key]=int(value)
                if not 0<=prepared[key]<=999999: raise ValueError("排序号须为 0–999999")
            else: prepared[key]=str(value).strip()[:160 if key=="custom_name" else 500]
        with self.lock,self._connect() as c:
            for pid in dict.fromkeys(str(x) for x in ids):
                row=c.execute("SELECT * FROM pages WHERE page_id=?",(pid,)).fetchone()
                if not row: continue
                reset_post=any(k in prepared and prepared[k]!=row[k] for k in ("monitor_posts","post_limit_hours"))
                values=dict(prepared)
                values["enabled"]=int(bool(values.get("monitor_growth",row["monitor_growth"]) or values.get("monitor_posts",row["monitor_posts"])))
                values["updated_at"]=now_iso()
                if reset_post: values["post_alert_key"]=""
                c.execute("UPDATE pages SET "+",".join(k+"=?" for k in values)+" WHERE page_id=?",(*values.values(),pid))


    def delete_ids(self,ids,delete_history=False):
        unique=list(dict.fromkeys(str(x) for x in ids))
        removed=0
        with self.lock,self._connect() as c:
            for pid in unique:
                removed+=c.execute("DELETE FROM pages WHERE page_id=?",(pid,)).rowcount
                c.execute("DELETE FROM follower_state WHERE page_id=?",(pid,))
                c.execute("INSERT OR REPLACE INTO removed_pages VALUES(?,?)",(pid,now_iso()))
        return removed


    def migrate_legacy_settings(self, rules=None, data=None):
        """One-time copy of old QSettings post rules/cache. Existing missing groups stay opt-in."""
        rules=rules if isinstance(rules,list) else []
        data=data if isinstance(data,dict) else {}
        with self.lock,self._connect() as c:
            if c.execute("SELECT 1 FROM app_meta WHERE key='legacy_posts_copied'").fetchone(): return
            limits={}
            for rule in rules:
                if not isinstance(rule,dict): continue
                try: hours=max(1,min(8760,int(rule.get("hours",24))))
                except (TypeError,ValueError): hours=24
                for pid in rule.get("page_ids",[]) or []:
                    pid=str(pid);limits[pid]=min(hours,limits.get(pid,hours))
            for pid,hours in limits.items():
                c.execute("UPDATE pages SET monitor_posts=1,enabled=1,post_limit_hours=? WHERE page_id=?",(hours,pid))
            for pid,info in data.items():
                if not isinstance(info,dict): continue
                ts=valid_post_ts(info.get("last_post_ts"))
                if ts is None: continue
                try: checked=float(info.get("checked_at") or 0)
                except (ValueError,TypeError): checked=0
                c.execute("""UPDATE pages SET last_post_ts=?,last_post_checked_ts=?,post_result='legacy',
                    post_source='旧版缓存',post_error='旧记录尚未复核，请执行一次巡检' WHERE page_id=?""",
                    (ts,checked,str(pid)))
            c.execute("INSERT INTO app_meta VALUES('legacy_posts_copied',?)",(now_iso(),))
            c.execute("INSERT OR REPLACE INTO app_meta VALUES('legacy_rules_backup',?)",
                      (json.dumps(rules,ensure_ascii=False),))


    def today_change(self,pid,now=None,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=time.time() if now is None else float(now)
        local=datetime.fromtimestamp(now).astimezone()
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        if not row or row["baseline_date"]!=local.date().isoformat():
            return {"delta":None,"partial":True,"note":"今天尚无成功采集记录"}
        if row["latest_ts"]>now+1 or row["latest_ts"]<=row["baseline_ts"]:
            return {"delta":None,"partial":True,"note":"今天首次检测已建立基准；再次巡检后显示新增"}
        partial=bool(row["partial"]);approx=bool(row["latest_approx"] or row["baseline_approx"])
        note=("自今日首次检测起" if partial else "以零点附近读数为基准")
        note+="（"+datetime.fromtimestamp(row["baseline_ts"]).astimezone().strftime("%H:%M")+"）"
        if approx:note+="；来源为缩写约值"
        return {"delta":row["latest_count"]-row["baseline_count"],"partial":partial,"approx":approx,"note":note}


    def yesterday_change(self,pid,now=None):
        """Return only yesterday's rolled-up delta; no historical time series is stored."""
        now=time.time() if now is None else float(now)
        yesterday=(datetime.fromtimestamp(now).astimezone().date()-timedelta(days=1)).isoformat()
        with self.lock,self._connect() as c:
            row=c.execute("SELECT yesterday_date,yesterday_delta,yesterday_partial,yesterday_approx FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        if not row or row["yesterday_date"]!=yesterday or row["yesterday_delta"] is None:
            return {"delta":None,"partial":True,"approx":False,"note":"需要跨日的成功巡检记录后显示"}
        note="昨天从首次有效基准起计算" if row["yesterday_partial"] else "昨天完整基准"
        if row["yesterday_approx"]:note+="；来源为缩写约值"
        return {"delta":int(row["yesterday_delta"]),"partial":bool(row["yesterday_partial"]),
                "approx":bool(row["yesterday_approx"]),"note":note}


    def record_posts(self,pid,result,now=None):
        """Persist success/failure separately; only fresh, confirmed results can alert."""
        now=time.time() if now is None else float(now)
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM pages WHERE page_id=?",(pid,)).fetchone()
            if not row or not row["monitor_posts"]: return None
            ts=valid_post_ts(result.get("last_post_ts"),now) if result.get("posts_ok") else None
            error=str(result.get("posts_error") or "未读取到可确认的主页贴文时间")[:300]
            if ts is not None and row["last_post_ts"] and ts < float(row["last_post_ts"])-120:
                ts=None;error="本次可见贴文早于历史最新记录，无法确认最新贴文"
            if ts is None:
                c.execute("""UPDATE pages SET last_post_checked_ts=?,post_result='failed',
                    post_error=?,last_inspected_at=?,updated_at=? WHERE page_id=?""",(now,error,now_iso(),now_iso(),pid))
                return None
            limit=int(row["post_limit_hours"] or 24)
            precision=max(1,int(result.get("post_precision_seconds") or 1))
            age=max(0,now-ts)
            overdue=age>=limit*3600
            # Relative timestamps can drift within one display unit, so treat them as the same episode
            # until a substantially newer post or a normal result is observed.
            previous_ts=float(row["last_post_ts"] or 0)
            same_episode=bool(row["post_alert_key"] and row["last_post_ts"] and
                abs(ts-previous_ts)<=max(precision,int(row["post_precision_seconds"] or 1),120))
            key=row["post_alert_key"] if overdue and same_episode else ""
            new_alert=None
            if overdue and not key:
                key=f"{int(ts)}:{limit}:{uuid.uuid4().hex[:8]}"
                message=f"距最近可确认贴文 {elapsed_label(ts,now)}，超过 {limit} 小时标准"
                cur=c.execute("""INSERT INTO post_alerts(page_id,alerted_at,alerted_ts,last_post_ts,limit_hours,message)
                    VALUES(?,?,?,?,?,?)""",(pid,datetime.fromtimestamp(now,timezone.utc).isoformat(),now,ts,limit,message))
                new_alert={"id":cur.lastrowid,"page_id":pid,"name":display_name(dict(row)),"avatar_path":row["avatar_path"] or "","message":message,"kind":"post"}
            c.execute("""UPDATE pages SET last_post_ts=?,last_post_checked_ts=?,post_result='ok',post_error='',
                post_source=?,post_url=?,post_precision_seconds=?,post_alert_key=?,last_inspected_at=?,updated_at=?
                WHERE page_id=?""",(ts,now,str(result.get("post_source") or "主页可见贴文")[:180],
                str(result.get("post_url") or "")[:1000],precision,key,now_iso(),now_iso(),pid))
            return new_alert


    def apply_collection(self,result,settings=None,purpose="monitor"):
        """Independent persistence of metadata, followers, and posting results."""
        opts=settings or {}
        pid=str(result.get("page_id") or "")
        row=self.page(pid)
        if row is None: return {"ignored":True,"success":False,"alerts":[]}
        name=normalize_name(result.get("page_name"),pid)
        self.update_metadata(pid,name,result.get("avatar_path") or "",result.get("name_error") or "")
        if purpose=="metadata":
            return {"ignored":False,"success":bool(name or result.get("avatar_fresh")),
                    "alerts":[],"error":result.get("name_error") or result.get("error") or ""}
        notices=[];successes=[];errors=[]
        if row["monitor_growth"]:
            ok=bool(result.get("growth_ok") and result.get("followers_count") is not None)
            if ok:
                try:
                    previous=self.record_followers(result,int(opts.get("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60)
                    value=int(result["followers_count"])
                    interval=int(opts.get("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60
                    threshold=int(opts.get("alert_threshold",500))
                    ts=float(result.get("collected_ts") or time.time())
                    if is_true(opts.get("alert_enabled"),True) and should_alert(value,previous,ts,bool(result.get("approx")),interval,threshold):
                        if not self.has_recent_alert(pid,int(opts.get("alert_cooldown_minutes",30))*60):
                            diff=value-previous["count"]
                            alert_id=self.add_alert(pid,value,previous["count"],diff,interval,threshold)
                            notices.append({"id":alert_id,"kind":"growth","page_id":pid,"name":name or display_name(row),
                                            "avatar_path":result.get("avatar_path") or row.get("avatar_path") or "",
                                            "message":f"本轮粉丝增加 {format_delta(diff)}"})
                except Exception as exc:
                    ok=False;errors.append(str(exc)[:220])
            else:
                errors.append(str(result.get("growth_error") or result.get("error") or "粉丝数无法读取"))
            with self.lock,self._connect() as c:
                c.execute("UPDATE pages SET growth_error=? WHERE page_id=?",
                          ("" if ok else errors[-1],pid))
            successes.append(ok)
        if row["monitor_posts"]:
            post_alert=self.record_posts(pid,result)
            if post_alert: notices.append(post_alert)
            posts_row=self.page(pid)
            ok=bool(result.get("posts_ok") and posts_row and posts_row["post_result"]=="ok")
            successes.append(ok)
            if not ok: errors.append(str(posts_row.get("post_error") if posts_row else "主页已删除"))
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET last_inspected_at=?,status=?,updated_at=? WHERE page_id=?",
                      (now_iso(),"正常" if successes and all(successes) else "部分成功" if any(successes) else "采集失败",now_iso(),pid))
        return {"ignored":False,"success":bool(successes and all(successes)),"alerts":notices,"error":"；".join(errors)}


    def combined_alerts(self,limit=100,unread_only=False):
        suffix=" AND a.acknowledged=0" if unread_only else ""
        with self.lock,self._connect() as c:
            growth=[dict(r) for r in c.execute("""
                SELECT a.id,a.page_id,a.alerted_at,a.alerted_ts,a.acknowledged,a.growth,COALESCE(p.avatar_path,'') avatar_path,
                COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM alerts a LEFT JOIN pages p ON a.page_id=p.page_id WHERE 1=1
            """+suffix+" ORDER BY a.alerted_ts DESC LIMIT ?",(limit,))]
            posts=[dict(r) for r in c.execute("""
                SELECT a.*,COALESCE(p.avatar_path,'') avatar_path,COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM post_alerts a LEFT JOIN pages p ON a.page_id=p.page_id WHERE 1=1
            """+suffix+" ORDER BY a.alerted_ts DESC LIMIT ?",(limit,))]
        for r in growth+posts:
            if not r.get("avatar_path"):
                cached=AVATAR_DIR/(str(r["page_id"])+".png")
                if cached.is_file():r["avatar_path"]=str(cached)
        for r in growth:r.update(kind="growth",message="粉丝增长 "+format_delta(r["growth"]))
        for r in posts:r["kind"]="post"
        return sorted(growth+posts,key=lambda x:x["alerted_ts"],reverse=True)[:limit]


    def unread_totals(self):
        with self.lock,self._connect() as c:
            g=c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0]
            p=c.execute("SELECT COUNT(*) FROM post_alerts WHERE acknowledged=0").fetchone()[0]
            return int(g),int(p)


    def acknowledge_notifications(self):
        with self.lock,self._connect() as c:
            c.execute("UPDATE alerts SET acknowledged=1")
            c.execute("UPDATE post_alerts SET acknowledged=1")

    def acknowledge_notification(self,kind,alert_id):
        table="post_alerts" if str(kind)=="post" else "alerts" if str(kind)=="growth" else ""
        try:alert_id=int(alert_id)
        except (TypeError,ValueError):return False
        if not table or alert_id<=0:return False
        with self.lock,self._connect() as c:
            return bool(c.execute(f"UPDATE {table} SET acknowledged=1 WHERE id=? AND acknowledged=0",(alert_id,)).rowcount)


    def export_manager_csv(self,path):
        cols=["page_id","page_name","custom_name","monitor_growth","monitor_posts","post_limit_hours",
              "sort_order","notes","last_followers","last_post_ts","post_result","last_inspected_at"]
        with open(path,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f)
            w.writerow(["专业ID","真实名称","自定义名称","粉丝监控","发帖监控","发帖超时小时","排序号",
                        "备注","当前粉丝","最近贴文时间戳","发帖读取状态","最后巡检"])
            for row in self.list_pages():
                w.writerow([safe_csv_cell(row.get(col,"")) for col in cols])


    def _migrate_snapshot_storage(self,c):
        """Collapse old samples into ONE bounded state row per managed page, then remove history."""
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'").fetchone():return
        cols=self._columns(c,"snapshots")
        for name,typ in {"collected_ts":"REAL","is_approx":"INTEGER NOT NULL DEFAULT 0",
                         "fan_count":"INTEGER","followers_count":"INTEGER"}.items():
            if name not in cols:c.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {typ}")
        for row in c.execute("SELECT id,collected_at FROM snapshots WHERE collected_ts IS NULL").fetchall():
            try:ts=datetime.fromisoformat(row["collected_at"].replace("Z","+00:00")).timestamp()
            except (ValueError,TypeError,AttributeError):continue
            c.execute("UPDATE snapshots SET collected_ts=? WHERE id=?",(ts,row["id"]))
        for page in c.execute("SELECT page_id FROM pages").fetchall():
            pid=page["page_id"]
            recent=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                FROM snapshots WHERE page_id=? AND collected_ts>0 AND collected_ts<=?
                AND COALESCE(followers_count,fan_count) IS NOT NULL
                ORDER BY collected_ts DESC,id DESC LIMIT 2""",(pid,time.time()+60)).fetchall()
            if not recent:continue
            latest=recent[0];prior=recent[1] if len(recent)>1 else None
            local=datetime.fromtimestamp(latest["ts"]).astimezone()
            midnight=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            base=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                FROM snapshots WHERE page_id=? AND collected_ts<=? AND COALESCE(followers_count,fan_count) IS NOT NULL
                ORDER BY collected_ts DESC,id DESC LIMIT 1""",(pid,midnight)).fetchone()
            partial=not base or midnight-base["ts"]>4500
            if partial:
                base=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                    FROM snapshots WHERE page_id=? AND collected_ts>=? AND collected_ts<=?
                    AND COALESCE(followers_count,fan_count) IS NOT NULL ORDER BY collected_ts,id LIMIT 1""",
                    (pid,midnight,latest["ts"])).fetchone()
            base=base or latest
            c.execute("""INSERT OR REPLACE INTO follower_state(
                page_id,latest_ts,latest_count,latest_approx,prior_ts,prior_count,prior_approx,
                baseline_date,baseline_ts,baseline_count,baseline_approx,partial)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,latest["ts"],latest["count"],latest["approx"],prior["ts"] if prior else None,
                 prior["count"] if prior else None,prior["approx"] if prior else None,
                 local.date().isoformat(),base["ts"],base["count"],base["approx"],int(partial)))
            c.execute("UPDATE pages SET last_followers=?,previous_followers=?,last_collected_at=?,approx=? WHERE page_id=?",
                (latest["count"],prior["count"] if prior else None,
                 datetime.fromtimestamp(latest["ts"],timezone.utc).isoformat(),latest["approx"],pid))
        c.execute("DROP TABLE snapshots")
        c.execute("INSERT OR REPLACE INTO app_meta VALUES('history_removed','1')")


    def record_followers(self,result,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        """Keep only the current reading, previous reading and today's baseline; no history series."""
        pid=str(result["page_id"]);count=int(result["followers_count"])
        ts=float(result.get("collected_ts") or time.time())
        if not 0<=count<=10_000_000_000 or not math.isfinite(ts) or ts<=0 or ts>time.time()+120:
            raise ValueError("粉丝数或采集时间无效")
        approx=int(bool(result.get("approx")));local=datetime.fromtimestamp(ts).astimezone()
        day=local.date().isoformat();midnight=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        stamp=datetime.fromtimestamp(ts,timezone.utc).isoformat(timespec="seconds")
        with self.lock,self._connect() as c:
            if not c.execute("SELECT 1 FROM pages WHERE page_id=?",(pid,)).fetchone():return None
            old=c.execute("SELECT * FROM follower_state WHERE page_id=?",(pid,)).fetchone()
            if old and ts<=old["latest_ts"]:return None
            prior={"ts":old["latest_ts"],"count":old["latest_count"],"approx":bool(old["latest_approx"])} if old else None
            yesterday=(local.date()-timedelta(days=1)).isoformat()
            y_date='';y_delta=None;y_partial=1;y_approx=0
            if old:
                if old["baseline_date"]==day:
                    y_date=str(old["yesterday_date"] or '')
                    y_delta=old["yesterday_delta"]
                    y_partial=int(old["yesterday_partial"] or 0)
                    y_approx=int(old["yesterday_approx"] or 0)
                elif old["baseline_date"]==yesterday:
                    y_date=yesterday
                    y_delta=int(old["latest_count"])-int(old["baseline_count"])
                    y_partial=int(old["partial"] or 0)
                    y_approx=int(bool(old["latest_approx"] or old["baseline_approx"]))
                elif str(old["yesterday_date"] or '')==yesterday:
                    y_date=yesterday;y_delta=old["yesterday_delta"]
                    y_partial=int(old["yesterday_partial"] or 0);y_approx=int(old["yesterday_approx"] or 0)
            if old and old["baseline_date"]==day and old["latest_ts"]>=midnight:
                base_ts,base,base_approx,partial=(old["baseline_ts"],old["baseline_count"],old["baseline_approx"],old["partial"])
            elif old and 0<=midnight-old["latest_ts"]<=max(3600,2.5*interval_seconds):
                base_ts,base,base_approx,partial=old["latest_ts"],old["latest_count"],old["latest_approx"],0
            else:
                base_ts,base,base_approx,partial=ts,count,approx,1
            c.execute("""INSERT OR REPLACE INTO follower_state(
                page_id,latest_ts,latest_count,latest_approx,prior_ts,prior_count,prior_approx,
                baseline_date,baseline_ts,baseline_count,baseline_approx,partial,
                yesterday_date,yesterday_delta,yesterday_partial,yesterday_approx)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,ts,count,approx,prior["ts"] if prior else None,prior["count"] if prior else None,
                 int(prior["approx"]) if prior else None,day,base_ts,base,base_approx,partial,
                 y_date,y_delta,y_partial,y_approx))
            name=normalize_name(result.get("page_name"),pid)
            c.execute("""UPDATE pages SET last_followers=?,previous_followers=?,last_collected_at=?,approx=?,
                page_name=CASE WHEN ?<>'' THEN ? ELSE page_name END,status='正常',updated_at=? WHERE page_id=?""",
                (count,prior["count"] if prior else None,stamp,approx,name,name,now_iso(),pid))
        return prior


# ========== Browser collector (self-contained) ==========
import io


def prepare_data_migration(store,target):
    """Copy and verify before switching paths. Never deletes the source."""
    old=store.path.parent.resolve();target=Path(target).expanduser().resolve()
    if target==old or target in old.parents or old in target.parents:
        raise ValueError("新目录必须与原目录独立，不能互为上级或子目录")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("目标目录必须为空，以免覆盖其他文件")
    ensure_private_directory(target)
    skips={store.path.name,store.path.name+"-wal",store.path.name+"-shm",
           "SingletonLock","SingletonCookie","SingletonSocket","DevToolsActivePort","lockfile"}
    manifest=[]
    with store.lock:
        store.checkpoint()
        for source in old.rglob("*"):
            if source.name in skips:continue
            if source.is_symlink():raise ValueError("源目录含未知符号链接，请检查后再迁移："+str(source))
            relative=source.relative_to(old);dest=target/relative
            if source.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            if source.is_file():
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,dest)
                def digest(path):
                    h=hashlib.sha256()
                    with path.open("rb") as f:
                        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
                    return h.digest()
                if source.stat().st_size!=dest.stat().st_size or digest(source)!=digest(dest):
                    raise RuntimeError("复制校验失败："+str(relative))
                manifest.append(str(relative))
        new_db=target/store.path.name
        store.backup(new_db)
        c=sqlite3.connect(str(new_db))
        try:
            check=c.execute("PRAGMA quick_check").fetchone()
            if not check or check[0]!="ok":raise RuntimeError("目标数据库完整性检查失败")
            for pid,avatar in c.execute("SELECT page_id,avatar_path FROM pages").fetchall():
                if not avatar:continue
                try:relative=Path(avatar).resolve().relative_to(old)
                except ValueError:continue
                c.execute("UPDATE pages SET avatar_path=? WHERE page_id=?",(str(target/relative),pid))
            c.commit()
        finally:c.close()
    pending=target/"updates/pending.json"
    if pending.is_file():
        try:
            info=json.loads(pending.read_text("utf-8"))
            if info.get("path"):
                relative=Path(info["path"]).resolve().relative_to(old)
                info["path"]=str(target/relative);save_json_atomic(pending,info)
        except (ValueError,TypeError,OSError):pass
    # Refuse automatic recursive deletion if an old directory contains unrelated top-level files.
    known={"avatars","browser_profile","monitor_accounts","public_avatar_profile","backups","error.log",
           "settings.ini","connector_registry.json","updates","location.json",".fbpm-owned","fb_growth_radar_v1.db","fb_growth_radar_v1.db-wal","fb_growth_radar_v1.db-shm"}
    unrelated=[p.name for p in old.iterdir() if p.name not in known]
    return {"old":old,"target":target,"database":new_db,"can_delete":not unrelated,"unrelated":unrelated,"files":len(manifest)}


def log_exception(text):
    try:
        ensure_private_directory(DATA_DIR)
        with (DATA_DIR/"error.log").open("a",encoding="utf-8") as f:
            f.write("\n"+now_iso()+"\n"+str(text)+"\n")
    except OSError:pass


class BrowserCollector:
    def __init__(self, profile_dir: Path | None = None, show_browser=DEFAULT_SHOW_BROWSER):
        self.profile_dir = str(ensure_private_directory(Path(profile_dir) if profile_dir is not None else monitor_profile_dir()))
        self.show_browser = is_true(show_browser, DEFAULT_SHOW_BROWSER)
        self._pw = None
        self.context = None
        self.channel = None
        self.home_page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("未安装浏览器控制依赖。请运行：python -m pip install playwright") from exc
        self._pw = sync_playwright().start()
        try:
            # Explicitly use installed Chrome. Do not silently switch to Chromium/Edge.
            self.context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                chromium_sandbox=True,
                headless=not self.show_browser,
                viewport={"width": 1440, "height": 960},
                locale="zh-CN",
                args=["--disable-notifications", "--no-first-run", "--no-default-browser-check"],
            )
            self.channel = "chrome"
            self.ensure_home()
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            detail = str(exc).strip().splitlines()[0][:260]
            raise RuntimeError(
                "已尝试启动本机谷歌浏览器，但无法正常打开脸书主页。\n"
                "请检查：谷歌浏览器是否安装、网络是否能访问 facebook.com、"
                "以及默认专用浏览器是否仍被其他窗口占用。\n"
                + ("后台模式启动失败，程序没有改为弹出前台浏览器。\n" if not self.show_browser else "")
                + f"具体原因：{detail}"
            ) from exc

    def __exit__(self, typ, exc, tb):
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        self.context = None
        self.home_page = None
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    def ensure_home(self):
        """Replace Playwright's initial about:blank with the real Facebook page."""
        if not self.context:
            raise RuntimeError("谷歌浏览器尚未启动")
        page = next((p for p in self.context.pages if not p.is_closed()), None)
        if page is None:
            page = self.context.new_page()
        for p in list(self.context.pages):
            if p is not page and not p.is_closed() and p.url == 'about:blank':
                try:
                    p.close()
                except Exception:
                    pass
        self.home_page = page
        try:
            page.goto(FACEBOOK_HOME, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception as exc:
            if not (page.url or '').startswith(('https://www.facebook.com/', 'https://facebook.com/')):
                raise RuntimeError(
                    "无法进入 facebook.com，浏览器仍停在空白页。请检查网络、代理或账号环境。"
                ) from exc
        if (page.url or '').startswith('about:blank'):
            raise RuntimeError("浏览器仍停在 about:blank，没有成功打开 Facebook。")
        if self.show_browser:
            page.bring_to_front()
        return page

    def login_interactive(self):
        """Only an explicit login action may request a visible browser."""
        if not self.show_browser:
            raise RuntimeError("后台巡检不会弹出登录窗口；请从设置打开默认专用浏览器登录。")
        if self.home_page is None or self.home_page.is_closed():
            self.ensure_home()
        self.home_page.bring_to_front()
        return self.home_page

    @staticmethod
    def _is_facebook_image_url(url: str) -> bool:
        try:
            u = urlsplit(url)
            host = (u.hostname or "").lower()
            return u.scheme == "https" and (
                host in ("facebook.com", "fbcdn.net", "fbsbx.com")
                or host.endswith(".facebook.com")
                or host.endswith(".fbcdn.net")
                or host.endswith(".fbsbx.com")
            )
        except ValueError:
            return False


    def _extract_name(self,page,body_text="",page_id="",matched_text=""):
        return normalize_name(extract_page_name(page,body_text,page_id,matched_text),page_id)

    def _avatar_candidates(self,page,name:str) -> list[dict]:
        """Discover avatar images from current FB layouts, not just alt text.

        Inspect visible HTML images, SVG image nodes and CSS background images;
        rank profile-like square images near the page title above global nav icons
        and fall back to Open Graph metadata only after visible candidates.
        """
        script=r"""(pageName) => {
          const title=document.querySelector('h1');
          const titleRect=title ? title.getBoundingClientRect() : null;
          const pageTitle=(pageName||'').trim().toLowerCase();
          const hits=[];
          const words=/profile picture|profile photo|avatar|picture of|page picture|page profile|头像|大头贴|大頭貼|头像照片|照片墙|主页照片/i;
          const cover=/cover photo|cover image|封面|封面照片|相册|帖子图片/i;
          function push(el,sel,i) {
            let r;try{r=el.getBoundingClientRect()}catch{return;}
            if(r.width<30||r.height<30||r.top>1800||r.bottom<0)return;
            const ratio=Math.max(r.width,r.height)/Math.max(1,Math.min(r.width,r.height));
            if(ratio>2.2)return;
            const tag=el.tagName.toLowerCase();
            const alt=String(el.getAttribute('alt')||el.getAttribute('aria-label')||'');
            let src=el.currentSrc||el.getAttribute('src')||el.getAttribute('href')||el.getAttribute('xlink:href')||'';
            if(!src) {
              const bg=getComputedStyle(el).backgroundImage||'';
              const m=bg.match(/url\(["']?(.*?)["']?\)/);
              if(m)src=m[1];
            }
            let score=0;
            if(words.test(alt))score+=145;
            if(cover.test(alt))score-=95;
            if(pageTitle&&alt.toLowerCase().includes(pageTitle))score+=42;
            if(ratio<=1.22)score+=35;
            if(r.width>=45&&r.width<=350&&r.height>=45&&r.height<=350)score+=25;
            if(r.top>=0&&r.top<730)score+=20;
            if(titleRect){
              let dist=Math.abs((r.top+r.height/2)-(titleRect.top+titleRect.height/2));
              if(dist<160)score+=45;
              else if(dist<310)score+=21;
            }
            const ancestor=el.closest('a[href]');
            if(ancestor&&/\/profile\.php|\/pages\/|facebook\.com\//i.test(ancestor.href||''))score+=15;
            if(el.closest('nav,[role=navigation],[role=banner],[data-pagelet=RightRail]'))score-=120;
            if(el.closest('article'))score-=85;
            if(r.width<48||r.height<48)score-=55;
            if(src.startsWith('data:image/'))score+=5;
            if(score>=25)hits.push({url:src,selector:sel,index:i,score,alt,width:r.width,height:r.height});
          }
          [...document.querySelectorAll('img')].forEach((el,i)=>push(el,'img',i));
          [...document.querySelectorAll('svg image')].forEach((el,i)=>push(el,'svg image',i));
          [...document.querySelectorAll('[role="img"]')].forEach((el,i)=>push(el,'[role="img"]',i));
          return hits.sort((a,b)=>b.score-a.score).slice(0,24);
        }"""
        try:
            candidates=list(page.evaluate(script,name) or [])
        except Exception:
            candidates=[]
        # Old-style selectors remain useful if Facebook changes the page header.
        if not candidates:
            selectors=("img[alt*='profile picture' i]", "img[alt*='profile photo' i]",
                       "img[alt*='头像']", "img[alt*='大头贴']")
            for sel in selectors:
                try:
                    for item in page.locator(sel).all()[:3]:
                        url=item.get_attribute('src',timeout=800)
                        if url:
                            candidates.append({"url":url,"selector":"","index":-1,"score":70})
                except Exception:
                    pass
        for selector in ("meta[property='og:image']","meta[name='twitter:image']"):
            try:
                url=page.locator(selector).first.get_attribute('content',timeout=1100)
                if url:
                    candidates.append({"url":url,"selector":"","index":-1,"score":0})
            except Exception:
                continue
        # Do not mistake the site's top-nav or large cover for the page avatar.
        candidates.sort(key=lambda item:float(item.get('score') or 0),reverse=True)
        seen=set();dedup=[]
        for candidate in candidates:
            key=(candidate.get('url',''),candidate.get('selector',''),candidate.get('index',-1))
            if key not in seen:
                seen.add(key);dedup.append(candidate)
        return dedup[:25]

    def _save_avatar_bytes(self,pid:str,body:bytes) -> str:
        from PIL import Image,ImageOps
        if not isinstance(body,(bytes,bytearray)) or not 150<=len(body)<=6_000_000:
            raise ValueError('头像图片数据不完整')
        with Image.open(io.BytesIO(body)) as im:
            # Validate dimensions before full decode to avoid allocating a
            # decompression-bomb-sized image from a small compressed response.
            if min(im.width,im.height)<32 or im.width*im.height>24_000_000:
                raise ValueError('头像尺寸不正确')
            im.load()
            ratio=max(im.width,im.height)/min(im.width,im.height)
            if ratio>1.55:
                raise ValueError('图片更像横幅或封面，不作为头像保存')
            avatar=ImageOps.fit(im.convert('RGB'),(192,192),method=Image.Resampling.LANCZOS)
        ensure_private_directory(AVATAR_DIR)
        target=AVATAR_DIR / f'{pid}.png'
        tmp=target.with_suffix('.tmp')
        avatar.save(tmp,format='PNG',optimize=True)
        tmp.replace(target)
        return str(target)

    def _cache_avatar(self,pid:str,candidates:list[dict],previous:str,page=None,force=False) -> str:
        old=Path(previous) if previous else None
        old_valid=bool(old and old.is_file() and old.stat().st_size>200)
        if old_valid and not force and time.time()-old.stat().st_mtime<5*86400:
            return str(old)
        try:
            from PIL import Image
        except ImportError:
            return str(old) if old_valid else ''
        deadline=time.monotonic()+10.0
        for candidate in candidates[:9]:
            remaining=deadline-time.monotonic()
            if remaining<0.25:
                break
            url=str(candidate.get('url') or '').strip()
            if url and url.startswith('//'):
                url='https:'+url
            if url and self._is_facebook_image_url(url) and not any(x in url.lower() for x in ('emoji.php','static.xx.fbcdn.net/rsrc.php')):
                try:
                    resp=self.context.request.get(url,timeout=min(3800,max(350,int(remaining*1000))))
                    if resp.ok and (resp.headers.get('content-type') or '').lower().startswith('image/'):
                        try:
                            return self._save_avatar_bytes(pid,resp.body())
                        except (OSError,ValueError):
                            pass
                except Exception:
                    pass
            # A browser-rendered image can be visible even if its signed URL
            # cannot be downloaded via the network request context. Screenshot
            # that *element*, not the whole page or cover image.
            selector=str(candidate.get('selector') or '')
            index=candidate.get('index',-1)
            if not page or not selector or not isinstance(index,int) or index<0:
                continue
            if candidate.get('score',0)<48:
                continue
            try:
                locator=page.locator(selector).nth(index)
                remaining=deadline-time.monotonic()
                if remaining<0.25:break
                image_bytes=locator.screenshot(timeout=min(3800,max(350,int(remaining*1000))))
                return self._save_avatar_bytes(pid,image_bytes)
            except Exception:
                continue
        return str(old) if old_valid else ''

    def fetch_page(self,page_row,purpose="monitor"):
        row=dict(page_row);pid=str(row["page_id"])
        if not re.fullmatch(r"[0-9]{5,25}",pid):raise ValueError("主页 ID 格式错误")
        grow=purpose=="monitor" and bool(row.get("monitor_growth",1))
        posts=purpose=="monitor" and bool(row.get("monitor_posts",0))
        info={"page_id":pid,"page_name":"","avatar_path":"","avatar_fresh":False,
              "growth_ok":False,"posts_ok":False,"metadata_ok":False,
              "collected_at":now_iso(),"collected_ts":time.time(),
              "growth_error":"","posts_error":"","name_error":""}
        page=self.context.new_page()
        try:
            try:page.goto(f"https://www.facebook.com/{pid}",wait_until="domcontentloaded",timeout=PAGE_LOAD_TIMEOUT_MS)
            except Exception:
                if not (page.url or "").startswith(("https://www.facebook.com/","https://facebook.com/")):raise
            if any(x in (page.url or "") for x in ("/login","/checkpoint","/recover","/two_factor")):
                raise RuntimeError("请先在设置中登录当前监控账号，完成 Facebook 安全验证")
            # Same initial stabilization and Escape handling as the reference.
            page.wait_for_timeout(2600)
            try:
                page.keyboard.press("Escape");page.wait_for_timeout(250);page.keyboard.press("Escape")
            except Exception:pass
            body="";parsed=None
            for delay in (0,650,1000):
                if delay:page.wait_for_timeout(delay)
                try:
                    body=page.locator("body").inner_text(timeout=8000)
                    parsed=extract_followers_from_text(body)
                    break
                except Exception:
                    if not grow:break
            matched=parsed[2] if parsed else ""
            # Identity is extracted AFTER follower text so the proximity fallback works.
            name=self._extract_name(page,body,pid,matched)
            if not name:name=self._fallback_name(pid,matched)
            name=normalize_name(name,pid);info["page_name"]=name
            if not name:
                info["name_error"]="已按参考程序尝试标题、头像名称、主页链接、元数据及备用地址；暂未读取到可信名称"
            stamp=time.time()
            info["avatar_path"]=self._cache_avatar(pid,self._avatar_candidates(page,name),
                row.get("avatar_path") or "",page=page,force=purpose=="metadata")
            if info["avatar_path"]:
                try:info["avatar_fresh"]=Path(info["avatar_path"]).stat().st_mtime>=stamp-.2
                except OSError:pass
            info["metadata_ok"]=bool(name or info["avatar_fresh"])
            if grow:
                if parsed is None:info["growth_error"]="未读取到可确认的粉丝数，本次不更新粉丝基准"
                else:
                    count,approx,matched=parsed
                    info.update(growth_ok=True,followers_count=count,approx=approx,matched_text=matched)
            if posts:
                post=self._extract_post(page,pid,name or normalize_name(row.get("page_name"),pid))
                if post:
                    info.update(posts_ok=True,last_post_ts=post["ts"],post_precision_seconds=post["precision"],
                                post_source=post["source"],post_url=post["url"])
                else:info["posts_error"]="未读取到可确认的主页自发贴文时间"
            info["collected_at"]=now_iso();info["collected_ts"]=time.time()
            return info
        except Exception as exc:
            reason=str(exc)[:300];info["error"]=reason
            if grow and not info["growth_ok"]:info["growth_error"]=reason
            if posts and not info["posts_ok"]:info["posts_error"]=reason
            if not info["page_name"]:info["name_error"]=reason
            return info
        finally:
            try:page.close()
            except Exception:pass

    def _fallback_name(self,pid,matched_text=""):
        """Same-session alternate routes used by the supplied reference program."""
        tab=self.context.new_page()
        try:
            for url in (f"https://www.facebook.com/profile.php?id={pid}",f"https://www.facebook.com/{pid}/about"):
                try:
                    tab.goto(url,wait_until="domcontentloaded",timeout=PAGE_LOAD_TIMEOUT_MS)
                    tab.wait_for_timeout(1800)
                    if any(x in (tab.url or "") for x in ("/login","/checkpoint","/recover")):continue
                    try:tab.keyboard.press("Escape")
                    except Exception:pass
                    body=tab.locator("body").inner_text(timeout=8000)
                    name=self._extract_name(tab,body,pid,matched_text)
                    if name:return name
                except Exception:continue
            return ""
        finally:
            try:tab.close()
            except Exception:pass

    def _post_candidates(self, page, pid, name):
        """Read only timestamp nodes attached to page-authored feed posts, not comments."""
        script = r"""
        ({pid, name}) => {
          const norm=s=>(s||'').trim().replace(/\s+/g,' ').toLowerCase();
          const hostOk=h=>h==='facebook.com'||h.endsWith('.facebook.com');
          const parts=u=>{try{const a=new URL(u,location.href);if(!hostOk(a.hostname))return '';
            const id=a.searchParams.get('id');if(id)return id;
            return a.pathname.replace(/^\/|\/$/g,'').split('/')[0];}catch(e){return '';}};
          const alias=new Set([pid,parts(location.href)].filter(Boolean));
          const own=a=>alias.has(parts(a.href)) || (name && norm(a.textContent)===norm(name));
          let articles=[...document.querySelectorAll('main [role="article"], [role="main"] [role="article"]')];
          if(!articles.length)articles=[...document.querySelectorAll('[data-pagelet^="FeedUnit_"], .userContentWrapper')];
          articles=articles.filter(a=>!a.parentElement?.closest('[role="article"]'));
          const rows=[];
          for(const art of articles.slice(0,12)){
            const text=(art.innerText||'').slice(0,260);
            if(/suggested for you|为你推荐|為你推薦|sponsored|赞助内容|贊助內容/i.test(text))continue;
            const nested=n=>{let a=n.closest('[role="article"]');return a&&a!==art;};
            const anchors=[...art.querySelectorAll('a[href]')].filter(a=>!nested(a));
            const header=anchors.slice(0,8);
            const authored=header.some(own);
            if(!authored)continue;
            const links=anchors.filter(a=>/\/posts\/|story_fbid=|\/videos\/|\/reel\/|\/permalink\//.test(a.href));
            const nodes=[...art.querySelectorAll('time[datetime],abbr[data-utime],abbr[title],[data-utime]')]
              .filter(n=>!nested(n) && !n.closest('[aria-label*="Comment"],[aria-label*="评论"],[data-testid*="comment"]'));
            for(const node of nodes.slice(0,3)){
              const link=node.closest('a[href]') || links[0];
              for(const attr of ['datetime','data-utime','title','aria-label']){
                const raw=node.getAttribute(attr);
                if(raw)rows.push({raw,authored:true,url:link?link.href:'',source:'主页贴文时间节点'});
              }
            }
            // Only header/permalink timestamp labels, never the full post text or its comments.
            for(const link of links.slice(0,2)){
              for(const raw of [link.getAttribute('aria-label'),link.getAttribute('title'),link.innerText]){
                if(raw && raw.length<140)rows.push({raw,authored:true,url:link.href,source:'主页贴文链接时间'});
              }
            }
          }
          return rows;
        }
        """
        try:
            return page.evaluate(script,{"pid":str(pid),"name":normalize_name(name,pid)}) or []
        except Exception:
            return []

    def _extract_post(self, page, pid, name):
        candidates=[]
        # Check more than the first item so a pinned old post does not automatically win.
        for step in range(3):
            candidates.extend(self._post_candidates(page,pid,name))
            if step<2:
                try:
                    page.mouse.wheel(0,650)
                    page.wait_for_timeout(650)
                except Exception: break
        chosen=choose_post_candidate(candidates)
        if not chosen:
            urls=list(dict.fromkeys(str(c.get("url") or "") for c in candidates if c.get("authored") and c.get("url")))
            for url in urls[:3]:
                try:
                    index=page.locator("a[href]").evaluate_all("(els,url)=>els.findIndex(e=>e.href===url)",url)
                    if index<0:continue
                    page.locator("a[href]").nth(index).hover(timeout=1800)
                    page.wait_for_timeout(300)
                    for text in page.locator('[role="tooltip"]').all_inner_texts():
                        candidates.append({"raw":text,"authored":True,"url":url,"source":"主页贴文时间提示"})
                except Exception:continue
            chosen=choose_post_candidate(candidates)
        if not chosen:return None
        url=chosen["url"]
        try:
            u=urlsplit(url)
            if u.scheme!="https" or not ((u.hostname or "")=="facebook.com" or (u.hostname or "").endswith(".facebook.com")):
                chosen["url"]=""
        except ValueError:chosen["url"]=""
        return chosen




# ========== GitHub Releases / verified update preparation (no Qt dependency) ==========
REPOSITORY = "bstbuku-ship-it/Page-Operations-Monitor"
REPOSITORY_URL = "https://github.com/" + REPOSITORY
RELEASES_API = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
# Fill these when building signed installation packages. Never take publisher pins from remote JSON.
UPDATE_WINDOWS_PUBLISHER_THUMBPRINT = ""
UPDATE_MACOS_TEAM_ID = ""
MAX_UPDATE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_JSON_BYTES = 2 * 1024 * 1024

class UpdateError(RuntimeError):
    pass

def release_version(value):
    match=re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?",str(value).strip())
    if not match:raise UpdateError("发布版本号须为 v1.9.1 这样的正式版本号")
    return tuple(int(x or 0) for x in match.groups())

def update_platform_key(system=None,machine=None):
    system=system or platform.system();machine=(machine or platform.machine()).lower()
    arch="arm64" if machine in ("arm64","aarch64") else "x64" if machine in ("amd64","x86_64","x64") else ""
    prefix={"Windows":"windows","Darwin":"macos"}.get(system)
    return f"{prefix}-{arch}" if prefix and arch else ""

def _trusted_update_url(url,asset=False):
    try:
        u=urlsplit(str(url))
        if u.scheme!="https" or u.username or u.password or u.port not in (None,443):return False
        host=(u.hostname or "").lower()
        if asset:
            return host=="github.com" and u.path.lower().startswith("/"+REPOSITORY.lower()+"/releases/download/")
        return host in ("api.github.com","github.com","objects.githubusercontent.com",
                        "release-assets.githubusercontent.com","github-releases.githubusercontent.com")
    except (ValueError,TypeError):return False

class _ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not _trusted_update_url(newurl):raise UpdateError("下载重定向到非信任地址，已停止")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_update_url(url):
    if not _trusted_update_url(url):raise UpdateError("更新地址不受信任")
    request=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json" if urlsplit(url).hostname=="api.github.com" else "application/octet-stream",
        "User-Agent":"Page-Operations-Monitor/"+APP_VERSION,
        "X-GitHub-Api-Version":"2026-03-10"})
    opener=urllib.request.build_opener(_ReleaseRedirectHandler(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return opener.open(request,timeout=20)

def load_update_json(url,open_fn=None):
    with (open_fn or open_update_url)(url) as response:
        raw=response.read(MAX_UPDATE_JSON_BYTES+1)
    if len(raw)>MAX_UPDATE_JSON_BYTES:raise UpdateError("更新清单过大，已停止")
    try:
        value=json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError,ValueError) as exc:raise UpdateError("更新服务器未返回有效 JSON") from exc
    if not isinstance(value,dict):raise UpdateError("更新信息格式不正确")
    return value

def _asset_digest(asset,manifest_item=None):
    digest=str(asset.get("digest") or "")
    api_hash=digest[7:].lower() if digest.startswith("sha256:") else ""
    declared=str((manifest_item or {}).get("sha256") or "").lower()
    if declared and not re.fullmatch(r"[0-9a-f]{64}",declared):raise UpdateError("清单中的 SHA-256 无效")
    if api_hash and not re.fullmatch(r"[0-9a-f]{64}",api_hash):raise UpdateError("GitHub 的 SHA-256 无效")
    if api_hash and declared and api_hash!=declared:raise UpdateError("清单与 GitHub 资产校验值不一致")
    return declared or api_hash

def select_release_asset(release,manifest=None,system=None,machine=None,frozen=None):
    frozen=bool(getattr(sys,"frozen",False)) if frozen is None else bool(frozen)
    key=update_platform_key(system,machine)
    assets=release.get("assets") or []
    if not isinstance(assets,list):raise UpdateError("版本资产列表无效")
    assets={str(a.get("name")):a for a in assets if isinstance(a,dict) and a.get("state","uploaded")=="uploaded"}
    version=str(release.get("tag_name") or "").lstrip("vV")
    names={
        "windows-x64":f"ProfessionalMonitorTool-{version}-windows-x64.zip",
        "windows-arm64":f"ProfessionalMonitorTool-{version}-windows-arm64.zip",
        "macos-arm64":f"ProfessionalMonitorTool-{version}-macos-arm64.zip",
        "macos-x64":f"ProfessionalMonitorTool-{version}-macos-x64.zip",
    }
    name=names.get(key);asset=assets.get(name) if name else None
    if not asset:return None
    url=str(asset.get("browser_download_url") or "")
    if not _trusted_update_url(url,asset=True):raise UpdateError("更新包不属于指定仓库的 Release")
    try:size=int(asset.get("size",0))
    except (ValueError,TypeError):raise UpdateError("更新包大小无效")
    if not 0<size<=MAX_UPDATE_BYTES:raise UpdateError("更新包大小超出允许范围")
    sha=_asset_digest(asset,None)
    return {"name":name,"url":url,"size":size,"sha256":sha,"installer":"platform-bundle","platform":key,
            "version":version,"source_mode":not frozen}

def query_latest_release(open_fn=None,system=None,machine=None,frozen=None):
    try:
        release=load_update_json(RELEASES_API,open_fn)
    except urllib.error.HTTPError as exc:
        if exc.code==404:return {"status":"unavailable","message":"暂未找到可公开访问的正式 Release（可能尚未发布或仓库暂不可访问）"}
        if exc.code in (403,429):raise UpdateError("GitHub 请求受限，请稍后再检查") from exc
        raise UpdateError(f"GitHub 返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise UpdateError("无法连接 GitHub，请检查网络后重试；没有把本次检查当作已是最新版") from exc
    if release.get("draft") or release.get("prerelease"):return {"status":"unavailable","message":"没有正式发布的稳定版本"}
    tag=str(release.get("tag_name") or "")
    if release_version(tag)<=release_version(APP_VERSION):return {"status":"current","version":tag}
    manifest=None
    for asset in release.get("assets",[]):
        if isinstance(asset,dict) and asset.get("name")=="update-manifest.json":
            url=str(asset.get("browser_download_url") or "")
            if not _trusted_update_url(url,asset=True):raise UpdateError("更新清单地址无效")
            manifest=load_update_json(url,open_fn);break
    plan=select_release_asset(release,manifest,system,machine,frozen)
    return {"status":"new","version":tag.lstrip("vV"),"title":str(release.get("name") or tag)[:200],
            "notes":str(release.get("body") or "本版本未填写更新日志。")[:50000],
            "published_at":str(release.get("published_at") or ""),
            "release_url":REPOSITORY_URL+"/releases/tag/"+tag,
            "asset":plan}

def file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def download_release_asset(plan,folder,progress=None,cancel=None,open_fn=None):
    # Revalidate even when a pending plan was restored from local settings.
    name=str(plan.get("name") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.(?:exe|msi|pkg|zip|dmg)",name):
        raise UpdateError("不安全的更新文件名")
    if not _trusted_update_url(plan.get("url"),asset=True):raise UpdateError("更新下载地址无效")
    sha=str(plan.get("sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}",sha):raise UpdateError("发布者尚未提供 SHA-256，不能进行自动下载与安装")
    total=int(plan.get("size") or 0)
    if not 0<total<=MAX_UPDATE_BYTES:raise UpdateError("更新包大小无效")
    folder=ensure_private_directory(Path(folder))
    target=folder/name;part=folder/(name+".part")
    if target.is_symlink() or part.is_symlink():raise UpdateError("下载文件不能是符号链接")
    if target.is_file() and target.stat().st_size==total and file_sha256(target)==sha:
        if progress:progress(total,total)
        return str(target)
    if shutil.disk_usage(folder).free<total+32*1024*1024:raise UpdateError("磁盘剩余空间不足")
    actual=0;h=hashlib.sha256()
    try:
        with (open_fn or open_update_url)(plan["url"]) as response,part.open("wb") as stream:
            while True:
                if cancel and cancel.is_set():raise UpdateError("下载已取消")
                block=response.read(128*1024)
                if not block:break
                actual+=len(block)
                if actual>total or actual>MAX_UPDATE_BYTES:raise UpdateError("下载长度超出声明大小")
                stream.write(block);h.update(block)
                if progress:progress(actual,total)
            stream.flush();os.fsync(stream.fileno())
        if actual!=total or h.hexdigest()!=sha:raise UpdateError("更新包校验失败，已删除不完整下载")
        os.replace(part,target)
        return str(target)
    finally:
        try:part.unlink(missing_ok=True)
        except OSError:pass

def save_json_atomic(path,value):
    path=Path(path);ensure_private_directory(path.parent)
    temp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    try:
        with temp.open("w",encoding="utf-8") as f:
            json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)

def validate_staged_update(plan,path,updates_dir):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise UpdateError("下载文件不存在或路径不安全")
    try:path.resolve().relative_to(Path(updates_dir).resolve())
    except ValueError:raise UpdateError("更新文件不在应用更新目录")
    if path.name!=plan.get("name") or path.stat().st_size!=int(plan.get("size",0)):
        raise UpdateError("下载文件与计划不匹配")
    expected=str(plan.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}",expected) or file_sha256(path)!=expected:
        raise UpdateError("安装前校验失败；文件可能已被修改")
    return path.resolve()

def signed_install_available(plan):
    if not getattr(sys,"frozen",False):return False,"当前是 Python 源码运行方式，不自动覆盖脚本；下载当前系统更新包后请手动运行其中的部署文件。"
    installer=str(plan.get("installer") or "")
    platform_key=str(plan.get("platform") or "")
    if sys.platform=="win32" and installer in ("inno","msi","deployer","platform-bundle") and platform_key.startswith("windows-"):
        if not re.fullmatch(r"[0-9A-Fa-f]{40,64}",UPDATE_WINDOWS_PUBLISHER_THUMBPRINT):
            return False,"安装版尚未配置 Windows 发布者签名指纹，不能自动执行安装。"
        return True,""
    if sys.platform=="darwin" and installer in ("pkg","platform-bundle") and platform_key.startswith("macos-"):
        if not re.fullmatch(r"[A-Z0-9]{10}",UPDATE_MACOS_TEAM_ID):
            return False,"安装版尚未配置 Apple Developer Team ID，不能自动执行安装。"
        return True,""
    return False,"当前平台或包格式不支持自动安装；可打开下载目录手动安装。"

def _extract_platform_bundle_installer(plan,path,updates_dir):
    """Extract only the installer/deployer for this running platform."""
    path=validate_staged_update(plan,path,updates_dir)
    key=str(plan.get("platform") or "");version=str(plan.get("version") or "")
    if key.startswith("windows-"):
        expected=f"ProfessionalMonitorTool-{version}-{key}-deployer.exe";kind="deployer"
    elif key.startswith("macos-"):
        expected=f"ProfessionalMonitorTool-{version}-{key}.pkg";kind="pkg"
    else:raise UpdateError("更新包与当前系统不匹配")
    try:
        with zipfile.ZipFile(path,"r") as zf:
            matches=[i for i in zf.infolist() if (not i.is_dir()) and PurePosixPath(i.filename.replace("\\","/")).name==expected]
            if len(matches)!=1:raise UpdateError("更新包中找不到唯一的当前系统部署文件")
            info=matches[0]
            if info.file_size<=0 or info.file_size>MAX_UPDATE_BYTES:raise UpdateError("更新包内部署文件大小异常")
            folder=ensure_private_directory(Path(updates_dir)/"extracted"/version);target=folder/expected;temp=folder/(expected+".part")
            h=hashlib.sha256();written=0
            with zf.open(info,"r") as src,temp.open("wb") as dst:
                while True:
                    block=src.read(128*1024)
                    if not block:break
                    written+=len(block)
                    if written>info.file_size:raise UpdateError("解压后的部署文件长度异常")
                    dst.write(block);h.update(block)
                dst.flush();os.fsync(dst.fileno())
            if written!=info.file_size:raise UpdateError("部署文件解压不完整")
            os.replace(temp,target)
    except zipfile.BadZipFile as exc:raise UpdateError("下载的更新包不是有效 ZIP") from exc
    return {"name":expected,"size":target.stat().st_size,"sha256":h.hexdigest(),"installer":kind,
            "platform":key,"version":version,"source_mode":False},target


def prepare_install_helper(plan,path,updates_dir):
    """Static OS helper: wait for this app to exit, recheck hash/signature, install, relaunch.
    Called ONLY after an explicit user confirmation. It never disables OS security checks.
    """
    if str(plan.get("installer") or "")=="platform-bundle":
        plan,path=_extract_platform_bundle_installer(plan,path,updates_dir)
    else:
        path=validate_staged_update(plan,path,updates_dir)
    allowed,reason=signed_install_available(plan)
    if not allowed:raise UpdateError(reason)
    folder=ensure_private_directory(Path(updates_dir)/"helper")
    result=folder/"install-result.json"
    result.unlink(missing_ok=True)
    job={"pid":os.getpid(),"path":str(path),"sha256":plan["sha256"],
         "installer":plan["installer"],"result":str(result),
         "thumbprint":UPDATE_WINDOWS_PUBLISHER_THUMBPRINT,"team":UPDATE_MACOS_TEAM_ID,
         "relaunch":str(Path(sys.executable).resolve()),"target_dir":str(Path(sys.executable).resolve().parent),
         "version":plan["version"]}
    if sys.platform=="win32":
        script=folder/"apply-update.ps1"
        script.write_text(WINDOWS_UPDATE_HELPER,encoding="utf-8-sig")
        jobfile=folder/"job.json";save_json_atomic(jobfile,job)
        powershell=Path(os.environ.get("SystemRoot","C:/Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"
        return [str(powershell),"-NoProfile","-NonInteractive","-File",str(script),"-PlanPath",str(jobfile)]
    bundle=next((p for p in Path(sys.executable).resolve().parents if p.suffix==".app"),None)
    if bundle is None:raise UpdateError("找不到当前 macOS 应用包，不能自动重启")
    def aq(value):return json.dumps(str(value),ensure_ascii=False)
    sig=("/usr/sbin/pkgutil --check-signature "+shlex.quote(str(path))+
         " && /usr/sbin/spctl --assess --type install --verbose=2 "+shlex.quote(str(path)))
    sha="/usr/bin/shasum -a 256 "+shlex.quote(str(path))
    wait=f"i=0; while [ \"$i\" -lt 120 ]; do /bin/kill -0 {os.getpid()} 2>/dev/null || exit 0; /bin/sleep 1; i=$((i+1)); done; exit 1"
    install="/usr/sbin/installer -pkg "+shlex.quote(str(path))+" -target /"
    status_ok="/usr/bin/printf '%s' "+shlex.quote(json.dumps({"status":"installed","version":plan["version"]}))+" > "+shlex.quote(str(result))
    status_bad="/usr/bin/printf '%s' "+shlex.quote(json.dumps({"status":"failed","version":plan["version"]}))+" > "+shlex.quote(str(result))
    script=folder/"apply-update.applescript"
    code="\n".join([
        "try","  do shell script "+aq(wait),
        "  set digestResult to do shell script "+aq(sha),
        "  if digestResult does not contain "+aq(plan["sha256"])+" then error \"SHA mismatch\"",
        "  set signatureResult to do shell script "+aq(sig),
        "  if signatureResult does not contain "+aq("("+UPDATE_MACOS_TEAM_ID+")")+' then error "Publisher mismatch"',
        "  do shell script "+aq(install)+" with administrator privileges",
        "  do shell script "+aq(status_ok),
        "  tell application \"System Events\" to open file POSIX file "+aq(str(bundle)),
        "on error errText number errNum",
        "  try","    do shell script "+aq(status_bad),"  end try",
        "end try",
    ])
    script.write_text(code,encoding="utf-8")
    return ["/usr/bin/osascript",str(script)]


WINDOWS_UPDATE_HELPER = r"""
param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$j = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    $old = Get-Process -Id ([int]$j.pid) -ErrorAction SilentlyContinue
    if ($old -and -not $old.WaitForExit(120000)) { throw 'The application did not exit.' }
    $hash = (Get-FileHash -LiteralPath $j.path -Algorithm SHA256).Hash
    if ($hash.ToLowerInvariant() -ne $j.sha256.ToLowerInvariant()) { throw 'SHA256 mismatch' }
    $signature = Get-AuthenticodeSignature -LiteralPath $j.path
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $j.thumbprint.ToUpperInvariant()) {
        throw 'Installer signature or publisher mismatch'
    }
    if ($j.installer -eq 'inno') {
        $p = Start-Process -FilePath $j.path -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' -Wait -PassThru
    } elseif ($j.installer -eq 'msi') {
        $args = '/i "' + $j.path + '" /passive /norestart'
        $p = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $args -Wait -PassThru
    } elseif ($j.installer -eq 'deployer') {
        $args = @('--silent-update','--target',[string]$j.target_dir)
        $p = Start-Process -FilePath $j.path -ArgumentList $args -Wait -PassThru
    } else { throw 'Unsupported installer type' }
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Installer exit code: $($p.ExitCode)" }
    @{status='installed';version=$j.version;reboot_required=($p.ExitCode -eq 3010)} |
        ConvertTo-Json | Set-Content -LiteralPath $j.result -Encoding UTF8
} catch {
    @{status='failed';version=$j.version;message=$_.Exception.Message} |
        ConvertTo-Json | Set-Content -LiteralPath $j.result -Encoding UTF8
}
if (-not (Get-Process -Id ([int]$j.pid) -ErrorAction SilentlyContinue)) {
    if (Test-Path -LiteralPath $j.relaunch) { Start-Process -FilePath $j.relaunch }
}
"""


def settings_locator_path():
    if os.environ.get("FBPM_DATA_DIR"):
        return Path(os.environ["FBPM_DATA_DIR"])/"location.json"
    if os.name=="nt":
        base=Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform=="darwin":
        base=Path.home()/"Library/Preferences"
    else:
        base=Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config")
    return base/"PageOperationsMonitor"/"location.json"

def read_settings_location(default,legacy=""):
    if os.environ.get("FBPM_DATA_DIR"):return Path(os.environ["FBPM_DATA_DIR"]).expanduser()
    path=settings_locator_path()
    if path.is_file():
        try:
            obj=json.loads(path.read_text("utf-8"))
            target=Path(str(obj["data_directory"])).expanduser()
            if not target.is_absolute():raise ValueError("relative directory")
            if not target.is_dir():raise ValueError("saved directory unavailable")
            return target
        except (KeyError,ValueError,OSError,TypeError) as exc:
            raise RuntimeError("无法读取已保存的数据目录；为避免另建空数据库，已停止启动。请检查："+str(path)) from exc
    return Path(legacy).expanduser() if legacy else Path(default)

def write_settings_location(path):
    save_json_atomic(settings_locator_path(),{"data_directory":str(Path(path).resolve()),"format":1})



# ========== Authenticated local Chrome connector + single instance ==========
"""POM connector protocol v1; local only, read-only page collection.
This section is embedded in the single-file desktop entry points at build time.
"""
import secrets
import socket
import queue
from dataclasses import dataclass, field
from pathlib import PureWindowsPath

CONNECTOR_VERSION = '1.4.0'
CONNECTOR_PROTOCOL = 1
CONNECTOR_PORT = 17831
CONNECTOR_EXTENSION_ID = 'lpjmbcclokpbgfogjhjepmnpoplgheoh'
CONNECTOR_ORIGIN = 'chrome-extension://' + CONNECTOR_EXTENSION_ID

# BEGIN BUNDLED CONNECTOR PACKAGE
# IMPORTANT: Connector version is independent from the desktop app version.
# Do not change this package/version unless the browser connector itself is intentionally updated.
BUNDLED_CONNECTOR_VERSION = '1.4.0'
BUNDLED_CONNECTOR_FILENAME = '专业监控工具-浏览器连接器-1.4.0.zip'
BUNDLED_CONNECTOR_SHA256 = '908bba147859bb2f28e68d28554a29bfe17cdccee16a826b2770790a026f81b6'
BUNDLED_CONNECTOR_ZIP_B64 = (
    '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'
    'TaCpGQIqQqAxBsdxaWtZjDG6bl3cGotUkh07n8NEmrgTxAkhMEKwY8ezCKXqFJgWEFLgFz38YjQERHsVq4kgko9kQqEcOcNyyFx6'
    'ftjioRgWuTlvDp0t+BDstNG6xMTkYEgA8YGx9oQOgxTQ07UykBniE4GQQFpbMtx97y94bs8Qy5Z2UyiZhnJARFDzLQQ2IjptDOmk'
    '4NndQ9x1z89pbclUTQWr5HgTGbDWdLUaUIwFpAw+jRr2CNl+o1FzjgQwW/Aj8TdYABoa3VsxBBWxGUBMALQEFV+2+ByqjqkPK2st'
    'uK7LocNDfOzjn+ZfP/sRPM/i+9VTM60Nrqtoy0iaDCRzrrEDTBbA8+rzcpQg7Qo+9rd/z+HDQ1XTwLIsFD6JENSqZfByjBpBzxgw'
    'pjybqm2P2Zc+/NfklTkQwBzBD50QgkODz2PKYFcXJiIGgcTzDKf0riWT7sL3S+EwUImstaazo51bb/s6PT3dfPSv/5AOR5aVM1JC'
    'WilyJcvmv/1n7rv/QdLpVI1yZvrGi4dKIcgXClz2ay/nwx98D+1tqi6vgm/54F/9A1/+ytfo6GivAz9K1RqLk3SR0bhuRfWpTDHr'
    'YRuaigXLwrHU5hl8mDUBHBn41lqUdDkw+CyFol/RB1CR/iuvCDy/QE/HCpb3rmXnrvtJJlrqpH1jDO3tbXzqH/+FB7Y+HKpnz69S'
    'z1apgmdQpsSDbIM4Qgh+duc9bLnrPt75u7/Nyy5YT1tbG5MTEzz0yGN87pbbuPf+B+js6CgTWi34CIE1hkR7BpVKVIanGtYvbLBJ'
    'RkhBKVcKl4RltYAwKzc78GEuiqA5gh9kbnFUksGR3YyM76e7YzmeF5zzE9kDlKVfG8gBSirOO+M6nnn+boQQDStgjKGrs4OtDz7M'
    'fT/fSndXJ5lMmtxUnqGRURyl6O7uqilTk5aoq15jaeYXWx/i3vu20tPdSSaTIpfLMzQ0iuMoujo7m/b84HWB8Q0tvV2oZAJvKldZ'
    'sQyJoMzrLKAk+bEp/KJXPmlkIcCHGQngyMGPaqOUw1RuhD0vPkFv96kUSwZBoOuPg48NFoQKpRLnnnENd227hfHJQziqsZm01pqW'
    'lgwIQankkc8XUUrS1dmBtTamjm1SvrrqTd9arS0tCCEolUrk84Ugr67qvBqCTwiur+lYvTTYVWTAxsScYC9h+JYFIRWTh8bQJR8n'
    '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'
    'AC0EAABc7gAAAAA='
)
# END BUNDLED CONNECTOR PACKAGE

class ConnectorError(RuntimeError):
    pass


def connector_version_tuple(value):
    """Chrome manifest versions are numeric dot-separated values (1-4 parts)."""
    parts = str(value or '').strip().split('.')
    if not parts or len(parts) > 4 or any(not p.isdigit() for p in parts):
        return None
    nums = tuple(int(p) for p in parts)
    return nums + (0,) * (4 - len(nums))


def bundled_connector_bytes():
    """Return the connector ZIP embedded in the desktop application and verify it before export."""
    try:
        data = base64.b64decode(BUNDLED_CONNECTOR_ZIP_B64.encode('ascii'), validate=True)
    except Exception as exc:
        raise ConnectorError('内置连接器数据损坏') from exc
    if hashlib.sha256(data).hexdigest().lower() != BUNDLED_CONNECTOR_SHA256.lower():
        raise ConnectorError('内置连接器校验失败')
    return data


def connector_needs_update(identity):
    current = connector_version_tuple((identity or {}).get('extension_version'))
    bundled = connector_version_tuple(BUNDLED_CONNECTOR_VERSION)
    return bool(current and bundled and current < bundled)


def save_bundled_connector(parent):
    """Let the user export the embedded connector package to a chosen location."""
    try:
        data = bundled_connector_bytes()
    except Exception as exc:
        QMessageBox.warning(parent, '连接器不可用', str(exc))
        return None
    downloads = Path.home() / 'Downloads'
    base = downloads if downloads.is_dir() else Path.home()
    default_path = base / BUNDLED_CONNECTOR_FILENAME
    path, _ = QFileDialog.getSaveFileName(parent, '保存浏览器连接器', str(default_path), 'ZIP 压缩包 (*.zip)')
    if not path:
        return None
    target = Path(path)
    if target.suffix.lower() != '.zip':
        target = target.with_suffix('.zip')
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.tmp')
        temp.write_bytes(data)
        os.replace(temp, target)
    except OSError as exc:
        QMessageBox.warning(parent, '保存失败', str(exc))
        return None
    show_hint(parent, f'连接器 v{BUNDLED_CONNECTOR_VERSION} 已保存；解压后在 Chrome 扩展程序页面加载该文件夹')
    return target


def bc_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ConnectorError('Refusing a symlink registry')
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        if os.name != 'nt':
            path.chmod(0o600)
    finally:
        try:temp.unlink(missing_ok=True)
        except OSError:pass


def connector_identity(raw):
    """Never treat client labels as detected filesystem or channel evidence."""
    raw = raw if isinstance(raw, dict) else {}
    limits = {'profile_name':80, 'profile_directory':100, 'profile_path':800,
              'channel_label':100, 'browser_brand':100, 'browser_version':80,
              'os':30, 'arch':30, 'extension_version':30}
    clean = {}
    for key, limit in limits.items():
        value = str(raw.get(key) or '').strip()
        if any(ord(ch) < 32 for ch in value) or len(value) > limit:
            raise ConnectorError('Invalid identity field: ' + key)
        clean[key] = value
    directory, path = clean['profile_directory'], clean['profile_path']
    if directory and not re.fullmatch(r'Default|Profile [0-9]{1,6}', directory):
        raise ConnectorError('Profile directory must be Default or Profile N')
    if path:
        p = PureWindowsPath(path) if re.match(r'^[a-zA-Z]:[\\/]', path) else Path(path)
        if not p.is_absolute():
            raise ConnectorError('Profile path must be absolute')
        if directory and p.name != directory:
            raise ConnectorError('Profile directory and full path do not match')
        if not directory:
            if not re.fullmatch(r'Default|Profile [0-9]{1,6}',p.name):
                raise ConnectorError('Profile path must end in Default or Profile N')
            clean['profile_directory'] = p.name
    clean['identity_source'] = 'profile-and-channel-manually-declared'
    return clean


def inspect_declared_profile(identity):
    """Local filesystem existence is evidence of a path, not proof of socket identity."""
    identity = connector_identity(identity)
    path = identity.get('profile_path', '')
    out = {'exists':False, 'local_state_match':False, 'local_name':'',
           'binding_verified':False, 'explanation':'No path supplied; connection identity is the paired instance ID.'}
    if not path:return out
    if os.name != 'nt' and re.match(r'^[a-zA-Z]:[\\/]', path):
        out['explanation']='Windows path declared on a different operating system; not locally verified.'
        return out
    p = Path(path).expanduser()
    out['exists'] = p.is_dir()
    if not out['exists']:
        out['explanation']='Declared path not found on this computer.'
        return out
    try:
        state = p.parent / 'Local State'
        if state.stat().st_size > 8_000_000:raise ValueError('Local State too large')
        data = json.loads(state.read_text('utf-8'))
        item = data.get('profile', {}).get('info_cache', {}).get(p.name)
        if isinstance(item, dict):
            out['local_state_match']=True
            out['local_name']=str(item.get('name') or '')[:100]
    except (OSError, ValueError, TypeError):pass
    out['explanation']='Path exists locally; its association with this connector is still user-declared.'
    return out


@dataclass
class _ConnectorSession:
    instance_id: str
    connection: object
    identity: dict
    last_seen: float = field(default_factory=time.monotonic)
    send_lock: object = field(default_factory=threading.Lock)

    def send(self, message):
        encoded = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
        with self.send_lock:self.connection.send(encoded)


@dataclass
class _ConnectorJob:
    session: object
    page_id: str
    event: object = field(default_factory=threading.Event)
    result: object = None
    error: str = ''


# Restricted RFC 6455 transport for the local connector. Standard library only.
# It isn't a public HTTP server: only loopback + the pinned extension Origin is accepted.
import socketserver
import struct
import select
import errno

CONNECTOR_BUILD = 'auto-connect-20261013'
CONNECTOR_PORTS = tuple(range(17831, 17841))
CONNECTOR_PRODUCT = 'PageOperationsMonitor'

class ConnectorFault(ConnectorError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _LocalWebSocket:
    MAX_MESSAGE = 1_048_576
    def __init__(self, sock, remainder=b''):
        self.sock = sock
        self.buffer = bytearray(remainder)
        self.send_lock = threading.RLock()
        self.closed = False
        self.fragments = bytearray()
        self.fragmented = False
        self.partial_since = None
        self.sock.settimeout(5)

    def _fill(self, count, deadline):
        while len(self.buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Connector receive timeout')
            if not select.select([self.sock], [], [], remaining)[0]:
                raise TimeoutError('Connector receive timeout')
            chunk = self.sock.recv(min(65536, max(4096, count - len(self.buffer))))
            if not chunk:
                raise ConnectionError('Browser closed the connection')
            self.buffer.extend(chunk)
            if self.partial_since is None:
                self.partial_since = time.monotonic()

    def _frame(self, payload, opcode=1):
        with self.send_lock:
            if self.closed:
                raise ConnectionError('Connection closed')
            n = len(payload)
            if n > self.MAX_MESSAGE:
                raise ConnectorError('Outgoing message exceeds limit')
            header = bytes([0x80 | opcode])
            if n < 126:
                header += bytes([n])
            elif n < 65536:
                header += bytes([126]) + struct.pack('!H', n)
            else:
                header += bytes([127]) + struct.pack('!Q', n)
            self.sock.sendall(header + payload)

    def send(self, text):
        if not isinstance(text, str):
            raise TypeError('Text messages only')
        self._frame(text.encode('utf-8'))

    def recv(self, timeout=22):
        deadline = time.monotonic() + timeout
        while True:
            # Preserve unread bytes on timeout, including a partly received frame.
            if self.partial_since is not None and time.monotonic() - self.partial_since > 30:
                raise ConnectorError('Incomplete frame deadline exceeded')
            self._fill(2, deadline)
            first, second = self.buffer[0], self.buffer[1]
            fin, opcode = bool(first & 128), first & 15
            if first & 0x70 or not second & 128:
                raise ConnectorError('Compressed or unmasked frame refused')
            if opcode not in (0, 1, 8, 9, 10):
                raise ConnectorError('Only text frames are accepted')
            n, pos = second & 127, 2
            if n == 126:
                self._fill(4, deadline)
                n = struct.unpack('!H', self.buffer[2:4])[0];pos = 4
                if n < 126:raise ConnectorError('Noncanonical frame length')
            elif n == 127:
                self._fill(10, deadline)
                n = struct.unpack('!Q', self.buffer[2:10])[0];pos = 10
                if n < 65536:raise ConnectorError('Noncanonical frame length')
            if n > self.MAX_MESSAGE or (opcode < 8 and n + len(self.fragments) > self.MAX_MESSAGE):
                raise ConnectorError('Incoming message exceeds limit')
            if opcode >= 8 and (not fin or n > 125):
                raise ConnectorError('Invalid control frame')
            self._fill(pos + 4 + n, deadline)
            mask = self.buffer[pos:pos+4]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.buffer[pos+4:pos+4+n]))
            del self.buffer[:pos+4+n]
            if not self.buffer and not self.fragmented:
                self.partial_since = None
            if opcode == 8:
                if len(payload) == 1:raise ConnectorError('Invalid close frame')
                if len(payload) >= 2:
                    code = struct.unpack('!H', payload[:2])[0]
                    if code < 1000 or code >= 5000 or code in (1004,1005,1006,1015) or 1016 <= code < 3000:
                        raise ConnectorError('Invalid close code')
                    payload[2:].decode('utf-8', 'strict')
                try:self._frame(payload, 8)
                except Exception:pass
                raise ConnectionError('Browser disconnected')
            if opcode == 9:
                self._frame(payload, 10);continue
            if opcode == 10:continue
            if opcode == 1:
                if self.fragmented:raise ConnectorError('Unexpected new text fragment')
                if fin:return payload.decode('utf-8', 'strict')
                self.fragments.extend(payload);self.fragmented=True
                self.partial_since=time.monotonic()
            else:
                if not self.fragmented:raise ConnectorError('Unexpected continuation')
                self.fragments.extend(payload)
                if fin:
                    text=bytes(self.fragments).decode('utf-8','strict')
                    self.fragments.clear();self.fragmented=False
                    self.partial_since=time.monotonic() if self.buffer else None
                    return text

    def close(self, code=1000, reason=''):
        with self.send_lock:
            if self.closed:return
            payload=struct.pack('!H', code)+str(reason).encode('utf-8')[:120].decode('utf-8','ignore').encode('utf-8')
            try:self._frame(payload, 8)
            except Exception:pass
            self.closed=True
            try:self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            try:self.sock.close()
            except OSError:pass


class _LocalConnectorHandler(socketserver.BaseRequestHandler):
    def handle(self):
        if self.client_address[0] != '127.0.0.1':return
        sock=self.request;sock.settimeout(4)
        try:
            data=bytearray();deadline=time.monotonic()+4
            while b'\r\n\r\n' not in data:
                if time.monotonic()>deadline or len(data)>8192:
                    raise ValueError('HTTP header limit')
                part=sock.recv(min(2048,8193-len(data)))
                if not part:return
                data.extend(part)
            head,remainder=bytes(data).split(b'\r\n\r\n',1)
            if len(head)>8192:raise ValueError('HTTP header limit')
            lines=head.decode('ascii','strict').split('\r\n')
            if lines[0] != 'GET /connector/v1 HTTP/1.1':
                self.deny(404,'Not found');return
            headers={}
            for line in lines[1:]:
                key,sep,value=line.partition(':');key=key.strip().lower()
                if not sep or key in headers or not key:
                    raise ValueError('Invalid or duplicate header')
                headers[key]=value.strip()
            if headers.get('host') != '127.0.0.1:'+str(self.server.server_address[1]):
                self.deny(403,'Host refused');return
            if headers.get('origin') != CONNECTOR_ORIGIN:
                self.deny(403,'Extension origin refused');return
            if headers.get('upgrade','').lower()!='websocket' or 'upgrade' not in [x.strip().lower() for x in headers.get('connection','').split(',')]:
                self.deny(400,'WebSocket upgrade required');return
            if headers.get('sec-websocket-version')!='13':
                self.deny(400,'Unsupported WebSocket version');return
            key=headers.get('sec-websocket-key','')
            if len(base64.b64decode(key,validate=True))!=16:
                raise ValueError('Invalid websocket key')
            accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
            sock.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode('ascii'))
            self.server.bridge._handle(_LocalWebSocket(sock,remainder))
        except (ValueError,UnicodeError):
            self.deny(400,'Invalid request')
        except (OSError,ConnectorError):pass

    def deny(self, code, message):
        try:
            body=message.encode('ascii')
            self.request.sendall(('HTTP/1.1 '+str(code)+' '+message+'\r\nConnection: close\r\nContent-Type: text/plain\r\nContent-Length: '+str(len(body))+'\r\n\r\n').encode('ascii')+body)
        except OSError:pass


class _LocalConnectorServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=32
    allow_reuse_address=False
    def __init__(self, address, bridge):
        self.bridge=bridge
        self.slots=threading.BoundedSemaphore(72)
        super().__init__(address,_LocalConnectorHandler)

    def server_bind(self):
        if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except Exception:
            self.slots.release();raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


def choose_connected_browser(rows, selected_id='', selection_mode=''):
    """Select a unique online instance; never substitute for an offline selection."""
    usable=[r for r in rows if not r.get('blocked')]
    online=[r for r in usable if r.get('online')]
    chosen=next((r for r in rows if r['instance_id']==selected_id),None)
    if chosen:
        if chosen.get('blocked'):return '', 'blocked'
        if not chosen.get('online'):return '', 'offline_selected'
        if len(online)>1 and selection_mode=='auto':return '', 'multiple'
        return selected_id, 'selected'
    if len(online)==1:return online[0]['instance_id'], 'automatic'
    if len(online)>1:return '', 'multiple'
    return '', 'waiting'



class ConnectorBridge:
    """Automatic enrollment from the pinned extension Origin; then per-profile tokens.

    Loopback only. This is not a barrier against malicious local native programs.
    No arbitrary code, URLs, cookies, or filesystem requests are sent to Chrome.
    """
    def __init__(self, registry, port=CONNECTOR_PORT):
        self.registry_path=Path(registry)
        self.port=int(port)
        self.lock=threading.RLock()
        self.records={}
        self.sessions={}
        self.jobs={}
        self.server=None
        self.thread=None
        self.error=''
        self._running=False
        if self.registry_path.is_file():
            try:
                if self.registry_path.stat().st_size > 1_000_000:raise ValueError('Registry too large')
                root=json.loads(self.registry_path.read_text('utf-8'))
                if root.get('schema') != 1:raise ValueError('Unsupported registry schema')
                for cid, value in root.get('clients', {}).items():
                    if re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',cid) and isinstance(value,dict):
                        self.records[cid]=value
            except (OSError,ValueError,TypeError,AttributeError) as exc:
                self.error='Connector registry could not be read: '+str(exc)

    def _save(self):
        bc_atomic(self.registry_path, {'schema':1,'clients':self.records})

    def relocate(self, path):
        with self.lock:
            self.registry_path=Path(path)
            self._save()

    def start(self):
        if self._running:return
        requested=self.port
        ports=[0] if requested==0 else list(dict.fromkeys([requested]+list(CONNECTOR_PORTS)))
        failures=[]
        for port in ports:
            server=None
            try:
                server=_LocalConnectorServer(('127.0.0.1',port),self)
                self.server=server;self.port=server.server_address[1]
                self._running=True
                self.thread=threading.Thread(target=server.serve_forever,
                    kwargs={'poll_interval':0.15},name='POM-local-connector',daemon=True)
                self.thread.start();self.error='';return
            except OSError as exc:
                if server:server.server_close()
                failures.append(str(port)+': '+str(exc))
                self._running=False;self.server=None
            except Exception:
                if server:server.server_close()
                self._running=False;self.server=None
                raise
        self.error=('\u672c\u673a\u8fde\u63a5\u670d\u52a1\u6682\u65f6\u65e0\u6cd5\u542f\u52a8\uff0c'
                    '\u8bf7\u68c0\u67e5\u7aef\u53e3\u5360\u7528\u6216\u5b89\u5168\u8f6f\u4ef6\u62e6\u622a\u3002\n' + '; '.join(failures))
        raise ConnectorError(self.error)


    def _authenticate(self, message):
        if message.get('protocol') != CONNECTOR_PROTOCOL:
            raise ConnectorFault('PROTOCOL_MISMATCH','Desktop and extension versions do not match')
        kind=message.get('type')
        if kind not in ('auto_hello','hello'):
            raise ConnectorFault('UPGRADE_REQUIRED','Install the automatic-connection extension included with this desktop build')
        if kind=='auto_hello' and message.get('product') != CONNECTOR_PRODUCT:
            raise ConnectorFault('PROTOCOL_MISMATCH','Unexpected connector product')
        cid=str(message.get('instance_id') or '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',cid):
            raise ConnectorFault('BAD_ID','Invalid instance ID')
        identity=connector_identity(message.get('identity'))
        token=str(message.get('token') or '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{32,256}',token):
            raise ConnectorFault('BAD_TOKEN','Invalid local installation token')
        digest=hashlib.sha256(token.encode('ascii')).hexdigest()
        with self.lock:
            record=self.records.get(cid)
            if record and record.get('blocked'):
                raise ConnectorFault('BLOCKED','This browser has been disabled in the desktop app')
            if record:
                if not secrets.compare_digest(digest,str(record.get('token_hash') or '')):
                    raise ConnectorFault('AUTH_MISMATCH','Connection identity is no longer valid; reset this connector in extension settings')
            else:
                if kind!='auto_hello':raise ConnectorFault('UPGRADE_REQUIRED','Please update the browser extension')
                if len(self.records)>=64:raise ConnectorFault('LIMIT','Maximum saved browser connections reached')
                record={'token_hash':digest,'paired_at':time.time(),'registration':'automatic-local','blocked':False}
            online=self.sessions.get(cid)
            if online and time.monotonic()-online.last_seen<65:
                raise ConnectorFault('INSTANCE_IN_USE','A copied Profile is using this instance ID')
            record['identity']=identity;record['last_connected_at']=time.time()
            self.records[cid]=record
            self._save()
        return cid,identity,None

    def _handle(self, ws):
        session=None
        try:
            first=ws.recv(timeout=8)
            if not isinstance(first,str) or len(first)>6000:raise ConnectorError('Invalid handshake')
            message=json.loads(first)
            if not isinstance(message,dict):raise ConnectorError('Invalid handshake')
            with self.lock:
                cid,identity,token=self._authenticate(message)
                old=self.sessions.get(cid)
                # A copied browser directory can duplicate storage IDs. Never auto-reroute an active session.
                if old and time.monotonic()-old.last_seen<65:
                    raise ConnectorError('This instance ID is already online; regenerate the connector ID in the copied profile')
                if old:
                    try:old.connection.close(1000,'Reconnected')
                    except Exception:pass
                session=_ConnectorSession(cid,ws,identity)
                self.sessions[cid]=session
            response={'type':'ready','protocol':CONNECTOR_PROTOCOL,'version':CONNECTOR_VERSION,'instance_id':cid,
                      'product':CONNECTOR_PRODUCT,'build':CONNECTOR_BUILD,'connection_mode':'auto'}
            if token:response['token']=token
            session.send(response)
            while self._running:
                try:raw=ws.recv(timeout=22)
                except TimeoutError:
                    if time.monotonic()-session.last_seen>65:break
                    session.send({'type':'ping'});continue
                if not isinstance(raw,str):raise ConnectorError('Text JSON required')
                msg=json.loads(raw)
                if not isinstance(msg,dict):raise ConnectorError('Invalid message')
                session.last_seen=time.monotonic()
                if msg.get('type') in ('ping','pong'):
                    if msg['type']=='ping':session.send({'type':'pong'})
                    continue
                if msg.get('type')=='result':
                    jid=str(msg.get('job_id') or '')
                    with self.lock:
                        job=self.jobs.get(jid)
                        if not job or job.session is not session:continue
                        payload=msg.get('payload')
                        if not isinstance(payload,dict) or str(payload.get('page_id') or '')!=job.page_id:
                            job.error='Result identity mismatch'
                        else:job.result=payload
                        job.event.set()
                else:raise ConnectorError('Unsupported message')
        except Exception as exc:
            try:ws.send(json.dumps({'type':'error','code':getattr(exc,'code','CONNECTOR_ERROR'),'message':str(exc)[:240]}))
            except Exception:pass
        finally:
            if session:
                with self.lock:
                    if self.sessions.get(session.instance_id) is session:self.sessions.pop(session.instance_id,None)
                    for job in self.jobs.values():
                        if job.session is session and not job.event.is_set():
                            job.error='Selected browser disconnected; no other profile was substituted'
                            job.event.set()
            try:ws.close()
            except Exception:pass

    def clients(self):
        with self.lock:
            rows=[]
            for cid,item in self.records.items():
                session=self.sessions.get(cid)
                online=bool(session and time.monotonic()-session.last_seen<65)
                rows.append({'instance_id':cid,'identity':dict(item.get('identity') or {}),'online':online,
                             'last_connected_at':item.get('last_connected_at',0),'blocked':bool(item.get('blocked'))})
            return rows

    def online(self, cid):
        return any(r['instance_id']==cid and r['online'] for r in self.clients())

    def request(self, cid, row, purpose='monitor', stop=None, timeout=120):
        pid=str(row.get('page_id') or '')
        if not re.fullmatch(r'[0-9]{5,25}',pid):raise ConnectorError('Invalid page ID')
        if purpose not in ('monitor','metadata'):raise ConnectorError('Unsupported purpose')
        with self.lock:
            session=self.sessions.get(cid)
            if not session or time.monotonic()-session.last_seen>=65:raise ConnectorError('Selected browser is offline')
            if any(j.session is session and not j.event.is_set() for j in self.jobs.values()):
                raise ConnectorError('Selected browser is busy')
            jid=secrets.token_hex(16);job=_ConnectorJob(session,pid);self.jobs[jid]=job
        try:
            session.send({'type':'collect','job_id':jid,'page_id':pid,'purpose':purpose,
                          'growth':bool(purpose=='monitor' and row.get('monitor_growth',1)),
                          'posts':bool(purpose=='monitor' and row.get('monitor_posts',0)),
                          'timeout_ms':max(5000,min(110000,int(timeout*1000)-5000))})
            end=time.monotonic()+timeout
            while not job.event.wait(.15):
                if stop and stop.is_set():raise ConnectorError('Task stopped')
                if time.monotonic()>end:raise ConnectorError('Browser task timed out')
            if job.error:raise ConnectorError(job.error)
            if not job.result:raise ConnectorError('No result received')
            return job.result
        finally:
            with self.lock:self.jobs.pop(jid,None)
            # Late results are ignored; cancel never touches tabs not created by this connector.
            if not job.event.is_set():
                try:session.send({'type':'cancel','job_id':jid})
                except Exception:pass

    def identify(self,cid):
        with self.lock:session=self.sessions.get(cid)
        if not session:raise ConnectorError('Selected browser is offline')
        session.send({'type':'identify'})

    def revoke(self,cid):
        # Keep a tombstone: offline disabled profiles must not auto-enroll again.
        with self.lock:
            record=self.records.get(cid)
            if not record:return
            record['blocked']=True;self._save()
            session=self.sessions.get(cid)
        if session:
            try:session.send({'type':'revoked'});session.connection.close(1000,'Disabled')
            except Exception:pass

    def allow(self,cid):
        with self.lock:
            if cid in self.records:
                self.records[cid]['blocked']=False;self._save()

    def forget(self,cid):
        """Delete an offline historical record. Online instances must be closed first."""
        with self.lock:
            session=self.sessions.get(cid)
            if session and time.monotonic()-session.last_seen<65:
                raise ConnectorError('请先关闭该浏览器或停用连接后再删除记录')
            self.records.pop(cid,None);self.sessions.pop(cid,None);self._save()

    def stop(self):
        self._running=False
        with self.lock:
            sessions=list(self.sessions.values())
            for job in self.jobs.values():job.error='Desktop connector stopped';job.event.set()
        for session in sessions:
            try:session.connection.close(1001,'Desktop stopped')
            except Exception:pass
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server=None
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
        self.thread=None


def chrome_launch_command(identity):
    """Explicit user action only. Launch known Chrome stable, never a supplied executable."""
    identity=connector_identity(identity)
    if identity.get('channel_label') not in ('Chrome Stable','Chrome \u7a33\u5b9a\u7248'):
        raise ConnectorError('One-click launch currently supports explicitly selected Chrome Stable only')
    directory=identity.get('profile_directory','')
    if not re.fullmatch(r'Default|Profile [0-9]{1,6}',directory):raise ConnectorError('Configure the Profile directory first')
    if os.name=='nt':
        roots=[Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/User Data']
        candidates=[Path(os.environ.get(k,''))/'Google/Chrome/Application/chrome.exe'
                    for k in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA')]
    elif sys.platform=='darwin':
        roots=[Path.home()/'Library/Application Support/Google/Chrome']
        candidates=[Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                    Path.home()/'Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    else:
        roots=[Path.home()/'.config/google-chrome']
        candidates=[Path(x) for x in ('/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/opt/google/chrome/google-chrome')]
    p=Path(identity.get('profile_path') or '')
    if not p.is_dir() or p.is_symlink() or p.resolve().parent!=roots[0].resolve() or p.name!=directory:
        raise ConnectorError('Only an existing Profile in this computer\'s standard Chrome Stable data directory can be launched')
    executable=next((x for x in candidates if x.is_file()),None)
    if executable is None:raise ConnectorError('Chrome Stable executable was not found')
    return [str(executable),'--profile-directory='+directory,'https://www.facebook.com/']


class SingleInstanceGuard:
    """Version-independent OS lock + authenticated loopback activation (no Qt required).
    The OS releases the file lock on crash. Never deletes another process's lock file.
    """
    def __init__(self, directory=None):
        if directory is None:
            if os.environ.get('POM_INSTANCE_DIR'):directory=Path(os.environ['POM_INSTANCE_DIR'])
            elif os.name=='nt':directory=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'PageOperationsMonitorRuntime'
            elif sys.platform=='darwin':directory=Path.home()/'Library/Application Support/PageOperationsMonitorRuntime'
            else:directory=Path.home()/'.local/state/PageOperationsMonitorRuntime'
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock_file=None;self.primary=False;self.socket=None;self.thread=None
        self.commands=queue.Queue();self.stopping=threading.Event();self.token=''

    def acquire(self):
        path=self.directory/'desktop.lock'
        if path.is_symlink():raise ConnectorError('Unsafe single-instance lock path')
        self.lock_file=open(path,'a+b')
        self.lock_file.seek(0,2)
        if self.lock_file.tell()==0:self.lock_file.write(b'0');self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lock_file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close();self.lock_file=None
            return False
        self.primary=True
        try:
            self.socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            self.socket.bind(('127.0.0.1',0));self.socket.listen(4);self.socket.settimeout(.3)
            self.token=secrets.token_urlsafe(32)
            bc_atomic(self.directory/'desktop.json',{'pid':os.getpid(),'port':self.socket.getsockname()[1],'token':self.token})
            self.thread=threading.Thread(target=self._listen,name='POM-activate',daemon=True);self.thread.start()
            return True
        except Exception:
            self.close();raise

    def _listen(self):
        while not self.stopping.is_set():
            try:conn,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:break
            try:
                with conn:
                    conn.settimeout(1);buf=b''
                    while b'\n' not in buf and len(buf)<1024:
                        chunk=conn.recv(1024-len(buf))
                        if not chunk:break
                        buf+=chunk
                    data=json.loads(buf.decode('utf-8').strip())
                    if data.get('action')=='show' and secrets.compare_digest(str(data.get('token') or ''),self.token):
                        self.commands.put('show');conn.sendall(b'OK\n')
                    else:conn.sendall(b'DENIED\n')
            except (OSError,ValueError,AttributeError):pass

    def activate_existing(self, timeout=10):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:
                path=self.directory/'desktop.json'
                if path.stat().st_size>4096:raise ValueError('Invalid instance descriptor')
                data=json.loads(path.read_text('utf-8'))
                if os.name=='nt':
                    try:
                        import ctypes
                        ctypes.windll.user32.AllowSetForegroundWindow(int(data['pid']))
                    except Exception:pass
                with socket.create_connection(('127.0.0.1',int(data['port'])),timeout=1) as conn:
                    conn.sendall((json.dumps({'action':'show','token':data['token']})+'\n').encode())
                    if conn.recv(16).startswith(b'OK'):return True
            except (OSError,ValueError,KeyError,TypeError):pass
            time.sleep(.15)
        return False

    def take_activation(self):
        found=False
        while True:
            try:self.commands.get_nowait();found=True
            except queue.Empty:return found

    def close(self):
        self.stopping.set()
        if self.socket:
            try:self.socket.close()
            except OSError:pass
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
        if self.primary and self.lock_file:
            try:
                descriptor=self.directory/'desktop.json'
                if descriptor.exists():descriptor.unlink()
            except OSError:pass
            try:
                self.lock_file.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.lock_file.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file.fileno(),fcntl.LOCK_UN)
            finally:self.lock_file.close()
        self.primary=False;self.lock_file=None

def connector_record(row, payload, purpose='monitor'):
    """Validate a connector observation, then reuse the desktop's existing parsers.
    No content returned by Chrome is executed by Python or used as a local path.
    """
    row=dict(row);pid=str(row['page_id']);stamp=time.time()
    result={'page_id':pid,'page_name':'','avatar_path':'','avatar_fresh':False,
            'metadata_ok':False,'growth_ok':False,'posts_ok':False,
            'name_error':'','growth_error':'','posts_error':'',
            'collected_ts':stamp,'collected_at':now_iso()}
    error=str(payload.get('error') or '')[:350] if isinstance(payload,dict) else 'Invalid connector result'
    if not isinstance(payload,dict) or str(payload.get('page_id'))!=pid:
        raise ConnectorError('Connector result does not belong to this Page ID')
    if payload.get('observed_url'):
        u=urlsplit(str(payload['observed_url']))
        if u.scheme!='https' or u.hostname not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'):
            raise ConnectorError('Unexpected result origin')
        if re.search(r'/(?:login|login.php|checkpoint|recover|two_factor)(?:/|$)',u.path):
            error='Facebook login/security verification is required in the selected profile'
    # Candidate order is supplied by the bundled extractor, which ports the supplied reference code.
    names=payload.get('name_candidates') or []
    if isinstance(names,list):
        for item in names[:160]:
            if not isinstance(item,dict):continue
            candidate=normalize_name(str(item.get('text') or '')[:240],pid)
            if candidate and looks_like_page_name(candidate,pid):
                result['page_name']=candidate;break
    if not result['page_name']:
        result['name_error']=error or '\u5f53\u524d\u767b\u5f55\u4f1a\u8bdd\u672a\u8fd4\u56de\u53ef\u786e\u8ba4\u7684\u4e3b\u9875\u540d\u79f0'
    image=payload.get('avatar_data')
    if isinstance(image,str) and image.startswith('data:image/png;base64,') and len(image)<300000:
        try:
            raw=base64.b64decode(image.split(',',1)[1],validate=True)
            from PIL import Image,ImageOps
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG' or im.width!=192 or im.height!=192:
                    raise ValueError('Connector avatar must be a 192px PNG')
                im.load();im=ImageOps.fit(im.convert('RGB'),(192,192))
            ensure_private_directory(AVATAR_DIR)
            target=AVATAR_DIR/(pid+'.png');temp=target.with_suffix('.connector.tmp')
            im.save(temp,format='PNG');temp.replace(target)
            result['avatar_path']=str(target);result['avatar_fresh']=True
        except Exception as exc:
            result['avatar_error']=str(exc)[:120]
    result['metadata_ok']=bool(result['page_name'] or result['avatar_fresh'])
    if purpose=='monitor' and row.get('monitor_growth'):
        text=payload.get('follower_text')
        if not isinstance(text,str) or len(text)>12000:text=''
        try:
            parsed=extract_followers_from_text(text)
            if parsed:
                count,approx,matched=parsed
                result.update(growth_ok=True,followers_count=count,approx=approx,matched_text=matched)
            else:raise ValueError('No follower statistic')
        except Exception:
            result['growth_error']=error or '\u672a\u8bfb\u5230\u53ef\u786e\u8ba4\u7684\u7c89\u4e1d\u6570\uff0c\u4e0d\u4f1a\u5199\u5165 0'
    if purpose=='monitor' and row.get('monitor_posts'):
        candidates=[]
        post_rows=payload.get('post_candidates')
        if not isinstance(post_rows,list):post_rows=[]
        for item in post_rows[:160]:
            if not isinstance(item,dict) or item.get('authored') is not True:continue
            try:
                u=urlsplit(str(item.get('url') or ''))
                if u.scheme!='https' or u.hostname not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'):continue
            except ValueError:continue
            candidates.append({'authored':True,'raw':str(item.get('raw') or '')[:180],
                               'url':str(item.get('url') or '')[:1500],
                               'source':'\u8fde\u63a5\u5668\u8bfb\u53d6\u7684\u4e3b\u9875\u81ea\u53d1\u8d34\u6587'})
        chosen=choose_post_candidate(candidates,now=stamp)
        if chosen:
            result.update(posts_ok=True,last_post_ts=chosen['ts'],post_precision_seconds=chosen['precision'],
                          post_source=chosen['source'],post_url=chosen['url'])
        else:result['posts_error']=error or '\u672a\u8bfb\u5230\u53ef\u786e\u8ba4\u7684\u81ea\u53d1\u8d34\u6587\u65f6\u95f4'
    if error:result['error']=error
    return result


def record_needs_recheck(row, record, purpose='monitor'):
    """Second-pass only for identity/post uncertainty, never merely for a growth miss."""
    row=dict(row);record=dict(record or {});pid=str(row.get('page_id') or '')
    name_ok=bool(normalize_name(record.get('page_name'),pid) or normalize_name(row.get('page_name'),pid))
    if not name_ok:
        return True
    if purpose=='monitor' and row.get('monitor_posts') and not record.get('posts_ok'):
        return True
    return False


def merge_recheck_record(first, second, row, purpose='monitor'):
    """Merge an automatic recheck without discarding a successful first observation.

    Growth data from the first pass is intentionally preserved so the corrective pass
    cannot create a second follower sample. Identity/avatar and post fields prefer the
    recheck only when it produced a confirmed value.
    """
    row=dict(row);first=dict(first or {});second=dict(second or {});out=dict(first)
    pid=str(row.get('page_id') or first.get('page_id') or second.get('page_id') or '')
    second_name=normalize_name(second.get('page_name'),pid)
    first_name=normalize_name(first.get('page_name'),pid)
    if second_name:
        out['page_name']=second_name;out['name_error']=''
    elif first_name:
        out['page_name']=first_name
    else:
        out['page_name']='';out['name_error']=str(second.get('name_error') or first.get('name_error') or '自动复检后仍未读取到可信主页名称')[:300]
    if second.get('avatar_fresh') and second.get('avatar_path'):
        out['avatar_path']=second.get('avatar_path');out['avatar_fresh']=True
    elif not out.get('avatar_path') and second.get('avatar_path'):
        out['avatar_path']=second.get('avatar_path')
    out['metadata_ok']=bool(normalize_name(out.get('page_name'),pid) or out.get('avatar_path'))

    # Keep the first successful growth sample exactly as-is.
    for key in ('growth_ok','followers_count','approx','matched_text','growth_error'):
        if key in first:out[key]=first[key]

    if purpose=='monitor' and row.get('monitor_posts'):
        if second.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url'):
                if key in second:out[key]=second[key]
            out['posts_error']=''
        elif first.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url','posts_error'):
                if key in first:out[key]=first[key]
        else:
            out['posts_ok']=False
            detail=str(second.get('posts_error') or first.get('posts_error') or '未读取到可确认的主页自发贴文时间')
            out['posts_error']=(detail+'；已自动复检一次仍无法确认')[:300]
    out['rechecked']=True
    out['recheck_ok']=not record_needs_recheck(row,out,purpose)
    out['collected_ts']=max(float(first.get('collected_ts') or 0),float(second.get('collected_ts') or 0),time.time())
    out['collected_at']=now_iso()
    if out.get('recheck_ok'):
        out.pop('error',None)
    return out


# ========== PyQt6 dashboard and application ==========
import sys
import uuid

# When double-clicking on Windows, missing packages would otherwise flash a
# console briefly and disappear; show an actionable native message instead.
try:
    import PyQt6
except ModuleNotFoundError as exc:
    message = (
        "缺少 PyQt6 图形界面依赖。\n\n请在命令行运行：\n"
        "python -m pip install PyQt6 Pillow\n"
        ""
        "安装后再启动 Page_Operations_Monitor_1.5.0.pyw。"
    )
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE + " · 依赖未安装", 0x10)
        except Exception:
            pass
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    raise SystemExit(1) from exc

from PyQt6.QtCore import (
    QObject, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QSettings, QThread, QTimer, QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPalette,
    QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSizeGrip, QSpinBox, QGraphicsDropShadowEffect,
    QStackedWidget, QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QToolTip, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QTabWidget,
    QStyledItemDelegate, QStyleOptionViewItem, QAbstractSpinBox, QProxyStyle, QProgressBar,
)

# Focused palettes. Blue-Orange Obsidian is the default theme.
THEME_PRESETS = {
    "石墨黑": dict(bg="#10151C",sidebar="#0D1117",panel="#19222D",panel_2="#253343",
        border="#35495E",text="#EEF4FC",muted="#9CAFBF",accent="#8280FF",green="#40D6AC",
        red="#F87186",amber="#F8BC65",cyan="#5CBEDC",input="#141D27",hover="#2D3F52",soft="#303153",light=False),
    "蓝橙曜石": dict(bg="#071421",sidebar="#06101B",panel="#0C2032",panel_2="#14314A",
        border="#244D68",text="#F3F7FB",muted="#93AFC2",accent="#2F86F6",green="#2CD5A7",
        red="#F06475",amber="#FF9F43",cyan="#47C4E8",input="#0A1B2A",hover="#173A55",soft="#173654",light=False),
    "清爽白": dict(bg="#F5F7FA",sidebar="#FFFFFF",panel="#FFFFFF",panel_2="#F1F4F8",
        border="#D7DEE8",text="#1E293B",muted="#66758A",accent="#356DF3",green="#16866A",
        red="#D9485F",amber="#C67B1B",cyan="#187FA8",input="#FFFFFF",hover="#EAF0F7",soft="#E6EEFF",light=True),
    "护眼绿": dict(bg="#EEF3EA",sidebar="#E5EDE1",panel="#F8FBF5",panel_2="#EAF2E5",
        border="#C6D6BF",text="#26332A",muted="#66766A",accent="#3D7D5A",green="#2E8A58",
        red="#C94E5C",amber="#B9792E",cyan="#3B7F88",input="#FFFFFF",hover="#DEE9D9",soft="#D4E6D5",light=True),
}
BG = THEME_PRESETS["蓝橙曜石"]["bg"]
SIDEBAR = THEME_PRESETS["蓝橙曜石"]["sidebar"]
PANEL = THEME_PRESETS["蓝橙曜石"]["panel"]
PANEL_2 = THEME_PRESETS["蓝橙曜石"]["panel_2"]
BORDER = THEME_PRESETS["蓝橙曜石"]["border"]
TEXT = THEME_PRESETS["蓝橙曜石"]["text"]
MUTED = THEME_PRESETS["蓝橙曜石"]["muted"]
ACCENT = THEME_PRESETS["蓝橙曜石"]["accent"]
GREEN = THEME_PRESETS["蓝橙曜石"]["green"]
RED = THEME_PRESETS["蓝橙曜石"]["red"]
AMBER = THEME_PRESETS["蓝橙曜石"]["amber"]
CYAN = THEME_PRESETS["蓝橙曜石"]["cyan"]



def paint_brand(p, rect):
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
    grad=QLinearGradient(x,y,x+w,y+h)
    grad.setColorAt(0,QColor("#6864F5"));grad.setColorAt(1,QColor("#2ECBBC"))
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(grad)
    p.drawRoundedRect(rect,w*.28,h*.28)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#FFFFFF"),w*.055,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    path=QPainterPath();path.moveTo(x+w*.2,y+h*.64);path.lineTo(x+w*.39,y+h*.46)
    path.lineTo(x+w*.55,y+h*.59);path.lineTo(x+w*.78,y+h*.3)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor("#FFFFFF"))
    for xx,yy in ((.2,.64),(.39,.46),(.55,.59),(.78,.3)):
        p.drawEllipse(QPointF(x+w*xx,y+h*yy),w*.042,w*.042)
    p.restore()


def ui_icon(kind,color=None):
    color=color or MUTED
    pm=QPixmap(64,64);pm.fill(Qt.GlobalColor.transparent)
    p=QPainter(pm);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color),3.1,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x1,y1,x2,y2):p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    if kind=="home":
        path=QPainterPath();path.moveTo(10,29);path.lineTo(32,11);path.lineTo(54,29)
        path.moveTo(17,25);path.lineTo(17,53);path.lineTo(47,53);path.lineTo(47,25)
        path.moveTo(27,53);path.lineTo(27,38);path.lineTo(37,38);path.lineTo(37,53);p.drawPath(path)
    elif kind in ("pages","id"):
        p.drawRoundedRect(QRectF(10,13,44,40),7,7)
        p.drawEllipse(QRectF(17,22,10,10));p.drawArc(QRectF(15,32,14,13),0,180*16)
        line(35,24,47,24);line(35,33,47,33);line(35,42,44,42)
    elif kind in ("history","trend"):
        line(12,10,12,53);line(12,53,54,53)
        path=QPainterPath();path.moveTo(20,42);path.lineTo(31,30);path.lineTo(40,34);path.lineTo(52,16);p.drawPath(path)
    elif kind in ("bell","alert"):
        path=QPainterPath();path.moveTo(15,45);path.quadTo(21,38,21,27)
        path.cubicTo(21,10,43,10,43,27);path.quadTo(43,38,49,45);path.closeSubpath();p.drawPath(path)
        p.drawArc(QRectF(26,45,12,12),180*16,180*16)
    elif kind=="browser":
        p.drawRoundedRect(QRectF(10,15,44,32),6,6);line(10,24,54,24)
        p.drawEllipse(QRectF(17,18,2,2));p.drawEllipse(QRectF(23,18,2,2));line(22,53,42,53);line(32,47,32,53)
    elif kind=="theme":
        p.drawEllipse(QRectF(12,12,40,40));p.drawEllipse(QRectF(22,20,7,7));p.drawEllipse(QRectF(34,18,7,7));p.drawEllipse(QRectF(40,31,7,7));line(24,43,33,43)
    elif kind=="settings":
        p.drawEllipse(QRectF(21,21,22,22));p.drawEllipse(QRectF(29,29,6,6))
        for angle in range(0,360,45):
            a=math.radians(angle);line(32+15*math.cos(a),32+15*math.sin(a),32+23*math.cos(a),32+23*math.sin(a))
    elif kind=="update":
        p.drawArc(QRectF(13,13,38,38),30*16,290*16);line(48,9,51,25);line(51,25,36,22)
    elif kind=="info":
        p.drawEllipse(QRectF(11,11,42,42));line(32,30,32,44);line(31,22,33,22)
    elif kind=="clock":
        p.drawEllipse(QRectF(11,11,42,42));line(32,21,32,33);line(32,33,41,38)
    elif kind=="people":
        p.drawEllipse(QRectF(16,13,15,15));p.drawEllipse(QRectF(37,17,11,11))
        p.drawArc(QRectF(11,33,26,24),0,180*16);p.drawArc(QRectF(35,35,19,18),0,180*16)
    elif kind=="play":
        path=QPainterPath();path.moveTo(23,14);path.lineTo(49,32);path.lineTo(23,50);path.closeSubpath();p.drawPath(path)
    elif kind=="pause":
        line(25,16,25,48);line(40,16,40,48)
    elif kind=="more":
        p.setBrush(QColor(color));p.setPen(Qt.PenStyle.NoPen)
        for yy in (17,32,47):p.drawEllipse(QPointF(32,yy),2.8,2.8)
    elif kind=="close":line(20,20,44,44);line(44,20,20,44)
    elif kind=="min":line(19,33,45,33)
    elif kind=="max":p.drawRoundedRect(QRectF(18,18,28,28),2,2)
    else:
        p.drawRoundedRect(QRectF(14,12,36,42),6,6)
        line(23,24,41,24);line(23,33,41,33);line(23,42,35,42)
    p.end();return QIcon(pm)


def icon_button(kind,tip,parent=None,size=40):
    b=QPushButton(parent);b.setObjectName("TopIconButton")
    b.setIcon(ui_icon(kind));b.setIconSize(QSize(21,21));b.setFixedSize(size,size)
    b.setCursor(Qt.CursorShape.PointingHandCursor);b.setToolTip(tip)
    b.setAccessibleName(tip);b.setProperty("iconKind",kind)
    return b


class ElideLabel(QLabel):
    def __init__(self,text="",parent=None):
        super().__init__(str(text),parent)
        self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)
    def paintEvent(self,event):
        p=QPainter(self);p.setFont(self.font());p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        p.drawText(self.contentsRect(),self.alignment(),
            self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(0,self.contentsRect().width())))
        p.end()


class ValueLabel(ElideLabel):
    """Numeric labels shrink locally instead of increasing a grid's minimum width."""
    def __init__(self,text="",large=22,parent=None):
        super().__init__(text,parent);self.large=large;self.setMinimumHeight(28)
    def paintEvent(self,event):
        p=QPainter(self);font=QFont(self.font());font.setBold(True)
        for px in range(self.large,12,-1):
            font.setPixelSize(px);p.setFont(font)
            if p.fontMetrics().horizontalAdvance(self.text())<=self.contentsRect().width():break
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        p.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,self.contentsRect().width()))
        p.end()


class DirectNumberSpinBox(QSpinBox):
    """Compact numeric field: click selects the value; valid typing commits via valueChanged."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(True)
        self.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
    def focusInEvent(self,event):
        super().focusInEvent(event);QTimer.singleShot(0,self.selectAll)
    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:QTimer.singleShot(0,self.selectAll)


class CheckDelegate(QStyledItemDelegate):
    """Centered indicator with full-cell hit testing and one integer state write per click."""
    @staticmethod
    def checked(value):
        return getattr(value, "value", value) == Qt.CheckState.Checked.value

    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight) if selected else option.palette.color(QPalette.ColorRole.AlternateBase if index.row()%2 else QPalette.ColorRole.Base))
        checked = self.checked(index.data(Qt.ItemDataRole.CheckStateRole))
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled and index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        label = ("\u5f00\u542f" if checked else "\u5173\u95ed") if index.column() else ""
        box, space = 19, 7 if label else 0
        text_width = option.fontMetrics.horizontalAdvance(label) if label else 0
        total = box + space + text_width
        left = option.rect.left() + max(2, (option.rect.width()-total)//2)
        rect = QRect(left, option.rect.center().y()-box//2, box, box)
        painter.setOpacity(1.0 if enabled else .5)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(ACCENT if checked else MUTED), 1))
        painter.setBrush(QColor(ACCENT) if checked else option.palette.color(QPalette.ColorRole.Base))
        painter.drawRoundedRect(QRectF(rect), 4, 4)
        if checked:
            painter.setPen(QPen(QColor("#FFFFFF"),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath();path.moveTo(rect.x()+4,rect.y()+9);path.lineTo(rect.x()+8,rect.y()+13);path.lineTo(rect.x()+15,rect.y()+5)
            painter.drawPath(path)
        if label:
            painter.setPen(QColor(TEXT if checked else MUTED));painter.setFont(option.font)
            text_rect=QRect(left+box+space,option.rect.top(),text_width+1,option.rect.height())
            painter.drawText(text_rect,Qt.AlignmentFlag.AlignCenter,label)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        flags=index.flags()
        if not (flags & Qt.ItemFlag.ItemIsEnabled and flags & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        kind=event.type()
        if kind in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonDblClick):
            if event.button()!=Qt.MouseButton.LeftButton:return False
            self._skip_release = kind==QEvent.Type.MouseButtonDblClick
            return option.rect.contains(event.position().toPoint())
        if kind==QEvent.Type.MouseButtonRelease:
            if event.button()!=Qt.MouseButton.LeftButton:return False
            if getattr(self,"_skip_release",False):
                self._skip_release=False;return True
            if not option.rect.contains(event.position().toPoint()):return False
        elif kind==QEvent.Type.KeyPress:
            if event.key() not in (Qt.Key.Key_Space,Qt.Key.Key_Select):return False
            if event.isAutoRepeat():return True
        else:
            return False
        value = Qt.CheckState.Unchecked.value if self.checked(index.data(Qt.ItemDataRole.CheckStateRole)) else Qt.CheckState.Checked.value
        return bool(model.setData(index, value, Qt.ItemDataRole.CheckStateRole))


class SortItem(QTableWidgetItem):
    def __init__(self,text="",key=None):
        super().__init__(str(text));self.sort_key=key if key is not None else str(text).casefold()
    def __lt__(self,other):
        a=self.sort_key;b=getattr(other,"sort_key",other.text().casefold())
        try:return a<b
        except TypeError:return str(a)<str(b)


_EMBEDDED_APP_ICON_PNG = (
    "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"
    "YII="
)

def make_app_icon():
    """Application/window/taskbar/tray icon. Works with external assets or standalone source."""
    for relative in ("PageOperationsMonitor.ico", "assets/icons/PageOperationsMonitor.ico",
                     "assets/icons/PageOperationsMonitor.png",
                     "assets/icons/PageOperationsMonitor.icns"):
        for path in asset_candidates(relative):
            if path.is_file():
                icon = QIcon(str(path))
                if not icon.isNull():
                    return icon
    pm = QPixmap()
    try:
        pm.loadFromData(base64.b64decode(_EMBEDDED_APP_ICON_PNG))
    except Exception:
        pass
    if not pm.isNull():
        icon = QIcon()
        for size in (16,20,24,32,40,48,64,128,256):
            icon.addPixmap(pm.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        return icon
    icon = QIcon()
    for size in (16,20,24,32,48,64,128,256):
        pm = QPixmap(size,size);pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm);paint_brand(painter,QRectF(1,1,size-2,size-2));painter.end()
        icon.addPixmap(pm)
    return icon



class ToastNotice(QFrame):
    """One non-modal, click-through notice centered below the middle of its parent window."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ToastNotice")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self);layout.setContentsMargins(20,13,20,13);layout.setSpacing(10)
        self.icon = QLabel();self.icon.setFixedSize(22,22);layout.addWidget(self.icon)
        self.message = QLabel();self.message.setObjectName("ToastMessage")
        self.message.setTextFormat(Qt.TextFormat.PlainText);self.message.setWordWrap(True)
        layout.addWidget(self.message,1)
        self.timer = QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.hide)
        shadow=QGraphicsDropShadowEffect(self);shadow.setBlurRadius(22);shadow.setOffset(0,4);shadow.setColor(QColor(0,0,0,165))
        self.setGraphicsEffect(shadow)
        self.hide()

    def show_message(self, text, duration_ms=3600):
        self.timer.stop()
        self.icon.setPixmap(ui_icon("info","#725015").pixmap(20,20))
        self.message.setText(str(text))
        self.setStyleSheet(
            "QFrame#ToastNotice {background:#FFF1C2;border:2px solid #F2BE49;border-radius:14px;}"
            "QLabel#ToastMessage {color:#142033;font-size:14px;font-weight:650;background:transparent;border:0;}"
            "QLabel {background:transparent;border:0;}")
        parent = self.parentWidget()
        available = max(220, parent.width()-64)
        natural = self.message.fontMetrics().horizontalAdvance(str(text)) + 72
        self.setFixedWidth(min(available,560,max(260,natural)))
        self.adjustSize()
        self.reposition();self.show();self.raise_()
        self.timer.start(_bounded_int(duration_ms,3600,3000,4000))

    def reposition(self):
        parent=self.parentWidget()
        if parent:
            self.move(*toast_position(parent.width(),parent.height(),self.width(),self.height()))


def show_hint(owner, message, duration_ms=3600):
    """Route brief messages from subpages/dialogs to the application's single toast."""
    target = owner
    while target is not None:
        handler = getattr(target,"show_toast",None)
        if callable(handler):
            handler(str(message),duration_ms)
            return
        target = target.parentWidget() if isinstance(target,QWidget) else None
    window = owner.window() if isinstance(owner,QWidget) else QApplication.activeWindow()
    if window:
        if not hasattr(window,"_local_hint"):
            window._local_hint = ToastNotice(window)
        window._local_hint.show_message(str(message),duration_ms)


class LoginWorker(QObject):
    status = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.profile_dir = monitor_profile_dir()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()


    def run(self):
        try:
            with BrowserCollector(profile_dir=self.profile_dir, show_browser=True) as collector:
                tab = collector.login_interactive()
                self.status.emit("已打开默认专用浏览器，请手动登录 Facebook；登录成功后关闭该窗口，再返回软件巡检。")
                while not self._stop.wait(0.4):
                    try:
                        if tab.is_closed():
                            break
                    except Exception:
                        break
                self.finished.emit("浏览器已关闭；如果你已完成脸书登录，登录会话已保存在默认专用浏览器资料中。")
        except Exception as exc:
            self.finished.emit("登录浏览器失败：" + str(exc)[:240])


class PersistentMonitorAlert(QDialog):
    """High-visibility business alert that never auto-closes."""
    def __init__(self, entries, owner, stack_index=0):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.owner=owner;self.entries=list(entries);self.stack_index=max(0,int(stack_index));self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True);self.setModal(False);self.setStyleSheet(owner.styleSheet())
        self.setWindowTitle('主页监控预警');self.setWindowIcon(make_app_icon());self.setMinimumWidth(450);self.setMaximumWidth(540)
        outer=QVBoxLayout(self);outer.setContentsMargins(10,10,10,10);panel=QFrame();panel.setObjectName('MonitorAlertPopup');outer.addWidget(panel)
        root=QVBoxLayout(panel);root.setContentsMargins(18,15,18,16);root.setSpacing(11)
        head=QHBoxLayout();symbol=QLabel('!');symbol.setObjectName('MonitorAlertSymbol');symbol.setFixedSize(34,34);symbol.setAlignment(Qt.AlignmentFlag.AlignCenter);head.addWidget(symbol)
        head_text=QVBoxLayout();head_text.setSpacing(0);title=QLabel('主页监控预警');title.setObjectName('MonitorAlertHeadline');head_text.addWidget(title)
        subtitle=QLabel('需要处理 · 此窗口不会自动关闭');subtitle.setObjectName('SmallMuted');head_text.addWidget(subtitle);head.addLayout(head_text);head.addStretch()
        close=QPushButton('×');close.setObjectName('AlertCloseButton');close.setFixedSize(32,32);close.clicked.connect(self.close);head.addWidget(close);root.addLayout(head)
        for entry in self.entries[:5]:
            row=QFrame();row.setObjectName('MonitorAlertRow');hl=QHBoxLayout(row);hl.setContentsMargins(10,9,10,9);hl.setSpacing(12)
            hl.addWidget(AvatarWidget(entry.get('name') or entry.get('page_name',''),entry.get('avatar_path',''),56,page_id=entry.get('page_id','')),0,Qt.AlignmentFlag.AlignTop)
            texts=QVBoxLayout();texts.setSpacing(4);page_name=entry.get('name') or entry.get('page_name') or '名称待获取';name=ElideLabel(page_name)
            name.setObjectName('MonitorAlertName');name.setMinimumHeight(22);name.setToolTip(page_name);texts.addWidget(name)
            meta=QHBoxLayout();event='发帖时间超标' if entry.get('kind')=='post' else '粉丝增长超标';badge=QLabel(event);badge.setObjectName('MonitorAlertEvent')
            badge.setProperty('kind',entry.get('kind','growth'));badge.setMaximumWidth(118);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);meta.addWidget(badge);meta.addStretch();texts.addLayout(meta)
            message=QLabel(str(entry.get('message') or ''));message.setWordWrap(True);message.setObjectName('MonitorAlertMessage');texts.addWidget(message);hl.addLayout(texts,1);root.addWidget(row)
        if len(self.entries)>5:
            more=QLabel(f'另有 {len(self.entries)-5} 条预警，请进入通知列表查看。');more.setObjectName('SmallMuted');root.addWidget(more)
        actions=QHBoxLayout();actions.addStretch();view=QPushButton('查看通知');view.setObjectName('PrimaryButton');view.clicked.connect(self.open_alerts);actions.addWidget(view)
        close2=QPushButton('关闭');close2.clicked.connect(self.close);actions.addWidget(close2);root.addLayout(actions)
        self.adjustSize();QTimer.singleShot(0,self.reposition)
    def reposition(self):
        screen=QApplication.screenAt(self.owner.frameGeometry().center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry();self.adjustSize();step=min(self.stack_index,4);x=area.right()-self.width()-22-step*18;y=area.bottom()-self.height()-22-step*32
            self.move(max(area.left()+10,x),max(area.top()+10,y))
    def open_alerts(self):
        self.owner.open_alert_notification(self.entries[0] if self.entries else {});self.close()


class CollectWorker(QObject):
    result=pyqtSignal(dict)
    progress=pyqtSignal(int,int,str)
    finished=pyqtSignal(bool,str)

    def __init__(self, pages, visible=DEFAULT_SHOW_BROWSER, gap=DEFAULT_PAGE_GAP_SECONDS,
                 profile_dir=None, purpose="monitor", gap_range=None):
        super().__init__()
        self.pages = [dict(row) for row in pages]
        self.profile_dir = Path(profile_dir) if profile_dir is not None else monitor_profile_dir()
        self.visible = is_true(visible, DEFAULT_SHOW_BROWSER)
        self.gap = _bounded_int(gap, DEFAULT_PAGE_GAP_SECONDS, 0, 120)
        self._gap_lock = threading.Lock()
        self._gap_range=(self.gap,self.gap)
        if gap_range is not None:self.set_gap_range(*gap_range)
        self.purpose = purpose
        self._stop = threading.Event()
        self._pause = threading.Event()

    def set_gap(self, seconds):
        self.set_gap_range(seconds,seconds)

    def set_gap_range(self, low, high):
        low=_bounded_int(low,DEFAULT_PAGE_GAP_MIN,0,120)
        high=_bounded_int(high,DEFAULT_PAGE_GAP_MAX,0,120)
        with self._gap_lock:
            self._gap_range=(min(low,high),max(low,high))
            self.gap=int(round((low+high)/2))

    def current_gap(self):
        with self._gap_lock:
            low,high=self._gap_range
        return random.uniform(low,high) if low!=high else float(low)

    def stop(self):
        self._stop.set();self._pause.clear()

    def toggle_pause(self):
        if self._pause.is_set():self._pause.clear()
        else:self._pause.set()
        return self._pause.is_set()

    def _wait_ready(self):
        while self._pause.is_set():
            if self._stop.wait(.12):return False
        return not self._stop.is_set()

    def run(self):
        success=0;failure=0;total=len(self.pages);aborted=False
        try:
            with BrowserCollector(self.profile_dir,self.visible) as collector:
                for index,row in enumerate(self.pages,1):
                    if not self._wait_ready():aborted=True;break
                    self.progress.emit(index,total,("同步资料 " if self.purpose=="metadata" else "巡检 ")+display_name(row))
                    try:
                        record=collector.fetch_page(row,purpose=self.purpose)
                    except Exception as exc:
                        record={"page_id":row["page_id"],"error":str(exc)[:260],
                                "growth_ok":False,"posts_ok":False,"metadata_ok":False}
                    if record_needs_recheck(row,record,self.purpose) and not self._stop.is_set():
                        self.progress.emit(index,total,"自动复检 "+display_name(row))
                        try:
                            retry=collector.fetch_page(row,purpose=self.purpose)
                        except Exception as exc:
                            retry={"page_id":row["page_id"],"error":str(exc)[:260],
                                   "growth_ok":False,"posts_ok":False,"metadata_ok":False}
                        record=merge_recheck_record(record,retry,row,self.purpose)
                    checks=[]
                    if self.purpose=="metadata":checks=[bool(record.get("metadata_ok"))]
                    else:
                        if row.get("monitor_growth"):checks.append(bool(record.get("growth_ok")))
                        if row.get("monitor_posts"):checks.append(bool(record.get("posts_ok")))
                    good=bool(checks and all(checks))
                    record["ok"]=good;record["purpose"]=self.purpose
                    self.result.emit(record)
                    if good:success+=1
                    else:failure+=1
                    self.progress.emit(index,total,f"已完成 {index} / {total}")
                    if index<total:
                        remaining=self.current_gap()
                        while remaining>0:
                            if not self._wait_ready():aborted=True;break
                            tick=min(.2,remaining)
                            if self._stop.wait(tick):aborted=True;break
                            remaining-=tick
                        if aborted:break
            task="资料同步" if self.purpose=="metadata" else "主页巡检"
            self.finished.emit(not aborted and failure==0,
                f"{task}{'已停止' if aborted else '完成'} · 完整成功 {success} / 部分或失败 {failure} / 共 {total}")
        except Exception as exc:
            self.finished.emit(False,"任务异常："+str(exc)[:300])


class ConnectorCollectWorker(CollectWorker):
    """Distribute one round across up to 10 connector browsers and auto-recheck ambiguity.

    A name/post result that cannot be confirmed is retried once.  When another selected
    browser is online the recheck prefers that browser; with only one browser it retries
    the same connector.  A successful first-pass follower observation is preserved so the
    corrective pass never creates a duplicate follower sample.
    """
    def __init__(self,pages,bridge,instance_ids,gap=8,purpose='monitor',gap_range=None):
        super().__init__(pages,gap=gap,purpose=purpose,gap_range=gap_range)
        if isinstance(instance_ids,str):instance_ids=[instance_ids]
        self.bridge=bridge;self.instance_ids=list(dict.fromkeys(str(x) for x in instance_ids if x))[:10]

    def _record_good(self,row,record):
        checks=[]
        if self.purpose=='metadata':checks=[bool(record.get('metadata_ok'))]
        else:
            if row.get('monitor_growth'):checks.append(bool(record.get('growth_ok')))
            if row.get('monitor_posts'):checks.append(bool(record.get('posts_ok')))
        return bool(checks and all(checks))

    def _recheck_connector(self,source_cid):
        online=[cid for cid in self.instance_ids if self.bridge.online(cid)]
        others=[cid for cid in online if cid!=source_cid]
        if others:return random.choice(others)
        return source_cid if source_cid in online else (online[0] if online else '')

    def run(self):
        total=len(self.pages);success=0;failure=0;finalized=0
        if not self.instance_ids:
            self.finished.emit(False,'没有可用浏览器连接器');return
        online=[cid for cid in self.instance_ids if self.bridge.online(cid)]
        if not online:
            self.finished.emit(False,'连接器中断：所有已选择浏览器均已离线');return
        self.instance_ids=online
        if total < len(self.instance_ids):
            self.finished.emit(False,f'任务数 {total} 少于当前在线连接器 {len(self.instance_ids)} 个，请减少连接器');return

        pages=list(self.pages);random.shuffle(pages)
        workq=queue.Queue();outq=queue.Queue();threads=[]
        initial={cid:pages[i] for i,cid in enumerate(self.instance_ids)}
        for row in pages[len(self.instance_ids):]:workq.put(row)
        remaining={'count':total};lock=threading.Lock()

        def mark_done():
            with lock:remaining['count']-=1
        def remaining_count():
            with lock:return remaining['count']

        def lane_worker(cid,first_row):
            row=first_row
            try:
                while not self._stop.is_set():
                    if not self._wait_ready():break
                    if row is None:
                        if remaining_count()<=0:break
                        try:row=workq.get(timeout=.35)
                        except queue.Empty:
                            if remaining_count()<=0:break
                            if not self.bridge.online(cid):
                                outq.put(('offline',cid,'浏览器连接已断开'));break
                            continue
                    if not self.bridge.online(cid):
                        workq.put(row);row=None;outq.put(('offline',cid,'浏览器连接已断开'));break
                    try:
                        payload=self.bridge.request(cid,row,self.purpose,self._stop,timeout=120)
                        if self._stop.is_set():
                            workq.put(row);row=None;break
                        record=connector_record(row,payload,self.purpose)
                    except ConnectorError as exc:
                        if not self.bridge.online(cid):
                            workq.put(row);row=None;outq.put(('offline',cid,str(exc)));break
                        record={'page_id':row['page_id'],'error':str(exc),'growth_ok':False,'posts_ok':False,'metadata_ok':False,
                                'name_error':str(exc),'posts_error':str(exc)}
                    mark_done();outq.put(('result',cid,dict(row),record));row=None
                    if remaining_count()<=0:break
                    remaining_wait=self.current_gap()
                    while remaining_wait>0 and not self._stop.is_set():
                        if not self._wait_ready():break
                        tick=min(.2,remaining_wait)
                        if self._stop.wait(tick):break
                        remaining_wait-=tick
            finally:outq.put(('done',cid))

        for cid in self.instance_ids:
            t=threading.Thread(target=lane_worker,args=(cid,initial[cid]),name='POM-connector-'+cid[:8],daemon=True)
            threads.append(t);t.start()

        done=0;offline=set();first_seen=0;rechecks=[]
        while done<len(threads):
            try:item=outq.get(timeout=.25)
            except queue.Empty:
                if not any(t.is_alive() for t in threads):break
                continue
            kind=item[0]
            if kind=='done':done+=1;continue
            if kind=='offline':offline.add(item[1]);continue
            _,cid,row,record=item;first_seen+=1
            if record_needs_recheck(row,record,self.purpose) and not self._stop.is_set():
                rechecks.append((cid,row,record))
                self.progress.emit(first_seen,total,f'首检 {first_seen} / {total} · 待自动复检')
                continue
            good=self._record_good(row,record);record['ok']=good;record['purpose']=self.purpose
            self.result.emit(record);finalized+=1
            if good:success+=1
            else:failure+=1
            self.progress.emit(first_seen,total,f'并行巡检 {first_seen} / {total}')

        for t in threads:t.join(timeout=1)

        # Recheck only the ambiguous subset. Prefer another browser when possible.
        for source_cid,row,first in rechecks:
            if self._stop.is_set():break
            target=self._recheck_connector(source_cid)
            second={'page_id':row['page_id'],'metadata_ok':False,'growth_ok':False,'posts_ok':False}
            if target:
                retry_row=dict(row)
                retry_purpose='metadata'
                if self.purpose=='monitor' and row.get('monitor_posts') and not first.get('posts_ok'):
                    retry_purpose='monitor';retry_row['monitor_growth']=False;retry_row['monitor_posts']=True
                try:
                    self.progress.emit(finalized+1,total,'自动复检 '+display_name(row)+(' · 换浏览器' if target!=source_cid else ' · 当前浏览器'))
                    payload=self.bridge.request(target,retry_row,retry_purpose,self._stop,timeout=120)
                    second=connector_record(retry_row,payload,retry_purpose)
                except ConnectorError as exc:
                    second.update(error=str(exc),name_error=str(exc),posts_error=str(exc))
            merged=merge_recheck_record(first,second,row,self.purpose)
            merged['recheck_connector_changed']=bool(target and target!=source_cid)
            good=self._record_good(row,merged);merged['ok']=good;merged['purpose']=self.purpose
            self.result.emit(merged);finalized+=1
            if good:success+=1
            else:failure+=1

        aborted=self._stop.is_set() and finalized<total
        if finalized<total and not aborted:
            active=[cid for cid in self.instance_ids if self.bridge.online(cid)]
            if not active:
                self.finished.emit(False,f'连接器中断：所有已选择浏览器均已离线，当前轮次已停止 · 已处理 {finalized}/{total}');return
            self.finished.emit(False,f'浏览器连接异常，本轮未完成 · 已处理 {finalized}/{total}');return
        task='资料同步' if self.purpose=='metadata' else '主页巡检'
        extra=f' · {len(offline)} 个浏览器中途离线' if offline else ''
        if rechecks:extra+=f' · 自动复检 {len(rechecks)} 个主页'
        self.finished.emit(not aborted and failure==0 and finalized==total,
            f"{task}{'已停止' if aborted else '完成'} · 完整成功 {success} / 部分或失败 {failure} / 共 {total} · 使用 {len(self.instance_ids)} 个浏览器{extra}")


class BrowserConnectionsDialog(QDialog):
    """Zero-configuration connector view. Checkboxes auto-save; no pairing step."""
    def __init__(self, owner):
        super().__init__(owner);self.owner=owner;self.bridge=owner.connector
        self.setWindowTitle('浏览器连接');self.resize(650,390)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,18,22,18);layout.setSpacing(10)
        title=QLabel('浏览器连接');title.setObjectName('DialogTitle');layout.addWidget(title)
        hint=QLabel('1 个在线浏览器自动使用；多个在线浏览器可勾选一个或多个并行巡检，修改后自动保存。')
        hint.setWordWrap(True);hint.setObjectName('SmallMuted');layout.addWidget(hint)
        connector_bar=QHBoxLayout();connector_bar.setSpacing(8);connector_bar.addStretch()
        self.export_connector_button=QPushButton('获取连接器');self.export_connector_button.setObjectName('PrimaryButton');self.export_connector_button.clicked.connect(self.export_connector)
        self.export_connector_button.setVisible(False);connector_bar.addWidget(self.export_connector_button)
        layout.addLayout(connector_bar)
        self.summary=QLabel();self.summary.setObjectName('InfoBox');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(('使用','浏览器备注','状态'))
        self.table.verticalHeader().hide();self.table.setShowGrid(False);self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setColumnWidth(0,58);self.table.setColumnWidth(2,92)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(0,CheckDelegate(self.table));layout.addWidget(self.table,1)
        buttons=QHBoxLayout();buttons.setSpacing(8)
        all_btn=QPushButton('全选在线');all_btn.clicked.connect(self.select_all_online);buttons.addWidget(all_btn);buttons.addStretch()
        self.block_button=QPushButton('停用');self.block_button.clicked.connect(self.toggle_block);buttons.addWidget(self.block_button)
        delete=QPushButton('删除旧记录');delete.clicked.connect(self.delete_record);buttons.addWidget(delete)
        retry=QPushButton('重新检测');retry.clicked.connect(self.retry);buttons.addWidget(retry);layout.addLayout(buttons)
        self.rows=[];self._signature=None;self._loading=False
        self.table.itemChanged.connect(self._item_changed);self.table.itemSelectionChanged.connect(self._selection_changed)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(900);self.refresh()

    def selected_row(self):
        row=self.table.currentRow();return self.rows[row] if 0<=row<len(self.rows) else None

    def checked_ids(self):
        out=[]
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.checkState()==Qt.CheckState.Checked:
                cid=str(item.data(Qt.ItemDataRole.UserRole) or '')
                if cid:out.append(cid)
        return out

    def _selection_changed(self):
        row=self.selected_row();self.block_button.setText('启用' if row and row.get('blocked') else '停用')

    def _persist_checks(self):
        rows={r['instance_id']:r for r in self.rows};ids=[cid for cid in self.checked_ids() if cid in rows and rows[cid]['online'] and not rows[cid].get('blocked')]
        if len(ids)>10:ids=ids[:10]
        self.owner.set_connector_selection(ids,initialized=True)

    def _item_changed(self,item):
        if self._loading or item.column()!=0:return
        ids=self.checked_ids();online=[r for r in self.rows if r['online'] and not r.get('blocked')]
        if len(ids)>10:
            self._loading=True;item.setCheckState(Qt.CheckState.Unchecked);self._loading=False;show_hint(self,'最多同时使用 10 个浏览器连接器');return
        if len(online)>1 and not ids:
            self._loading=True;item.setCheckState(Qt.CheckState.Checked);self._loading=False;show_hint(self,'多个浏览器在线时至少保留 1 个');return
        self._persist_checks();self._signature=None;self.owner.refresh_connector_summary()

    def refresh(self):
        try:
            if not self.bridge._running:self.bridge.start()
        except Exception as exc:self.bridge.error=str(exc)
        rows=sorted(self.bridge.clients(),key=lambda r:(r.get('blocked',False),not r['online'],r['identity'].get('profile_name',''),r['instance_id']))
        # Up to 3 connections stay compact. From the 4th connection onward the dialog
        # grows with the list; 7-10 connections use a wider layout as well.
        row_count=len(rows)
        visible_rows=max(3,min(10,row_count))
        target_w=650 if row_count<=3 else (760 if row_count<=6 else 860)
        target_h=390 if row_count<=3 else 315 + visible_rows*46
        screen=self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry()
            target_w=min(target_w,max(650,int(available.width()*0.88)))
            target_h=min(target_h,max(390,int(available.height()*0.88)))
        self.table.setMinimumHeight(150 if row_count<=3 else min(500,42*visible_rows+38))
        if getattr(self,'_auto_size_rows',None)!=row_count:
            self.setMinimumSize(650,390)
            self.resize(target_w,target_h)
            self._auto_size_rows=row_count
            QTimer.singleShot(0,lambda w=target_w,h=target_h:self.resize(w,h))
        saved=set(self.owner.configured_connector_ids(include_offline=True));signature=json.dumps(rows,sort_keys=True)+json.dumps(sorted(saved))+str(self.owner.connector_selection_initialized())
        if signature==self._signature:return
        self._signature=signature;current=self.selected_row()['instance_id'] if self.selected_row() else '';self.rows=rows
        online=[r for r in rows if r['online'] and not r.get('blocked')]
        if len(online)==1:saved={online[0]['instance_id']}
        elif len(online)>1 and not self.owner.connector_selection_initialized():saved={r['instance_id'] for r in online[:10]}
        self._loading=True;self.table.blockSignals(True);self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            identity=row['identity'];cid=row['instance_id'];marker=QTableWidgetItem('')
            marker.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsUserCheckable);marker.setData(Qt.ItemDataRole.UserRole,cid)
            marker.setCheckState(Qt.CheckState.Checked if cid in saved and row['online'] and not row.get('blocked') else Qt.CheckState.Unchecked);marker.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.table.setItem(i,0,marker)
            name=identity.get('profile_name') or ('Chrome '+cid[:6])
            status='已停用' if row.get('blocked') else ('在线' if row['online'] else '离线')
            for col,text in ((1,name),(2,status)):
                cell=QTableWidgetItem(str(text));cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter);cell.setToolTip(str(text));self.table.setItem(i,col,cell)
            self.table.setRowHeight(i,42)
            if cid==current:self.table.selectRow(i)
        self.table.blockSignals(False);self._loading=False
        outdated_count=self._refresh_connector_bundle_state(rows)
        if self.bridge.error:self.summary.setText('连接服务异常：'+self.bridge.error)
        elif not online:self.summary.setText('未检测到在线连接器')
        elif outdated_count:self.summary.setText(f'{len(online)} 个浏览器在线 · {outdated_count} 个连接器版本较旧')
        elif len(online)==1:self.summary.setText('1 个浏览器在线 · 已自动使用')
        else:self.summary.setText(f'{len(online)} 个浏览器在线 · 已勾选 {len([x for x in saved if any(r["instance_id"]==x and r["online"] and not r.get("blocked") for r in rows)])} 个 · 多选时并行分配任务')
        self._selection_changed()

    def export_connector(self):
        save_bundled_connector(self)

    def _refresh_connector_bundle_state(self,rows):
        online=[r for r in rows if r.get('online') and not r.get('blocked')]
        outdated=[r for r in online if connector_needs_update(r.get('identity') or {})]
        # Keep the browser window clean: when the installed connector is current,
        # there is no download/export action here. Settings always keeps a manual export entry.
        if outdated:
            self.export_connector_button.setText('更新连接器')
            self.export_connector_button.setToolTip(f'导出内置连接器 v{BUNDLED_CONNECTOR_VERSION}')
            self.export_connector_button.setVisible(True)
        elif not online:
            self.export_connector_button.setText('获取连接器')
            self.export_connector_button.setToolTip(f'导出内置连接器 v{BUNDLED_CONNECTOR_VERSION}')
            self.export_connector_button.setVisible(True)
        else:
            self.export_connector_button.setVisible(False)
        return len(outdated)

    def select_all_online(self):
        self._loading=True
        try:
            selected=0
            for i,row in enumerate(self.rows):
                use=row['online'] and not row.get('blocked') and selected<10;self.table.item(i,0).setCheckState(Qt.CheckState.Checked if use else Qt.CheckState.Unchecked)
                if use:selected+=1
        finally:self._loading=False
        self._persist_checks();self._signature=None;self.refresh();self.owner.refresh_connector_summary()

    def identify(self):
        row=self.selected_row()
        if not row:return
        try:self.bridge.identify(row['instance_id'])
        except Exception as exc:show_hint(self,str(exc))

    def retry(self):
        self._signature=None;self.refresh();self.owner.refresh_connector_summary();show_hint(self,'正在自动检测本机浏览器连接器')

    def toggle_block(self):
        row=self.selected_row()
        if not row:return
        if row.get('blocked'):self.bridge.allow(row['instance_id']);show_hint(self,'已启用，连接器会自动重新连接')
        else:self.bridge.revoke(row['instance_id']);show_hint(self,'已停用该浏览器连接')
        self._signature=None;self.refresh();self.owner.refresh_connector_summary()

    def delete_record(self):
        row=self.selected_row()
        if not row:return
        if row.get('online') and not row.get('blocked'):show_hint(self,'请先停用该连接，再删除旧记录');return
        try:self.bridge.forget(row['instance_id'])
        except Exception as exc:show_hint(self,str(exc));return
        saved=[x for x in self.owner.configured_connector_ids(include_offline=True) if x!=row['instance_id']]
        self.owner.set_connector_selection(saved,initialized=self.owner.connector_selection_initialized())
        self._signature=None;self.refresh();show_hint(self,'旧连接记录已删除')


class BrandMark(QWidget):
    def __init__(self,size=40,parent=None):
        super().__init__(parent);self.setFixedSize(size,size)
        self.setToolTip("原创监控图形标志")
    def paintEvent(self,event):
        p=QPainter(self);paint_brand(p,QRectF(1,1,self.width()-2,self.height()-2));p.end()


class DraggableHeader(QFrame):
    """Allow dragging and double-click maximizing the custom title bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().showNormal() if self.window().isMaximized() else self.window().showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def resolve_avatar_path(page_id="", preferred=""):
    """Resolve the live page avatar first, then the shared ID cache."""
    preferred=str(preferred or "").strip()
    if preferred:
        try:
            p=Path(preferred)
            if p.is_file() and p.stat().st_size>100:return str(p)
        except OSError:pass
    pid=str(page_id or "").strip()
    if pid:
        try:
            cached=AVATAR_DIR/(pid+".png")
            if cached.is_file() and cached.stat().st_size>100:return str(cached)
        except OSError:pass
    return ""


class AvatarWidget(QWidget):
    def __init__(self, name="", path="", size=52, parent=None, page_id=""):
        super().__init__(parent)
        self.name = name or "P"
        self.path = resolve_avatar_path(page_id,path)
        self.setFixedSize(size,size)
        self.image = QPixmap(self.path) if self.path else QPixmap()
        if self.image.isNull():
            self.setToolTip("头像与 FB专业ID管理共用同一缓存；正常巡检时自动更新。")
        else:
            self.setToolTip("已缓存的真实主页头像")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0,0,self.width(),self.height())
        clip = QPainterPath(); clip.addEllipse(r.adjusted(1,1,-1,-1)); p.setClipPath(clip)
        if not self.image.isNull():
            scaled = self.image.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
            sx=(scaled.width()-self.width())//2; sy=(scaled.height()-self.height())//2
            p.drawPixmap(0,0,scaled,sx,sy,self.width(),self.height())
        else:
            g=QLinearGradient(0,0,self.width(),self.height()); g.setColorAt(0,QColor(ACCENT)); g.setColorAt(1,QColor(CYAN))
            p.fillRect(self.rect(),g)
            p.setClipping(False); p.setPen(QColor("white"))
            p.setFont(QFont("Microsoft YaHei UI",max(11,self.width()//3),QFont.Weight.DemiBold))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.name[:1].upper())
        p.setClipping(False); p.setPen(QPen(QColor(BORDER),1.1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r.adjusted(.7,.7,-.7,-.7))




class MetricCard(QFrame):
    def __init__(self,title,accent=None,kind="pages"):
        super().__init__();self.setObjectName("MetricCard");self.setProperty("tone",kind);self.setMinimumWidth(0);self.setFixedHeight(104)
        layout=QHBoxLayout(self);layout.setContentsMargins(14,12,14,12);layout.setSpacing(12)
        self.icon_label=QLabel();self.icon_label.setFixedSize(40,40)
        self.icon_label.setPixmap(ui_icon(kind,accent or ACCENT).pixmap(28,28));self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setObjectName("MetricIcon");layout.addWidget(self.icon_label)
        self.kind=kind;self.accent=accent or ACCENT
        col=QVBoxLayout();col.setSpacing(1);col.setContentsMargins(0,0,0,0)
        self.label=ElideLabel(title);self.label.setObjectName("MetricLabel");self.label.setMinimumHeight(22)
        self.value=ValueLabel("—",28);self.value.setObjectName("MetricValue");self.value.setMinimumHeight(33)
        self.note=ElideLabel("");self.note.setObjectName("SmallMuted");self.note.setMinimumHeight(18)
        col.addWidget(self.label);col.addWidget(self.value);col.addWidget(self.note);layout.addLayout(col,1)
    def set_values(self,value,note=""):
        self.value.setText(str(value));self.value.setToolTip(str(value))
        self.note.setText(str(note));self.note.setToolTip(str(note))



class CopyLabel(ElideLabel):
    def __init__(self,text="",copy_text=None,parent=None):
        super().__init__(text,parent);self.copy_text=str(text if copy_text is None else copy_text)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setToolTip(str(text)+"\n点击复制")
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            QApplication.clipboard().setText(self.copy_text)
            QToolTip.showText(event.globalPosition().toPoint(),"已复制",self)
            event.accept()
        else:super().mouseReleaseEvent(event)

class PageCard(QFrame):
    open_requested=pyqtSignal(str)
    manage_requested=pyqtSignal(str)
    def __init__(self,row,rank=0,window_label=""):
        super().__init__();self.row=dict(row);self.setObjectName("PageCard")
        self.setMinimumWidth(0);self.setFixedHeight(216)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        pid=str(row["page_id"]);name=display_name(row);post=row.get("post_view") or post_view(row)
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,10);layout.setSpacing(8)
        header=QHBoxLayout();header.setSpacing(9)
        header.addWidget(AvatarWidget(name,row.get("avatar_path",""),42,page_id=pid),0,Qt.AlignmentFlag.AlignTop)
        identity=QVBoxLayout();identity.setSpacing(2)
        title=CopyLabel(name);title.setObjectName("CardTitle");title.setMinimumHeight(22)
        title.setToolTip("专业名称："+(normalize_name(row.get("page_name"),pid) or name or "尚未获取")+"\n点击复制名称")
        ident=CopyLabel("ID  "+pid,pid);ident.setObjectName("CardId");ident.setMinimumHeight(18)
        ident.setToolTip("公共主页编号："+pid+"\n点击复制完整 ID")
        identity.addWidget(title);identity.addWidget(ident);header.addLayout(identity,1)
        menu=icon_button("more","主页操作",self,26);menu.setIconSize(QSize(18,18));menu.clicked.connect(self.show_menu)
        header.addWidget(menu,0,Qt.AlignmentFlag.AlignTop);layout.addLayout(header)

        values=QHBoxLayout();values.setSpacing(8)
        today=row.get("today") or {"delta":None,"partial":True,"note":"暂无记录"}
        specs=[
            ("当前粉丝" if row.get("monitor_growth") else "上次粉丝",
             format_compact_count(row.get("last_followers")),"BigNumber",
             "实际粉丝数："+format_count(row.get("last_followers"))+("\n粉丝监控未开启，显示最后一次已保存值" if not row.get("monitor_growth") else "")+("（约值）" if row.get("approx") else "")),
            ("今日新增",("未监控" if not row.get("monitor_growth") else
              (("≈" if today.get("approx") else "")+format_delta(today["delta"])+"")),
             "GrowthUp" if row.get("monitor_growth") and (today.get("delta") or 0)>0 else
             "GrowthDown" if row.get("monitor_growth") and (today.get("delta") or 0)<0 else "GrowthFlat",today.get("note","")),
            ("距上次发帖",post.get("elapsed_short",post["elapsed"]),
             "GrowthDown" if post["state"]=="overdue" else "GrowthSoon" if post["state"] in ("soon","unknown","unverified")
             else "GrowthUp" if post["state"]=="ok" else "GrowthFlat",post["tooltip"])
        ]
        for i,(label,text,objectname,tip) in enumerate(specs):
            col=QVBoxLayout();col.setSpacing(1)
            heading=ElideLabel(label);heading.setMinimumHeight(17);heading.setObjectName("SmallMuted")
            value=ValueLabel(text,20 if i==0 else 18);value.setObjectName(objectname);value.setToolTip(tip)
            col.addWidget(heading);col.addWidget(value);values.addLayout(col,12 if i==2 else 11 if i==0 else 9)
        layout.addLayout(values)
        modules=[]
        if row.get("monitor_growth"):modules.append("粉丝监控")
        if row.get("monitor_posts"):modules.append("发帖监控")
        module_hint=ElideLabel(" · ".join(modules) or "尚未选择监控模块")
        module_hint.setObjectName("SmallMuted");module_hint.setMinimumHeight(22)
        layout.addWidget(module_hint)
        layout.addStretch(1)

        footer=QHBoxLayout();footer.setSpacing(4)
        checked=row.get("last_inspected_at") or row.get("last_collected_at") or ""
        label=ElideLabel("最近检查 "+local_time_label(checked,False));label.setMinimumHeight(22)
        label.setToolTip(local_time_label(checked));label.setObjectName("SmallMuted");footer.addWidget(label,1)
        state="normal";status="正常"
        if not row.get("monitor_growth") and not row.get("monitor_posts"): status="未选择模块";state="off"
        elif post["state"]=="overdue":status="发帖超时";state="alert"
        elif row.get("is_growth_alert"):status="增长超标";state="alert"
        elif post["state"]=="soon":status="即将超时";state="warning"
        elif post["state"] in ("unknown","unverified"):status="发帖待核实";state="warning"
        elif row.get("monitor_growth") and row.get("growth_error"):status="粉丝读取失败";state="warning"
        elif not checked:status="待巡检";state="off"
        badge=QLabel(status);badge.setObjectName("StatusBadge");badge.setProperty("state",state)
        badge.setMinimumHeight(23);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);footer.addWidget(badge)
        layout.addLayout(footer)
        self.setToolTip("双击卡片编辑监控设置；点击名称或 ID 直接复制。")

    def mouseDoubleClickEvent(self,event):
        self.manage_requested.emit(self.row["page_id"]);event.accept()

    def show_menu(self):
        pid=self.row["page_id"]
        menu=QMenu(self)
        menu.addAction("编辑监控模块 / 发帖标准",lambda:self.manage_requested.emit(pid))
        menu.addSeparator()
        menu.addAction("打开主页",lambda:self.open_requested.emit(pid))
        url=self.row.get("post_url")
        if url and urlsplit(url).scheme=="https" and ((urlsplit(url).hostname or "")=="facebook.com" or (urlsplit(url).hostname or "").endswith(".facebook.com")):
            menu.addAction("打开已读取的贴文",lambda:QDesktopServices.openUrl(QUrl(url)))
        menu.popup(self.mapToGlobal(QPoint(max(0,self.width()-190),38)))


class ResponsiveCards(QWidget):
    def __init__(self,parent=None,settings=None):
        super().__init__(parent);self.setObjectName("CardCanvas");self.settings=settings
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,4,6)
        self.grid.setHorizontalSpacing(10);self.grid.setVerticalSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards=[];self.columns=0
    def set_cards(self,cards):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.cards=list(cards);self.columns=0;self.reflow()
    def reflow(self):
        try:desired=max(4,min(8,int(self.settings.value("dashboard_columns",5)))) if self.settings else 5
        except (TypeError,ValueError):desired=5
        available=max(220,self.width()-4)
        columns=max(1,min(desired,int((available+10)//(172+10))))
        if columns==self.columns:return
        self.columns=columns
        while self.grid.count():self.grid.takeAt(0)
        for i,w in enumerate(self.cards):self.grid.addWidget(w,i//columns,i%columns)
        for col in range(8):self.grid.setColumnStretch(col,1 if col<columns else 0)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()


class BatchAddDialog(QDialog):
    def __init__(self,parent=None,initial=""):
        super().__init__(parent);self.setWindowTitle("添加专业 ID");self.resize(620,600)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,20);root.setSpacing(12)
        title=QLabel("批量添加专业 ID");title.setObjectName("DialogTitle");root.addWidget(title)
        note=QLabel("支持逐行 ID、表格粘贴和带数字 ID 的主页链接。重复 ID 会跳过；已有主页的模块、名称和备注不会被覆盖。")
        note.setWordWrap(True);note.setObjectName("SmallMuted");root.addWidget(note)
        form=QFormLayout()
        self.mode_box=QComboBox();self.mode_box.addItem("新增 ID（保留已有主页）","add");self.mode_box.addItem("覆盖当前 ID 列表（保留已有配置）","replace")
        form.addRow("导入方式",self.mode_box);root.addLayout(form)
        self.edit=QPlainTextEdit();self.edit.setPlaceholderText("在这里粘贴专业 ID，一行一个…")
        self.edit.setPlainText(initial);self.edit.setMinimumHeight(200);root.addWidget(self.edit,1)
        self.preview=QLabel();self.preview.setWordWrap(True);self.preview.setObjectName("SmallMuted");root.addWidget(self.preview)
        box=QFrame();box.setObjectName("SettingsCard");bl=QVBoxLayout(box);bl.setContentsMargins(14,12,14,12)
        label=QLabel("新添加主页默认监控模块");label.setObjectName("SettingsTitle");bl.addWidget(label)
        modules=QHBoxLayout();self.growth=QCheckBox("粉丝监控");self.posts=QCheckBox("发帖时间监控")
        self.growth.setChecked(True);self.posts.setChecked(True);modules.addWidget(self.growth);modules.addWidget(self.posts);modules.addStretch();bl.addLayout(modules)
        threshold=QHBoxLayout();threshold.addWidget(QLabel("超过多久未发帖提醒"))
        self.hours=QSpinBox();self.hours.setRange(1,8760);self.hours.setValue(24);self.hours.setSuffix(" 小时")
        threshold.addWidget(self.hours);threshold.addStretch();bl.addLayout(threshold);root.addWidget(box)
        actions=QHBoxLayout();actions.addStretch()
        cancel=QPushButton("取消");cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        save=QPushButton("确认导入");save.setObjectName("PrimaryButton");save.clicked.connect(self.accept);actions.addWidget(save);root.addLayout(actions)
        self.edit.textChanged.connect(self.update_preview);self.update_preview()
    def text(self):return self.edit.toPlainText()
    def mode(self):return self.mode_box.currentData()
    def update_preview(self):
        parsed=normalize_page_ids(self.text())
        self.preview.setText(f"有效 ID {len(parsed.ids)} 个 · 重复 {parsed.duplicates} 个 · 无法识别 {len(parsed.rejected)} 项")
    def accept(self):
        parsed=normalize_page_ids(self.text())
        if not parsed.ids:
            QMessageBox.warning(self,"没有有效 ID","请粘贴有效的数字主页 ID 后再导入。");return
        if parsed.rejected:
            answer=QMessageBox.question(self,"确认跳过无效内容",
                f"有 {len(parsed.rejected)} 项无法识别，将跳过：\n"+ "\n".join(parsed.rejected[:8])+"\n\n继续导入其余有效 ID？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        super().accept()




class DashboardPage(QWidget):
    collect_once=pyqtSignal()
    toggle_auto=pyqtSignal()
    view_alerts=pyqtSignal()
    open_manager=pyqtSignal(str)
    open_page=pyqtSignal(str)
    timing_changed=pyqtSignal(int,int,int,int,int)

    def __init__(self,store,settings):
        super().__init__();self.setObjectName("DashboardPage");self.store=store;self.settings=settings
        self.paused=False;self._active=False;self._auto=False
        self.build_ui();self.refresh()

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,12);root.setSpacing(13)
        top=QHBoxLayout();top.setSpacing(10)
        self.run_badge=QLabel("\u4e0a\u6b21\u5de1\u68c0\u65f6\u95f4\uff1a\u2014");self.run_badge.setObjectName("RunBadge");top.addWidget(self.run_badge)
        top.addStretch()
        self.once_btn=QPushButton("立即巡检");self.once_btn.setIcon(ui_icon("play","#FFFFFF"))
        self.once_btn.setIconSize(QSize(16,16));self.once_btn.setObjectName("PrimaryButton");self.once_btn.setFixedSize(140,40)
        self.once_btn.clicked.connect(self.collect_once.emit);top.addWidget(self.once_btn)
        self.auto_btn=QPushButton("启用自动巡检");self.auto_btn.setObjectName("AutoButton");self.auto_btn.setFixedSize(140,40)
        self.auto_btn.clicked.connect(self.toggle_auto.emit);top.addWidget(self.auto_btn);root.addLayout(top)
        metrics=QHBoxLayout();metrics.setSpacing(12)
        self.metric_pages=MetricCard("专业主页数",ACCENT,"pages")
        self.metric_total=MetricCard("当前粉丝总量",CYAN,"people")
        self.metric_yesterday=MetricCard("昨日新增",AMBER,"history")
        self.metric_growth=MetricCard("今日新增",GREEN,"trend")
        self.metric_post=MetricCard("发帖已超时",AMBER,"clock")
        self.metric_alerts=MetricCard("增长超标预警",RED,"bell")
        for metric in (self.metric_pages,self.metric_total,self.metric_yesterday,self.metric_growth,self.metric_post,self.metric_alerts):metrics.addWidget(metric,1)
        root.addLayout(metrics)
        control_bar=QFrame();control_bar.setObjectName("TimingBar")
        toolbar=QHBoxLayout(control_bar);toolbar.setContentsMargins(10,7,10,7);toolbar.setSpacing(5)
        minutes,j0,j1,g0,g1=random_inspection_timing(self.settings)
        def spin(value,low,high,width=47,tip=""):
            widget=DirectNumberSpinBox();widget.setObjectName("QuickTimingSpin");widget.setRange(low,high);widget.setValue(value)
            widget.setFixedSize(width,34);widget.setToolTip(tip);return widget
        def timing_label(text,tip):
            label=QLabel(text);label.setObjectName("QuickTimingLabel");label.setToolTip(tip);return label
        toolbar.addWidget(timing_label("每轮间隔","自动巡检每轮的基准间隔（分钟）"));self.quick_interval=spin(minutes,5,1440,52,"每轮间隔基准，单位：分钟");toolbar.addWidget(self.quick_interval)
        toolbar.addSpacing(4);toolbar.addWidget(timing_label("浮动范围","每轮会随机提前或延后，填写最小/最大分钟数"));self.quick_jitter_min=spin(j0,0,1439,43,"随机浮动最小分钟数");toolbar.addWidget(self.quick_jitter_min)
        dash1=QLabel("–");dash1.setObjectName("QuickTimingLabel");toolbar.addWidget(dash1);self.quick_jitter_max=spin(j1,0,1439,43,"随机浮动最大分钟数");toolbar.addWidget(self.quick_jitter_max)
        toolbar.addSpacing(4);toolbar.addWidget(timing_label("主页间隔","每两个主页之间随机等待，单位：秒"));self.quick_gap_min=spin(g0,0,120,39,"主页间隔最小秒数");toolbar.addWidget(self.quick_gap_min)
        dash2=QLabel("–");dash2.setObjectName("QuickTimingLabel");toolbar.addWidget(dash2);self.quick_gap_max=spin(g1,0,120,39,"主页间隔最大秒数");toolbar.addWidget(self.quick_gap_max)
        for widget in (self.quick_interval,self.quick_jitter_min,self.quick_jitter_max,self.quick_gap_min,self.quick_gap_max):widget.valueChanged.connect(self._quick_timing_changed)
        toolbar.addStretch(1)
        self.status_filter=QComboBox()
        for name,value in (("全部主页","all"),("粉丝监控","growth"),("发帖监控","posts"),("发帖超时","overdue"),("待核实","unknown"),("未选择模块","off")):self.status_filter.addItem(name,value)
        self.status_filter.currentIndexChanged.connect(lambda _:self.refresh());self.status_filter.setFixedWidth(106);toolbar.addWidget(self.status_filter)
        self.search=QLineEdit();self.search.setPlaceholderText("搜索名称 / 专业 ID");self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(190);self.search.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(lambda _:self.refresh());toolbar.addWidget(self.search)
        self.sort_box=QComboBox()
        for name,key in (("自定义排序","manual"),("增长预警优先","growth"),("发帖超时优先","post"),("名称排序","name")):self.sort_box.addItem(name,key)
        self.sort_box.currentIndexChanged.connect(lambda _:self.refresh());self.sort_box.setFixedWidth(126);toolbar.addWidget(self.sort_box)
        self.columns_box=QComboBox()
        for num in range(4,9):self.columns_box.addItem(f"每行 {num} 个",num)
        try:col=max(4,min(8,int(self.settings.value("dashboard_columns",5))))
        except (ValueError,TypeError):col=5
        self.columns_box.setCurrentIndex(col-4);self.columns_box.setFixedWidth(92);self.columns_box.setToolTip("可选每行 4–8 张；窗口太窄时会自动减少实际列数")
        self.columns_box.currentIndexChanged.connect(self._columns_changed);toolbar.addWidget(self.columns_box)
        for control in (self.status_filter,self.search,self.sort_box,self.columns_box):control.setFixedHeight(36)
        root.addWidget(control_bar)
        self.scroll=QScrollArea();self.scroll.setObjectName("CardScroll");self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards=ResponsiveCards(settings=self.settings);self.scroll.setWidget(self.cards)
        # setWidget() turns this on by default; disable it AFTER attaching the canvas.
        self.cards.setAutoFillBackground(False);self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setMinimumHeight(230);root.addWidget(self.scroll,1)
        panel=QFrame();panel.setObjectName("MonitorPanel");self.notice_panel=panel
        pl=QVBoxLayout(panel);pl.setContentsMargins(14,10,14,12);pl.setSpacing(6)
        row=QHBoxLayout();label=QLabel("最近预警");label.setObjectName("PanelTitle");row.addWidget(label)
        self.alert_count=QLabel("");self.alert_count.setObjectName("SmallMuted");row.addWidget(self.alert_count);row.addStretch()
        link=QPushButton("全部通知");link.setObjectName("LinkButton");link.clicked.connect(self.view_alerts.emit);row.addWidget(link);pl.addLayout(row)
        self.notices=QHBoxLayout();self.notices.setSpacing(12);pl.addLayout(self.notices);root.addWidget(panel)
        footer=QHBoxLayout()
        self.status=ElideLabel("就绪");self.status.setMinimumHeight(20);self.status.setObjectName("FooterText")
        self.next_run=QLabel("自动巡检未开启");self.next_run.setObjectName("FooterText")
        footer.addWidget(self.status,1);footer.addWidget(self.next_run)
        version=QLabel("V"+APP_VERSION);version.setObjectName("FooterText");footer.addWidget(version);root.addLayout(footer)
        for box,key,default in ((self.status_filter,"dashboard/filter","all"),(self.sort_box,"dashboard/sort","manual")):
            box.blockSignals(True);box.setCurrentIndex(max(0,box.findData(self.settings.value(key,default))));box.blockSignals(False)
            box.currentIndexChanged.connect(self._remember_view)
        self.search.blockSignals(True);self.search.setText(str(self.settings.value("dashboard/search","")));self.search.blockSignals(False)
        self.search.textChanged.connect(self._remember_view)

    def _quick_timing_changed(self,*_):
        widgets=(self.quick_interval,self.quick_jitter_min,self.quick_jitter_max,self.quick_gap_min,self.quick_gap_max)
        # One edited endpoint moves the opposite endpoint when needed, never an invalid interval.
        sender=self.sender()
        for lower,upper in ((self.quick_jitter_min,self.quick_jitter_max),(self.quick_gap_min,self.quick_gap_max)):
            if lower.value()>upper.value():
                target=upper if sender is lower else lower
                value=lower.value() if target is upper else upper.value()
                target.blockSignals(True);target.setValue(value);target.blockSignals(False)
        values=normalize_random_timing(*(w.value() for w in widgets))
        self.set_timing_values(*values);self.timing_changed.emit(*values)

    def set_timing_values(self,minutes,j0,j1,g0,g1):
        for widget,value in zip((self.quick_interval,self.quick_jitter_min,self.quick_jitter_max,self.quick_gap_min,self.quick_gap_max),(minutes,j0,j1,g0,g1)):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)


    def _remember_view(self,*_):
        self.settings.setValue("dashboard/filter",self.status_filter.currentData())
        self.settings.setValue("dashboard/sort",self.sort_box.currentData())
        self.settings.setValue("dashboard/search",self.search.text())
        self.settings.sync()

    def _columns_changed(self):
        self.settings.setValue("dashboard_columns",self.columns_box.currentData());self.settings.sync()
        self.cards.columns=0;self.cards.reflow()

    def set_running(self,auto,active):
        self._auto=auto;self._active=active
        label="暂停中" if active and self.paused else "巡检中" if active else "自动巡检已开启" if auto else "待巡检"
        self.run_badge.setToolTip(label)
        self.once_btn.setText("继续巡检" if active and self.paused else "暂停巡检" if active else "立即巡检")
        self.once_btn.setIcon(ui_icon("pause" if active and not self.paused else "play","#FFFFFF"))
        self.once_btn.setToolTip("暂停在当前主页处理完成后生效；继续不会从头重跑" if active else "巡检所有已选择模块的专业 ID")
        self.auto_btn.setText("暂停自动巡检" if auto else "启用自动巡检")
        self.auto_btn.setProperty("autoEnabled",auto)
        self.auto_btn.setToolTip("仅停止后续定时轮次；暂停当前轮次请点击左侧巡检按钮")
        self.auto_btn.style().unpolish(self.auto_btn);self.auto_btn.style().polish(self.auto_btn)

    def refresh(self):
        now=time.time()
        try:interval=int(self.settings.value("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60
        except (ValueError,TypeError):interval=DEFAULT_INTERVAL_MINUTES*60
        rows=self.store.dashboard_rows(None,interval)
        if not self._active or not hasattr(self,"_last_inspection_stamp"):
            self._last_inspection_stamp=latest_inspection_stamp(self.settings,rows)
        self.run_badge.setText("上次巡检时间："+inspection_stamp_label(self._last_inspection_stamp))
        unread_pages={a["page_id"] for a in self.store.alert_rows() if not a["acknowledged"]}
        today_sum=0;covered=0;partial=0;yesterday_sum=0;yesterday_covered=0;yesterday_partial=0
        growth_rows=[r for r in rows if r["monitor_growth"]]
        post_rows=[r for r in rows if r["monitor_posts"]]
        for row in rows:
            row["post_view"]=post_view(row,now,interval)
            row["is_growth_alert"]=row["monitor_growth"] and row["page_id"] in unread_pages
            if row["monitor_growth"]:
                row["today"]=self.store.today_change(row["page_id"],now,interval)
                row["yesterday"]=self.store.yesterday_change(row["page_id"],now)
                if row["today"]["delta"] is not None:
                    today_sum+=row["today"]["delta"];covered+=1
                    partial+=int(row["today"]["partial"])
                if row["yesterday"]["delta"] is not None:
                    yesterday_sum+=row["yesterday"]["delta"];yesterday_covered+=1
                    yesterday_partial+=int(row["yesterday"]["partial"])
        total=sum(r["last_followers"] for r in growth_rows if r["last_followers"] is not None)
        sampled=sum(r["last_followers"] is not None for r in growth_rows)
        overdue=sum(r["post_view"]["state"]=="overdue" for r in rows)
        unverified=sum(r["post_view"]["state"] in ("unknown","unverified") for r in rows)
        g,p=self.store.unread_totals()
        self.metric_pages.set_values(len(rows),f"粉丝监控 {len(growth_rows)} · 发帖监控 {len(post_rows)}")
        self.metric_total.set_values(format_count(total) if sampled else "—",f"有粉丝记录 {sampled} / {len(growth_rows)}")
        self.metric_yesterday.set_values(format_delta(yesterday_sum) if yesterday_covered else "—",
            f"可比较 {yesterday_covered} 个"+(f" · {yesterday_partial} 个为部分日" if yesterday_partial else ""))
        self.metric_growth.set_values(format_delta(today_sum) if covered else "—",f"可比较 {covered} 个"+(f" · {partial} 个从今日首检起计算" if partial else ""))
        self.metric_post.set_values(overdue,f"监控 {len(post_rows)} 个 · 待核实 {unverified}")
        self.metric_alerts.set_values(g,"尚未标记已读的增长预警")
        needle=self.search.text().strip().casefold();mode=self.status_filter.currentData()
        filtered=[]
        for r in rows:
            if needle and needle not in (display_name(r)+" "+r["page_id"]+" "+r.get("notes","")).casefold():continue
            if mode=="growth" and not r["monitor_growth"]:continue
            if mode=="posts" and not r["monitor_posts"]:continue
            if mode=="overdue" and r["post_view"]["state"]!="overdue":continue
            if mode=="unknown" and r["post_view"]["state"] not in ("unknown","unverified"):continue
            if mode=="off" and (r["monitor_growth"] or r["monitor_posts"]):continue
            filtered.append(r)
        order=self.sort_box.currentData()
        if order=="name":filtered.sort(key=lambda r:display_name(r).casefold())
        elif order=="growth":
            filtered.sort(key=lambda r:(not bool(r.get("is_growth_alert")),r["post_view"]["state"]!="overdue",
                r.get("today",{}).get("delta") is None,-(r.get("today",{}).get("delta") or 0),r["sort_order"]))
        elif order=="post":
            filtered.sort(key=lambda r:(r["post_view"]["state"]!="overdue",not bool(r.get("is_growth_alert")),
                float(r.get("last_post_ts") or now+1),r["sort_order"]))
        else:filtered.sort(key=lambda r:(r["sort_order"],r["page_id"]))
        self.status_filter.setToolTip("匹配 %s 个，共 %s 个主页" % (len(filtered),len(rows)))
        cards=[]
        for r in filtered:
            card=PageCard(r)
            card.open_requested.connect(self.open_page.emit)
            card.manage_requested.connect(self.open_manager.emit);cards.append(card)
        if not cards:
            empty=QFrame();empty.setObjectName("EmptyState");layout=QVBoxLayout(empty);layout.setContentsMargins(20,30,20,30)
            title=QLabel("尚无匹配主页");title.setObjectName("SectionTitle");layout.addWidget(title)
            msg=QLabel("在右上角「FB专业ID管理」添加 ID，并勾选粉丝监控、发帖监控或两者。")
            msg.setWordWrap(True);msg.setObjectName("SmallMuted");layout.addWidget(msg)
            add=QPushButton("打开 FB专业ID管理");add.setObjectName("PrimaryButton");add.clicked.connect(lambda:self.open_manager.emit(""))
            layout.addWidget(add,0,Qt.AlignmentFlag.AlignLeft);cards=[empty]
        scroll=self.scroll.verticalScrollBar().value()
        self.cards.set_cards(cards)
        self.scroll.verticalScrollBar().setValue(scroll)
        while self.notices.count():
            item=self.notices.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.alert_count.setText(f"{g+p} 条未读")
        entries=self.store.combined_alerts(limit=3,unread_only=True)
        self.notice_panel.setVisible(bool(entries))
        for entry in entries:
            frame=QFrame();frame.setObjectName("AlertRow");layout=QHBoxLayout(frame);layout.setContentsMargins(9,5,9,5);layout.setSpacing(9)
            avatar=AvatarWidget(entry["page_name"],entry.get("avatar_path",""),40,page_id=entry.get("page_id",""))
            avatar.setToolTip(entry["page_name"]+" · ID "+entry["page_id"]);layout.addWidget(avatar)
            texts=QVBoxLayout();texts.setSpacing(2)
            title=ElideLabel(("发帖超时 · " if entry["kind"]=="post" else "增长超标 · ")+entry["page_name"])
            title.setObjectName("AlertRowTitle");title.setMinimumHeight(21)
            desc=ElideLabel(entry["message"]);desc.setMinimumHeight(18);desc.setObjectName("SmallMuted");desc.setToolTip(entry["message"])
            texts.addWidget(title);texts.addWidget(desc);layout.addLayout(texts,1);self.notices.addWidget(frame,1)




class AlertsPage(QWidget):
    ack_requested=pyqtSignal()
    read_changed=pyqtSignal()
    def __init__(self,store):
        super().__init__();self.store=store;self.setObjectName("AlertsPage");self.mode="current";self._highlight_key=None
        root=QVBoxLayout(self);root.setContentsMargins(24,22,24,18);root.setSpacing(12)
        head=QHBoxLayout();title=QLabel("通知");title.setObjectName("PageTitle");head.addWidget(title);head.addStretch()
        self.history_btn=QPushButton("历史记录");self.history_btn.setObjectName("NoticeHistoryButton");self.history_btn.clicked.connect(self.toggle_history);head.addWidget(self.history_btn)
        self.filter=QComboBox()
        for text,key in (("全部类型","all"),("粉丝增长","growth"),("发帖超时","post")):self.filter.addItem(text,key)
        self.filter.currentIndexChanged.connect(lambda _:self.refresh());self.filter.setFixedWidth(112);head.addWidget(self.filter)
        self.ack_btn=QPushButton("全部标为已读");self.ack_btn.setObjectName("SecondaryButton");self.ack_btn.clicked.connect(self.ack_requested.emit);head.addWidget(self.ack_btn);root.addLayout(head)
        self.summary=QLabel();self.summary.setObjectName("NoticeSummary");self.summary.setWordWrap(True);root.addWidget(self.summary)
        note=QLabel("默认只显示未读通知；点击任意一条即视为已读并移入历史记录。历史数据长期保留，不会因已读而删除。")
        note.setObjectName("SmallMuted");note.setWordWrap(True);root.addWidget(note)
        self.table=QTableWidget(0,7);self.table.setObjectName("AlertsTable");self.table.setHorizontalHeaderLabels(("头像","类型","专业名称","专业 ID","通知内容","记录时间","状态"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.verticalHeader().setVisible(False);self.table.setAlternatingRowColors(True);self.table.setShowGrid(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col,width in ((0,58),(1,100),(2,190),(3,170),(5,150),(6,75)):self.table.setColumnWidth(col,width)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._row_clicked)
        root.addWidget(self.table,1);self.open_current()

    def open_current(self):
        self.mode="current";self._highlight_key=None
        self.history_btn.setText("历史记录");self.history_btn.setProperty("active",False)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(True);self.refresh()

    def toggle_history(self):
        if self.mode=="history":
            self.open_current();return
        self.mode="history";self._highlight_key=None
        self.history_btn.setText("返回当前");self.history_btn.setProperty("active",True)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(False);self.refresh()

    def _visible_rows(self):
        rows=self.store.combined_alerts(limit=5000);kind=self.filter.currentData()
        if kind!="all":rows=[r for r in rows if r["kind"]==kind]
        if self.mode=="current":rows=[r for r in rows if not bool(r.get("acknowledged"))]
        else:rows=[r for r in rows if bool(r.get("acknowledged"))]
        return rows

    def refresh(self):
        rows=self._visible_rows();self.table.clearContents();self.table.setRowCount(len(rows));matched=None
        for i,r in enumerate(rows):
            cell=QWidget();layout=QHBoxLayout(cell);layout.setContentsMargins(9,3,9,3);layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(AvatarWidget(r["page_name"],r.get("avatar_path",""),36,page_id=r.get("page_id","")));self.table.setCellWidget(i,0,cell)
            values=("发帖超时" if r["kind"]=="post" else "粉丝增长",r["page_name"],r["page_id"],r["message"],local_time_label(r["alerted_at"]),"已读" if r["acknowledged"] else "未读")
            key=(r["kind"],int(r.get("id") or 0),r["page_id"])
            for j,text in enumerate(values,1):
                item=QTableWidgetItem(str(text));item.setToolTip(str(text));item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if j in (1,3,5,6) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                item.setData(Qt.ItemDataRole.UserRole,key)
                if j==1:item.setForeground(QColor(AMBER if r["kind"]=="post" else RED))
                self.table.setItem(i,j,item)
            self.table.setRowHeight(i,50)
            if self._highlight_key==(r["kind"],int(r.get("id") or 0)):matched=i
        g,p=self.store.unread_totals()
        if self.mode=="current":
            self.summary.setText(f"当前未读 {g+p} 条 · 粉丝增长 {g} · 发帖超时 {p}" if g+p else "当前没有未读通知")
        else:self.summary.setText(f"历史记录 {len(rows)} 条 · 已读通知永久保留")
        if matched is not None:
            self.table.setCurrentCell(matched,1);self.table.selectRow(matched);item=self.table.item(matched,1)
            if item:self.table.scrollToItem(item,QAbstractItemView.ScrollHint.PositionAtCenter)

    def _row_clicked(self,row,col):
        if self.mode!="current":return
        item=self.table.item(row,1) or self.table.item(row,col)
        if not item:return
        key=item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key,(tuple,list)) or len(key)<2:return
        kind,alert_id=key[0],key[1]
        if self.store.acknowledge_notification(kind,alert_id):
            self._highlight_key=None;self.read_changed.emit();self.refresh()

    def focus_alert(self,entry):
        try:self._highlight_key=(str(entry.get("kind") or ""),int(entry.get("id") or 0))
        except (TypeError,ValueError):self._highlight_key=(str(entry.get("kind") or ""),0)
        self.mode="current";self.history_btn.setText("历史记录");self.history_btn.setProperty("active",False)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(True)
        # A previous type filter must not hide the notification opened from the popup.
        self.filter.blockSignals(True);self.filter.setCurrentIndex(0);self.filter.blockSignals(False)
        self.refresh()
        if self.table.currentRow()>=0:self.table.setFocus(Qt.FocusReason.OtherFocusReason)


# 1.8: 发帖监控已移入每个专业 ID 的配置。


# 1.8: 发帖监控已移入每个专业 ID 的配置。



class PageEditDialog(QDialog):
    def __init__(self,row,parent=None):
        super().__init__(parent);self.row=row;self.setWindowTitle("编辑专业 ID");self.resize(560,450)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,20);root.setSpacing(14)
        head=QHBoxLayout();head.addWidget(AvatarWidget(display_name(row),row.get("avatar_path",""),54,page_id=row.get("page_id","")))
        texts=QVBoxLayout()
        name=QLabel(display_name(row));name.setWordWrap(True);name.setObjectName("SectionTitle");texts.addWidget(name)
        pid=CopyLabel("公共主页编号："+row["page_id"],row["page_id"]);pid.setMinimumHeight(23);texts.addWidget(pid)
        head.addLayout(texts,1);root.addLayout(head)
        real=QLabel("最近读取的真实名称："+(normalize_name(row.get("page_name"),row["page_id"]) or "尚未成功读取"))
        real.setWordWrap(True);real.setObjectName("SmallMuted");root.addWidget(real)
        form=QFormLayout();form.setVerticalSpacing(12)
        self.custom=QLineEdit(str(row.get("custom_name") or ""));self.custom.setPlaceholderText("留空时显示自动采集的真实名称")
        form.addRow("自定义显示名称",self.custom)
        modules=QWidget();ml=QHBoxLayout(modules);ml.setContentsMargins(0,0,0,0)
        self.growth=QCheckBox("粉丝监控");self.posts=QCheckBox("发帖监控")
        self.growth.setChecked(bool(row["monitor_growth"]));self.posts.setChecked(bool(row["monitor_posts"]))
        ml.addWidget(self.growth);ml.addWidget(self.posts);ml.addStretch();form.addRow("监控模块（可多选）",modules)
        self.hours=QSpinBox();self.hours.setRange(1,8760);self.hours.setValue(int(row["post_limit_hours"]));self.hours.setSuffix(" 小时")
        form.addRow("发帖超时标准",self.hours)
        self.order=QSpinBox();self.order.setRange(0,999999);self.order.setValue(int(row["sort_order"]));form.addRow("排序号（越小越靠前）",self.order)
        self.notes=QPlainTextEdit(str(row.get("notes") or ""));self.notes.setMaximumHeight(82);form.addRow("备注",self.notes);root.addLayout(form)
        actions=QHBoxLayout();actions.addStretch()
        cancel=QPushButton("取消");cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        save=QPushButton("保存");save.setObjectName("PrimaryButton");save.clicked.connect(self.accept);actions.addWidget(save);root.addLayout(actions)
    def values(self):
        return dict(custom_name=self.custom.text().strip(),monitor_growth=self.growth.isChecked(),
                    monitor_posts=self.posts.isChecked(),post_limit_hours=self.hours.value(),
                    sort_order=self.order.value(),notes=self.notes.toPlainText().strip())


class PageManagementPage(QWidget):
    add_requested=pyqtSignal()
    delete_requested=pyqtSignal(list)
    config_changed=pyqtSignal()
    def __init__(self,store,settings):
        super().__init__();self.store=store;self.settings=settings;self._loading=False;self._busy=False
        self.setObjectName("ManagerPage");self.build_ui();self.refresh()

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(24,20,24,16);root.setSpacing(13)
        title=QLabel("FB专业ID管理");title.setObjectName("PageTitle");root.addWidget(title)
        desc=QLabel("一次添加，多模块共用。直接勾选监控模块；双击名称、标准、排序或备注即可编辑。")
        desc.setObjectName("Subtitle");desc.setWordWrap(True);root.addWidget(desc)
        actions=QHBoxLayout();actions.setSpacing(8)
        self.add_btn=QPushButton("添加 ID");self.add_btn.setObjectName("PrimaryButton");self.add_btn.clicked.connect(self._request_add)
        self.batch_btn=QPushButton("批量设置");self.batch_btn.clicked.connect(self.batch_settings)
        self.delete_btn=QPushButton("批量删除");self.delete_btn.setObjectName("DangerButton");self.delete_btn.clicked.connect(self.delete_selected)
        for btn in (self.add_btn,self.batch_btn,self.delete_btn):
            btn.setFixedHeight(38);actions.addWidget(btn)
        actions.addStretch();root.addLayout(actions)
        tools=QHBoxLayout();tools.setSpacing(10)
        self.select_all=QCheckBox("全选当前结果");self.select_all.toggled.connect(self.select_visible);tools.addWidget(self.select_all)
        self.summary=QLabel();self.summary.setObjectName("SmallMuted");tools.addWidget(self.summary);tools.addStretch()
        self.filter=QComboBox()
        for name,key in (("全部模块","all"),("粉丝监控","growth"),("发帖监控","posts"),("两者都关闭","off")):self.filter.addItem(name,key)
        self.filter.currentIndexChanged.connect(lambda _:self.refresh());tools.addWidget(self.filter)
        self.search=QLineEdit();self.search.setPlaceholderText("搜索名称、ID 或备注");self.search.setClearButtonEnabled(True);self.search.setFixedWidth(270)
        self.search.textChanged.connect(lambda _:self.refresh());tools.addWidget(self.search)
        root.addLayout(tools)
        self.table=QTableWidget(0,10);self.table.setObjectName("IdManagerTable")
        self.table.setHorizontalHeaderLabels(("选择","头像","专业名称","专业 ID","粉丝监控","发帖监控","发帖标准（h）","排序","备注","资料状态"))
        self.table.setIconSize(QSize(34,34));self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False);self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setSortingEnabled(True);self.table.sortItems(7,Qt.SortOrder.AscendingOrder)
        widths={0:47,1:57,2:210,3:177,4:88,5:88,6:118,7:64,8:190,9:110}
        for col,width in widths.items():
            self.table.setColumnWidth(col,width)
            self.table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8,QHeaderView.ResizeMode.Stretch)
        for col in (0,4,5):self.table.setItemDelegateForColumn(col,CheckDelegate(self.table))
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellClicked.connect(self._clicked)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        root.addWidget(self.table,1)
        hint=QLabel("排序号会同步到主界面“自定义排序”。名称和头像会在正常巡检时自动更新；未获取资料不会伪造。")
        hint.setObjectName("SmallMuted");hint.setWordWrap(True);root.addWidget(hint)
        self.filter.blockSignals(True);self.filter.setCurrentIndex(max(0,self.filter.findData(self.settings.value("manager/filter","all"))));self.filter.blockSignals(False)
        self.search.blockSignals(True);self.search.setText(str(self.settings.value("manager/search","")));self.search.blockSignals(False)
        state=self.settings.value("manager/header")
        if state:
            try:self.table.horizontalHeader().restoreState(state)
            except (TypeError,ValueError):pass
        self.filter.currentIndexChanged.connect(self._remember)
        self.search.textChanged.connect(self._remember)
        self.table.horizontalHeader().sectionResized.connect(self._remember)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._remember)

    def _remember(self,*_):
        if self._loading:return
        self.settings.setValue("manager/filter",self.filter.currentData())
        self.settings.setValue("manager/search",self.search.text())
        self.settings.setValue("manager/header",self.table.horizontalHeader().saveState())
        self.settings.sync()

    def set_busy(self,busy):
        self._busy=bool(busy)
        # Keep action buttons clickable during collection so the user gets an immediate
        # bottom toast explaining why an edit cannot run yet.
        for b in (self.add_btn,self.batch_btn,self.delete_btn):b.setEnabled(True)
        # Selection/copying is harmless during collection. Disabling the whole table made
        # single checkbox clicks fail while the external Select All checkbox still worked.
        self.table.setEnabled(True)
        blocked=self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                for col in range(self.table.columnCount()):
                    item=self.table.item(row,col)
                    if item is None:continue
                    flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable
                    if col==0 or (col in (4,5) and not busy):flags|=Qt.ItemFlag.ItemIsUserCheckable
                    if col in (6,7,8) and not busy:flags|=Qt.ItemFlag.ItemIsEditable
                    item.setFlags(flags)
        finally:self.table.blockSignals(blocked)
        self.table.viewport().update()
        if busy:self.summary.setText("正在巡检 · 可查看和复制 ID，修改操作将在本轮结束后恢复")

    def _busy_notice(self):
        show_hint(self,"正在巡检，请等待本轮巡检结束后再修改专业 ID。")

    def _request_add(self):
        if self._busy:
            self._busy_notice();return
        self.add_requested.emit()

    def ids(self):
        checked=[]
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.checkState()==Qt.CheckState.Checked:checked.append(str(item.data(Qt.ItemDataRole.UserRole)))
        if checked:return list(dict.fromkeys(checked))
        return list(dict.fromkeys(str(self.table.item(idx.row(),0).data(Qt.ItemDataRole.UserRole))
                                 for idx in self.table.selectionModel().selectedRows()))

    def select_visible(self,checked):
        self.table.blockSignals(True)
        try:
            for r in range(self.table.rowCount()):
                item=self.table.item(r,0)
                if item:item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:self.table.blockSignals(False)
        self._sync_selection_header()

    def _sync_selection_header(self):
        count=self.table.rowCount()
        chosen=sum(1 for r in range(count) if self.table.item(r,0) and self.table.item(r,0).checkState()==Qt.CheckState.Checked)
        self.select_all.blockSignals(True)
        self.select_all.setChecked(count>0 and chosen==count)
        self.select_all.blockSignals(False)
        self.select_all.setToolTip("\u5df2\u52fe\u9009 %s / %s \u4e2a" % (chosen,count))

    def _clicked(self,row,col):
        if self._busy and col in (2,4,5,6,7,8,9):
            self._busy_notice();return
        if col==3:
            text=self.table.item(row,col).text()
            QApplication.clipboard().setText(text)
            QToolTip.showText(self.table.mapToGlobal(QPoint(20,20)),"已复制 ID："+text,self.table)

    def _double_clicked(self,row,col):
        if col==2:
            if self._busy:
                self._busy_notice();return
            pid=self.table.item(row,0).data(Qt.ItemDataRole.UserRole);self.edit_id(pid)

    def edit_id(self,pid):
        if self._busy:
            self._busy_notice();return
        row=self.store.page(pid)
        if not row:return
        dlg=PageEditDialog(row,self)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            try:self.store.update_config([pid],**dlg.values())
            except (ValueError,TypeError) as exc:QMessageBox.warning(self,"未保存",str(exc));return
            self.refresh();self.config_changed.emit()



    def delete_selected(self):
        if self._busy:
            self._busy_notice();return
        ids=self.ids()
        if not ids:show_hint(self,"请选择需要删除的专业 ID。");return
        self.delete_requested.emit(ids)

    def batch_settings(self):
        if self._busy:
            self._busy_notice();return
        ids=self.ids()
        if not ids:show_hint(self,"请选择一个或多个专业 ID。");return
        dlg=QDialog(self);dlg.setWindowTitle(f"批量设置 {len(ids)} 个专业 ID");dlg.resize(470,310)
        root=QVBoxLayout(dlg);form=QFormLayout()
        selects={}
        for name,key in (("粉丝监控","monitor_growth"),("发帖监控","monitor_posts")):
            combo=QComboBox();combo.addItem("保持原设置",None);combo.addItem("开启",True);combo.addItem("关闭",False)
            form.addRow(name,combo);selects[key]=combo
        limit_flag=QCheckBox("修改发帖超时标准");hours=QSpinBox();hours.setRange(1,8760);hours.setValue(24);hours.setSuffix(" 小时")
        form.addRow(limit_flag,hours);root.addLayout(form)
        row=QHBoxLayout();row.addStretch();cancel=QPushButton("取消");save=QPushButton("保存")
        cancel.clicked.connect(dlg.reject);save.clicked.connect(dlg.accept);save.setObjectName("PrimaryButton")
        row.addWidget(cancel);row.addWidget(save);root.addLayout(row)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        fields={key:combo.currentData() for key,combo in selects.items() if combo.currentData() is not None}
        if limit_flag.isChecked():fields["post_limit_hours"]=hours.value()
        if fields:
            self.store.update_config(ids,**fields);self.refresh();self.config_changed.emit()

    def _item_changed(self,item):
        if self._loading:return
        col=item.column()
        if col==0:
            self._sync_selection_header();return
        marker=self.table.item(item.row(),0)
        if not marker:return
        pid=str(marker.data(Qt.ItemDataRole.UserRole))
        if self._busy:self.refresh();return
        try:
            if col in (4,5):
                key="monitor_growth" if col==4 else "monitor_posts"
                self.store.update_config([pid],**{key:item.checkState()==Qt.CheckState.Checked})
                item.sort_key=int(item.checkState()==Qt.CheckState.Checked)
            elif col in (6,7):
                value=int(item.text().strip())
                self.store.update_config([pid],**{("post_limit_hours" if col==6 else "sort_order"):value})
                item.sort_key=value
            elif col==8:self.store.update_config([pid],notes=item.text())
            else:return
        except (ValueError,TypeError) as exc:
            QMessageBox.warning(self,"输入无效",str(exc));self.refresh();return
        count=self.table.rowCount()
        growth=sum(self.table.item(r,4).checkState()==Qt.CheckState.Checked for r in range(count))
        posts=sum(self.table.item(r,5).checkState()==Qt.CheckState.Checked for r in range(count))
        self.summary.setText(f"{count} 个 ID · 粉丝监控 {growth} · 发帖监控 {posts}")
        self.config_changed.emit()

    def focus_id(self,pid):
        self.search.clear();self.filter.setCurrentIndex(0);self.refresh()
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==pid:
                self.table.selectRow(r);self.table.scrollToItem(self.table.item(r,2));return

    def refresh(self):
        checked=set()
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.checkState()==Qt.CheckState.Checked:checked.add(item.data(Qt.ItemDataRole.UserRole))
        selected=set(self.ids()) if self.table.rowCount() else set()
        scroll=self.table.verticalScrollBar().value()
        sort_col=self.table.horizontalHeader().sortIndicatorSection();sort_order=self.table.horizontalHeader().sortIndicatorOrder()
        needle=self.search.text().casefold().strip();mode=self.filter.currentData()
        rows=[]
        for row in self.store.list_pages():
            if needle and needle not in (display_name(row)+" "+row["page_id"]+" "+row["notes"]).casefold():continue
            if mode=="growth" and not row["monitor_growth"]:continue
            if mode=="posts" and not row["monitor_posts"]:continue
            if mode=="off" and (row["monitor_growth"] or row["monitor_posts"]):continue
            rows.append(row)
        self._loading=True;self.table.blockSignals(True);self.table.setSortingEnabled(False)
        self.table.clearContents();self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            pid=row["page_id"]
            for col in range(10):
                item=SortItem("")
                flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable
                if col in (0,4,5):flags|=Qt.ItemFlag.ItemIsUserCheckable
                if col in (6,7,8):flags|=Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.table.setItem(i,col,item)
            self.table.item(i,0).setData(Qt.ItemDataRole.UserRole,pid)
            self.table.item(i,0).setCheckState(Qt.CheckState.Checked if pid in checked else Qt.CheckState.Unchecked)
            wrapper=QWidget();avatar_layout=QHBoxLayout(wrapper);avatar_layout.setContentsMargins(0,0,0,0)
            avatar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar_layout.addWidget(AvatarWidget(display_name(row),row["avatar_path"],36,page_id=pid))
            self.table.setCellWidget(i,1,wrapper)
            for col,text in ((2,display_name(row)),(3,pid),(6,str(row["post_limit_hours"])),(7,str(row["sort_order"])),(8,row["notes"])):
                item=self.table.item(i,col);item.setText(text);item.sort_key=int(text) if col in (6,7) else text.casefold()
            self.table.item(i,2).setToolTip("真实名称："+(normalize_name(row["page_name"],pid) or "未获取")+"\n双击编辑自定义名称与配置")
            self.table.item(i,3).setToolTip("点击复制完整 ID："+pid)
            for col,key in ((4,"monitor_growth"),(5,"monitor_posts")):
                item=self.table.item(i,col);item.setCheckState(Qt.CheckState.Checked if row[key] else Qt.CheckState.Unchecked);item.sort_key=int(row[key])
            state="已同步" if normalize_name(row["page_name"],pid) else "名称待获取"
            if row.get("name_error"):state="待核实"
            item=self.table.item(i,9);item.setText(state);item.setToolTip(row.get("name_error") or row.get("metadata_checked_at") or "巡检时同步资料")
            self.table.setRowHeight(i,52)
        self.table.setSortingEnabled(True);self.table.sortItems(sort_col,sort_order)
        self.table.blockSignals(False);self._loading=False
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).data(Qt.ItemDataRole.UserRole) in selected:
                for c in range(self.table.columnCount()):self.table.item(r,c).setSelected(True)
        self.table.verticalScrollBar().setValue(scroll)
        self._sync_selection_header()
        g=sum(r["monitor_growth"] for r in rows);p=sum(r["monitor_posts"] for r in rows)
        self.summary.setText(f"{len(rows)} 个 ID · 粉丝监控 {g} · 发帖监控 {p}")
        self.set_busy(self._busy)


class SettingsPage(QWidget):
    login_requested=pyqtSignal()
    save_requested=pyqtSignal(bool)
    export_requested=pyqtSignal()
    backup_requested=pyqtSignal()
    data_dir_requested=pyqtSignal()
    cleanup_requested=pyqtSignal()

    def __init__(self,store:Store,settings:QSettings):
        super().__init__();self.store=store;self.settings=settings
        self.build_ui();self.load_settings()
        self.autosave=QTimer(self);self.autosave.setSingleShot(True)
        self.autosave.timeout.connect(self._request_autosave)
        for widget in self.findChildren(QSpinBox):
            widget.setKeyboardTracking(isinstance(widget,DirectNumberSpinBox))
            widget.valueChanged.connect(lambda *_:self.autosave.start(260))
            widget.editingFinished.connect(lambda:self.autosave.start(1))
        for widget in self.findChildren(QCheckBox):
            widget.toggled.connect(lambda *_:self.autosave.start(120))

    @staticmethod
    def section(title,description=""):
        card=QFrame();card.setObjectName("SettingsCard")
        layout=QVBoxLayout(card);layout.setContentsMargins(20,18,20,18);layout.setSpacing(13)
        heading=QLabel(title);heading.setObjectName("SettingsTitle");layout.addWidget(heading)
        if description:
            sub=QLabel(description);sub.setObjectName("SmallMuted");sub.setWordWrap(True);layout.addWidget(sub)
        return card,layout

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(30,24,30,20);root.setSpacing(16)
        title=QLabel("设置");title.setObjectName("PageTitle");root.addWidget(title)
        note=QLabel("浏览器连接、巡检、提醒、数据与维护设置；FB 专业 ID 请使用右上角「ID管理」。")
        note.setObjectName("Subtitle");note.setWordWrap(True);root.addWidget(note)
        tabs=QTabWidget();tabs.setObjectName("SettingsTabs");root.addWidget(tabs,1)
        def make_tab(label):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
            body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(8,10,12,8);layout.setSpacing(14)
            scroll.setWidget(body);tabs.addTab(scroll,label);return layout
        account_layout=make_tab("浏览器与巡检")
        data_layout=make_tab("数据与迁移")

        browser,bl=self.section("01  Chrome 浏览器连接器","")
        row=QHBoxLayout();row.setSpacing(10)
        self.login_button=QPushButton("浏览器连接");self.login_button.setObjectName("PrimaryButton")
        self.login_button.clicked.connect(self.login_requested.emit);row.addWidget(self.login_button)
        self.connector_package_button=QPushButton(f"获取连接器 v{BUNDLED_CONNECTOR_VERSION}");self.connector_package_button.setObjectName("SecondaryButton")
        self.connector_package_button.setToolTip("将软件内置的浏览器连接器 ZIP 保存到你选择的位置")
        self.connector_package_button.clicked.connect(lambda:save_bundled_connector(self));row.addWidget(self.connector_package_button)
        row.addStretch();bl.addLayout(row)
        self.connector_summary=QLabel("等待浏览器连接");self.connector_summary.setWordWrap(True)
        self.connector_summary.setTextFormat(Qt.TextFormat.PlainText);bl.addWidget(self.connector_summary)
        account_layout.addWidget(browser)

        collect,cl=self.section("02  \u5de1\u68c0\u4e0e\u542f\u52a8",
            "\u6bcf\u8f6e\u4ee5\u57fa\u51c6\u95f4\u9694\u4e3a\u4e2d\u5fc3\u968f\u673a\u63d0\u524d\u6216\u5ef6\u540e\uff1b\u4e24\u4e2a\u4e3b\u9875\u4e4b\u95f4\u4e5f\u968f\u673a\u7b49\u5f85\u3002\u4e3b\u754c\u9762\u53ef\u76f4\u63a5\u4fee\u6539\u5e76\u81ea\u52a8\u4fdd\u5b58\u3002")
        form=QGridLayout();form.setHorizontalSpacing(18);form.setVerticalSpacing(13)
        self.interval=DirectNumberSpinBox();self.interval.setRange(5,1440);self.interval.setToolTip("单位：分钟")
        self.jitter_min=DirectNumberSpinBox();self.jitter_min.setRange(0,1439);self.jitter_min.setToolTip("单位：分钟")
        self.jitter_max=DirectNumberSpinBox();self.jitter_max.setRange(0,1439);self.jitter_max.setToolTip("单位：分钟")
        self.gap_min=DirectNumberSpinBox();self.gap_min.setRange(0,120);self.gap_min.setToolTip("单位：秒")
        self.gap_max=DirectNumberSpinBox();self.gap_max.setRange(0,120);self.gap_max.setToolTip("单位：秒")
        form.addWidget(QLabel("每轮间隔（分钟）"),0,0);form.addWidget(self.interval,0,1)
        float_label=QLabel("浮动范围（分钟）");form.addWidget(float_label,0,2)
        float_box=QWidget();float_layout=QHBoxLayout(float_box);float_layout.setContentsMargins(0,0,0,0);float_layout.setSpacing(6)
        float_layout.addWidget(self.jitter_min);float_layout.addWidget(QLabel("–"));float_layout.addWidget(self.jitter_max);float_layout.addStretch();form.addWidget(float_box,0,3)
        form.addWidget(QLabel("主页间隔（秒）"),1,0)
        gap_box=QWidget();gap_layout=QHBoxLayout(gap_box);gap_layout.setContentsMargins(0,0,0,0);gap_layout.setSpacing(6)
        gap_layout.addWidget(self.gap_min);gap_layout.addWidget(QLabel("–"));gap_layout.addWidget(self.gap_max);gap_layout.addStretch();form.addWidget(gap_box,1,1,1,3)
        for widget in (self.interval,self.jitter_min,self.jitter_max,self.gap_min,self.gap_max):widget.setFixedWidth(86)
        self.start_auto=QCheckBox("\u542f\u52a8\u8f6f\u4ef6\u65f6\u81ea\u52a8\u5de1\u68c0\uff08\u9ed8\u8ba4\u5173\u95ed\uff09")
        self.start_auto.setToolTip("\u53ea\u6709\u5728\u6b64\u660e\u786e\u5f00\u542f\uff0c\u4e0b\u6b21\u542f\u52a8\u624d\u81ea\u52a8\u5de1\u68c0\u3002\u4e3b\u9875\u7684\u6309\u94ae\u4ec5\u63a7\u5236\u672c\u6b21\u8fd0\u884c\u3002")
        self.silent_to_tray=QCheckBox("\u9759\u9ed8\u6536\u8d77\u5230\u6258\u76d8\uff08\u5173\u95ed\u6b64\u9879\u4f1a\u663e\u793a\u63d0\u793a\uff09")
        self.silent_to_tray.setToolTip("\u5f00\u542f\uff1a\u5173\u95ed\u7a97\u53e3\u4e0d\u63d0\u793a\u3002\u5173\u95ed\uff1a\u6536\u8d77\u65f6\u63d0\u793a\u4ecd\u5728\u540e\u53f0\u8fd0\u884c\u3002\u4e24\u79cd\u60c5\u51b5\u90fd\u4fdd\u6301\u6258\u76d8\u5de1\u68c0\uff0c\u5b8c\u5168\u9000\u51fa\u8bf7\u7528\u6258\u76d8\u83dc\u5355\u3002")
        form.addWidget(self.start_auto,2,0,1,4);form.addWidget(self.silent_to_tray,3,0,1,4)
        tip=QLabel("默认：120分钟±(15–25)分钟；主页间隔每次随机6–9秒。将浮动两项设为0可使用固定轮次间隔。多浏览器时只在用户选择的在线连接器之间并行分配任务。")
        tip.setObjectName("SmallMuted");tip.setWordWrap(True);form.addWidget(tip,4,0,1,4)
        form.setColumnStretch(1,1);form.setColumnStretch(3,1);cl.addLayout(form);account_layout.addWidget(collect)

        alert,al=self.section("03  增长提醒",
            "增长和发帖异常使用不会自动关闭的专用预警窗口；删除、更新安装、失败等重要事项仍需确认。普通成功提示显示为短暂气泡。")
        ar=QGridLayout();ar.setVerticalSpacing(12);ar.setHorizontalSpacing(12)
        self.alert_enabled=QCheckBox("开启桌面增长提醒");self.sound=QCheckBox("触发提醒时播放系统提示音")
        ar.addWidget(self.alert_enabled,0,0,1,2);ar.addWidget(self.sound,0,2,1,2)
        ar.addWidget(QLabel("单次增长阈值"),1,0)
        self.threshold=DirectNumberSpinBox();self.threshold.setRange(1,100_000_000);self.threshold.setSingleStep(100);self.threshold.setToolTip("粉丝数")
        ar.addWidget(self.threshold,1,1)
        ar.addWidget(QLabel("同一主页冷却时间"),1,2)
        self.cooldown=DirectNumberSpinBox();self.cooldown.setRange(5,1440);self.cooldown.setToolTip("单位：分钟");ar.addWidget(self.cooldown,1,3)
        al.addLayout(ar);account_layout.addWidget(alert);account_layout.addStretch()

        data,dl=self.section("数据管理",
            "保存专业 ID、当前状态、今日计算基准和通知；不保存历史快照。目录迁移会同时迁移设置、头像与默认浏览器资料。")
        self.data_path_label=QLabel(str(DATA_DIR));self.data_path_label.setObjectName("PathLabel");self.data_path_label.setWordWrap(True);dl.addWidget(self.data_path_label)
        buttons=QHBoxLayout()
        self.choose_data_dir=QPushButton("更改保存目录并迁移数据");self.choose_data_dir.setObjectName("PrimaryButton")
        self.choose_data_dir.clicked.connect(self.data_dir_requested.emit);buttons.addWidget(self.choose_data_dir)
        folder=QPushButton("打开数据目录");folder.setObjectName("SecondaryButton")
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR))));buttons.addWidget(folder)
        backup=QPushButton("备份数据库");backup.setObjectName("SecondaryButton");backup.clicked.connect(self.backup_requested.emit)
        buttons.addWidget(backup);buttons.addStretch();dl.addLayout(buttons);data_layout.addWidget(data)

        updates,ul=self.section("版本更新与保存",
            "仅检查正式稳定版本；所有设置保存在当前数据目录的 settings.ini。更新下载完成后仍需用户确认才会执行。")
        self.auto_update=QCheckBox("启动后自动检查新版本，并在发现新版时提示")
        ul.addWidget(self.auto_update)
        self.settings_path_label=QLabel(self.settings.fileName());self.settings_path_label.setObjectName("PathLabel");self.settings_path_label.setWordWrap(True)
        ul.addWidget(self.settings_path_label);data_layout.addWidget(updates)

        maintenance,ml=self.section("智能维护",
            "只清理可重新生成的更新缓存、残留临时文件和过大的运行日志；不会删除专业 ID、通知、头像、设置或浏览器连接记录。")
        maintenance_row=QHBoxLayout();maintenance_row.setSpacing(10)
        clean_btn=QPushButton("智能清理缓存");clean_btn.setObjectName("PrimaryButton")
        clean_btn.clicked.connect(self.cleanup_requested.emit);maintenance_row.addWidget(clean_btn)
        self.cleanup_status=QLabel("扫描后会先显示可清理内容和预计释放空间，再由你确认。")
        self.cleanup_status.setObjectName("SmallMuted");self.cleanup_status.setWordWrap(True)
        maintenance_row.addWidget(self.cleanup_status,1);ml.addLayout(maintenance_row);data_layout.addWidget(maintenance);data_layout.addStretch()
        self.save_note=QLabel("所有设置修改后自动保存，下次启动继续使用");self.save_note.setObjectName("SmallMuted")
        root.addWidget(self.save_note)

    def refresh_data_path(self):
        self.data_path_label.setText(str(DATA_DIR));self.settings_path_label.setText(self.settings.fileName())

    def open_monitor_directory(self):
        self.login_requested.emit()

    def load_settings(self):
        minutes,j0,j1,g0,g1=random_inspection_timing(self.settings)
        pairs=((self.interval,minutes),(self.jitter_min,j0),(self.jitter_max,j1),(self.gap_min,g0),(self.gap_max,g1),
               (self.threshold,_bounded_int(self.settings.value("alert_threshold",500),500,1,100_000_000)),
               (self.cooldown,_bounded_int(self.settings.value("alert_cooldown_minutes",30),30,5,1440)))
        for widget,value in pairs:
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        for widget,key,default in ((self.start_auto,"start_auto",False),(self.silent_to_tray,"silent_to_tray",True),
                (self.alert_enabled,"alert_enabled",True),(self.sound,"alert_sound",True),
                (self.auto_update,"auto_check_updates",True)):
            widget.blockSignals(True);widget.setChecked(is_true(self.settings.value(key,default),default));widget.blockSignals(False)

    def save_settings(self):
        timing=save_random_timing(self.settings,(self.interval.value(),self.jitter_min.value(),self.jitter_max.value(),self.gap_min.value(),self.gap_max.value()))
        for widget,value in zip((self.interval,self.jitter_min,self.jitter_max,self.gap_min,self.gap_max),timing):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        values={
            "start_auto":int(self.start_auto.isChecked()),
            "min_to_tray":1,"silent_to_tray":int(self.silent_to_tray.isChecked()),"alert_enabled":int(self.alert_enabled.isChecked()),
            "alert_sound":int(self.sound.isChecked()),"alert_threshold":self.threshold.value(),
            "alert_cooldown_minutes":self.cooldown.value(),"auto_check_updates":int(self.auto_update.isChecked()),
        }
        for key,value in values.items():self.settings.setValue(key,value)
        self.settings.sync()
        if self.settings.status()!=QSettings.Status.NoError:
            raise OSError("无法写入配置文件："+self.settings.fileName())

    def _request_autosave(self):
        self.save_requested.emit(False)

    def flush_pending(self):
        if self.autosave.isActive():
            self.autosave.stop()
            # Keep MainWindow's runtime schedule and quick controls in sync, too.
            self.save_requested.emit(False)
        # Flush all controls even if a last click has not yet scheduled the debounce timer.
        self.save_settings()




class QuickToolTipStyle(QProxyStyle):
    def styleHint(self,hint,option=None,widget=None,returnData=None):
        if hint==QStyle.StyleHint.SH_ToolTip_WakeUpDelay:return 60
        if hint==QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:return 0
        return super().styleHint(hint,option,widget,returnData)

class UpdateWorker(QObject):
    done=pyqtSignal(dict)
    progress=pyqtSignal(object,object)
    def __init__(self,operation,info=None,folder=None):
        super().__init__();self.operation=operation;self.info=info or {};self.folder=folder;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            if self.operation=="check":
                result=query_latest_release()
            elif self.operation=="download":
                path=download_release_asset(self.info["asset"],self.folder,
                    progress=lambda a,b:self.progress.emit(a,b),cancel=self.cancel_event)
                result={"status":"ready","path":path,"info":self.info}
            else:
                path=validate_staged_update(self.info["asset"],self.info["path"],self.folder)
                result={"status":"ready","path":str(path),"info":self.info}
        except Exception as exc:
            result={"status":"cancelled" if self.cancel_event.is_set() else "error","message":str(exc)[:600]}
        self.done.emit(result)

class UpdateDialog(QDialog):
    download_requested=pyqtSignal()
    install_requested=pyqtSignal()
    later_requested=pyqtSignal()
    cancel_requested=pyqtSignal()
    def __init__(self,info,parent=None):
        super().__init__(parent);self.info=info;self.ready_path=""
        self.setWindowTitle("发现新版本 · "+APP_TITLE);self.resize(630,530)
        root=QVBoxLayout(self);root.setContentsMargins(24,22,24,20);root.setSpacing(13)
        heading=QLabel("新版本 V"+str(info.get("version","")));heading.setObjectName("PageTitle");root.addWidget(heading)
        repo=QLabel("当前 V"+APP_VERSION+"   →   V"+str(info.get("version","")))
        repo.setObjectName("SmallMuted");root.addWidget(repo)
        title=QLabel(str(info.get("title") or "版本更新"));title.setTextFormat(Qt.TextFormat.PlainText);title.setWordWrap(True);root.addWidget(title)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setPlainText(str(info.get("notes") or "暂无更新日志"))
        root.addWidget(self.notes,1)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setObjectName("SmallMuted");root.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.hide();root.addWidget(self.progress)
        row=QHBoxLayout();row.addStretch()
        self.cancel_btn=QPushButton();self.cancel_btn.hide()
        self.later=QPushButton("以后再说");self.later.clicked.connect(self._later);row.addWidget(self.later)
        self.action=QPushButton("升级");self.action.setObjectName("PrimaryButton");self.action.clicked.connect(self._action);row.addWidget(self.action)
        root.addLayout(row)
        asset=info.get("asset")
        if not asset:
            self.action.setEnabled(False);self.status.setText("此版本尚未上传适合当前系统的更新包。")
        elif not asset.get("sha256"):
            self.action.setEnabled(False);self.status.setText("发布包缺少 SHA-256，自动下载暂不可用，请发布者完善 Release 资产校验信息。")
        else:
            self.status.setText("下载将在后台进行；不会在下载后未经确认就退出或安装。"+
                ("\n当前为源码运行方式：下载的新文件不会自动覆盖正在执行的 Python 文件。" if asset.get("source_mode") else ""))
    def _action(self):
        if self.ready_path:self.install_requested.emit()
        else:self.download_requested.emit()
    def _later(self):
        self.later_requested.emit();self.hide()
    def downloading(self):
        self.action.setEnabled(False);self.progress.show()
        self.status.setText("正在后台下载。可以选择“以后再说”关闭窗口，下载会继续。")
    def set_progress(self,done,total):
        self.progress.setValue(int(100*int(done)/max(1,int(total))))
        self.status.setText(f"已下载 {int(done)/1048576:.1f} / {int(total)/1048576:.1f} MB，完成后校验 SHA-256。")
    def ready(self,path):
        self.ready_path=str(path);self.progress.show();self.progress.setValue(100);self.action.setEnabled(True)
        allowed,reason=signed_install_available(self.info.get("asset") or {})
        self.action.setText("现在更新" if allowed else "打开下载目录")
        self.status.setText("下载和完整性校验完成。\n"+("下载完成，是否现在更新？点击“现在更新”会安全结束巡检并重启；也可以选择“以后再说”。" if allowed else reason))
    def error(self,text):
        self.status.setText(str(text));self.action.setEnabled(bool((self.info.get("asset") or {}).get("sha256")))


class WindowResizeHandle(QWidget):
    """Transparent native resize edge for the frameless main window."""
    def __init__(self,edges,cursor,parent=None):
        super().__init__(parent);self.edges=edges;self.setCursor(cursor);self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,False)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and not self.window().isMaximized():
            handle=self.window().windowHandle()
            try:
                if handle and handle.startSystemResize(self.edges):
                    event.accept();return
            except Exception:pass
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Window)
        self._ui_restoring=True
        legacy=QSettings("GrowthRadar","FBGrowthRadar")
        directory=read_settings_location(DATA_DIR,str(legacy.value("data_directory","") or ""))
        self._set_paths(directory)
        ini=DATA_DIR/"settings.ini";first_local=not ini.exists()
        self.settings=QSettings(str(ini),QSettings.Format.IniFormat);self.settings.setFallbacksEnabled(False)
        if first_local and not os.environ.get("FBPM_DATA_DIR"):
            for key in legacy.allKeys():self.settings.setValue(key,legacy.value(key))
        self._preferences_migrated=migrate_runtime_preferences(self.settings)
        migrate_random_preferences(self.settings)
        self._settings_timing=random_inspection_timing(self.settings)
        self.settings.setValue("data_directory",str(DATA_DIR));self.settings.sync()
        if self.settings.status()!=QSettings.Status.NoError:raise RuntimeError("无法写入本地配置文件："+str(ini))
        write_settings_location(DATA_DIR)
        self._update_thread=None;self._update_worker=None;self._update_dialog=None;self._update_info=None
        self._update_manual=False;self._install_command=None
        self._ui_save_timer=QTimer(self);self._ui_save_timer.setSingleShot(True);self._ui_save_timer.timeout.connect(self.save_ui_state)
        self._updates_timer=QTimer(self);self._updates_timer.setInterval(6*60*60*1000)
        self._updates_timer.timeout.connect(lambda:self.check_for_updates(False))
        self.store=Store(DB_PATH)
        def old_json(key,fallback):
            try:return json.loads(str(self.settings.value(key,json.dumps(fallback))))
            except (ValueError,TypeError):return fallback
        self.store.migrate_legacy_settings(old_json("post_monitor_rules",[]),old_json("post_monitor_data",{}))
        self.worker=None;self.worker_thread=None;self.login_worker=None;self.login_thread=None
        self._closing=False;self._maintenance=False;self._tray_hint_shown=False
        self.auto_enabled=False;self.next_run_at=None;self.active_run_id=None
        self.run_started_at=None;self.run_ok=0;self.run_fail=0;self.current_purpose="monitor"
        self._tick=0;self._popup=None;self._notice_queue=[];self._toast=None
        self.auto_timer=QTimer(self);self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(lambda:self.start_collection(False))
        self.count_timer=QTimer(self);self.count_timer.setInterval(1000);self.count_timer.timeout.connect(self.update_countdown)
        self.paint_timer=QTimer(self);self.paint_timer.setSingleShot(True);self.paint_timer.timeout.connect(self.refresh_all)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.flush_notices)
        self.apply_theme(str(self.settings.value("ui_theme","蓝橙曜石")),refresh=False)
        app_icon=make_app_icon()
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon);self.setWindowTitle(APP_TITLE+" · "+APP_VERSION)
        self.resize(1536,1024);self.setMinimumSize(980,680)
        self.tray=QSystemTrayIcon(make_app_icon(),self);self.tray.setToolTip(APP_TITLE)
        self.tray_menu=QMenu(self)
        self.tray_menu.addAction("打开监控看板",self.show_dashboard)
        self.tray_menu.addAction("立即巡检",self.dashboard_run_button)
        self.tray_menu.addAction("启用 / 暂停自动巡检",self.toggle_auto)
        self.tray_menu.addSeparator();self.tray_menu.addAction("完全退出",self.exit_application)
        self.tray.setContextMenu(self.tray_menu);self.tray.activated.connect(self.on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        self.connector=ConnectorBridge(DATA_DIR/"connector_registry.json",CONNECTOR_PORT)
        if not os.environ.get("FBPM_TEST_MODE"):
            try:self.connector.start()
            except ConnectorError as exc:log_exception(str(exc))
        self._connector_dialog=None
        self._connector_timer=QTimer(self);self._connector_timer.setInterval(1000)
        self._connector_timer.timeout.connect(self.refresh_connector_summary)
        self.build_ui();self.apply_style();self.refresh_all();self.count_timer.start()
        self._connector_timer.start();self.refresh_connector_summary()
        self.size_grip=QSizeGrip(self);self.size_grip.setFixedSize(16,16)
        self.size_grip.move(self.width()-18,self.height()-18);self.size_grip.raise_()
        self._create_resize_handles()
        QTimer.singleShot(0,self.restore_ui_state)
        if not os.environ.get("FBPM_TEST_MODE") and "--diagnose" not in sys.argv:
            QTimer.singleShot(1800,self.startup_update_check);self._updates_timer.start()
        if self.store.upgrade_backup:self.dashboard.status.setText("升级前安全备份已保存："+self.store.upgrade_backup)
        if is_true(self.settings.value("start_auto","0")) and not os.environ.get("FBPM_TEST_MODE") and "--diagnose" not in sys.argv:
            QTimer.singleShot(900,self.start_auto)

    @staticmethod
    def _set_paths(path):
        global DATA_DIR,DB_PATH,BROWSER_PROFILE_DIR,AVATAR_DIR
        DATA_DIR=ensure_private_directory(Path(path))
        DB_PATH=DATA_DIR/"fb_growth_radar_v1.db";BROWSER_PROFILE_DIR=DATA_DIR/"browser_profile";AVATAR_DIR=DATA_DIR/"avatars"

    def build_ui(self):
        root=QWidget();root.setObjectName("Root");self.setCentralWidget(root)
        layout=QVBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        header=DraggableHeader();header.setObjectName("HeaderBar");header.setFixedHeight(64)
        bar=QHBoxLayout(header);bar.setContentsMargins(18,8,10,8);bar.setSpacing(7)
        self.brand_mark=BrandMark(40);bar.addWidget(self.brand_mark);bar.addSpacing(4)
        self.brand_name=QLabel(APP_TITLE);self.brand_name.setObjectName("BrandName")
        self.brand_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);bar.addWidget(self.brand_name)
        tagline=QLabel("专业主页 · 粉丝与发帖监控");tagline.setObjectName("BrandSub")
        tagline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);bar.addWidget(tagline);bar.addStretch()
        self.brand_caption=tagline
        self.page_nav_buttons={}
        for index,kind,tip in ((0,"home","返回主界面"),(3,"pages","FB专业ID管理")):
            btn=icon_button(kind,tip,self)
            if index==0:
                btn.setText("主页");btn.setObjectName("HomePill");btn.setFixedSize(90,40)
                btn.setIcon(ui_icon("home","#FFFFFF"));btn.setToolTip("返回主页")
            else:
                btn.setText("ID管理");btn.setObjectName("HeaderAction");btn.setFixedSize(104,40)
            btn.clicked.connect(lambda _=False,i=index:self.switch_page(i));bar.addWidget(btn)
            self.page_nav_buttons[index]=btn
        connector_wrap=QWidget();connector_wrap.setFixedSize(102,42);connector_grid=QGridLayout(connector_wrap);connector_grid.setContentsMargins(0,0,0,0)
        self.connector_button=icon_button("browser","\u6d4f\u89c8\u5668\u8fde\u63a5",connector_wrap)
        self.connector_button.setText("\u6d4f\u89c8\u5668");self.connector_button.setObjectName("HeaderAction");self.connector_button.setFixedSize(96,40)
        self.connector_button.clicked.connect(self.open_login_browser);connector_grid.addWidget(self.connector_button,0,0)
        self.connector_dot=QLabel(connector_wrap);self.connector_dot.setObjectName("ConnectorDot");self.connector_dot.setFixedSize(12,12)
        self.connector_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        connector_grid.addWidget(self.connector_dot,0,0,Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignRight);bar.addWidget(connector_wrap)
        self.theme_pill=QPushButton("主题 · "+self.theme_name);self.theme_pill.setObjectName("ThemePill");self.theme_pill.setProperty("iconKind","theme");self.theme_pill.setIcon(ui_icon("theme",ACCENT));self.theme_pill.setIconSize(QSize(18,18))
        self.theme_pill.setFixedSize(140,40);self.theme_pill.setToolTip("切换主题：蓝橙曜石、石墨黑、清爽白、护眼绿")
        self.theme_pill.clicked.connect(self.show_theme_menu);bar.addWidget(self.theme_pill)
        wrap=QWidget();wrap.setFixedSize(84,42);grid=QGridLayout(wrap);grid.setContentsMargins(0,0,0,0)
        self.notification_btn=icon_button("bell","通知",wrap)
        self.notification_btn.setText("通知");self.notification_btn.setObjectName("HeaderAction");self.notification_btn.setFixedSize(80,40)
        self.notification_btn.clicked.connect(lambda:self.switch_page(2));grid.addWidget(self.notification_btn,0,0)
        self.notification_badge=QLabel();self.notification_badge.setObjectName("NotificationBadge")
        self.notification_badge.setFixedSize(19,17);self.notification_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        grid.addWidget(self.notification_badge,0,0,Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignRight);bar.addWidget(wrap)
        self.page_nav_buttons[2]=self.notification_btn
        self.settings_btn=icon_button("settings","设置",self);self.settings_btn.setText("设置");self.settings_btn.setObjectName("HeaderAction");self.settings_btn.setFixedSize(80,40);self.settings_btn.clicked.connect(lambda:self.switch_page(4));bar.addWidget(self.settings_btn)
        self.page_nav_buttons[4]=self.settings_btn
        self.update_btn=icon_button("update","检查更新",self);self.update_btn.setObjectName("UpdateButton")
        self.update_btn.setProperty("hasUpdate",False);self.update_btn.clicked.connect(lambda _=False:self.check_for_updates(True));bar.addWidget(self.update_btn)
        line=QFrame();line.setObjectName("HeaderDivider");line.setFixedSize(1,26);bar.addWidget(line)
        minimum=icon_button("min","最小化",self,34);minimum.clicked.connect(self.showMinimized);bar.addWidget(minimum)
        self.max_btn=icon_button("max","最大化 / 还原",self,34);self.max_btn.clicked.connect(self.toggle_maximized);bar.addWidget(self.max_btn)
        close=icon_button("close","关闭",self,34);close.setObjectName("CloseWindowButton");close.clicked.connect(self.close);bar.addWidget(close)
        layout.addWidget(header)
        self.stack=QStackedWidget();self.stack.setObjectName("MainStack")
        self.dashboard=DashboardPage(self.store,self.settings)
        reserved_slot=QWidget()  # retired history slot; not exposed in navigation
        self.alerts=AlertsPage(self.store)
        self.page_manager=PageManagementPage(self.store,self.settings)
        self.settings_page=SettingsPage(self.store,self.settings)
        for page in (self.dashboard,reserved_slot,self.alerts,self.page_manager,self.settings_page):self.stack.addWidget(page)
        layout.addWidget(self.stack,1);self.wire_signals();self.switch_page(0)

    def wire_signals(self):
        d=self.dashboard;d.collect_once.connect(self.dashboard_run_button);d.toggle_auto.connect(self.toggle_auto)
        d.view_alerts.connect(lambda:self.switch_page(2));d.open_manager.connect(self.open_manager)
        d.open_page.connect(self.open_page);d.timing_changed.connect(self.on_quick_timing_changed)
        m=self.page_manager;m.add_requested.connect(self.open_batch_dialog)
        m.delete_requested.connect(self.delete_ids)
        m.config_changed.connect(self.refresh_dashboard)
        self.alerts.ack_requested.connect(self.ack_alerts);self.alerts.read_changed.connect(self.refresh_dashboard)
        settings=self.settings_page;settings.login_requested.connect(self.open_login_browser)
        settings.save_requested.connect(self.save_settings)
        settings.export_requested.connect(self.export_csv);settings.backup_requested.connect(self.backup_db)
        settings.data_dir_requested.connect(self.move_data_directory);settings.cleanup_requested.connect(self.smart_cleanup_cache)

    def switch_page(self,index):
        if index not in (0,2,3,4):index=0
        self.stack.setCurrentIndex(index)
        if not self._ui_restoring:
            self.settings.setValue("ui/page",index);self.settings.sync()
        for idx,button in self.page_nav_buttons.items():
            button.setProperty("active",idx==index);button.style().unpolish(button);button.style().polish(button)
        if index==0:self.refresh_dashboard()
        elif index==2:self.alerts.open_current()
        elif index==3:self.page_manager.refresh()
        elif index==4:self.settings_page.refresh_data_path()

    def open_manager(self,pid=""):
        self.switch_page(3)
        if pid:self.page_manager.focus_id(pid);self.page_manager.edit_id(pid)

    def _update_header_icons(self,unread=None):
        if not hasattr(self,"page_nav_buttons"):return
        colors={"pages":CYAN,"browser":GREEN,"theme":ACCENT,"settings":CYAN,"update":MUTED}
        for button in self.findChildren(QPushButton):
            kind=button.property("iconKind")
            if not kind:continue
            if button.objectName()=="HomePill":color="#FFFFFF"
            elif kind=="bell":color=RED if (unread or 0)>0 else CYAN
            elif kind=="browser":color=GREEN if (hasattr(self,"connector") and self.selected_connectors()) else RED
            elif kind=="update" and getattr(self,"_update_available",False):color=AMBER
            else:color=colors.get(kind,MUTED)
            button.setIcon(ui_icon(kind,color))

    def set_update_attention(self,active,version=""):
        self._update_available=bool(active)
        if not hasattr(self,"update_btn"):return
        self.update_btn.setProperty("hasUpdate",bool(active))
        self.update_btn.setToolTip(("有新版本 V"+str(version)+" 待更新") if active else "检查更新")
        self.update_btn.style().unpolish(self.update_btn);self.update_btn.style().polish(self.update_btn)
        self._update_header_icons(sum(self.store.unread_totals()) if hasattr(self,"store") else 0)

    def refresh_dashboard(self):
        self.dashboard.refresh();self.dashboard.set_running(self.auto_enabled,self.worker_thread is not None)
        g,p=self.store.unread_totals();n=g+p
        self.notification_badge.setText(str(n) if n<100 else "99+");self.notification_badge.setVisible(n>0)
        self.notification_btn.setToolTip(f"通知 · {n} 条未读")
        self._update_header_icons(n)

    def refresh_all(self):
        self.refresh_dashboard()
        index=self.stack.currentIndex()
        if index==2:self.alerts.refresh()
        elif index==3:self.page_manager.refresh()

    def open_alert_notification(self,entry):
        self.show();self.showNormal();self.raise_();self.activateWindow();self.switch_page(2)
        self.alerts.focus_alert(entry or {})

    def schedule_refresh(self):
        if not self.paint_timer.isActive():self.paint_timer.start(450)

    def open_batch_dialog(self):
        if self._tasks_busy():return
        dlg=BatchAddDialog(self)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        parsed=normalize_page_ids(dlg.text())
        if dlg.mode()=="replace":
            old={p["page_id"] for p in self.store.list_pages()}
            removed=len(old-set(parsed.ids))
            answer=QMessageBox.question(self,"确认覆盖当前 ID 列表",
                f"当前 {len(old)} 个 ID，将移除不在新列表中的 {removed} 个 ID。\n只保留当前监控设置；新列表中已存在 ID 的配置也会保留。\n\n确认覆盖？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        try:
            result=self.store.import_ids(parsed.ids,dlg.mode(),dlg.growth.isChecked(),dlg.posts.isChecked(),dlg.hours.value())
        except Exception as exc:QMessageBox.warning(self,"导入失败",str(exc));return
        self.switch_page(3);self.refresh_all()
        msg=f"新增 {result['added']} 个 · 已存在跳过 {result['skipped']} 个 · 移除 {result['removed']} 个"
        self.dashboard.status.setText(msg);show_hint(self,msg+"\n\n名称和头像会在正常巡检时自动更新。")

    def delete_ids(self,ids):
        if self._tasks_busy():return
        ids=list(dict.fromkeys(ids))
        answer=QMessageBox.question(self,"确认批量删除",
            f"从当前列表移除 {len(ids)} 个专业 ID？\n\n对应的当前状态与今日基准会移除；已有通知保留。重新添加同一 ID 将重新建立基准。",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.store.delete_ids(ids,False);self.refresh_all()
        self.show_toast(f"已移除 {len(ids)} 个专业 ID")

    def _tasks_busy(self):
        if self.worker_thread is not None or self.login_thread is not None or self._maintenance:
            show_hint(self,"请等待当前巡检或连接任务结束后再操作。暂停不会结束当前任务。")
            return True
        return False

    def dashboard_run_button(self):
        if self.worker is not None:self.toggle_pause_collection()
        else:self.start_collection(True)

    def toggle_pause_collection(self):
        if self.worker is None:return
        self.dashboard.paused=self.worker.toggle_pause()
        self.dashboard.set_running(self.auto_enabled,True)
        self.dashboard.status.setText("已请求暂停：当前主页处理完成后停止进入下一页" if self.dashboard.paused else "继续本轮巡检")

    def start_collection(self,once=True):
        if self._closing or self._maintenance:return
        if self.login_thread is not None:
            if once:show_hint(self,"请先关闭登录浏览器，再巡检。")
            elif self.auto_enabled:self.auto_timer.start(30000)
            return
        if self.worker_thread is not None:return
        pages=self.store.list_pages(enabled_only=True)
        if not pages:
            self.stop_auto()
            if once:show_hint(self,"请在 FB专业ID管理中添加 ID，并至少勾选一个监控模块。")
            return
        self._start_worker(pages,"monitor")

    def sync_profiles(self,ids):
        if self._tasks_busy():return
        chosen=set(ids);pages=[p for p in self.store.list_pages() if p["page_id"] in chosen]
        if pages:self._start_worker(pages,"metadata")

    def _start_worker(self,pages,purpose):
        try:self.settings_page.flush_pending()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"\u8bbe\u7f6e\u672a\u80fd\u4fdd\u5b58",str(exc));return
        cids=self.selected_connectors(require_all=False)
        if not cids:
            self.dashboard.status.setText("浏览器连接未就绪，请打开已安装连接器的 Chrome")
            if self.auto_enabled:self.stop_auto()
            else:self.show_toast("请先确认右上角浏览器连接状态")
            return
        if len(pages)<len(cids):
            self.show_toast(f"本轮只有 {len(pages)} 个任务，少于已选 {len(cids)} 个连接器，请减少连接器数量")
            if self.auto_enabled:self.stop_auto()
            return
        self.auto_timer.stop();self.next_run_at=None;self.current_purpose=purpose
        self.active_run_id=uuid.uuid4().hex;self.store.start_run(self.active_run_id,len(pages))
        self.run_started_at=time.time();self.run_ok=0;self.run_fail=0
        self.worker_thread=QThread(self);timing=random_inspection_timing(self.settings)
        self.worker=ConnectorCollectWorker(pages,self.connector,cids,purpose=purpose,gap_range=timing[3:])
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_collect_result);self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_collection_finished)
        self.worker.finished.connect(self.worker.deleteLater);self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_worker)
        self.dashboard.paused=False;self.dashboard.set_running(self.auto_enabled,True);self.page_manager.set_busy(True)
        self.dashboard.status.setText(f"通过 {len(cids)} 个 Chrome 连接器并行开始任务 · {len(pages)} 个 ID")
        self.worker_thread.start()

    def on_progress(self,current,total,info):
        self.dashboard.status.setText(f"{info}  ·  {current}/{total}")

    def on_collect_result(self,data):
        options={key:self.settings.value(key,default) for key,default in
                 (("interval_minutes",DEFAULT_INTERVAL_MINUTES),("alert_threshold",500),("alert_enabled",1),("alert_cooldown_minutes",30))}
        try:out=self.store.apply_collection(data,options,self.current_purpose)
        except Exception as exc:
            import traceback;log_exception(traceback.format_exc())
            self.run_fail+=1;self.dashboard.status.setText("记录保存失败："+str(exc)[:180]);return
        if out.get("ignored"):return
        if out["success"]:self.run_ok+=1
        else:self.run_fail+=1
        if out.get("error"):self.dashboard.status.setText(str(data.get("page_id"))+" · "+out["error"][:180])
        if out["alerts"]:
            self._notice_queue.extend(out["alerts"])
            if not self.notice_timer.isActive():self.notice_timer.start(500)
        self.schedule_refresh()

    def flush_notices(self):
        queued=self._notice_queue;self._notice_queue=[]
        if not queued:return
        fresh=self.store.combined_alerts(limit=300,unread_only=True);entries=[]
        for raw in queued:
            match=next((row for row in fresh if row.get("kind")==raw.get("kind") and row.get("page_id")==raw.get("page_id")
                        and (not raw.get("id") or int(row.get("id") or 0)==int(raw.get("id") or 0))),None)
            item=dict(match or raw)
            pid=str(item.get("page_id") or "")
            page=self.store.page(pid) or {}
            # Popup must use the same avatar cache as the dashboard. A queued/stale path
            # must never override the current valid page avatar.
            current_avatar=str(page.get("avatar_path") or "") if isinstance(page,dict) else ""
            cached=AVATAR_DIR/(pid+".png") if pid else None
            if current_avatar and Path(current_avatar).is_file():
                item["avatar_path"]=current_avatar
            elif cached is not None and cached.is_file():
                item["avatar_path"]=str(cached)
            elif not (item.get("avatar_path") and Path(str(item.get("avatar_path"))).is_file()):
                item["avatar_path"]=""
            if page:
                item["page_name"]=display_name(page)
                item.setdefault("name",item["page_name"])
            entries.append(item)
        if not hasattr(self,'_monitor_alert_popups'):self._monitor_alert_popups=[]
        self._monitor_alert_popups=[p for p in self._monitor_alert_popups if p.isVisible()]
        popup=PersistentMonitorAlert(entries,self,len(self._monitor_alert_popups))
        self._monitor_alert_popups.append(popup)
        popup.finished.connect(lambda _=0,p=popup:self._monitor_alert_popups.remove(p) if p in self._monitor_alert_popups else None)
        popup.show();popup.raise_();popup.activateWindow()
        if is_true(self.settings.value("alert_sound","1"),True):QApplication.beep()

    def on_collection_finished(self,ok,message):
        if self.active_run_id:
            state="completed" if ok and self.run_fail==0 else "partial" if self.run_ok else "failed"
            self.store.finish_run(self.active_run_id,self.run_ok,self.run_fail,state)
        if self.current_purpose=="monitor" and self.run_ok+self.run_fail>0:
            stamp=now_iso();self.settings.setValue("last_inspection_at",stamp);self.settings.sync()
            self.dashboard._last_inspection_stamp=stamp
            self.dashboard.run_badge.setText("上次巡检时间："+inspection_stamp_label(stamp))
        if "连接器中断" in message and self.auto_enabled:
            self.stop_auto();self.dashboard.status.setText(message+" · 自动巡检已暂停，请恢复浏览器连接后重新开启")
        else:self.dashboard.status.setText(message)
        self.schedule_refresh()

    def cleanup_worker(self):
        thread=self.worker_thread
        self.worker=None;self.worker_thread=None;self.active_run_id=None
        if thread:thread.deleteLater()
        self.dashboard.paused=False;self.page_manager.set_busy(False)
        self.dashboard.set_running(self.auto_enabled,False)
        if self._closing:self.check_pending_exit();return
        if self.auto_enabled:self.schedule_next_round(self.run_started_at)
        self.refresh_all()

    def toggle_auto(self):
        if self.auto_enabled:self.stop_auto()
        else:self.start_auto()

    def start_auto(self):
        if self.auto_enabled:return
        cids=self.selected_connectors(require_all=False)
        if not cids:
            self.show_toast("未检测到在线浏览器连接器，请先打开已安装连接器的 Chrome")
            return
        try:self.settings_page.flush_pending()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"设置未能保存",str(exc));return
        pages=self.store.list_pages(enabled_only=True)
        if not pages:
            self.show_toast("请先在 ID管理中选择粉丝监控或发帖监控。")
            return
        if len(pages)<len(cids):
            self.show_toast(f"监控任务 {len(pages)} 个，少于已选连接器 {len(cids)} 个，请减少连接器")
            return
        self.auto_enabled=True
        # Deliberately do NOT write start_auto or change the startup checkbox.
        if not self.worker_thread:self.start_collection(False)
        self.dashboard.set_running(True,self.worker_thread is not None)

    def stop_auto(self):
        # This only stops scheduling in this process; explicit startup preference is independent.
        self.auto_enabled=False;self.next_run_at=None;self.auto_timer.stop()
        self.dashboard.set_running(False,self.worker_thread is not None)
        self.dashboard.status.setText("已暂停自动巡检；当前任务可用巡检按钮暂停")

    def update_countdown(self):
        self._tick+=1
        if self.auto_enabled and self.next_run_at:
            secs=max(0,int(self.next_run_at-time.time()));mm,ss=divmod(secs,60)
            self.dashboard.next_run.setText(f"下次巡检 {mm:02d}:{ss:02d}")
        elif self.worker_thread:self.dashboard.next_run.setText("当前轮次进行中")
        elif self.auto_enabled:self.dashboard.next_run.setText("自动巡检等待中")
        else:self.dashboard.next_run.setText("自动巡检未开启")
        if self._tick%60==0 and not self._maintenance:self.refresh_dashboard()

    def open_login_browser(self):
        if self._connector_dialog is None:
            self._connector_dialog=BrowserConnectionsDialog(self)
        self._connector_dialog.refresh();self._connector_dialog.show()
        self._connector_dialog.raise_();self._connector_dialog.activateWindow()

    def connector_selection_initialized(self):
        return is_true(self.settings.value('connector/selection_initialized',0),False)

    def configured_connector_ids(self,include_offline=False):
        rows=self.connector.clients();by_id={r['instance_id']:r for r in rows if not r.get('blocked')}
        online=[r['instance_id'] for r in rows if r['online'] and not r.get('blocked')][:10]
        raw=str(self.settings.value('connector/selected_ids','') or '');ids=[]
        if raw:
            try:
                value=json.loads(raw);ids=[str(x) for x in value if str(x) in by_id][:10] if isinstance(value,list) else []
            except (ValueError,TypeError):ids=[]
        if not ids:
            legacy=str(self.settings.value('connector/selected_id','') or '')
            if legacy in by_id:ids=[legacy]
        # A single online connector is always zero-configuration: use it automatically.
        # Only when multiple connectors are online do we respect/ask for a saved selection.
        if len(online)==1:
            ids=[online[0]]
        elif len(online)>1 and not self.connector_selection_initialized():
            ids=online[:10]
        if include_offline:return list(dict.fromkeys(ids))[:10]
        return [cid for cid in ids if cid in online][:10]

    def set_connector_selection(self,ids,initialized=True):
        ids=list(dict.fromkeys(str(x) for x in ids if x))[:10]
        self.settings.setValue('connector/selected_ids',json.dumps(ids,ensure_ascii=False));self.settings.setValue('connector/selection_initialized',1 if initialized else 0)
        self.settings.remove('connector/selected_id');self.settings.remove('connector/selection_mode');self.settings.sync();self.refresh_connector_summary()

    def selected_connectors(self,require_all=False):
        configured=self.configured_connector_ids(include_offline=True);active=self.configured_connector_ids(include_offline=False)
        if require_all and configured and len(active)!=len(configured):return []
        return active

    def selected_connector(self):
        active=self.selected_connectors();return active[0] if active else ''

    def refresh_connector_summary(self):
        if self._closing:return
        if not self.connector._running and not os.environ.get('FBPM_TEST_MODE'):
            now=time.monotonic()
            if now-getattr(self,'_connector_last_retry',0)>10:
                self._connector_last_retry=now
                try:self.connector.start()
                except Exception as exc:self.connector.error=str(exc)
        rows=self.connector.clients();online=[r for r in rows if r['online'] and not r.get('blocked')]
        configured=self.configured_connector_ids(include_offline=True);active=self.configured_connector_ids(include_offline=False)
        outdated=[r for r in online if connector_needs_update(r.get('identity') or {})]
        if self.connector.error:text='浏览器连接服务异常：'+self.connector.error;state='error'
        elif not online:text='未检测到在线浏览器连接器';state='error'
        elif outdated:text=f'{len(outdated)} 个浏览器连接器版本较旧，可在设置中获取 v{BUNDLED_CONNECTOR_VERSION}';state='warn'
        elif len(online)==1:
            name=online[0]['identity'].get('profile_name') or ('Chrome '+online[0]['instance_id'][:6]);text='已自动连接：'+name;state='ok'
        elif configured and len(active)==len(configured):text=f'已连接 {len(active)} 个浏览器，任务将并行分配';state='ok'
        elif configured:text=f'已配置 {len(configured)} 个浏览器，其中 {len(active)} 个在线';state='warn'
        else:text=f'检测到 {len(online)} 个浏览器，请选择使用范围';state='warn'
        try:self.settings_page.connector_summary.setText(text)
        except Exception:pass
        self.connector_button.setToolTip(text+'\n点击查看浏览器连接')
        if hasattr(self,'connector_dot'):
            color={'ok':'#26C281','warn':'#F0A43A','error':'#E75768'}[state];self.connector_dot.setStyleSheet(f'background:{color};border:2px solid {BG};border-radius:6px;');self.connector_dot.setToolTip(text)
        if self.auto_enabled and not active:
            if self.worker is not None:self.worker.stop()
            self.stop_auto();self.dashboard.status.setText('所有可用浏览器连接均已中断，自动巡检已暂停')

    def activate_existing_window(self):
        # Restore this window and the user's current page; do not start a task.
        if self.isMaximized():self.showMaximized()
        else:self.showNormal()
        self.raise_();self.activateWindow()
        if os.name=="nt":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:pass

    def on_login_finished(self,message):
        self.dashboard.status.setText(message)
        if message.startswith("登录浏览器失败"):QMessageBox.warning(self,"登录失败",message)

    def cleanup_login(self):
        if self.login_thread:self.login_thread.deleteLater()
        self.login_worker=None;self.login_thread=None;self.page_manager.set_busy(False)
        if self._closing:self.check_pending_exit()
        elif self.auto_enabled:self.next_run_at=time.time()+2;self.auto_timer.start(2000)

    def save_settings(self, show_hint=False):
        previous=self._settings_timing
        try:self.settings_page.save_settings()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"保存失败",str(exc));return
        self._apply_timing(previous)
        self.dashboard.status.setText("设置已保存")
        self.settings_page.save_note.setText("已自动保存 · 下次启动保留")
        self.refresh_all()
        if show_hint:self.show_toast("设置已保存")

    def schedule_next_round(self, started_at=None):
        timing=random_inspection_timing(self.settings)
        minutes,deadline,delay_ms=plan_next_round(timing,started_at)
        self._next_round_minutes=minutes;self.next_run_at=deadline
        self.auto_timer.start(delay_ms)
        self.dashboard.next_run.setToolTip("\u672c\u6b21\u968f\u673a\u8f6e\u6b21\u95f4\u9694\uff1a%s \u5206\u949f" % minutes)

    def _apply_timing(self, previous):
        values=random_inspection_timing(self.settings)
        self._settings_timing=values
        self.dashboard.set_timing_values(*values)
        if self.worker is not None:self.worker.set_gap_range(*values[3:])
        if self.auto_enabled and self.worker_thread is None and values[:3]!=previous[:3]:
            self.schedule_next_round()
        self.update_countdown()

    def on_quick_timing_changed(self, minutes, j0, j1, g0, g1):
        previous=self._settings_timing
        values=normalize_random_timing(minutes,j0,j1,g0,g1)
        widgets=(self.settings_page.interval,self.settings_page.jitter_min,self.settings_page.jitter_max,self.settings_page.gap_min,self.settings_page.gap_max)
        for widget,value in zip(widgets,values):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        try:
            self.settings_page.autosave.stop();self.settings_page.save_settings()
        except (ValueError,OSError) as exc:
            self.dashboard.set_timing_values(*previous)
            for widget,value in zip(widgets,previous):
                widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
            QMessageBox.warning(self,"\u8bbe\u7f6e\u672a\u80fd\u4fdd\u5b58",str(exc));return
        self._apply_timing(previous)
        self.settings_page.save_note.setText("\u5df2\u81ea\u52a8\u4fdd\u5b58 \u00b7 \u4e0e\u4e3b\u754c\u9762\u540c\u6b65")
        self.dashboard.status.setText("\u968f\u673a\u95f4\u9694\u5df2\u4fdd\u5b58\uff1a\u57fa\u51c6 %s \u5206\u949f\uff0c\u4e0a\u4e0b\u6d6e\u52a8 %s\u2014%s \u5206\u949f\uff1b\u4e3b\u9875 %s\u2014%s \u79d2" % values)

    def ack_alerts(self):
        self.store.acknowledge_notifications();self.alerts.refresh();self.refresh_dashboard()
        self.show_toast("通知已标记为已读")

    def show_toast(self, text, duration_ms=3600):
        self.dashboard.status.setText(str(text))
        if not self.isVisible() or self.isMinimized():
            return
        if self._toast is None:
            self._toast=ToastNotice(self)
        self._toast.show_message(str(text),duration_ms)


    def _create_resize_handles(self):
        specs={
            "left":(Qt.Edge.LeftEdge,Qt.CursorShape.SizeHorCursor),
            "right":(Qt.Edge.RightEdge,Qt.CursorShape.SizeHorCursor),
            "top":(Qt.Edge.TopEdge,Qt.CursorShape.SizeVerCursor),
            "bottom":(Qt.Edge.BottomEdge,Qt.CursorShape.SizeVerCursor),
            "tl":(Qt.Edge.TopEdge|Qt.Edge.LeftEdge,Qt.CursorShape.SizeFDiagCursor),
            "tr":(Qt.Edge.TopEdge|Qt.Edge.RightEdge,Qt.CursorShape.SizeBDiagCursor),
            "bl":(Qt.Edge.BottomEdge|Qt.Edge.LeftEdge,Qt.CursorShape.SizeBDiagCursor),
            "br":(Qt.Edge.BottomEdge|Qt.Edge.RightEdge,Qt.CursorShape.SizeFDiagCursor),
        }
        self._resize_handles={}
        for key,(edges,cursor) in specs.items():
            handle=WindowResizeHandle(edges,cursor,self);self._resize_handles[key]=handle;handle.raise_()
        self._layout_resize_handles()

    def _layout_resize_handles(self):
        if not hasattr(self,"_resize_handles"):return
        w,h=self.width(),self.height();edge=7;corner=15
        geo={
            "left":QRect(0,corner,edge,max(0,h-2*corner)),
            "right":QRect(max(0,w-edge),corner,edge,max(0,h-2*corner)),
            "top":QRect(corner,0,max(0,w-2*corner),edge),
            "bottom":QRect(corner,max(0,h-edge),max(0,w-2*corner),edge),
            "tl":QRect(0,0,corner,corner),
            "tr":QRect(max(0,w-corner),0,corner,corner),
            "bl":QRect(0,max(0,h-corner),corner,corner),
            "br":QRect(max(0,w-corner),max(0,h-corner),corner,corner),
        }
        visible=not self.isMaximized()
        for key,handle in self._resize_handles.items():
            handle.setGeometry(geo[key]);handle.setVisible(visible);handle.raise_()
        if hasattr(self,"size_grip"):self.size_grip.raise_()

    def show_dashboard(self):
        self.showNormal();self.raise_();self.activateWindow();self.switch_page(0)

    def reset_ui_layout(self):
        for key in ("ui/geometry","ui/maximized","ui/page","dashboard/scroll","manager/header","alerts/header"):
            self.settings.remove(key)
        self.settings.sync();self.showNormal();self.resize(1360,880)
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry();self.move(area.center()-self.rect().center())
        self.switch_page(0);self.show_toast("窗口布局已恢复默认")

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"_ui_save_timer") and not self._ui_restoring:self._ui_save_timer.start(250)
        if hasattr(self,"brand_caption"):self.brand_caption.setVisible(self.width()>=1460)
        if getattr(self,"_toast",None) is not None:
            self._toast.reposition()
        if hasattr(self,"size_grip"):
            self.size_grip.move(self.width()-18,self.height()-18);self.size_grip.setVisible(not self.isMaximized())
        self._layout_resize_handles()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,"max_btn"):
            self.max_btn.setToolTip("还原" if self.isMaximized() else "最大化")
            QTimer.singleShot(0,self._layout_resize_handles)

    def toggle_maximized(self):
        if self.isMaximized():self.showNormal()
        else:self.showMaximized()


    def check_for_updates(self,manual=True):
        if self._closing or self._maintenance:return
        if not manual and not is_true(self.settings.value("auto_check_updates",1)):return
        if self._update_thread is not None:
            if manual:
                if self._update_dialog:self._update_dialog.show();self._update_dialog.raise_()
                else:self.dashboard.status.setText("版本检查正在进行，请稍候")
            return
        self._update_manual=bool(manual)
        self.dashboard.status.setText("正在检查 GitHub 正式发布版本…")
        self._start_update_task("check")

    def move_data_directory(self):
        if self._tasks_busy():return
        if self._update_thread is not None:
            show_hint(self,"请等待版本检查或下载结束后再迁移目录。");return
        old=DATA_DIR.resolve()
        parent=QFileDialog.getExistingDirectory(self,"选择新数据文件夹的上级目录",str(old.parent))
        if not parent:return
        name,ok=QInputDialog.getText(self,"新文件夹名称","在所选位置创建的文件夹：",QLineEdit.EchoMode.Normal,"专业监控工具数据")
        if not ok:return
        name=name.strip()
        if not name or name in (".","..") or any(ch in name for ch in '/\\:*?"<>|'):
            QMessageBox.warning(self,"名称无效","请填写普通文件夹名称。");return
        target=Path(parent)/name
        if QMessageBox.question(self,"确认迁移",
            f"数据、设置、头像及浏览器资料将迁移到：\n{target}\n\n验证并切换成功后删除旧应用数据目录；如有无关文件，则保留原目录。",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.settings_page.flush_pending();self.save_ui_state();self.settings.sync()
        self._maintenance=True;self.auto_timer.stop();self.paint_timer.stop();self._ui_save_timer.stop()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        moved=None
        try:
            result=prepare_data_migration(self.store,target)
            new_settings=QSettings(str(result["target"]/"settings.ini"),QSettings.Format.IniFormat);new_settings.setFallbacksEnabled(False)
            new_settings.setValue("data_directory",str(result["target"]));new_settings.sync()
            if new_settings.status()!=QSettings.Status.NoError:raise RuntimeError("新目录配置不可写")
            # No commit to the new path until both copied DB and INI are usable.
            write_settings_location(result["target"])
            self._set_paths(result["target"]);self.store.path=result["database"];self.connector.relocate(DATA_DIR/"connector_registry.json")
            self.settings=new_settings
            for obj in (self.dashboard,self.dashboard.cards,self.page_manager,self.settings_page):obj.settings=new_settings
            self.settings_page.refresh_data_path();moved=result
        except Exception as exc:
            log_exception(str(exc));QMessageBox.critical(self,"迁移未完成",str(exc)+"\n原数据没有删除。")
        finally:
            QApplication.restoreOverrideCursor();self._maintenance=False
        if moved:
            if moved["can_delete"]:
                try:shutil.rmtree(moved["old"]);note="原应用数据目录已删除。"
                except OSError as exc:note="新目录已启用；原目录删除失败："+str(exc)
            else:note="旧目录存在非应用文件，未删除："+", ".join(moved["unrelated"][:6])
            self.refresh_all();QMessageBox.information(self,"迁移完成",str(moved["target"])+"\n\n"+note)
        if self.auto_enabled:self.next_run_at=time.time()+30;self.auto_timer.start(30000)

    def smart_cleanup_cache(self):
        if self._tasks_busy():
            self.show_toast("正在巡检，请等待本轮结束后再清理缓存");return
        if self._update_thread is not None:
            self.show_toast("版本检查或下载进行中，暂不能清理更新缓存");return
        candidates=[];updates=DATA_DIR/"updates"
        if updates.exists():candidates.append(("更新下载与解压缓存",updates))
        for root in (DATA_DIR,AVATAR_DIR):
            if not root.exists():continue
            for p in root.rglob("*"):
                if p.is_file() and p.name.lower().endswith((".part",".tmp",".connector.tmp")):
                    candidates.append(("残留临时文件",p))
        log=DATA_DIR/"error.log";log_trim=log.is_file() and log.stat().st_size>2*1024*1024
        total=0;seen=set();items=[]
        for label,path in candidates:
            try:
                rp=path.resolve()
                if rp in seen:continue
                seen.add(rp)
                size=sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
                total+=size;items.append((label,path,size))
            except OSError:pass
        if log_trim:
            try:total+=max(0,log.stat().st_size-512*1024)
            except OSError:pass
        if total<=0:
            self.show_toast("缓存状态良好，没有发现需要清理的垃圾文件");return
        labels=[]
        if any(x[0]=="更新下载与解压缓存" for x in items):labels.append("旧更新下载/解压缓存")
        if any(x[0]=="残留临时文件" for x in items):labels.append("中断留下的临时文件")
        if log_trim:labels.append("过大的运行日志（保留最近约 512KB）")
        answer=QMessageBox.question(self,"确认智能清理",
            f"检测到约 {total/1048576:.1f} MB 可安全清理内容：\n"+"、".join(labels)+
            "\n\n不会删除专业 ID、通知、头像、设置、数据库或浏览器连接记录。\n\n现在清理吗？",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        released=0
        for _label,path,size in sorted(items,key=lambda x:len(str(x[1])),reverse=True):
            try:
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink(missing_ok=True)
                released+=size
            except OSError:pass
        if log_trim:
            try:
                data=log.read_bytes();keep=data[-512*1024:];log.write_bytes(keep);released+=len(data)-len(keep)
            except OSError:pass
        ensure_private_directory(DATA_DIR/"updates")
        if hasattr(self.settings_page,"cleanup_status"):
            self.settings_page.cleanup_status.setText(f"上次清理释放约 {released/1048576:.1f} MB；核心数据未改动。")
        self.show_toast(f"智能清理完成 · 释放约 {released/1048576:.1f} MB")

    def open_page(self,pid):
        QDesktopServices.openUrl(QUrl(f"https://www.facebook.com/{pid}"))


    def export_csv(self,kind=None):
        if kind not in ("current","alerts"):
            choice,ok=QInputDialog.getItem(self,"导出数据","内容：",["主页当前状态","通知"],0,False)
            if not ok:return
            kind="current" if choice=="主页当前状态" else "alerts"
        filename="pages.csv" if kind=="current" else "notifications.csv"
        path,_=QFileDialog.getSaveFileName(self,"导出",str(Path.home()/filename),"CSV (*.csv)")
        if not path:return
        try:self.store.export_csv(path,kind);show_hint(self,"已导出："+path)
        except Exception as exc:QMessageBox.warning(self,"导出失败",str(exc))

    def backup_db(self):
        stamp=datetime.now().strftime("%Y%m%d_%H%M")
        path,_=QFileDialog.getSaveFileName(self,"备份数据库",str(Path.home()/f"ProfessionalMonitor_backup_{stamp}.db"),"本地数据库数据库 (*.db)")
        if not path:return
        try:
            self.store.backup(Path(path))
            show_hint(self,f"本地主页、当前状态与预警已备份（不含浏览器登录资料）：\n{path}")
        except Exception as exc:
            QMessageBox.warning(self,"备份失败",str(exc))


    def on_tray_activated(self,reason):
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:self.show_dashboard()

    def on_tray_hint(self):
        if is_true(self.settings.value("silent_to_tray",1),True):return
        self.tray.showMessage(APP_TITLE,"窗口已收起到托盘，继续后台运行。双击托盘图标可打开；完全退出请使用托盘菜单。",QSystemTrayIcon.MessageIcon.Information,4000)

    def exit_application(self):
        self._closing=True;self.auto_enabled=False;self.auto_timer.stop();self.next_run_at=None
        self.close()

    def check_pending_exit(self):
        if self._closing and self.worker_thread is None and self.login_thread is None and self._update_thread is None:
            QTimer.singleShot(0,self.close)

    def closeEvent(self,event):
        try:
            self.settings_page.flush_pending();self.save_ui_state()
        except Exception as exc:
            log_exception("保存设置失败："+str(exc))
            QMessageBox.warning(self,"设置未能保存",str(exc)+"\n请检查数据目录写入权限。")
            event.ignore();self._closing=False;return
        if self._toast is not None:self._toast.hide()
        if not self._closing:
            event.ignore()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show();self.hide();self.on_tray_hint()
            else:
                # Never hide the only recoverable window when the OS has no tray.
                self.showMinimized()
            return
        self._closing=True
        self.auto_enabled=False;self.auto_timer.stop();self.count_timer.stop();self._updates_timer.stop()
        if self.worker_thread is not None or self.login_thread is not None or self._update_thread is not None:
            if self.worker:self.worker.stop()
            if self.login_worker:self.login_worker.stop()
            if self._update_worker:self._update_worker.cancel()
            self.dashboard.status.setText("正在安全结束当前任务…")
            event.ignore();return
        if self._install_command:
            try:
                kwargs={"close_fds":True}
                if os.name=="nt":kwargs["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0)
                subprocess.Popen(self._install_command,**kwargs)
                self._install_command=None
            except OSError as exc:
                self._closing=False;self.count_timer.start();self._updates_timer.start()
                QMessageBox.warning(self,"无法启动安装器",str(exc));event.ignore();return
        self._connector_timer.stop();self.connector.stop()
        self.settings.sync();self.tray.hide();event.accept()
        QTimer.singleShot(0,QApplication.instance().quit)

    def apply_theme(self,theme_name=None,refresh=True):
        global BG,SIDEBAR,PANEL,PANEL_2,BORDER,TEXT,MUTED,ACCENT,GREEN,RED,AMBER,CYAN
        name=str(theme_name or "蓝橙曜石")
        if name not in THEME_PRESETS:name="蓝橙曜石"
        self.theme_name=name;p=THEME_PRESETS[name]
        for key,target in (("bg","BG"),("sidebar","SIDEBAR"),("panel","PANEL"),("panel_2","PANEL_2"),
                ("border","BORDER"),("text","TEXT"),("muted","MUTED"),("accent","ACCENT"),
                ("green","GREEN"),("red","RED"),("amber","AMBER"),("cyan","CYAN")):
            globals()[target]=p[key]
        self.settings.setValue("ui_theme",name);self.settings.sync()
        app=QApplication.instance()
        palette=QPalette()
        for role,color in ((QPalette.ColorRole.Window,BG),(QPalette.ColorRole.Base,p["input"]),
            (QPalette.ColorRole.AlternateBase,PANEL_2),(QPalette.ColorRole.WindowText,TEXT),
            (QPalette.ColorRole.Text,TEXT),(QPalette.ColorRole.Button,PANEL_2),(QPalette.ColorRole.ButtonText,TEXT),
            (QPalette.ColorRole.Highlight,ACCENT),(QPalette.ColorRole.HighlightedText,"#FFFFFF"),
            (QPalette.ColorRole.ToolTipBase,PANEL_2),(QPalette.ColorRole.ToolTipText,TEXT),
            (QPalette.ColorRole.PlaceholderText,MUTED)):
            palette.setColor(role,QColor(color))
        app.setPalette(palette)
        try:
            families=set(QFontDatabase.families())
            family=next((f for f in ("Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC","WenQuanYi Zen Hei","PingFang SC","DejaVu Sans") if f in families),"Sans Serif")
        except Exception:family="Sans Serif"
        font=QFont(family);font.setPixelSize(13);app.setFont(font)
        self.apply_style()
        if hasattr(self,"theme_pill"):self.theme_pill.setText("主题 · "+name)
        if hasattr(self,"dashboard"):
            for card,color in ((self.dashboard.metric_pages,ACCENT),(self.dashboard.metric_total,CYAN),(self.dashboard.metric_yesterday,AMBER),
                (self.dashboard.metric_growth,GREEN),(self.dashboard.metric_post,AMBER),(self.dashboard.metric_alerts,RED)):
                card.icon_label.setPixmap(ui_icon(card.kind,color).pixmap(28,28))
            self._update_header_icons(sum(self.store.unread_totals()) if hasattr(self,"store") else 0)
            if refresh:self.refresh_all()
        for avatar in self.findChildren(AvatarWidget):avatar.update()


    def apply_style(self):
        p=THEME_PRESETS.get(getattr(self,"theme_name","蓝橙曜石"),THEME_PRESETS["蓝橙曜石"])
        field=p["input"];hover=p["hover"];soft=p["soft"];light=bool(p.get("light"))
        status_ok_bg="#E4F4ED" if light else "#103D39"
        status_ok_border="#B8DCCF" if light else "#24584E"
        status_alert_bg="#FBE7EA" if light else "#422438"
        status_alert_border="#E8B6BE" if light else "#613447"
        status_warn_bg="#FBF0DD" if light else "#3B3028"
        status_warn_border="#E5C893" if light else "#665039"
        danger_bg="#F9E5E8" if light else "#3B2333"
        danger_border="#E3B4BC" if light else "#603A4D"
        table_selection="#DCE4F6" if light else "#263D63"
        disabled_text="#A09184" if light else "#667C95"
        self.setStyleSheet(f"""
            QMainWindow, QWidget#Root, QStackedWidget#MainStack, QWidget#DashboardPage,
            QWidget#ManagerPage, QWidget#AlertsPage {{ background:{BG}; color:{TEXT}; }}
            QWidget {{ color:{TEXT}; font-size:13px; }}
            QLabel {{ background:transparent; border:0; }}
            QDialog, QMessageBox {{ background:{BG}; }}
            QFrame#HeaderBar {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {SIDEBAR},stop:1 {BG}); border-bottom:1px solid {BORDER}; }}
            QLabel#BrandName {{ font-size:21px;font-weight:800;color:{TEXT}; }}
            QLabel#BrandSub {{ font-size:11px;color:{MUTED};margin-left:10px; }}
            QFrame#HeaderDivider {{ background:{BORDER}; }}
            QPushButton#TopIconButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:0; }}
            QPushButton#HeaderAction {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:0 10px;font-size:12px;font-weight:650; }}
            QPushButton#HeaderAction:hover {{ background:{hover};border-color:{ACCENT}; }}
            QPushButton#HeaderAction[active='true'] {{ background:{soft};border-color:{ACCENT}; }}
            QPushButton#HomePill {{ background:#4443AD;border:1px solid #8C88FA;border-radius:20px;
                color:#FFFFFF;padding:0 10px;font-size:13px;font-weight:750; }}
            QPushButton#HomePill[active='true'] {{ background:#5A55D6;border-color:#AAA6FF; }}
            QPushButton#HomePill:hover {{ background:#655FE4; }}
            QLabel#QuickTimingLabel {{ color:{MUTED};font-size:11px; }}
            QSpinBox#QuickTimingSpin {{ padding:4px 3px;font-size:12px;font-weight:650; }}
            QPushButton#ThemePill {{ background:{soft};border:1px solid {ACCENT};border-radius:20px;padding:0 12px;font-size:12px;font-weight:750; }}
            QPushButton#ThemePill:hover {{ background:{hover}; }}
            QPushButton#UpdateButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:0; }}
            QPushButton#UpdateButton:hover {{ background:{hover};border-color:{ACCENT}; }}
            QPushButton#UpdateButton[hasUpdate='true'] {{ background:{status_warn_bg};border:1px solid {AMBER}; }}
            QProgressBar {{ border:1px solid {BORDER};border-radius:6px;background:{PANEL_2};height:18px;text-align:center; }}
            QProgressBar::chunk {{ background:{ACCENT};border-radius:5px; }}
            QPushButton#TopIconButton:hover {{ background:{hover};border-color:{BORDER}; }}
            QPushButton#TopIconButton[active='true'] {{ background:{soft};border-color:{ACCENT}; }}
            QPushButton#CloseWindowButton {{ background:transparent;border:0;border-radius:8px;padding:0; }}
            QPushButton#CloseWindowButton:hover {{ background:#913447; }}
            QLabel#NotificationBadge {{ background:{RED};color:#FFFFFF;border-radius:8px;font-size:9px;font-weight:800; }}
            QLabel#PageTitle {{ font-size:24px;font-weight:800;color:{TEXT}; }}
            QLabel#DialogTitle {{ font-size:23px;font-weight:800; }}
            QLabel#SectionTitle {{ font-size:17px;font-weight:750; }}
            QLabel#SettingsTitle, QLabel#PanelTitle {{ font-size:14px;font-weight:750; }}
            QLabel#Subtitle, QLabel#SmallMuted, QLabel#FooterText {{ color:{MUTED};font-size:11px; }}
            QLabel#Eyebrow {{ color:{CYAN};font-size:11px;font-weight:700; }}
            QLabel#RunBadge {{ color:{TEXT};font-size:13px;font-weight:650;padding:7px 8px; }}
            QFrame#TimingBar {{ background:{PANEL};border:1px solid {BORDER};border-radius:10px; }}
            QFrame#MetricCard, QFrame#PageCard, QFrame#SettingsCard, QFrame#EmptyState, QFrame#DetailStat {{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {PANEL_2},stop:0.55 {PANEL},stop:1 {PANEL});
                border:1px solid {BORDER};border-radius:15px;
            }}
            QFrame#MetricCard[tone='pages'] {{ border-top:2px solid {ACCENT}; }}
            QFrame#MetricCard[tone='people'] {{ border-top:2px solid {CYAN}; }}
            QFrame#MetricCard[tone='history'] {{ border-top:2px solid {AMBER}; }}
            QFrame#MetricCard[tone='trend'] {{ border-top:2px solid {GREEN}; }}
            QFrame#MetricCard[tone='clock'] {{ border-top:2px solid {AMBER}; }}
            QFrame#MetricCard[tone='bell'] {{ border-top:2px solid {RED}; }}
            QFrame#PageCard:hover {{ border:1px solid {ACCENT}; }}
            QFrame#MonitorPanel {{ background:{PANEL};border:1px solid {BORDER};border-radius:14px; }}
            QFrame#AlertRow {{ background:transparent;border-left:2px solid {BORDER}; }}
            QLabel#AlertRowTitle {{ color:{AMBER};font-size:12px;font-weight:650; }}
            QLabel#MetricIcon {{ background:{PANEL_2};border-radius:13px; }}
            QLabel#MetricLabel {{ color:{TEXT};font-size:15px;font-weight:800; }}
            QLabel#MetricValue {{ color:{TEXT};font-weight:800; }}
            QLabel#CardTitle {{ font-size:14px;font-weight:750;color:{TEXT}; }}
            QLabel#CardId {{ color:{MUTED};font-size:11px; }}
            QLabel#BigNumber {{ color:{TEXT};font-weight:800; }}
            QLabel#GrowthUp {{ color:{GREEN};font-weight:750; }}
            QLabel#GrowthDown {{ color:{RED};font-weight:750; }}
            QLabel#GrowthSoon {{ color:{AMBER};font-weight:700; }}
            QLabel#GrowthFlat {{ color:{MUTED};font-weight:650; }}
            QLabel#StatusBadge {{ background:{status_ok_bg};color:{GREEN};border:1px solid {status_ok_border};border-radius:7px;
                padding:3px 7px;font-size:11px;font-weight:700; }}
            QLabel#StatusBadge[state='alert'] {{ background:{status_alert_bg};color:{RED};border-color:{status_alert_border}; }}
            QLabel#StatusBadge[state='warning'] {{ background:{status_warn_bg};color:{AMBER};border-color:{status_warn_border}; }}
            QLabel#StatusBadge[state='off'] {{ background:{PANEL_2};color:{MUTED};border-color:{BORDER}; }}
            QLabel#DetailNumber {{ color:{TEXT};font-size:20px;font-weight:800; }}
            QLabel#PathLabel {{ color:{CYAN};font-size:12px; }}
            QLabel#InfoBox {{ background:{PANEL_2};border-radius:10px;padding:12px;color:{MUTED}; }}
            QPushButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:9px;padding:8px 13px;
                color:{TEXT};font-weight:650; }}
            QPushButton:hover {{ background:{hover};border-color:{ACCENT}; }}
            QPushButton:disabled {{ color:{disabled_text};border-color:{BORDER};background:{PANEL}; }}
            QPushButton#PrimaryButton {{ background:{ACCENT};border:1px solid {ACCENT};color:#FFFFFF; }}
            QPushButton#PrimaryButton:hover {{ border-color:#A4A0FF; }}
            QPushButton#AutoButton {{ background:{PANEL_2};border:1px solid {BORDER}; }}
            QPushButton#AutoButton[autoEnabled='true'] {{ background:{soft};border-color:{ACCENT}; }}
            QPushButton#DangerButton {{ background:{danger_bg};color:{RED};border:1px solid {danger_border}; }}
            QPushButton#LinkButton {{ background:transparent;border:0;color:{CYAN};padding:4px 8px;font-size:11px; }}
            QPushButton#NoticeModeButton, QPushButton#NoticeHistoryButton {{ background:{PANEL_2};border:1px solid {BORDER};padding:7px 12px; }}
            QPushButton#NoticeModeButton[active='true'] {{ background:{soft};border-color:{ACCENT};color:{TEXT}; }}
            QPushButton#NoticeHistoryButton {{ color:{MUTED}; }}
            QPushButton#NoticeHistoryButton[active='true'] {{ background:{soft};border-color:{BORDER};color:{TEXT}; }}
            QLabel#NoticeSummary {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:9px 12px;color:{TEXT};font-weight:650; }}
            QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
                background:{field};border:1px solid {BORDER};border-radius:8px;
                padding:7px 9px;color:{TEXT};selection-background-color:{ACCENT};
            }}
            QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color:{ACCENT}; }}
            QComboBox QAbstractItemView {{ background:{PANEL};border:1px solid {BORDER};color:{TEXT};selection-background-color:{soft}; }}
            QCheckBox {{ spacing:8px;color:{TEXT}; }}
            QCheckBox::indicator {{ width:17px;height:17px;border:1px solid {BORDER};border-radius:4px;background:{field}; }}
            QCheckBox::indicator:checked {{ background:{ACCENT};border:2px solid #ABA8FF; }}
            QScrollArea {{ background:transparent;border:0; }}
            QWidget#CardCanvas {{ background:transparent; }}
            QScrollBar:vertical {{ background:transparent;width:9px;margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER};border-radius:4px;min-height:25px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar:horizontal {{ background:transparent;height:9px;margin:0; }}
            QScrollBar::handle:horizontal {{ background:{BORDER};border-radius:4px;min-width:25px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
            QTableWidget {{ background:{PANEL};alternate-background-color:{PANEL_2};border:1px solid {BORDER};
                border-radius:10px;gridline-color:transparent;selection-background-color:{table_selection};selection-color:{TEXT}; }}
            QTableWidget::item {{ border-bottom:1px solid {BORDER};padding:6px; }}
            QHeaderView::section {{ background:{PANEL_2};border:0;border-bottom:1px solid {BORDER};color:{MUTED};padding:10px 6px;font-size:12px;font-weight:700; }}
            QTableWidget#IdManagerTable {{ font-size:12px; }}
            QTabWidget::pane {{ border:1px solid {BORDER};border-radius:10px;background:{BG}; }}
            QTabBar::tab {{ background:{PANEL_2};border:1px solid {BORDER};color:{MUTED};padding:10px 17px;
                border-top-left-radius:8px;border-top-right-radius:8px;margin-right:5px; }}
            QTabBar::tab:selected {{ background:{soft};color:{TEXT};border-bottom-color:{ACCENT}; }}
            QMenu {{ background:{PANEL};border:1px solid {BORDER};padding:5px;color:{TEXT}; }}
            QMenu::item {{ padding:8px 18px;border-radius:5px; }}
            QMenu::item:selected {{ background:{soft}; }}
            QLabel#ConnectorDot {{ border-radius:6px; }}
            QFrame#MonitorAlertPopup {{ background:{PANEL};border:2px solid {AMBER};border-radius:18px; }}
            QLabel#MonitorAlertHeadline {{ font-size:18px;font-weight:850;color:{TEXT}; }}
            QLabel#MonitorAlertSymbol {{ background:{AMBER};color:#16110A;border-radius:17px;font-size:22px;font-weight:900; }}
            QFrame#MonitorAlertRow {{ background:{PANEL_2};border:1px solid {BORDER};border-left:4px solid {AMBER};border-radius:12px; }}
            QLabel#MonitorAlertName {{ font-size:15px;font-weight:850;color:{TEXT}; }}
            QLabel#MonitorAlertEvent {{ background:{soft};border:1px solid {BORDER};border-radius:7px;padding:3px 7px;font-size:11px;font-weight:800;color:{AMBER}; }}
            QLabel#MonitorAlertEvent[kind='growth'] {{ color:{RED};background:{danger_bg};border-color:{RED}; }}
            QLabel#MonitorAlertEvent[kind='post'] {{ color:{AMBER};background:{soft};border-color:{AMBER}; }}
            QLabel#MonitorAlertMessage {{ color:{TEXT};font-size:12px; }}
            QPushButton#AlertCloseButton {{ background:transparent;border:0;font-size:21px;padding:0;color:{MUTED}; }}
            QToolTip {{ background:{PANEL_2};color:{TEXT};border:1px solid {BORDER};padding:6px; }}
            QSizeGrip {{ background:transparent; }}
        """)


    def show_theme_menu(self):
        menu=QMenu(self)
        for name in THEME_PRESETS:
            action=menu.addAction(name);action.setCheckable(True);action.setChecked(name==self.theme_name)
            action.triggered.connect(lambda checked=False,n=name:self.apply_theme(n))
        menu.exec(self.theme_pill.mapToGlobal(QPoint(0,self.theme_pill.height()+3)))

    def restore_ui_state(self):
        self.alerts.filter.blockSignals(True)
        self.alerts.filter.setCurrentIndex(max(0,self.alerts.filter.findData(self.settings.value("alerts/filter","all"))))
        self.alerts.filter.blockSignals(False)
        header=self.settings.value("alerts/header")
        if header:
            try:self.alerts.table.horizontalHeader().restoreState(header)
            except (TypeError,ValueError):pass
        geometry=self.settings.value("ui/geometry")
        if geometry:
            try:self.restoreGeometry(geometry)
            except (TypeError,ValueError):pass
        screen=QApplication.primaryScreen()
        if screen and not any(sc.availableGeometry().intersects(self.frameGeometry()) for sc in QApplication.screens()):
            self.move(screen.availableGeometry().topLeft()+QPoint(25,25))
        if is_true(self.settings.value("ui/maximized",False)):self.showMaximized()
        try:index=int(self.settings.value("ui/page",0))
        except (ValueError,TypeError):index=0
        self.switch_page(index);self._ui_restoring=False
        try:offset=int(self.settings.value("dashboard/scroll",0))
        except (ValueError,TypeError):offset=0
        QTimer.singleShot(0,lambda:self.dashboard.scroll.verticalScrollBar().setValue(offset))

    def save_ui_state(self):
        if self._ui_restoring or not hasattr(self,"stack"):return
        if not self.isMinimized():
            self.settings.setValue("ui/geometry",self.saveGeometry())
            self.settings.setValue("ui/maximized",self.isMaximized())
        self.settings.setValue("ui/page",self.stack.currentIndex())
        self.settings.setValue("dashboard/scroll",self.dashboard.scroll.verticalScrollBar().value())
        self.settings.setValue("alerts/filter",self.alerts.filter.currentData())
        self.settings.setValue("alerts/header",self.alerts.table.horizontalHeader().saveState())
        self.settings.sync()

    def moveEvent(self,event):
        super().moveEvent(event)
        if hasattr(self,"_ui_save_timer") and not self._ui_restoring:self._ui_save_timer.start(250)


    def startup_update_check(self):
        result_path=DATA_DIR/"updates/helper/install-result.json"
        if result_path.is_file():
            try:
                result=json.loads(result_path.read_text("utf-8-sig"))
                if result.get("status")=="failed":
                    QMessageBox.warning(self,"上次更新未安装",str(result.get("message") or "系统安装器或签名验证未通过。原数据保留，可重新检查版本。"))
                else:self.dashboard.status.setText("更新安装已完成 · 当前版本 "+APP_VERSION)
                result_path.unlink(missing_ok=True)
            except (OSError,ValueError):pass
        pending=DATA_DIR/"updates/pending.json"
        if pending.is_file():
            try:
                info=json.loads(pending.read_text("utf-8"))
                if release_version(info.get("version",""))>release_version(APP_VERSION):
                    self.set_update_attention(True,info.get("version",""))
                    self._update_manual=False;self._start_update_task("verify",info);return
                pending.unlink(missing_ok=True)
            except (ValueError,OSError,UpdateError):pass
        self.check_for_updates(False)

    def _start_update_task(self,operation,info=None):
        if self._update_thread is not None:return
        self._update_operation=operation
        thread=QThread(self);worker=UpdateWorker(operation,info,DATA_DIR/"updates")
        self._update_thread=thread;self._update_worker=worker
        worker.moveToThread(thread);thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.done.connect(self._update_done)
        worker.done.connect(worker.deleteLater);worker.done.connect(thread.quit)
        thread.finished.connect(self._update_cleanup);thread.start()

    def _update_progress(self,done,total):
        if self._update_dialog:self._update_dialog.set_progress(done,total)

    def _show_update_dialog(self,info):
        if self._update_dialog:
            self._update_dialog.close();self._update_dialog.deleteLater()
        self._update_info=dict(info)
        dlg=UpdateDialog(info,self);self._update_dialog=dlg
        dlg.download_requested.connect(self._download_update);dlg.install_requested.connect(self._install_update)
        dlg.later_requested.connect(self._postpone_update)
        dlg.cancel_requested.connect(self._cancel_update_download)
        dlg.show();dlg.raise_();dlg.activateWindow()
        return dlg

    def _update_done(self,result):
        status=result.get("status")
        if self._closing:return
        if status=="new":
            self.set_update_attention(True,result.get("version",""))
            self.settings.setValue("update/last_checked",now_iso());self.settings.sync()
            version=result.get("version","")
            snoozed=str(self.settings.value("update/snooze_version",""))==version
            try:until=float(self.settings.value("update/snooze_until",0))
            except (ValueError,TypeError):until=0
            if not self._update_manual and snoozed and time.time()<until:
                self.dashboard.status.setText("发现新版 V"+version+" · 已设置稍后提醒")
            else:self._show_update_dialog(result)
        elif status=="ready":
            self.set_update_attention(True,(result.get("info") or {}).get("version",""))
            info=dict(result["info"]);info["path"]=result["path"]
            save_json_atomic(DATA_DIR/"updates/pending.json",info)
            dlg=self._show_update_dialog(info);dlg.ready(result["path"])
            self.dashboard.status.setText("新版已下载并校验，可选择更新或稍后安装")
        elif status in ("error","cancelled"):
            message=str(result.get("message") or "下载已取消")
            self.dashboard.status.setText(message)
            if self._update_dialog and self._update_operation!="check":
                self._update_dialog.error(message)
            elif self._update_manual:
                if status=="cancelled":self.show_toast("下载已取消")
                else:QMessageBox.warning(self,"版本检查未完成",message)
        elif status=="current":
            self.set_update_attention(False)
            self.settings.setValue("update/last_checked",now_iso());self.settings.sync()
            message="当前已是最新版本（V"+APP_VERSION+"）"
            self.dashboard.status.setText(message)
            if self._update_manual:self.show_toast(message)
        else:
            message=str(result.get("message") or "暂未获取到发布信息")
            self.dashboard.status.setText(message)
            if self._update_manual:self.show_toast(message)

    def _update_cleanup(self):
        if self._update_thread:self._update_thread.deleteLater()
        self._update_thread=None;self._update_worker=None
        if self._closing:self.check_pending_exit()

    def _download_update(self):
        if self._closing:return
        if self._update_thread is not None:
            QTimer.singleShot(150,self._download_update);return
        if not self._update_info or not self._update_info.get("asset"):return
        self._update_dialog.downloading()
        self._start_update_task("download",dict(self._update_info))

    def _cancel_update_download(self):
        if self._update_worker:self._update_worker.cancel()

    def _postpone_update(self):
        if self._update_info:
            self.settings.setValue("update/snooze_version",self._update_info.get("version",""))
            self.settings.setValue("update/snooze_until",time.time()+6*3600);self.settings.sync()

    def _install_update(self):
        if not self._update_info or not self._update_dialog or not self._update_dialog.ready_path:return
        plan=self._update_info.get("asset") or {};path=self._update_dialog.ready_path
        try:
            validate_staged_update(plan,path,DATA_DIR/"updates")
            allowed,reason=signed_install_available(plan)
            if not allowed:
                QMessageBox.information(self,"已下载，待手动安装",reason+"\n\n文件："+path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)));return
            answer=QMessageBox.question(self,"确认退出并更新",
                "将安全结束当前巡检并退出应用，安装校验过的新版本后重启。\n系统可能请求安装权限；数据与设置不会删除。\n\n现在更新？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            self._install_command=prepare_install_helper(plan,path,DATA_DIR/"updates")
            self.exit_application()
        except Exception as exc:QMessageBox.warning(self,"未开始安装",str(exc))


class NoWheelSpinBoxFilter(QObject):
    """Prevent accidental numeric changes while scrolling settings pages."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QSpinBox, QComboBox)):
            event.ignore()
            return True
        return False


def main():
    configure_process_identity()
    app=QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    app.setStyle(QuickToolTipStyle("Fusion"))
    app.setApplicationName(APP_TITLE);app.setOrganizationName("GrowthRadar")
    app.setQuitOnLastWindowClosed(False)
    wheel_filter=NoWheelSpinBoxFilter(app);app.installEventFilter(wheel_filter)
    instance=SingleInstanceGuard()
    try:
        primary=instance.acquire()
    except Exception as exc:
        QMessageBox.warning(None,"\u542f\u52a8\u5931\u8d25",str(exc));return 1
    if not primary:
        if instance.activate_existing():return 0
        QMessageBox.warning(None,"\u8f6f\u4ef6\u5df2\u5728\u8fd0\u884c",
            "\u5df2\u68c0\u6d4b\u5230\u539f\u7a97\u53e3\uff0c\u4f46\u6682\u65f6\u672a\u6536\u5230\u5524\u56de\u54cd\u5e94\u3002\u8bf7\u7a0d\u5019\u6216\u4ece\u6258\u76d8\u6253\u5f00\uff1b\u672c\u6b21\u4e0d\u4f1a\u521b\u5efa\u7b2c\u4e8c\u4e2a\u8fdb\u7a0b\u3002")
        return 0
    def exception_hook(exc_type,exc,tb):
        import traceback
        text="".join(traceback.format_exception(exc_type,exc,tb));log_exception(text)
        if sys.stderr is not None:
            try:sys.stderr.write(text)
            except Exception:pass
        QMessageBox.critical(None,APP_TITLE + "发生错误",
            "详细信息已记录到当前数据目录的 error.log。\n\n"+str(exc)[:600])
    sys.excepthook=exception_hook
    try:window=MainWindow()
    except Exception:
        exception_hook(*sys.exc_info());instance.close();return 1
    window.show()
    activation_timer=QTimer(app);activation_timer.setInterval(100)
    activation_timer.timeout.connect(lambda:window.activate_existing_window() if instance.take_activation() else None)
    activation_timer.start()
    if "--diagnose" in sys.argv:
        def diagnostic():
            info={"version":APP_VERSION,"window":[window.width(),window.height()],
                  "cards":len(window.dashboard.cards.cards),"columns":window.dashboard.cards.columns,
                  "id_count":len(window.store.list_pages()),"background":window.theme_name,
                  "worker_running":window.worker_thread is not None}
            ensure_private_directory(DATA_DIR)
            (DATA_DIR/"ui_diagnostic.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
            window.grab().save(str(DATA_DIR/"ui_diagnostic.png"))
            window._closing=True;window.close()
        QTimer.singleShot(1000,diagnostic)
    try:
        return app.exec()
    finally:
        window.connector.stop()
        instance.close()


if __name__=="__main__":
    raise SystemExit(main())
