#!/usr/bin/env python3
"""
yt2tg - Download YouTube videos → upload to Telegram Forum Topics.

Features:
  - Resume-safe: tracks completed uploads in state.json; safe to kill & restart
  - Partial download resume: yt-dlp --continue picks up where it left off
  - Membership videos: -m flag filters subscriber-only content
  - Channel URLs: auto-enumerates all videos from a channel
  - Forum topics: auto-creates one Telegram topic per YouTube channel
  - Large files: up to 4 GB via Pyrogram (Telegram Premium)
  - Caption: title, channel, date, description, original URL

Usage:  python yt2tg.py -h
Setup:  python yt2tg.py --setup
"""

import sys

# Force UTF-8 output so Unicode characters print correctly on Windows CMD/PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR   = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

CONFIG_PATH   = SCRIPT_DIR / "config.json"
STATE_PATH    = SCRIPT_DIR / "state.json"
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
COOKIES_PATH  = Path(os.getenv("COOKIES_PATH", SCRIPT_DIR / "cookies.txt"))

MAX_CAPTION   = 1024
MAX_FILE_MB   = 4096   # Telegram Premium upper limit
MAX_CONCURRENT = 5     # simultaneous downloads


# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════

def load_json(path, default=None):
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config_from_env(cfg):
    """Overlay .env values onto config dict. .env takes priority."""
    env_map = {
        "TELEGRAM_BOT_TOKEN":     "bot_token",
        "TELEGRAM_API_ID":        "api_id",
        "TELEGRAM_API_HASH":      "api_hash",
        "TELEGRAM_GROUP_CHAT_ID": "group_chat_id",
    }
    for env_key, cfg_key in env_map.items():
        val = os.getenv(env_key)
        if val:
            cfg[cfg_key] = val
    # Cast group_chat_id to int if numeric
    gid = cfg.get("group_chat_id", "")
    if isinstance(gid, str) and gid.lstrip("-").isdigit():
        cfg["group_chat_id"] = int(gid)
    return cfg


def validate_config(cfg):
    missing = [k for k in ("bot_token", "api_id", "api_hash", "group_chat_id") if not cfg.get(k)]
    if missing:
        print(f"[ERROR] Missing config: {', '.join(missing)}")
        print("  Set values in .env file or run: python yt2tg.py --setup")
        sys.exit(1)


def run_setup(config_path):
    print("═══ yt2tg Setup ═══\n")
    cfg = load_json(config_path)

    def ask(label, key, cast=str):
        cur = cfg.get(key, "")
        val = input(f"{label} [{cur}]: ").strip()
        return cast(val) if val else cast(cur) if cur else None

    cfg["bot_token"]     = ask("Bot Token (from @BotFather)", "bot_token") or ""
    cfg["api_id"]        = ask("API ID (my.telegram.org)", "api_id") or ""
    cfg["api_hash"]      = ask("API Hash (my.telegram.org)", "api_hash") or ""
    chat_raw             = ask("Group Chat ID (e.g. -1001234567890)", "group_chat_id") or ""
    cfg["group_chat_id"] = int(chat_raw) if str(chat_raw).lstrip("-").isdigit() else chat_raw
    cfg.setdefault("channel_mappings", {})

    save_json(cfg, config_path)
    print(f"\n✓ Saved to {config_path}")
    print("Make sure the bot is admin in your group with 'Manage Topics' permission.")


# ══════════════════════════════════════════════════════════════════════════════
# State  (tracks which video IDs have been successfully uploaded)
# ══════════════════════════════════════════════════════════════════════════════

class State:
    def __init__(self, path=STATE_PATH):
        self.path = path
        data = load_json(path, {"completed": [], "failed": {}})
        self.completed: set  = set(data.get("completed", []))
        self.failed:    dict = data.get("failed", {})

    def is_done(self, vid_id: str) -> bool:
        return vid_id in self.completed

    def mark_done(self, vid_id: str):
        self.completed.add(vid_id)
        self.failed.pop(vid_id, None)
        self._save()

    def mark_failed(self, vid_id: str, reason: str):
        self.failed[vid_id] = reason
        self._save()

    def _save(self):
        save_json({"completed": sorted(self.completed), "failed": self.failed}, self.path)

    def summary(self):
        return f"{len(self.completed)} completed, {len(self.failed)} failed"


# ══════════════════════════════════════════════════════════════════════════════
# yt-dlp helpers
# ══════════════════════════════════════════════════════════════════════════════

