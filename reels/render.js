#!/usr/bin/env node
// Render an original AI-tip reel from a spec file.
//   node reels/render.js reels/specs/<name>.json
// Outputs output/<name>/video.mp4, thumbnail.jpg, caption.txt
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FPS = 30;

// Epidemic Sound effects (licensed, not committed): see reels/sfx.json for IDs.
// Each cue: [file, start time (s), gain (dB), optional max length (s)]
const SFX = path.join(ROOT, '.work', 'sfx');
function addSound(out, T) {
  const silent = path.join(out, 'silent.mp4'), video = path.join(out, 'video.mp4');
  const need = ['whoosh', 'typing', 'sent', 'tap', 'success'];
  if (!need.every(n => fs.existsSync(path.join(SFX, n + '.wav')))) {
    console.warn('\nno sound effects in .work/sfx, video has no audio');
    fs.renameSync(silent, video);
    return;
  }
  const cues = [['whoosh', 0.0, 6]];
  T.rounds.forEach(r => {
    cues.push(['whoosh', r.start - 0.25, 6],
      ['typing', r.typeStart, -3, r.typeEnd - r.typeStart],
      ['sent', r.typeEnd + 0.05, 0],
      ...r.lineTimes.map(t => ['tap', t, 6]));
  });
  cues.push(
    ['whoosh', T.endStart - 0.25, 6],
    ['success', T.endStart + 0.1, 12]);
  const args = ['-v', 'error', '-y', '-i', silent];
  const parts = [];
  cues.forEach(([name, start, gain, len], i) => {
    args.push('-i', path.join(SFX, name + '.wav'));
    const trim = len ? `atrim=0:${len},afade=t=out:st=${Math.max(0, len - 0.3)}:d=0.3,` : '';
    const ms = Math.round(start * 1000);
    parts.push(`[${i + 1}:a]${trim}aformat=sample_rates=48000:channel_layouts=stereo,volume=${gain}dB,adelay=${ms}|${ms}[a${i}]`);
  });
  const mix = cues.map((_, i) => `[a${i}]`).join('') +
    `amix=inputs=${cues.length}:normalize=0,alimiter=limit=0.89,apad,atrim=0:${T.total}[aout]`;
  args.push('-filter_complex', parts.join(';') + ';' + mix, '-map', '0:v', '-map', '[aout]',
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', video);
  require('child_process').execFileSync('ffmpeg', args, { stdio: 'inherit' });
  fs.unlinkSync(silent);
}

(async () => {
  const specPath = process.argv[2];
  const name = path.basename(specPath, '.json');
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  const out = path.join(ROOT, 'output', name);
  fs.mkdirSync(out, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'tip_reel.html'));
  const avatar = 'data:image/png;base64,' + fs.readFileSync(path.join(ROOT, 'assets', 'avatar.png')).toString('base64');
  const T = await page.evaluate(([s, a]) => window.setup(s, a), [spec, avatar]);
  const total = T.total;
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);

  const frames = Math.round(total * FPS);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    path.join(out, 'silent.mp4')], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let i = 0; i < frames; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 90 === 0) process.stdout.write(`frame ${i}/${frames}\r`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  addSound(out, T);

  // thumbnail = hook scene, fully shown
  await page.evaluate(() => window.render(1.6));
  await page.screenshot({ path: path.join(out, 'thumbnail.jpg'), type: 'jpeg', quality: 95 });
  // preview stills for checking each scene
  if (process.env.PREVIEW) {
    for (const t of String(process.env.PREVIEW).split(',')) {
      await page.evaluate(x => window.render(x), parseFloat(t));
      await page.screenshot({ path: path.join(process.env.PREVIEW_DIR || out, `preview_${t}.png`) });
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(out, 'caption.txt'), spec.caption.trim() + '\n');
  console.log(`\ndone -> ${out} (${total.toFixed(1)}s)`);
})();
