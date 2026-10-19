# Prompt for bolt.new (demo setup)

This prompt has the Bolt app call the API **directly from the browser**, with the
API key in frontend config. That's fine for a demo. Anyone who opens the app can
see the key and use your server, so shut the server down or change `API_KEY`
when the demo is over.

Do this first: deploy the API, because Bolt cannot host it. Use the **Deploy to
Render** button in `README.md`. It's free and you sign in with GitHub. You'll come
away with the two values the prompt needs: the service URL and the generated
`API_KEY`. CORS is open to all origins by default, so the Bolt app can call it
with no extra setup. Then paste everything inside the block below into Bolt.

```text
Add an "Import audio from YouTube" feature to this app. The audio should end up in the app's existing audio upload flow, as if the user had picked an MP3 file themselves.

Do NOT download or convert YouTube in this app. A separate conversion API is already deployed. Call it directly from the frontend with fetch(). It allows cross-origin requests. Its docs are at https://github.com/sauxyrl/yt-audio-api.

## Config
Put these in .env and read them with import.meta.env. This is a demo, so frontend env vars are fine:
VITE_YT_AUDIO_API_URL=https://REPLACE-WITH-API-URL     (no trailing slash)
VITE_YT_AUDIO_API_KEY=REPLACE-WITH-API-KEY

## The API
Every request needs the header `X-API-Key: <VITE_YT_AUDIO_API_KEY>`.

- POST {base}/v1/jobs
  JSON body: {"url": "<youtube url>", "bitrate": 192}
  → 202 {"id": "<job id>", "status": "queued", ...}
- GET {base}/v1/jobs/{id}
  → {"id", "status": "queued" | "running" | "done" | "error", "title", "duration", "file_url", "error"}
  `error` is a message when status is "error" (e.g. the video is live or longer than 1 hour).
- GET {base}/v1/jobs/{id}/file
  → the MP3 bytes, Content-Type audio/mpeg. Available for 1 hour after the job finishes.
- HTTP errors: 400 = not a YouTube link, 401 = bad API key, 404 = job not found or expired, 409 = file requested before the job is done. Error bodies look like {"detail": "<message>"}.

## What to build
1. A text input for a YouTube URL and an "Import" button. Check that it's a youtube.com or youtu.be link before sending.
2. On Import: POST /v1/jobs (the server may be asleep, so allow up to 90 seconds for this first request and show "Waking up the converter…"), then poll GET /v1/jobs/{id} every 3 seconds while the status is "queued" or "running". Give up after 10 minutes with a timeout message.
3. When the status is "done": fetch /v1/jobs/{id}/file (with the X-API-Key header), read the response as a Blob, and wrap it in a File named after the job's title (made filename-safe, ending in .mp3, type "audio/mpeg"). Pass that File into the app's EXISTING audio upload function, the same one used when a user picks a file. Don't build a second upload path.
4. Show progress (Queued → Converting → Uploading). On failure, show the API's error message ("detail" or the job's "error") and let the user retry. On success, the new audio appears wherever uploaded audio normally appears.
5. Put all the API calls in one small module (e.g. src/lib/ytAudio.ts) so the UI component stays simple.
6. Show this small note under the input: "Only import audio you have the rights to use."
```

## After Bolt finishes

- Fill in the two values in Bolt's `.env`. `VITE_YT_AUDIO_API_URL` is the
  deployed base URL with no trailing slash, and `VITE_YT_AUDIO_API_KEY` is the
  `API_KEY` you set on the server.
- Test with a short Creative Commons video first.
- If imports fail with "Sign in to confirm you're not a bot", YouTube is blocking
  the hosting provider's IP. That is a hosting problem, not a Bolt problem. See
  "If the live test fails" in `HANDOFF.md`.
- If the browser console shows a CORS error, check that the URL has no trailing
  slash and that `CORS_ORIGINS` on the server is unset or includes the app's
  origin.
