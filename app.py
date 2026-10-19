"""YouTube -> MP3 HTTP API (a thin wrapper around yt-dlp + ffmpeg).

Endpoints
  GET  /health                      liveness check
  POST /v1/convert                  sync: returns the MP3 bytes directly (audio/mpeg)
  POST /v1/jobs                     async: queue a conversion, returns {"id": ...}
  GET  /v1/jobs/{id}                job status + metadata
  GET  /v1/jobs/{id}/file           download the finished MP3

Request body for both POST routes:
  {"url": "https://www.youtube.com/watch?v=...", "bitrate": 192, "callback_url": null}

Auth: send `X-API-Key: <key>` when the API_KEY env var is set.
Only convert media you own or have the right to use (your own uploads, Creative
Commons, public domain). Downloading other content may breach YouTube's Terms.
"""

import os
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yt_dlp
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

API_KEY = os.environ.get("API_KEY")
MAX_DURATION = int(os.environ.get("MAX_DURATION_SECONDS", 3600))
JOB_TTL = int(os.environ.get("JOB_TTL_SECONDS", 3600))
WORKERS = int(os.environ.get("WORKERS", 2))
WORK_DIR = Path(os.environ.get("WORK_DIR", tempfile.gettempdir())) / "yt-audio-api"
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
                 "music.youtube.com", "youtu.be"}

WORK_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="YouTube to MP3 API", version="1.0.0")
pool = ThreadPoolExecutor(max_workers=WORKERS)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


class ConvertRequest(BaseModel):
    url: str
    bitrate: int = Field(192, ge=64, le=320)
    callback_url: str | None = None  # async only: POSTed the job JSON when done


def require_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "invalid or missing X-API-Key")


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(400, "url must be a youtube.com or youtu.be link")
    return url


def convert(url: str, bitrate: int, out_dir: Path) -> dict:
    """Download best audio, transcode to MP3, return metadata incl. file path."""
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "match_filter": yt_dlp.utils.match_filter_func(f"!is_live & duration <=? {MAX_DURATION}"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
             "preferredquality": str(bitrate)},
            {"key": "FFmpegMetadata"},
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    mp3 = out_dir / f"{info['id']}.mp3"
    if not mp3.exists():
        raise RuntimeError(f"video rejected (live, or longer than {MAX_DURATION}s) or conversion failed")
    return {"video_id": info["id"], "title": info.get("title"),
            "duration": info.get("duration"), "path": str(mp3)}


def safe_filename(title: str | None, fallback: str) -> str:
    keep = "".join(c for c in (title or "") if c.isalnum() or c in " -_()").strip()
    return f"{keep or fallback}.mp3"


@app.get("/health")
def health():
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


@app.post("/v1/convert", dependencies=[Depends(require_key)])
def convert_sync(req: ConvertRequest, background: BackgroundTasks):
    validate_url(req.url)
    out_dir = Path(tempfile.mkdtemp(dir=WORK_DIR))
    try:
        meta = convert(req.url, req.bitrate, out_dir)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise HTTPException(422, str(e))
    background.add_task(shutil.rmtree, out_dir, True)  # after the response is sent
    return FileResponse(meta["path"], media_type="audio/mpeg",
                        filename=safe_filename(meta["title"], meta["video_id"]))


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("path", "dir", "callback_url")}


def run_job(job_id: str):
    job = jobs[job_id]
    job["status"] = "running"
    try:
        job.update(convert(job["url"], job["bitrate"], Path(job["dir"])))
        job["status"] = "done"
        job["file_url"] = f"/v1/jobs/{job_id}/file"
    except Exception as e:
        job["status"], job["error"] = "error", str(e)
    job["finished_at"] = time.time()
    if job.get("callback_url"):
        try:
            httpx.post(job["callback_url"], json=public(job), timeout=10)
        except httpx.HTTPError:
            pass


def reap_expired():
    cutoff = time.time() - JOB_TTL
    with jobs_lock:
        for job_id in [j for j, v in jobs.items() if v.get("finished_at", 1e18) < cutoff]:
            shutil.rmtree(jobs.pop(job_id)["dir"], ignore_errors=True)


@app.post("/v1/jobs", status_code=202, dependencies=[Depends(require_key)])
def create_job(req: ConvertRequest):
    validate_url(req.url)
    reap_expired()
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "status": "queued", "url": req.url, "bitrate": req.bitrate,
           "callback_url": req.callback_url, "created_at": time.time(),
           "dir": tempfile.mkdtemp(dir=WORK_DIR)}
    with jobs_lock:
        jobs[job_id] = job
    pool.submit(run_job, job_id)
    return public(job)


def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found or expired")
    return job


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_key)])
def job_status(job_id: str):
    return public(get_job(job_id))


@app.get("/v1/jobs/{job_id}/file", dependencies=[Depends(require_key)])
def job_file(job_id: str):
    job = get_job(job_id)
    if job["status"] != "done":
        raise HTTPException(409, f"job is {job['status']}")
    return FileResponse(job["path"], media_type="audio/mpeg",
                        filename=safe_filename(job.get("title"), job["video_id"]))