def find_ytdlp():
    # Prefer local binary (already present in repo or downloaded)
    for candidate in [SCRIPT_DIR / "yt-dlp.exe", SCRIPT_DIR / "yt-dlp"]:
        if candidate.exists():
            return str(candidate)
    if shutil.which("yt-dlp"):
        return "yt-dlp"
    print("[ERROR] yt-dlp not found. Put yt-dlp / yt-dlp.exe in this folder or run: pip install yt-dlp")
    sys.exit(1)


def ytdlp_cmd(extra_args, cookies_path=None):
    cmd = [find_ytdlp()]
    cp  = cookies_path or COOKIES_PATH
    if cp and Path(cp).exists():
        cmd += ["--cookies", str(cp)]
    # Use the iOS client — bypasses YouTube's JS/nsig challenge entirely.
    # No Node.js or remote solver scripts needed; works everywhere.
    cmd += ["--extractor-args", "youtube:player_client=ios,web"]
    return cmd + extra_args


def get_metadata(url, cookies_path=None):
    """Return metadata dict for a single video URL."""
    cmd = ytdlp_cmd(["--dump-json", "--no-download", url], cookies_path)
    r   = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip() or f"exit {r.returncode}")
    # yt-dlp may emit multiple JSON lines for playlists; take first
    for line in r.stdout.strip().splitlines():
        if line.strip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("No JSON output from yt-dlp")


def is_channel_url(url: str) -> bool:
    return bool(re.search(
        r"youtube\.com/(@[\w.-]+|channel/[\w-]+|c/[\w.-]+|user/[\w.-]+)(/.*)?$",
        url
    ))


def enumerate_channel(url, cookies_path=None, membership_only=False):
    """Return list of metadata dicts for every video in a channel/playlist."""
    print(f"  Scanning: {url}")
    cmd = ytdlp_cmd(["--flat-playlist", "--dump-json", "--no-download", url], cookies_path)
    r   = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip())

    entries = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    # Populate webpage_url for all flat entries
    for e in entries:
        if not e.get("webpage_url"):
            e["webpage_url"] = e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"

    print(f"  Found {len(entries)} video(s) in channel")

    if not membership_only:
        return entries

    # ── Membership filter ────────────────────────────────────────────────────
    # Strategy A (fast, zero extra calls):
    #   YouTube's channel page already marks members-only videos.
    #   yt-dlp flat-playlist entries include an `availability` field when
    #   the channel page exposes it (requires valid cookies to see your memberships).
    entries_with_avail = [e for e in entries if e.get("availability") is not None]

    if entries_with_avail:
        filtered = [e for e in entries if e.get("availability") == "subscriber_only"]
        print(f"  Membership filter via channel listing: "
              f"{len(filtered)} members-only out of {len(entries)} videos")
        for e in filtered:
            print(f"    ✓ {e.get('title', e['id'])[:80]}")
        return filtered

    # Strategy B (fallback — individual per-video checks):
    #   Flat entries didn't carry availability (rare; happens on some channels).
    #   Check each video individually. iOS client avoids JS challenge issues.
    print(f"  Channel listing has no availability data — checking videos individually...")
    print(f"  Tip: make sure cookies.txt is fresh and includes your membership session.")
    filtered = []
    for i, entry in enumerate(entries, 1):
        vid_url = entry["webpage_url"]
        try:
            meta = get_metadata(vid_url, cookies_path)
            avail = meta.get("availability", "")
            if avail == "subscriber_only":
                filtered.append(meta)
                print(f"  [{i}/{len(entries)}] ✓ Members-only: {meta.get('title', '?')[:70]}")
            else:
                print(f"  [{i}/{len(entries)}] – Public: {meta.get('title', '?')[:70]}")
        except RuntimeError as e:
            s = str(e)
            if "members-only" in s.lower() or "Join this channel" in s:
                print(f"  [{i}/{len(entries)}] ✓ Members-only (access denied — refresh cookies): "
                      f"{entry.get('title', entry['id'])[:60]}")
                entry["availability"] = "subscriber_only"
                filtered.append(entry)
            else:
                # Non-fatal: skip this video, keep going
                print(f"  [{i}/{len(entries)}] Skip ({s[:60]})")
    return filtered


def resolve_urls(urls, cookies_path=None, membership_only=False):
    """Expand input URLs (videos or channels) → list of video metadata dicts."""
    result = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            if is_channel_url(url):
                videos = enumerate_channel(url, cookies_path, membership_only)
                result.extend(videos)
            else:
                try:
                    meta = get_metadata(url, cookies_path)
                    if membership_only and meta.get("availability") != "subscriber_only":
                        print(f"  Skip (not membership): {meta.get('title', url)[:70]}")
                        continue
                    result.append(meta)
                except RuntimeError as e:
                    s = str(e)
                    if "members-only" in s.lower() or "Join this channel" in s:
                        print(f"  Members-only (cookies needed): {url}")
                        result.append({"id": _url_to_id(url), "webpage_url": url,
                                       "title": f"(members-only) {url}", "availability": "subscriber_only"})
                    else:
                        print(f"  Error resolving {url}: {s[:120]}")
        except Exception as e:
            print(f"  Error: {e}")
    return result


