#!/usr/bin/env node
// Render a swipe (carousel) post from a spec file.
//   node reels/carousel.js reels/specs/<name>.json
// Outputs output/<name>/slide-01.png ... and caption.txt (1080x1350, Instagram 4:5)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

(async () => {
  const specPath = process.argv[2];
  const name = path.basename(specPath, '.json');
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  const out = path.join(ROOT, 'output', name);
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(out)) if (/^slide-\d+\.png$/.test(f)) fs.unlinkSync(path.join(out, f));

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'carousel.html'));
  const avatar = 'data:image/png;base64,' + fs.readFileSync(path.join(ROOT, 'assets', 'avatar.png')).toString('base64');
  const n = await page.evaluate(([s, a]) => window.show(s, 0, a), [spec, avatar]);
  for (let i = 0; i < n; i++) {
    await page.evaluate(([s, k, a]) => window.show(s, k, a), [spec, i, avatar]);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(100);
    await page.screenshot({ path: path.join(out, `slide-${String(i + 1).padStart(2, '0')}.png`) });
  }
  await browser.close();
  fs.writeFileSync(path.join(out, 'caption.txt'), spec.caption.trim() + '\n');
  console.log(`done -> ${out} (${n} slides)`);
})();
