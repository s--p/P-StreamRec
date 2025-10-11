# P-StreamRec

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-red.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![Open Source](https://img.shields.io/badge/Open%20Source-Yes-green.svg)](https://github.com/raccommode/P-StreamRec)

**Automatic recording of Chaturbate and m3u8 streams with a modern web interface**

![P-StreamRec Interface](screen.png)

## ✨ Features

- 🎥 **24/7 automatic recording** - Monitors and records when users go live
- 🎬 **Auto MP4 conversion** - Automatically converts recordings to compressed MP4 after stream ends
- 🌐 **Web interface** - Manage recordings and watch replays in browser
- 📦 **Docker ready** - One command to get started
- 🔄 **GitOps updates** - Update directly from the interface
- 🎯 **Chaturbate + m3u8 support** - Works with any HLS stream
- 💾 **Smart storage** - Unique ID per recording, automatic compression
- 📊 **Size display** - Shows file sizes in MB or GB (>1000 MB)

## ⚙️ Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTPUT_DIR` | `/data` | Recordings folder (Docker volume) |
| `PORT` | `8080` | Web interface port |
| `FFMPEG_PATH` | `ffmpeg` | Path to ffmpeg |
| `HLS_TIME` | `4` | HLS segment duration (seconds) |
| `HLS_LIST_SIZE` | `6` | Number of segments in playlist |
| `CB_RESOLVER_ENABLED` | `true` | **Enable Chaturbate support** |
| `CB_COOKIE` | - | Chaturbate session cookie (optional) |
| `AUTO_RECORD_USERS` | - | Comma-separated list of users to auto-record |
| `TZ` | `UTC` | Timezone (e.g., `America/New_York`) |

## 🚀 Quick Start

### Docker Run
```bash
docker run -d \
  --name p-streamrec \
  -p 8080:8080 \
  -v ./data:/data \
  -e CB_RESOLVER_ENABLED=true \
  ghcr.io/raccommode/p-streamrec:latest
```

### Docker Compose
```yaml
version: "3.8"
services:
  p-streamrec:
    image: ghcr.io/raccommode/p-streamrec:latest
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - CB_RESOLVER_ENABLED=true
    restart: unless-stopped
```

**Access:** `http://localhost:8080`

## 📖 Usage

1. **Add a model**: Click **+** → Enter Chaturbate username or m3u8 URL
2. **Auto-record**: System checks every 2 minutes and records when live
3. **Auto-convert**: When stream ends, system converts TS to MP4 (50-70% smaller)
4. **Watch replays**: Click model card → **Replays** tab (TS or MP4 available)
5. **Update**: Click **GitOps** button in header to update app (Git deployment only)

**Recording Format:**
- Original: `/data/records/<username>/YYYYMMDD_HHMMSS_ID.ts` (MPEG-TS)
- Converted: `/data/records/<username>/YYYYMMDD_HHMMSS_ID.mp4` (H.264, auto-generated)
- Each recording has unique ID: `username_YYYYMMDD_HHMMSS_sessionID`

## 💻 Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 📂 File Management

**Automatic Conversion:**
- System automatically converts TS → MP4 when stream ends
- MP4 files are 50-70% smaller (H.264 codec, CRF 23)
- Conversion runs in background, no user action needed
- Both TS and MP4 available in Replays tab

**Play recordings:**
- **Browser**: Use Replays tab (supports TS and MP4)
- **VLC/MPV**: Open files directly from `/data/records/<username>/`
- **MP4**: Better for streaming, smaller file size
- **TS**: Original quality, no re-encoding

**Manual conversion (if needed):**
```bash
ffmpeg -i input.ts -c:v libx264 -crf 23 -c:a aac output.mp4
```

## ⚠️ Notes

- **Storage**: TS ~2-4 GB/hour, MP4 ~600 MB-1.2 GB/hour (after conversion)
- **Sizes displayed**: MB for files < 1000 MB, GB for larger files
- **Unique IDs**: Each recording has timestamp + session ID for easy identification
- Use only for public, legally accessible content

## 📜 License

**Non-Commercial Open Source License** - See [LICENSE](LICENSE)

✅ Free to use, modify, and distribute  
❌ **No commercial use or revenue generation**  
🔄 Share modifications under same license  
📝 Attribution required
