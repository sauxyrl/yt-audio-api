# Prompt for bolt.new

Do this first: deploy this API somewhere with a public HTTPS URL, such as Render,
Railway, or Fly.io (each can build the included `Dockerfile`), and set `API_KEY`.
Bolt cannot host it. Then paste everything inside the block below into Bolt.

```text
Add an "Import audio from YouTube" feature to this app. The audio should end up in the app's existing audio upload flow, as if the user had uploaded an MP3 themselves.

Do NOT download or convert YouTube in this app. A separate conversion API already exists and is deployed. Call it. Its source and docs are at https://github.com/sauxyrl/yt-audio-api.

## The API
Base URL: stored in the server secret YT_AUDIO_API_URL
Every request needs the header `X-API-Key: <value of server secret YT_AUDIO_API_KEY>`

- POST {base}/v1/jobs
  JSON body: {"url": "<youtube url>", "bitrate": 192}
  → 202 {"id": "<job id>", "status": "queued", ...}
- GET {base}/v1/jobs/{id}
  → {"id", "status": "queued" | "running" | "done" | "error", "title", "duration", "file_url", "error"}
  `file_url` is a path relative to the base URL. `error` is a message when status is "error" (e.g. the video is live or longer than 1 hour).
- GET {base}/v1/jobs/{id}/file
  → the MP3 bytes, Content-Type audio/mpeg. Available for 1 hour after the job finishes.
- HTTP errors: 400 = not a YouTube link, 401 = bad API key, 404 = job not found or expired, 409 = file requested before the job is done, 422 = invalid request body.

Use the job endpoints above. Do not use the API's synchronous /v1/convert endpoint, because long videos can exceed serverless function time limits.

## Requirements
1. The API key is a secret. Never put it in frontend code or in any VITE_/NEXT_PUBLIC_/public env variable. All calls to the API must go through server-side code (a Supabase Edge Function if this project uses Supabase; otherwise this stack's server functions). Store YT_AUDIO_API_URL and YT_AUDIO_API_KEY as server-side secrets. The API sends no CORS headers, so calls from the browser will fail anyway.
2. Server side, expose three actions:
   a. start: validate the URL, POST /v1/jobs, return the job id.
   b. status: GET /v1/jobs/{id}, return status/title/error.
   c. finish: when status is "done", download the MP3 from /v1/jobs/{id}/file and save it through the app's EXISTING audio upload/storage code path. Name the file after the job's title, made filename-safe, ending in .mp3. Return the saved audio record/URL.
3. Client side: poll the status action every 3 seconds while the job is queued or running. Stop after 10 minutes and show a timeout error. When it is done, call finish.
4. UI: a text input for a YouTube URL and an "Import" button. Check that it's a youtube.com or youtu.be link before sending. While working, show the progress (Queued → Converting → Saving). On failure, show the API's error message and let the user retry. On success, the new audio appears wherever uploaded audio normally appears.
5. Reuse the existing upload logic. Don't build a second, parallel storage path.
6. Show this small note under the input: "Only import audio you have the rights to use."

When you're done, tell me which secrets I need to set and where.
```

## After Bolt finishes

- Set the two secrets it names. `YT_AUDIO_API_URL` is the deployed base URL with
  no trailing slash, and `YT_AUDIO_API_KEY` is the `API_KEY` you set on the server.
- Test with a short Creative Commons video first.
- If imports fail with "Sign in to confirm you're not a bot", YouTube is blocking
  the hosting provider's IP. That is a hosting problem, not a Bolt problem. See
  "If the live test fails" in `HANDOFF.md`.
