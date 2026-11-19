
import os
import uuid
import subprocess
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
WORK = BASE / "work"
OUT = BASE / "outputs"

WORK.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

app = FastAPI(title="PeakCut AI 2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUT)), name="outputs")


@app.get("/")
def home():
    return {"message": "PeakCut AI 2.0 backend is running!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process")
async def process_video(
    video: UploadFile = File(...),
    clip_seconds: int = Form(30),
    number_of_clips: int = Form(5),
    vertical: bool = Form(True),
    quality: int = Form(1080),
):
    if not video.filename:
        raise HTTPException(400, "Please upload a video.")

    if clip_seconds not in [20, 30, 45, 60]:
        raise HTTPException(400, "Invalid clip duration.")

    if number_of_clips not in [3, 5, 10]:
        raise HTTPException(400, "Invalid number of clips.")

    if quality not in [720, 1080]:
        raise HTTPException(400, "Invalid quality.")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    if not ffmpeg or not ffprobe:
        raise HTTPException(500, "FFmpeg is not installed on the server.")

    job = uuid.uuid4().hex
    job_dir = WORK / job
    job_dir.mkdir(parents=True)

    input_path = job_dir / "input_video"
    try:
        with input_path.open("wb") as f:
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        probe = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(input_path),
            ],
            capture_output=True,
            text=True,
        )

        if probe.returncode != 0:
            raise HTTPException(400, "Could not read this video.")

        duration = float(probe.stdout.strip())
        if duration <= 0:
            raise HTTPException(400, "Video duration is invalid.")

        window = 5
        scores = []
        position = 0.0

        while position < duration:
            result = subprocess.run(
                [
                    ffmpeg, "-ss", str(position),
                    "-i", str(input_path),
                    "-t", str(min(window, duration - position)),
                    "-vn", "-af", "volumedetect",
                    "-f", "null", "-"
                ],
                capture_output=True,
                text=True,
            )

            output = result.stderr
            loudness = -100.0

            for line in output.splitlines():
                if "mean_volume:" in line:
                    try:
                        loudness = float(
                            line.split("mean_volume:")[1]
                            .split("dB")[0].strip()
                        )
                    except ValueError:
                        pass

            scores.append((loudness, position))
            position += window

        scores.sort(reverse=True)
        chosen = []

        for score, start in scores:
            start = max(0, min(start, duration - clip_seconds))
            if all(abs(start - old) >= clip_seconds for old in chosen):
                chosen.append(start)
            if len(chosen) >= number_of_clips:
                break

        output_dir = OUT / job
        output_dir.mkdir(parents=True)

        clips = []

        for index, start in enumerate(chosen, 1):
            output_path = output_dir / f"clip_{index}.mp4"

            if vertical:
                vf = (
                    f"scale={quality}:{quality}:force_original_aspect_ratio=increase,"
                    f"crop={quality}: {quality}:"
                    f"(iw-{quality})/2:(ih-{quality})/2"
                )
                vf = (
                    f"scale={quality}:"
                    f"{int(quality * 16 / 9)}:"
                    "force_original_aspect_ratio=increase,"
                    f"crop={quality}:{int(quality * 16 / 9)}"
                )
            else:
                vf = f"scale='min({quality},iw)':-2"

            command = [
                ffmpeg, "-y",
                "-ss", str(start),
                "-i", str(input_path),
                "-t", str(clip_seconds),
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output_path),
            ]

            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                clips.append({
                    "name": output_path.name,
                    "url": f"/outputs/{job}/{output_path.name}",
                    "start_seconds": round(start, 2),
                })

        return {
            "status": "complete",
            "clips": clips,
            "note": "Clips are ranked by audio loudness, not semantic AI."
        }

    finally:
        await video.close()
