"""Reels: the day's card slides as a 9:16 video with original music.

Each slide sits a little smaller than full width on a soft, blurred copy of itself (so Instagram's
buttons and caption don't cover the card), and slides change with a swipe-left transition, like
flicking through the carousel. Music comes from assets/music/ (original tracks made by bot/music.py,
or any royalty-free .m4a / .mp3 you drop in there), faded in and out.

config.toml [reels]: mode (auto / manual / off), days, seconds_per_slide, audio_name.
In manual mode the video is made without music, for adding a trending sound in the Instagram app.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date as Date
from pathlib import Path

from PIL import Image, ImageFilter

from .util import log, warn

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"
RW, RH = 1080, 1920
CARD_SCALE = 0.9
CARD_TOP = 250          # keeps the card clear of Instagram's top bar and the caption area at the bottom
FPS = 30
TRANSITION = 0.45
HOOK_SECONDS = 2.6      # the 'myth or fact?' opener of ingredient Reels
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("ffmpeg 을 찾지 못했어요 (pip install imageio-ffmpeg)")
        return exe


def settings(cfg) -> dict:
    r = cfg.raw.get("reels", {})
    mode = str(r.get("mode", "off")).strip().lower()
    return {"mode": mode if mode in ("auto", "manual", "off") else "off",
            "days": [DAYS[d[:3].lower()] for d in r.get("days", []) if d[:3].lower() in DAYS],
            "seconds": float(r.get("seconds_per_slide", 3.6)),
            "audio_name": str(r.get("audio_name", "")).strip(),
            "twin_card": bool(r.get("twin_card", False))}


def is_reel_day(cfg, today: Date, override: str | None = None) -> bool:
    s = settings(cfg)
    if override == "yes":
        return True
    if override == "no" or s["mode"] == "off":
        return False
    return today.weekday() in s["days"]


def tracks() -> list[Path]:
    if not MUSIC_DIR.exists():
        return []
    return sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".m4a", ".mp3", ".aac", ".wav"))


def pick_track(number: int) -> Path | None:
    ts = tracks()
    return ts[number % len(ts)] if ts else None


def frame(slide: Path, out: Path, handle: str = "") -> Path:
    from PIL import ImageDraw
    card = Image.open(slide).convert("RGB")
    base = card.getpixel((8, 8))
    darker = tuple(max(0, int(c * 0.86)) for c in base)
    bg = Image.new("RGB", (RW, RH), base)
    grad = Image.linear_gradient("L").resize((RW, RH))
    bg = Image.composite(Image.new("RGB", (RW, RH), darker), bg, grad)
    w, h = int(card.width * CARD_SCALE), int(card.height * CARD_SCALE)
    small = card.resize((w, h), Image.LANCZOS)
    x, y = (RW - w) // 2, CARD_TOP
    shadow = Image.new("L", (RW, RH), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + 18, x + w, y + h + 18), 36, fill=70)
    bg.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(28)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), 36, fill=255)
    bg.paste(small, (x, y), mask)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out, "PNG")
    return out


def build_reel(slides: list[Path], out_video: Path, cover_out: Path, seconds: float = 3.6,
               music: Path | None = None, ffmpeg: str | None = None, lead: float | None = None) -> float:
    """Writes the MP4 (H.264 + AAC, 1080x1920, 30 fps) and a JPG cover. Returns the duration in seconds."""
    ff = ffmpeg or ffmpeg_path()
    work = out_video.parent / f".{out_video.stem}_frames"
    frames = [frame(s, work / f"{i:02d}.png") for i, s in enumerate(slides, 1)]
    Image.open(frames[0]).convert("RGB").save(cover_out, "JPEG", quality=90)
    n = len(frames)
    first, last = seconds + 0.6, seconds + 0.9  # a beat longer on the cover and the last card
    lengths = [first] + [seconds] * (n - 2) + [last] if n > 1 else [first + 1]
    if lead and n > 2:  # a short hook card in front: the original cover keeps its longer first beat
        lengths = [lead, first] + [seconds] * (n - 3) + [last]
    total = sum(lengths) - TRANSITION * (n - 1)
    cmd = [ff, "-y", "-loglevel", "error"]
    for f, ln in zip(frames, lengths):
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{ln:.3f}", "-i", str(f)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    chains = [f"[{i}:v]format=yuv420p,setsar=1[v{i}]" for i in range(n)]
    last_label, offset = "v0", 0.0
    for i in range(1, n):
        offset += lengths[i - 1] - TRANSITION
        label = f"x{i}"
        chains.append(f"[{last_label}][v{i}]xfade=transition=slideleft:duration={TRANSITION}:offset={offset:.3f}[{label}]")
        last_label = label
    if music:
        chains.append(f"[{n}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.8,"
                      f"afade=t=out:st={max(0.0, total - 2.0):.3f}:d=2,volume=0.9[a]")
    cmd += ["-filter_complex", ";".join(chains), "-map", f"[{last_label}]"]
    if music:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "20",
            "-maxrate", "8M", "-bufsize", "16M", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out_video)]
    out_video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(work, ignore_errors=True)
    return round(total, 2)


def make_for_post(cfg, post: dict, slides: list[Path], out: Path, manual: bool | None = None,
                  hook: Path | None = None) -> dict | None:
    """Builds site/reels/NNN.mp4 (+ cover) for a prepared post and returns the record to keep on the post."""
    s = settings(cfg)
    mode = "manual" if manual else (s["mode"] if s["mode"] != "off" else "auto")
    music = None if mode == "manual" else pick_track(post["number"])
    if mode == "auto" and music is None:
        warn("assets/music/ 에 음악이 없어서 릴스를 음악 없이 만들어요.")
    folder = post["folder"]
    video = out / "reels" / f"{folder}.mp4"
    cover = out / "reels" / f"{folder}.jpg"
    try:
        secs = build_reel(([hook] if hook else []) + list(slides), video, cover, s["seconds"], music,
                          lead=HOOK_SECONDS if hook else None)
    except Exception as exc:
        err = getattr(exc, "stderr", b"") or b""
        warn(f"릴스 영상을 만들지 못했어요 (카드뉴스는 그대로 올려요): {exc} {err[-300:].decode(errors='ignore')}")
        return None
    size = video.stat().st_size // 1024
    log(f"릴스 영상 준비: reels/{folder}.mp4 ({secs}초, {size} KB, 음악: {music.stem if music else '없음'}, {mode})")
    return {"mode": mode, "video": f"reels/{folder}.mp4", "cover": f"reels/{folder}.jpg", "seconds": secs,
            "track": music.stem if music else "", "status": "prepared"}


def reel_caption(caption: str, twin_card: bool = False) -> str:
    """The carousel caption; with a pointer to the card version only when that version is posted too."""
    if not twin_card:
        return caption[:2200]
    head, _, rest = caption.partition("\n")
    note = "📌 Prefer to swipe? The card version is on our profile too. Save it for later."
    return f"{head}\n{note}\n{rest}"[:2200]
