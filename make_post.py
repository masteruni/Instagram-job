#!/usr/bin/env python3
"""Turn an Instagram reel link into a branded @theaiedgedaily post.

Outputs (in output/<shortcode>/):
  video.mp4      1080x1920 reel: black canvas, header, hook line, clip
  thumbnail.jpg  1080x1920 cover: full-bleed frame, navy gradients, header
  caption.txt    post caption (edit the CAPTION template below or pass --caption)

Usage:
  python3 make_post.py <instagram_url> --hook "Yep that's your daughter"
      [--thumb-time 4.0] [--thumb-focus 0.5] [--caption "..."]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
AVATAR = ROOT / "assets" / "avatar.png"
FONT_DIR = Path("/usr/share/fonts/opentype/inter")
BOLD = str(FONT_DIR / "Inter-Bold.otf")
REGULAR = str(FONT_DIR / "Inter-Regular.otf")
ITALIC = str(FONT_DIR / "Inter-Italic.otf")

W, H = 1080, 1920
NAME = "The AI Edge Daily"
HANDLE = "@theaiedgedaily"
BADGE_BLUE = (24, 119, 242)
NAVY = (2, 18, 88)


def run(cmd):
    subprocess.run(cmd, check=True)


def download(url, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    if (workdir / "source.mp4").exists() and (workdir / "source.info.json").exists():
        # already fetched; re-downloading quickly trips Instagram's rate limit (HTTP 429)
        return workdir / "source.mp4", json.loads((workdir / "source.info.json").read_text())
    run(["yt-dlp", "-q", "--no-warnings", "--write-info-json",
         "-f", "bv*+ba/b", "--merge-output-format", "mp4",
         "-o", str(workdir / "source.%(ext)s"), url])
    info = json.loads((workdir / "source.info.json").read_text())
    return workdir / "source.mp4", info


def detect_clip_box(src, samples=24):
    """Find the actual video area inside the source reel.

    Works on any layout (black or white template, text above/below): the clip is
    the region whose pixels change over time, while backgrounds and burned-in text stay still.
    """
    import numpy as np
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(src)],
        capture_output=True, text=True).stdout
    meta = json.loads(probe)
    w, h = meta["streams"][0]["width"], meta["streams"][0]["height"]
    dur = float(meta["format"]["duration"])
    frames = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        if len(raw) == w * h:
            frames.append(np.frombuffer(raw, np.uint8).reshape(h, w))
    if len(frames) < 3:
        return None
    stack = np.stack(frames).astype(np.int16)
    moving = (stack.max(0) - stack.min(0)) > 25

    def longest_run(mask):
        best, cur, start = (0, -1), 0, 0
        for i, v in enumerate(mask):
            if v:
                if cur == 0:
                    start = i
                cur += 1
                if cur > best[1] - best[0] + 1:
                    best = (start, i)
            else:
                cur = 0
        return best

    top, bot = longest_run(moving.mean(1) > 0.25)
    left, right = longest_run(moving[top:bot + 1].mean(0) > 0.25)
    if bot - top < 50 or right - left < 50:
        return None
    # static parts of the clip (a still wall, a TV logo) don't move, so grow the
    # box outward until rows/columns are just the template's background colour
    bg = int(np.median(np.concatenate([stack[:, :8, :8].ravel(), stack[:, :8, -8:].ravel()])))
    content = (np.abs(stack - bg) > 18).any(0)
    while top > 0 and content[top - 1, left:right + 1].mean() > 0.5:
        top -= 1
    while bot < h - 1 and content[bot + 1, left:right + 1].mean() > 0.5:
        bot += 1
    while left > 0 and content[top:bot + 1, left - 1].mean() > 0.5:
        left -= 1
    while right < w - 1 and content[top:bot + 1, right + 1].mean() > 0.5:
        right += 1
    # trim 2px of edge anti-aliasing and keep yuv420-friendly even values
    top, left = (top + 2) // 2 * 2, (left + 2) // 2 * 2
    cw, ch = (right - 2 - left) // 2 * 2, (bot - 2 - top) // 2 * 2
    return cw, ch, left, top


def ss(img_size, scale=4):
    return Image.new("RGBA", (img_size[0] * scale, img_size[1] * scale), (0, 0, 0, 0))


def badge(size):
    """Verified badge: scalloped blue rosette with white check (supersampled)."""
    import math
    s = 4
    im = ss((size, size), s)
    d = ImageDraw.Draw(im)
    S = size * s
    c, n = S / 2, 12
    r_out, r_in = S / 2, S / 2 * 0.86
    pts = []
    for i in range(n * 2 * 8):
        a = math.pi * 2 * i / (n * 2 * 8)
        r = r_in + (r_out - r_in) * (0.5 + 0.5 * math.cos(a * n))
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=BADGE_BLUE)
    lw = int(S * 0.1)
    d.line([(S * 0.29, S * 0.52), (S * 0.44, S * 0.66), (S * 0.72, S * 0.37)],
           fill="white", width=lw, joint="curve")
    for p in [(S * 0.29, S * 0.52), (S * 0.72, S * 0.37)]:
        d.ellipse((p[0] - lw / 2, p[1] - lw / 2, p[0] + lw / 2, p[1] + lw / 2), fill="white")
    return im.resize((size, size), Image.LANCZOS)


def draw_header(canvas, x, y, avatar_d, name_size, handle_size, name_color, handle_color, gap):
    """Avatar circle + bold name + badge + italic handle. (x, y) = avatar top-left."""
    av = Image.open(AVATAR).convert("RGBA").resize((avatar_d, avatar_d), Image.LANCZOS)
    canvas.alpha_composite(av, (x, y))
    d = ImageDraw.Draw(canvas)
    fn = ImageFont.truetype(BOLD, name_size)
    fh = ImageFont.truetype(ITALIC, handle_size)
    tx = x + avatar_d + gap
    # vertically centre the two-line text block on the avatar
    name_h = fn.getbbox("Th")[3]
    handle_h = fh.getbbox("@h")[3]
    line_gap = int(name_size * 0.12)
    top = y + (avatar_d - (name_h + line_gap + handle_h)) // 2
    d.text((tx, top), NAME, font=fn, fill=name_color)
    nw = d.textlength(NAME, font=fn)
    bsize = int(name_size * 0.95)
    b = badge(bsize)
    cap_top = fn.getbbox("T")[1]
    canvas.alpha_composite(b, (int(tx + nw + name_size * 0.14),
                               int(top + cap_top + (name_h - cap_top - bsize) / 2)))
    d.text((tx, top + name_h + line_gap), HANDLE, font=fh, fill=handle_color)


def wrap(text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if font.getlength(t) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def build_video(src, box, hook, out, workdir):
    cw, ch, cx, cy = box
    margin = 35
    vid_w = W - 2 * margin
    vid_h = int(round(vid_w * ch / cw / 2)) * 2

    # Layout measured from the Canva template (screenshot 2), scaled to 1080 wide
    avatar_d, pad_x = 148, 83
    fhook = ImageFont.truetype(REGULAR, 52)
    hook_lines = wrap(hook, fhook, W - 2 * 110)
    line_h = int(52 * 1.25)
    hook_block = line_h * len(hook_lines)
    header_to_hook = 165 - 0  # avatar top -> hook top
    hook_to_video = 40
    block_h = header_to_hook + hook_block + hook_to_video + vid_h
    top = (H - block_h) // 2

    bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw_header(bg, pad_x, top, avatar_d, 50, 34,
                name_color=(255, 255, 255), handle_color=(142, 142, 147), gap=14)
    d = ImageDraw.Draw(bg)
    hy = top + header_to_hook
    for i, line in enumerate(hook_lines):
        d.text((110, hy + i * line_h), line, font=fhook, fill="white")
    vid_y = hy + hook_block + hook_to_video
    bg_path = workdir / "video_bg.png"
    bg.convert("RGB").save(bg_path)

    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(bg_path), "-i", str(src),
         "-filter_complex",
         f"[1:v]crop={cw}:{ch}:{cx}:{cy},scale={vid_w}:{vid_h}:flags=lanczos,setsar=1[v];"
         f"[0:v][v]overlay={margin}:{vid_y}:shortest=1,format=yuv420p[out]",
         "-map", "[out]", "-map", "1:a?", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-r", "30", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])


def build_thumbnail(src, box, t, focus, out, workdir):
    cw, ch, cx, cy = box
    frame = workdir / "thumb_frame.png"
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(src),
         "-vf", f"crop={cw}:{ch}:{cx}:{cy}", "-frames:v", "1", str(frame)])
    im = Image.open(frame).convert("RGB")
    # cover-fit 9:16, horizontal focus point 0..1
    scale = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * scale + 0.5), int(im.height * scale + 0.5)), Image.LANCZOS)
    left = int(min(max(focus * im.width - W / 2, 0), im.width - W))
    top = (im.height - H) // 2
    canvas = im.crop((left, top, left + W, top + H)).convert("RGBA")

    # navy gradients sampled from the template: solid at the edges, header sits on navy
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gp = grad.load()
    for y in range(H):
        r = y / H
        a = 0.0
        if r < 0.36:
            a = min(1.0, (1 - r / 0.36) ** 0.8 * 1.15)
        elif r > 0.70:
            a = ((r - 0.70) / 0.30) ** 1.3
        if a:
            col = NAVY + (int(255 * min(a * 1.02, 1)),)
            for x in range(W):
                gp[x, y] = col
    canvas.alpha_composite(grad)

    # header measured from the Canva template (screenshot 1), scaled to 1080 wide
    draw_header(canvas, 70, 300, 210, 64, 44,
                name_color=(205, 210, 218), handle_color=(150, 152, 160), gap=40)
    canvas.convert("RGB").save(out, quality=95)


CAPTION = """{hook} 😭