def _url_to_id(url):
    m = re.search(r"v=([\w-]+)", url)
    return m.group(1) if m else url


def download_video(url, out_dir, cookies_path=None):
    """
    Download a video to out_dir using yt-dlp.
    --continue resumes partial downloads.
    Returns Path to the final file.
    """
    out_tpl = str(Path(out_dir) / "%(title).200s.%(ext)s")
    cmd = ytdlp_cmd([
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--continue",                        # resume partial downloads ✓
        "-o", out_tpl,
        "--no-mtime",
        "--restrict-filenames",
        url,
    ], cookies_path)

    r = subprocess.run(cmd)   # no capture — let yt-dlp print its own progress bar
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp exited with code {r.returncode}")

    files = [f for f in Path(out_dir).iterdir() if f.is_file() and not f.suffix == ".part"]
    if not files:
        raise RuntimeError("No file found after download")
    return max(files, key=lambda p: p.stat().st_size)


# ══════════════════════════════════════════════════════════════════════════════
# Telegram helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_caption(meta: dict) -> str:
    title    = meta.get("title", "Untitled") or "Untitled"
    channel  = meta.get("channel") or meta.get("uploader") or "Unknown"
    raw_date = meta.get("upload_date", "")
    date_str = ""
    if raw_date:
        try:
            date_str = datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            date_str = raw_date
    desc     = (meta.get("description") or "").strip()
    url      = meta.get("webpage_url") or meta.get("url") or ""

    header   = f"<b>{_esc(title)}</b>\n\n"
    info     = f"📺 {_esc(channel)}"
    if date_str:
        info += f"\n📅 {date_str}"
    info    += "\n"
    footer   = f"\n🔗 {url}" if url else ""

    # How much room is left for description?
    fixed    = len(header) + len(info) + len(footer)
    budget   = MAX_CAPTION - fixed - 2    # 2 for "\n\n" before desc
    caption  = header + info
    if budget > 30 and desc:
        trimmed  = desc[:budget]
        if len(desc) > budget:
            trimmed = trimmed[:budget - 1] + "…"
        caption += f"\n{_esc(trimmed)}"
    caption += footer
    return caption[:MAX_CAPTION]


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _upload_progress(current, total):
    if not total:
        return
    pct    = current * 100 / total
    filled = int(30 * current / total)
    bar    = "█" * filled + "░" * (30 - filled)
    done   = current / (1024 * 1024)
    total_ = total  / (1024 * 1024)
    print(f"\r  Upload: [{bar}] {pct:5.1f}%  {done:.0f}/{total_:.0f} MB", end="", flush=True)


async def get_or_create_topic(client, cfg, chat_id, channel_id, channel_name, config_path):
    mappings = cfg.setdefault("channel_mappings", {})
    key      = channel_id or channel_name

    if key in mappings:
        tid = mappings[key]["topic_id"]
        print(f"  Topic: '{channel_name}' → thread {tid}")
        return tid
    # Name-based fallback
    for v in mappings.values():
        if v.get("name") == channel_name:
            print(f"  Topic: '{channel_name}' → thread {v['topic_id']} (by name)")
            return v["topic_id"]

    print(f"  Creating topic '{channel_name}'...")
    try:
        topic = await client.create_forum_topic(chat_id, channel_name)
        tid   = topic.id
        mappings[key] = {"name": channel_name, "topic_id": tid}
        save_json(cfg, config_path)
        print(f"  Created topic '{channel_name}' (ID {tid})")
        return tid
    except Exception as e:
        print(f"  Warning: Could not create topic ({e}). Sending to general chat.")
        return None


async def upload(client, file_path: Path, chat_id, topic_id, caption: str):
    kw = dict(
        chat_id=chat_id,
        caption=caption,
        parse_mode="html",
        progress=_upload_progress,
    )
    if topic_id:
        kw["message_thread_id"] = topic_id

    if file_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
        await client.send_video(video=str(file_path), **kw)
    else:
        await client.send_document(document=str(file_path), **kw)
    print()  # end progress line


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════

