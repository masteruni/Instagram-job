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

## Original AI-tip reels

Write a spec in `reels/specs/<name>.json` (hook, prompt, answer lines, caption), then:

```bash
node reels/render.js reels/specs/<name>.json   # needs Playwright Chromium + ffmpeg
```

Results land in `output/<name>/`. In text, `*word*` is yellow, `**word**` is bold and `==text==` gets highlighted.

Sound effects come from Epidemic Sound (IDs in `reels/sfx.json`). Download each as WAV
into `.work/sfx/<name>.wav`; they are licensed, so they are not committed. Without them the reel renders silent.
