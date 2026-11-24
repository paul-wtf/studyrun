// Writes static/favicon.svg and the PNG app icons from one template, in the family's style
// (accent square, crust letters). Same Playwright setup as screenshots.mjs:
//
//   NODE_PATH=<dir containing the playwright package> node scripts/icons.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const PEACH = '#fab387';
const CRUST = '#11111b';
const root = fileURLToPath(new URL('..', import.meta.url));

// Maskable icons get cropped to a circle of 80% of their width, so they are full-bleed with
// smaller letters.
const svg = ({ maskable = false } = {}) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="${maskable ? 0 : 16}" fill="${PEACH}" />
  <text
    x="32"
    y="34"
    text-anchor="middle"
    dominant-baseline="central"
    font-family="'JetBrains Mono', ui-monospace, Menlo, monospace"
    font-weight="700"
    font-size="${maskable ? 20 : 26}"
    fill="${CRUST}"
  >sr</text>
</svg>
`;

writeFileSync(`${root}static/favicon.svg`, svg());

const font = readFileSync(
  require.resolve('@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2', { paths: [root] })
).toString('base64');

const browser = await chromium.launch();
try {
  for (const [file, size, maskable] of [['icon-192.png', 192, false], ['icon-512.png', 512, false], ['icon-maskable-512.png', 512, true]]) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(
      `<style>@font-face { font-family: 'JetBrains Mono'; src: url(data:font/woff2;base64,${font}); font-weight: 100 800; }
       body { margin: 0; } svg { display: block; width: ${size}px; height: ${size}px; }</style>${svg({ maskable })}`
    );
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${root}static/${file}`, omitBackground: true });
    await page.close();
    console.log(`static/${file}`);
  }
} finally {
  await browser.close();
}
