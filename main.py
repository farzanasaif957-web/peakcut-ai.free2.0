import os, uuid, subprocess, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
WORK = BASE / "work"
OUT = BASE / "outputs"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
app = FastAPI(title="PeakCut AI 2.0 API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=OUT), name="outputs")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2500:])
    return p.stdout

def duration_seconds(path):
    raw = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)]).strip()
    return float(raw)

def audio_activity_scores(path, total, count, clip_len):
    # Lightweight baseline: sample RMS loudness in short windows with FFmpeg.
    # This is NOT semantic AI and cannot understand speech, jokes, or context.
    window = 5.0
    scores=[]
    t=0.0
    while t < total:
        cmd=["ffmpeg","-hide_banner","-nostats","-ss",str(t),"-t",str(min(window,total-t)),"-i",str(path),
             "-vn","-af","volumedetect","-f","null","-"]
        p=subprocess.run(cmd,capture_output=True,text=True)
        text=p.stderr
        import re
        m=re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB",text)
        score=float(m.group(1)) if m else -90.0
        scores.append((t,score))
        t+=window
    # Select separated windows with higher average audio activity.
    candidates=[]
    half=clip_len/2
    for start,score in scores:
        center=start+window/2
        clip_start=max(0,min(total-clip_len,center-half))
        candidates.append((score,clip_start))
    candidates.sort(reverse=True)
    chosen=[]
    for score,start in candidates:
        if all(abs(start-x)>clip_len*0.8 for x in chosen):
            chosen.append(start)
        if len(chosen)>=count: break
    if not chosen:
        chosen=[max(0,(total-clip_len)/2)]
    while len(chosen)<count:
        chosen.append(max(0,(total-clip_len)*(len(chosen)+1)/(count+1)))
    return sorted(chosen)

@app.get("/")
def health():
    return {"service":"PeakCut AI 2.0","status":"ready","note":"Starter backend; audio-activity highlight ranking is not semantic AI."}

@app.post("/process")
async def process(file: UploadFile=File(...), duration: int=Form(30), count: int=Form(5),
                  format: str=Form("vertical"), quality: int=Form(1080)):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(500,"FFmpeg and FFprobe must be installed on the server.")
    if duration not in (20,30,45,60) or count not in (3,5,10) or format not in ("vertical","original") or quality not in (720,1080):
        raise HTTPException(400,"Invalid export settings.")
    suffix=Path(file.filename or "upload.mp4").suffix.lower()
    if suffix not in (".mp4",".mov",".mkv",".webm",".m4v"):
        raise HTTPException(400,"Please upload an MP4, MOV, MKV, WebM or M4V video.")
    job=uuid.uuid4().hex
    source=WORK/f"{job}{suffix}"
    try:
        with source.open("wb") as f:
            while chunk:=await file.read(1024*1024):
                f.write(chunk)
        total=duration_seconds(source)
        if total < duration:
            raise HTTPException(400,f"Video is shorter than the selected {duration}-second clip length.")
        starts=audio_activity_scores(source,total,count,duration)
        results=[]
        for i,start in enumerate(starts,1):
            dest=OUT/f"{job}_clip_{i}.mp4"
            if format=="vertical":
                vf=f"scale='if(gte(a,0.5625),-2,{quality})':'if(gte(a,0.5625),{quality},-2)',crop={quality}*9/16:{quality}:(iw-ow)/2:(ih-oh)/2,setsar=1"
            else:
                vf=f"scale='min({quality},iw)':-2"
            cmd=["ffmpeg","-y","-hide_banner","-ss",str(start),"-i",str(source),"-t",str(duration),
                 "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","19","-c:a","aac","-b:a","192k","-movflags","+faststart",str(dest)]
            run(cmd)
            results.append({"name":dest.name,"download_url":f"/outputs/{dest.name}","start_seconds":round(start,1)})
        return {"job_id":job,"source_duration_seconds":round(total,1),"clips":results,
                "notice":"Initial audio-activity ranking only; not semantic AI. Captions/transcription are not yet enabled."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500,str(e))
    finally:
        try: source.unlink(missing_ok=True)
        except Exception: pass