async def run(args, cfg, config_path):
    from pyrogram import Client

    chat_id = cfg["group_chat_id"]
    if isinstance(chat_id, str) and chat_id.lstrip("-").isdigit():
        chat_id = int(chat_id)

    cookies = args.cookies

    # ── Resolve URLs ──────────────────────────────────────────────────────────
    print("\n═══ Resolving URLs ═══")
    videos = resolve_urls(args.urls, cookies, args.membership_only)

    if not videos:
        print("No videos found.")
        return

    # ── Confirmation for full-channel downloads ───────────────────────────────
    if any(is_channel_url(u) for u in args.urls) and not args.membership_only and not args.yes:
        print(f"\n  Found {len(videos)} video(s).")
        try:
            ans = input("  Download all? [y/N/m=membership only]: ").strip().lower()
        except EOFError:
            ans = "y"          # non-interactive (Colab cell) → proceed
        if ans == "m":
            videos = [v for v in videos if v.get("availability") == "subscriber_only"]
            print(f"  Filtered to {len(videos)} membership video(s)")
        elif ans != "y":
            print("  Aborted.")
            return

    # ── Load state & show plan ─────────────────────────────────────────────────
    state   = State(args.state)
    pending = [v for v in videos if not state.is_done(v.get("id", "") or _url_to_id(v.get("webpage_url","")))]
    already = len(videos) - len(pending)

    print(f"\n═══ Plan: {len(pending)} to process, {already} already done (state: {state.summary()}) ═══")
    if args.dry_run:
        for i, v in enumerate(pending, 1):
            print(f"  {i}. [{v.get('availability','public')}] {v.get('title', v.get('webpage_url','?'))[:80]}")
        print("(dry-run — no downloads)")
        return

    if not pending:
        print("Nothing to do.")
        return

    # ── Ensure downloads dir exists ────────────────────────────────────────────
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    # ── Pyrogram client ────────────────────────────────────────────────────────
    client = Client(
        "yt2tg_session",
        api_id=int(cfg["api_id"]),
        api_hash=cfg["api_hash"],
        bot_token=cfg["bot_token"],
        in_memory=True,         # no .session file noise; bot_token auth needs no interactivity
    )
    await client.start()

    done_n = fail_n = skip_n = 0
    counters_lock = asyncio.Lock()
    # Semaphore limits concurrent downloads; uploads stay sequential (Telegram rate limits)
    dl_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    upload_lock  = asyncio.Lock()

    async def process_video(i, meta):
        nonlocal done_n, fail_n, skip_n

        vid_id  = meta.get("id") or _url_to_id(meta.get("webpage_url", ""))
        vid_url = meta.get("webpage_url") or meta.get("url") or ""
        title   = meta.get("title", vid_url)[:80]

        print(f"\n{'═'*60}")
        print(f"[{i}/{len(pending)}] {title}")
        print(f"  ID: {vid_id}  |  URL: {vid_url}")

        # Need full metadata (flat-playlist entries are slim)
        if "channel" not in meta or "description" not in meta:
            print(f"  [{vid_id}] Fetching full metadata...")
            try:
                meta = get_metadata(vid_url, cookies)
                vid_id = meta.get("id", vid_id)
            except RuntimeError as e:
                print(f"  [{vid_id}] Metadata error: {e}")
                state.mark_failed(vid_id, str(e))
                async with counters_lock:
                    fail_n += 1
                return

        # Size pre-check
        est_bytes = meta.get("filesize_approx") or meta.get("filesize") or 0
        if est_bytes and est_bytes > MAX_FILE_MB * 1024 * 1024:
            msg = f"Estimated {est_bytes//1048576}MB > {MAX_FILE_MB}MB limit"
            print(f"  [{vid_id}] Skip: {msg}")
            state.mark_failed(vid_id, msg)
            async with counters_lock:
                skip_n += 1
            return

        # Download — with semaphore to limit concurrency
        vid_dl_dir = DOWNLOADS_DIR / vid_id
        vid_dl_dir.mkdir(exist_ok=True)

        async with dl_semaphore:
            print(f"  [{vid_id}] Downloading...")
            try:
                file_path = await asyncio.to_thread(
                    download_video, vid_url, vid_dl_dir, cookies
                )
            except RuntimeError as e:
                print(f"  [{vid_id}] Download error: {e}")
                state.mark_failed(vid_id, str(e))
                async with counters_lock:
                    fail_n += 1
                return

        size_mb = file_path.stat().st_size / 1048576
        print(f"  [{vid_id}] File: {file_path.name} ({size_mb:.1f} MB)")

        if size_mb > MAX_FILE_MB:
            msg = f"File {size_mb:.0f}MB > {MAX_FILE_MB}MB limit"
            print(f"  [{vid_id}] Skip: {msg}")
            state.mark_failed(vid_id, msg)
            async with counters_lock:
                skip_n += 1
            return

        # Topic + Upload — sequential to avoid Telegram rate limits
        async with upload_lock:
            channel_name = meta.get("channel") or meta.get("uploader") or "Unknown"
            channel_id   = meta.get("channel_id") or meta.get("uploader_id") or channel_name
            topic_id     = await get_or_create_topic(
                client, cfg, chat_id, channel_id, channel_name, config_path
            )
            caption = build_caption(meta)
            try:
                await upload(client, file_path, chat_id, topic_id, caption)
                print(f"  [{vid_id}] Uploaded!")
                state.mark_done(vid_id)
                shutil.rmtree(vid_dl_dir, ignore_errors=True)
                async with counters_lock:
                    done_n += 1
            except Exception as e:
                print(f"  [{vid_id}] Upload error: {e}")
                state.mark_failed(vid_id, str(e))
                async with counters_lock:
                    fail_n += 1

    try:
        tasks = [process_video(i, meta) for i, meta in enumerate(pending, 1)]
        await asyncio.gather(*tasks)
    finally:
        await client.stop()

    print(f"\n{'═'*60}")
    print(f"Done  ✓ {done_n} uploaded  ✗ {fail_n} failed  – {skip_n} skipped")
    print(f"State: {state.summary()}")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        prog="yt2tg",
        description="YouTube → Telegram (Forum Topics). Resume-safe, supports membership videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
