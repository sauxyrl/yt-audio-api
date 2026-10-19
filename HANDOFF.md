# Handoff — YouTube → MP3 API

**Status:** built and tested offline; **not yet tested against real YouTube.**
The build environment's network blocks YouTube, so the one remaining check is a
live run on your machine (step 3 below, about 5 minutes).

## What was verified, and what wasn't

| Check | Result |
|---|---|
| Auth: missing `X-API-Key` → 401 | ✅ automated test |
| Non-YouTube URL → 400; bitrate outside 64–320 → 422 | ✅ automated test |
| Sync `/v1/convert` returns a real MP3 (ffprobe: mp3, correct duration) | ✅ automated test* |
| Async job: queued → done → file download | ✅ automated test* |
| Failed conversion leaves no temp files behind | ✅ automated test |
| Unknown job id → 404 | ✅ automated test |
| **Download from an actual YouTube URL** | ❌ **not run.** Network blocked. Use `scripts/smoke_test.sh` |
| `callback_url` POST on job completion | ❌ not tested |
| Docker image build | ❌ not run (no Docker in the build environment) |

\* The tests use a 5-second video served from a local web server in place of
YouTube. That exercises the real yt-dlp download path and the real ffmpeg
transcode. Only YouTube's own extractor is untested.

## Verify it on your machine

**1. Prerequisites:** Python 3.10+ and ffmpeg (`brew install ffmpeg` on Mac;
`winget install ffmpeg` on Windows). Or just Docker.

**2. Run the offline tests:**

```bash
git clone https://github.com/sauxyrl/yt-audio-api && cd yt-audio-api
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q          # expect: 8 passed
```

**3. Run the live YouTube test.** This is the step that hasn't been done.

```bash
API_KEY=change-me uvicorn app:app --port 8000      # terminal 1
scripts/smoke_test.sh http://localhost:8000 change-me   # terminal 2 (Mac/Linux/WSL)
```

It converts a Creative Commons video (Big Buck Bunny) both ways and ends in
`PASS`. On Windows without WSL, run the curl commands from `README.md` instead.

**4. Optional:** build the container with
`docker build -t yt-audio-api . && docker run -p 8000:8000 -e API_KEY=change-me yt-audio-api`,
then rerun step 3 against it.

## If the live test fails

| Symptom | Likely cause and fix |
|---|---|
| `Sign in to confirm you're not a bot` | YouTube is blocking the IP (common on cloud servers, rare at home). Run it on a home or office machine, or pass browser cookies to yt-dlp (see the yt-dlp FAQ on `--cookies-from-browser`). |
| `Unable to extract …`, `HTTP Error 403`, `nsig` errors | yt-dlp is out of date. Run `pip install -U yt-dlp` (or rebuild the image). This is the most common failure over time. |
| `ffprobe/ffmpeg not found` | ffmpeg isn't on PATH. |
| 422 `video rejected` | The video is live or longer than `MAX_DURATION_SECONDS` (default 1 hour). |

## Connecting the video editor

**For a bolt.new app,** use the ready-made prompt in `BOLT_PROMPT.md`.

For any other client, pick the pattern that fits it:

- **The editor can call a URL and save the response:** use `POST /v1/convert`.
  The response body *is* the MP3.
- **The editor has short request timeouts:** use `POST /v1/jobs`, then poll
  `GET /v1/jobs/{id}` (or pass a `callback_url`), then `GET /v1/jobs/{id}/file`.
- **The editor only accepts uploads to its own endpoint:** not built yet. The
  change is small: when a job finishes, POST the MP3 to the editor's upload URL in
  `run_job()` in `app.py`, next to where `callback_url` is called.

## Before exposing it beyond your own machine

- Set `API_KEY`. Without it the API is open to anyone who can reach it.
- Put it behind HTTPS (a reverse proxy such as Caddy or nginx).
- Jobs live in memory. A restart drops in-progress jobs, and running more than one
  server process won't share jobs. Move job state to Redis or a database if either
  matters.
- Only convert content you have rights to (your own uploads, Creative Commons,
  public domain).

## Files

```
app.py                  the whole service (FastAPI + yt-dlp + ffmpeg)
tests/test_app.py       offline tests (no network needed)
scripts/smoke_test.sh   live YouTube end-to-end check
Dockerfile              python:3.12-slim + ffmpeg (honors $PORT)
render.yaml             one-click free deploy on Render (see README)
.github/workflows/ci.yml  runs pytest on every push
README.md               API usage
BOLT_PROMPT.md          copy-paste prompt for integrating from bolt.new
```
