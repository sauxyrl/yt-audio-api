# YouTube → MP3 API

A small HTTP service that takes a YouTube URL and returns an MP3. It wraps
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (download) and ffmpeg (transcode).

> Only convert media you have rights to: your own uploads, Creative Commons, or
> public domain. Downloading other content may violate YouTube's Terms of Service
> and copyright law.

## Run

```bash
docker build -t yt-audio-api .
docker run -p 8000:8000 -e API_KEY=change-me yt-audio-api
```

Or run it without Docker. ffmpeg must be on PATH:

```bash
pip install -r requirements.txt
API_KEY=change-me uvicorn app:app --host 0.0.0.0 --port 8000
```

Interactive docs (OpenAPI) are at `http://localhost:8000/docs`.

| Env var | Default | Meaning |
|---|---|---|
| `API_KEY` | unset (no auth) | Required `X-API-Key` header value |
| `MAX_DURATION_SECONDS` | 3600 | Reject longer videos and live streams |
| `JOB_TTL_SECONDS` | 3600 | How long finished async files are kept |
| `WORKERS` | 2 | Concurrent async conversions |
| `WORK_DIR` | system temp | Scratch space for downloads |
| `CORS_ORIGINS` | `*` | Comma-separated browser origins allowed to call the API, e.g. `https://myapp.netlify.app` |

## Plugging it into an editor

**Simplest, synchronous.** One request returns the MP3 bytes. Use this when the
editor can wait for a request to finish, which takes about as long as the video's
audio download.

```bash
curl -X POST http://localhost:8000/v1/convert \
  -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "bitrate": 192}' \
  -o audio.mp3
```

**Asynchronous, for long videos or editor plugins with short timeouts.**

```bash
# 1. queue the job → 202 {"id": "...", "status": "queued"}
curl -X POST http://localhost:8000/v1/jobs -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/VIDEO_ID", "callback_url": "https://editor.example/hooks/mp3"}'

# 2. poll (or wait for the callback POST, which carries the same JSON)
curl http://localhost:8000/v1/jobs/<id> -H "X-API-Key: change-me"
#    → {"status": "done", "title": "...", "duration": 212, "file_url": "/v1/jobs/<id>/file"}

# 3. fetch the MP3 and hand it to the editor's upload step
curl http://localhost:8000/v1/jobs/<id>/file -H "X-API-Key: change-me" -o audio.mp3
```

Status values: `queued` → `running` → `done` | `error` (with an `error` message).

## Notes

- YouTube changes often. When downloads start failing, update yt-dlp
  (`pip install -U yt-dlp` or rebuild the image) before you debug anything else.
- Job state is held in memory, so a restart forgets queued jobs. That is fine for
  a single editor workstation. For a shared deployment, move jobs to Redis or a
  database.
- Only `youtube.com`, `youtu.be`, and `music.youtube.com` URLs are accepted
  (`ALLOWED_HOSTS` in `app.py`). This stops the server from being used to fetch
  arbitrary URLs.
- Playlists are ignored; a playlist link converts just the one video it points to.