EXAMPLES
--------
  First-time setup:
    python yt2tg.py --setup

  Single video:
    python yt2tg.py "https://youtube.com/watch?v=abc123"

  Multiple videos:
    python yt2tg.py URL1 URL2 URL3

  All videos from a channel (asks confirmation):
    python yt2tg.py "https://youtube.com/@NahamSec"

  Membership-only from a channel:
    python yt2tg.py -m "https://youtube.com/@NahamSec"

  Membership-only, skip confirmation (good for Colab/scripts):
    python yt2tg.py -m -y "https://youtube.com/@NahamSec"

  Preview without downloading:
    python yt2tg.py --dry-run -m "https://youtube.com/@NahamSec"

  Custom cookies / config:
    python yt2tg.py --cookies /path/to/cookies.txt URL

NOTES
-----
  - Downloads go to ./downloads/<video_id>/ (persistent across restarts)
  - Completed uploads are tracked in state.json — re-running skips done videos
  - yt-dlp --continue resumes partial downloads automatically
  - Telegram Premium supports up to 4 GB uploads via Pyrogram
  - Bot must be admin in the group with 'Manage Topics' permission

SETUP GUIDE
-----------
  1. Create bot: @BotFather -> /newbot -> copy token
  2. Get API credentials: https://my.telegram.org -> App configuration
  3. Create a Telegram supergroup -> Settings -> enable Topics/Forum mode
  4. Add bot as admin (Manage Topics permission required)
  5. Get group chat ID: add @userinfobot to group, it will show the ID
  6. Run: python yt2tg.py --setup
  7. Place cookies.txt in this folder (export from browser while logged into YouTube)
""",
    )

    p.add_argument("urls", nargs="*", help="YouTube video or channel URLs")
    p.add_argument("-m", "--membership-only", action="store_true",
                   help="Download only membership/subscriber-only videos")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Skip all confirmation prompts (useful in Colab)")
    p.add_argument("--setup",   action="store_true", help="Interactive setup wizard")
    p.add_argument("--dry-run", action="store_true", help="List videos without downloading")
    p.add_argument("--cookies", default=str(COOKIES_PATH),
                   help=f"Path to cookies.txt (default: {COOKIES_PATH.name})")
    p.add_argument("--config",  default=str(CONFIG_PATH),
                   help=f"Path to config.json (default: {CONFIG_PATH.name})")
    p.add_argument("--state",   default=str(STATE_PATH),
                   help=f"Path to state.json (default: {STATE_PATH.name})")

    args = p.parse_args()

    if args.setup:
        run_setup(args.config)
        return

    if not args.urls:
        p.print_help()
        return

    cfg = load_json(args.config)
    cfg = load_config_from_env(cfg)
    validate_config(cfg)

    if not Path(args.cookies).exists():
        print(f"[WARN] Cookies not found: {args.cookies}")
        print("       Private/membership videos will fail. Export cookies.txt from your browser.")

    asyncio.run(run(args, cfg, args.config))


if __name__ == "__main__":
    main()
