"""Offline tests: a local HTTP server stands in for YouTube, so these run without
network access. They exercise the real yt-dlp download + ffmpeg MP3 transcode.
A live YouTube check is in scripts/smoke_test.sh."""

import functools
import os
import shutil
import subprocess
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest
from fastapi.testclient import TestClient

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["API_KEY"] = "test-key"

import app  # noqa: E402  (env must be set first)

app.API_KEY = "test-key"
AUTH = {"X-API-Key": "test-key"}
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def media_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("media")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=5",
         "-shortest", "-metadata", "title=Test Tone", str(root / "test.mp4")],
        check=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.ALLOWED_HOSTS.add("127.0.0.1")  # test-only: let the local server through
    yield f"http://127.0.0.1:{server.server_port}"
    app.ALLOWED_HOSTS.discard("127.0.0.1")
    server.shutdown()


@pytest.fixture
def client():
    return TestClient(app.app)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name,duration",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.split())


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_requires_api_key(client):
    r = client.post("/v1/convert", json={"url": "https://youtu.be/x"})
    assert r.status_code == 401


def test_rejects_non_youtube_host(client):
    r = client.post("/v1/convert", headers=AUTH, json={"url": "https://example.com/v.mp4"})
    assert r.status_code == 400


def test_rejects_bad_bitrate(client):
    r = client.post("/v1/convert", headers=AUTH,
                    json={"url": "https://youtu.be/x", "bitrate": 999})
    assert r.status_code == 422


def test_sync_convert_returns_mp3(client, media_url, tmp_path):
    r = client.post("/v1/convert", headers=AUTH,
                    json={"url": f"{media_url}/test.mp4", "bitrate": 128})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert 'filename="test.mp3"' in r.headers["content-disposition"]
    out = tmp_path / "out.mp3"
    out.write_bytes(r.content)
    info = probe(out)
    assert info["format_name"] == "mp3"
    assert abs(float(info["duration"]) - 5) < 0.5


def test_sync_failure_cleans_up(client, media_url):
    before = set(app.WORK_DIR.iterdir())
    r = client.post("/v1/convert", headers=AUTH, json={"url": f"{media_url}/missing.mp4"})
    assert r.status_code == 422
    assert set(app.WORK_DIR.iterdir()) == before


def test_async_job_lifecycle(client, media_url, tmp_path):
    r = client.post("/v1/jobs", headers=AUTH, json={"url": f"{media_url}/test.mp4"})
    assert r.status_code == 202
    job_id = r.json()["id"]
    for _ in range(60):
        status = client.get(f"/v1/jobs/{job_id}", headers=AUTH).json()
        if status["status"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert status["status"] == "done", status
    f = client.get(status["file_url"], headers=AUTH)
    assert f.status_code == 200 and f.headers["content-type"] == "audio/mpeg"
    out = tmp_path / "job.mp3"
    out.write_bytes(f.content)
    assert probe(out)["format_name"] == "mp3"


def test_unknown_job_is_404(client):
    assert client.get("/v1/jobs/nope", headers=AUTH).status_code == 404
