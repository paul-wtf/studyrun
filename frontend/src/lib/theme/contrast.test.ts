import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { MANTLE, STORAGE_KEY, type Theme } from '#lib/stores/theme.ts';

const css = readFileSync(resolve('src/lib/theme/tokens.css'), 'utf8');

function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(selector + ' {');
  if (start < 0) throw new Error(`no block ${selector}`);
  const body = css.slice(start, css.indexOf('\n}', start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6}|var\(--[a-z0-9-]+\))\s*;/g)) out[m[1]] = m[2];
  return out;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const themes: [Theme, string][] = [
  ['mocha', ":root[data-theme='mocha']"],
  ['latte', ":root[data-theme='latte']"]
];

describe.each(themes)('%s contrast', (name, selector) => {
  const vars = tokens(selector);
  const get = (n: string): string => {
    let v = vars[n];
    while (v?.startsWith('var(')) v = vars[v.slice(4, -1)];
    expect(v, `${n} resolves to a hex value`).toMatch(/^#/);
    return v;
  };

  it.each(['--text', '--text-muted', '--accent-text'])('%s reaches 4.5:1 on crust, mantle and base', (token) => {
    for (const bg of ['--crust', '--mantle', '--base']) {
      expect(contrast(get(token), get(bg)), `${token} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(['--success', '--error'])('%s reaches 4.5:1 on base', (token) => {
    expect(contrast(get(token), get('--base'))).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps text readable on secondary buttons and chips', () => {
    expect(contrast(get('--text'), get('--surface0'))).toBeGreaterThanOrEqual(4.5);
  });

  it('keeps the delete button label readable on the error fill', () => {
    expect(contrast(get('--base'), get('--error'))).toBeGreaterThanOrEqual(4.5);
  });

  it('gives the browser chrome the mantle colour', () => {
    expect(MANTLE[name]).toBe(get('--mantle'));
  });
});

describe('values copied out of tokens.css and theme.ts', () => {
  const html = readFileSync(resolve('src/app.html'), 'utf8');
  const manifest = JSON.parse(readFileSync(resolve('static/manifest.webmanifest'), 'utf8'));

  it('keeps the pre-paint script in step with the theme store', () => {
    expect(html).toContain(`localStorage.getItem('${STORAGE_KEY}')`);
    expect(html).toContain(`<meta name="theme-color" content="${MANTLE.mocha}" />`);
    expect(html).toContain(`t === 'latte' ? '${MANTLE.latte}' : '${MANTLE.mocha}'`);
  });

  it('gives the installed app the Mocha crust and mantle', () => {
    expect(manifest.background_color).toBe(tokens(":root[data-theme='mocha']")['--crust']);
    expect(manifest.theme_color).toBe(MANTLE.mocha);
  });
});
