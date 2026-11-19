# PeakCut AI 2.0 — starter project

## What's working in this starter
- Mobile-friendly frontend.
- Upload video to a FastAPI backend.
- FFmpeg MP4 clip export.
- Vertical 9:16 or original aspect ratio.
- Initial audio-activity ranking to suggest clip moments.

## Important limitations
- The highlight selector is a basic loudness/activity heuristic, **not semantic AI**.
- Automatic speech transcription and animated word-by-word captions are not implemented yet.
- The YouTube URL field is informational only. This project does not download YouTube videos. Use uploads you own or have permission to edit.
- Five-hour uploads / five-minute processing are performance goals, not promises. They require a capable server, sufficient storage, bandwidth, CPU/GPU and possibly paid infrastructure.
- GitHub Pages only hosts the frontend. It cannot run this Python backend.

## Run locally
1. Install Python 3.11+ and FFmpeg/FFprobe.
2. In `backend/`, run `pip install -r requirements.txt`
3. Run `uvicorn main:app --host 0.0.0.0 --port 8000`
4. Open `frontend/index.html` in a browser.

The frontend defaults to `http://localhost:8000`. For deployment, set the API address in browser localStorage:
`localStorage.setItem("peakcut_api", "https://YOUR-BACKEND-DOMAIN")`

## Deploy
Deploy `frontend/` to GitHub Pages. Deploy `backend/` to a Python host that supports FFmpeg and large uploads. Check the host's free-tier limits before relying on it for long videos.
