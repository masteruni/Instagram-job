# Instagram job

Turn an Instagram reel link into a branded @theaiedgedaily post:
`video.mp4` (1080x1920), `thumbnail.jpg` (1080x1920) and `caption.txt`.

```bash
pip install yt-dlp pillow   # also needs ffmpeg + Inter font
python3 make_post.py "<reel url>" --hook "Yep that's your daughter" \
  --context "One-line context for the caption" --tags "#comedy #reels" \
  --thumb-time 4.0 --thumb-focus 0.5
```

Results land in `output/<shortcode>/`. `assets/avatar.png` is the profile picture.
