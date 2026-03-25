# yt2tg

Download YouTube membership-only videos and upload them to Telegram.

Give it a YouTube channel URL, it fetches all members-only videos, downloads up to 5 simultaneously, and uploads each to your Telegram group (with forum topics per channel).

## What it does

1. Takes a YouTube channel URL (you must have an active membership)
2. Scans the channel and filters members-only videos
3. Downloads videos concurrently (5 at a time) using yt-dlp
4. Uploads each video to Telegram via Pyrogram (supports up to 4 GB with Telegram Premium)
5. Tracks progress in `state.json` — safe to stop and resume anytime

## Prerequisites

- **Python 3.10+**
- **YouTube membership** for the target channel
- **Telegram Premium** (for uploading large files up to 4 GB)
- **Telegram Bot** with admin access to your group
- **cookies.txt** exported from your browser (while logged into YouTube)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/sudo-change/yt-tg.git
cd yt-tg
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Get Telegram credentials

| What | Where to get it |
|------|-----------------|
| Bot Token | [@BotFather](https://t.me/BotFather) on Telegram -> `/newbot` |
| API ID & Hash | [my.telegram.org](https://my.telegram.org) -> API development tools |
| Group Chat ID | Add [@userinfobot](https://t.me/userinfobot) to your group, it replies with the ID |

Your Telegram group must have **Topics/Forum mode enabled** (Settings -> Topics), and the bot must be **admin with "Manage Topics" permission**.

### 3. Configure secrets

Copy the example and fill in your values:

```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890
TELEGRAM_GROUP_CHAT_ID=-1001234567890
COOKIES_PATH=cookies.txt
```

### 4. Export YouTube cookies

1. Install the **"Get cookies.txt LOCALLY"** browser extension ([Chrome](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) / [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/))
2. Go to [youtube.com](https://youtube.com) while logged in with your membership
3. Click the extension -> export cookies
4. Save as `cookies.txt` in the project folder

> Cookies expire periodically. If downloads start failing with "Join this channel" errors, export fresh cookies.

## Usage

```bash
# Preview members-only videos (no download)
python yt2tg.py --dry-run -m "https://youtube.com/@ChannelName"

# Download and upload all members-only videos
python yt2tg.py -m -y "https://youtube.com/@ChannelName"

# Single video
python yt2tg.py "https://youtube.com/watch?v=abc123"

# Multiple videos
python yt2tg.py "URL1" "URL2" "URL3"

# All videos from a channel (not just members-only)
python yt2tg.py -y "https://youtube.com/@ChannelName"
```

### CLI flags

| Flag | Description |
|------|-------------|
| `-m`, `--membership-only` | Only download members-only videos |
| `-y`, `--yes` | Skip confirmation prompts |
| `--dry-run` | List videos without downloading |
| `--setup` | Interactive config wizard (alternative to `.env`) |
| `--cookies PATH` | Custom cookies.txt path |
| `--config PATH` | Custom config.json path |
| `--state PATH` | Custom state.json path |

## Resume & Recovery

- **state.json** tracks completed uploads. Re-running the same command skips already-uploaded videos.
- **Partial downloads** resume automatically (yt-dlp `--continue`).
- If Colab disconnects or your machine reboots, just run the command again.

## Google Colab

Use `colab.ipynb` for running in Google Colab. It clones this repo, installs deps, and runs the tool — follow the cells in order.

## File structure

```
.env                # Your secrets (gitignored)
.env.example        # Template for .env
cookies.txt         # YouTube cookies (gitignored)
requirements.txt    # Python dependencies
yt2tg.py            # Main script
colab.ipynb         # Google Colab notebook
state.json          # Upload progress tracker (auto-generated, gitignored)
config.json         # Alternative config via --setup (gitignored)
downloads/          # Temp download folder (auto-created, gitignored)
```
