# yt-tg — YouTube → Telegram Uploader

Download YouTube videos (including **membership-only**) and upload them to a **Telegram supergroup with Forum Topics** — one topic per YouTube channel, auto-created.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sudo-change/yt-tg/blob/main/colab.ipynb)

---

## Features

- **Membership videos** — downloads subscriber-only content using your cookies
- **Channel scan** — give a channel URL, it finds all (or only membership) videos
- **Auto topics** — creates a Telegram Forum topic per YouTube channel automatically
- **Resume-safe** — tracks uploads in `state.json`; re-running skips completed videos
- **Partial download resume** — `yt-dlp --continue` picks up interrupted downloads
- **Large files** — up to 4 GB via Pyrogram (requires Telegram Premium)
- **Rich captions** — title, channel name, upload date, description, original URL

---

## Quick Start (Google Colab — recommended)

Click the badge above or go to:
**[colab.research.google.com/github/sudo-change/yt-tg/blob/main/colab.ipynb](https://colab.research.google.com/github/sudo-change/yt-tg/blob/main/colab.ipynb)**

Then follow the cells in order (first time only):

| Cell | What it does |
|------|-------------|
| **Cell 1** | Clones this repo + installs `pyrogram`, `tgcrypto`, `yt-dlp` |
| **Cell 2** | Write your Telegram credentials to `config.json` |
| **Cell 3** | Upload your `cookies.txt` from your browser |
| **Cell 4** | Preview videos (dry-run, no download) |
| **Cell 5** | **Main cell** — download & upload |
| **Cell 6** | Check progress (how many uploaded / failed) |
| **Cell 7** | Force re-upload specific videos |

> **Resuming after Colab disconnects:** Re-run Cell 1 → Cell 2 → Cell 5.
> Already-uploaded videos are skipped. Partial downloads resume automatically.

---

## Local Setup (Windows / Linux)

```bash
git clone https://github.com/sudo-change/yt-tg.git
cd yt-tg
```

**Windows:**
```bat
setup.bat
```

**Linux / Mac:**
```bash
bash setup.sh
```

This creates a virtual environment and installs all dependencies.

---

## One-time Telegram Setup

You need to do this once before first use.

### 1. Create a Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow prompts → copy the **bot token**

### 2. Get API Credentials

1. Go to **https://my.telegram.org**
2. Log in with your phone number
3. Click **API development tools**
4. Create an app → copy **App api_id** and **App api_hash**

### 3. Create a Telegram Supergroup with Topics

1. Create a new Telegram group
2. Go to **Group Settings → Edit → Topics** → enable it
3. Add your bot as **admin** → give it the **Manage Topics** permission
4. To get the group chat ID: add **@userinfobot** to the group → it replies with the ID (a negative number like `-1001234567890`)

### 4. Get Your YouTube Cookies

1. Install the **"Get cookies.txt LOCALLY"** extension ([Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) / [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/))
2. Log into **YouTube** in your browser
3. Click the extension → **Export** for `youtube.com`
4. Save the file as `cookies.txt`

> Re-export cookies whenever you see "cookies expired" errors.

### 5. Configure the Tool

```bash
python yt2tg.py --setup
```

Enter your bot token, API ID, API hash, and group chat ID when prompted.

---

## Usage

```
python yt2tg.py [URLs...] [-m] [-y] [--dry-run] [--setup] [-h]
```

| Flag | Description |
|------|-------------|
| `-m` | Download only membership/subscriber-only videos |
| `-y` | Skip all confirmation prompts (use in Colab / scripts) |
| `--dry-run` | List videos that would be processed, without downloading |
| `--setup` | Run interactive setup wizard |
| `--cookies PATH` | Use a custom cookies.txt path |
| `-h` | Show full help with examples |

### Examples

```bash
# Single video
python yt2tg.py "https://youtube.com/watch?v=abc123"

# Multiple videos at once
python yt2tg.py URL1 URL2 URL3

# All videos from a channel (asks confirmation)
python yt2tg.py "https://youtube.com/@NahamSec"

# Membership-only videos from a channel
python yt2tg.py -m "https://youtube.com/@NahamSec"

# Membership-only, no confirmation prompt (for scripts/Colab)
python yt2tg.py -m -y "https://youtube.com/@NahamSec"

# Preview without downloading
python yt2tg.py --dry-run -m "https://youtube.com/@NahamSec"
```

---

## Files

```
yt-tg/
├── yt2tg.py          # Main CLI tool
├── colab.ipynb       # Google Colab notebook
├── requirements.txt  # Python dependencies
├── setup.sh          # Linux/Colab setup script
├── setup.bat         # Windows setup script
└── .gitignore        # Excludes secrets and downloads
```

Files created at runtime (gitignored, never pushed):

```
config.json           # Your Telegram credentials + channel→topic mappings
cookies.txt           # Your YouTube session cookies
state.json            # Upload progress tracker
downloads/            # Per-video download folders (cleaned after upload)
```

---

## How Resume Works

Every time a video is successfully uploaded to Telegram, its YouTube video ID is saved to `state.json`:

```json
{
  "completed": ["abc123", "xyz789"],
  "failed": {}
}
```

On the next run, completed IDs are skipped immediately. If a download was in progress when Colab stopped, `yt-dlp --continue` resumes the partial file from where it left off.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `cookies expired` error | Re-export `cookies.txt` from your browser and re-upload (Cell 3) |
| `Join this channel` error | Your YouTube account needs membership for that channel |
| `Manage Topics` permission error | Make the bot an admin and enable the Manage Topics permission |
| File > 4 GB skipped | Telegram's limit even with Premium — video is too long |
| `tgcrypto` install fails on Windows | Optional — ignore it. Uploads still work, just slightly slower |
| Topic not created | Bot must be admin in the group before running |

---

## Requirements

- Python 3.8+
- `pyrogram` — Telegram MTProto client (supports large file uploads)
- `tgcrypto` — optional crypto speedup for Pyrogram
- `yt-dlp` — YouTube downloader

Install: `pip install pyrogram tgcrypto yt-dlp`

Telegram Premium is required for files over 2 GB (up to 4 GB).