{context}

Follow @theaiedgedaily for daily clips that hit different ⚡

🎥 Credit: {credit}
-
{tags}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--hook", required=True, help="line shown above the clip")
    ap.add_argument("--context", default="", help="1-2 sentence body for the caption")
    ap.add_argument("--tags", default="#comedy #funny #reels #viral #explorepage")
    ap.add_argument("--thumb-time", type=float, default=None)
    ap.add_argument("--thumb-focus", type=float, default=0.5)
    args = ap.parse_args()

    code = re.search(r"/(?:reel|p|reels)/([\w-]+)", args.url)
    code = code.group(1) if code else "post"
    outdir = ROOT / "output" / code
    work = ROOT / ".work" / code
    src, info = download(args.url, work)

    box = detect_clip_box(src)
    if box is None:
        sys.exit("could not detect clip area")
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout)
    t = args.thumb_time if args.thumb_time is not None else dur * 0.4

    outdir.mkdir(parents=True, exist_ok=True)
    build_video(src, box, args.hook, outdir / "video.mp4", work)
    build_thumbnail(src, box, t, args.thumb_focus, outdir / "thumbnail.jpg", work)
    credit = "@" + (info.get("channel") or info.get("uploader_id") or "original creator")
    (outdir / "caption.txt").write_text(CAPTION.format(
        hook=args.hook, context=args.context, credit=credit, tags=args.tags).replace("\n\n\n", "\n\n"))
    print(f"done -> {outdir}")


if __name__ == "__main__":
    main()
