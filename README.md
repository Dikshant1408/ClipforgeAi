# ClipForge AI

ClipForge AI is an automated tool to create YouTube Shorts from channel uploads or livestreams. It monitors YouTube RSS feeds, downloads new videos/streams using `yt-dlp`, transcribes the audio using `faster-whisper`, automatically detects the best engaging highlight moments, crops to vertical 9:16 format with burned subtitles using `FFmpeg`, generates viral title, description, and hashtags using Gemini LLM, and schedules daily uploads at 6:00 PM (18:00) using the YouTube Data API.

All pipeline processes coordinate through a local SQLite database for crash-safety, state tracking, and duplicate prevention.

---

## Prerequisites

Before running the tool, make sure your Windows PC has:
1. **Python 3.10 or 3.12+** installed.
2. **FFmpeg** installed and added to your system's `PATH`.

---

## Installation & Setup

1. **Clone the repository** and open the directory:
   ```bash
   cd "d:\Projects\Startup Ideas\ClipForge AI"
   ```

2. **Create a virtual environment** and install dependencies:
   ```bash
   py -3.10 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

4. **OAuth Credentials for YouTube**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/).
   - Create a project and enable the **YouTube Data API v3**.
   - Set up the OAuth consent screen and add yourself as a test user.
   - Create **OAuth client ID credentials** for a desktop application.
   - Download the JSON credentials file and save it as `client_secret.json` in the project root.

5. **Customize Configuration**:
   Copy `config.example.json` to `config.json` and configure your channels, publish time, and timezone:
   ```json
   {
     "source_channels": [
       {
         "name": "Tarik",
         "channel_id": "UC1",
         "enabled": true,
         "priority": 100
       }
     ],
     "publish_time": "18:00",
     "timezone": "Asia/Kolkata",
     "monitor_interval_minutes": 10,
     "clip": {
       "min_seconds": 20,
       "max_seconds": 60,
       "crop": "center"
     },
      "whisper": {
        "model": "small",
        "device": "cpu",
        "language": "ko"
      },
     "llm": {
       "provider": "gemini",
       "model": "gemini-2.0-flash"
     },
     "youtube": {
       "privacy_status": "public",
       "category_id": "20"
     },
     "storage": {
       "root": "./storage"
     },
      "max_disk_gb": 50
    }
    ```

    > **Language Hint:** Set `"language"` inside the `"whisper"` block to a [ISO 639-1 code](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) (e.g. `"ko"` for Korean, `"ja"` for Japanese, `"en"` for English). Without it, smaller Whisper models (`small`, `medium`) may auto-translate non-English speech into English text. For non-English channels, also upgrade the model to at least `"medium"`.

---

## Running the Tool

- **Run in Always-On Automation Mode**:
  Runs the poller, worker, and daily scheduler:
  ```bash
  .venv\Scripts\python.exe -m clipforge.main
  ```

- **Run in Dry-Run Scheduler Mode**:
  Run the scheduler but do not upload videos to YouTube (writes metadata JSON to `storage/dryrun/`):
  ```bash
  .venv\Scripts\python.exe -m clipforge.main --dry-run
  ```

- **One-Off Test Video (Dry-Run)**:
  Processes a single video URL, runs highlight clipping, subtitles, LLM title generation, saves the final `.mp4` and `.json` metadata, and exits without uploading:
  ```bash
  .venv\Scripts\python.exe -m clipforge.main --once "https://www.youtube.com/watch?v=VIDEO_ID"
  ```

---

## Copyright & Safety Risk Warning

> [!WARNING]
> **Copyright Infringement Risk:** Automatically downloading and re-uploading other creators' content carries a high risk of copyright claims, channel strikes, or permanent channel termination. Use this pipeline primarily for processing your own livestreams, content you have explicit reuse permissions for, or content licensed for reuse (e.g., Creative Commons).
