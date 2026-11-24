import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

async function load() {
  vi.resetModules();
  return import('./theme.ts');
}

describe('theme store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    document.head.innerHTML = '<meta name="theme-color" content="#181825" />';
  });

  const themeColor = () => document.querySelector('meta[name="theme-color"]')?.getAttribute('content');

  it('defaults to mocha', async () => {
    const { theme } = await load();
    expect(get(theme)).toBe('mocha');
    expect(document.documentElement.dataset.theme).toBe('mocha');
  });

  it('toggles, persists and reflects the theme on the document', async () => {
    const { theme, toggleTheme } = await load();
    toggleTheme();
    expect(get(theme)).toBe('latte');
    expect(localStorage.getItem('studyrun-theme')).toBe('latte');
    expect(document.documentElement.dataset.theme).toBe('latte');
    expect(themeColor()).toBe('#e6e9ef');
    toggleTheme();
    expect(get(theme)).toBe('mocha');
    expect(localStorage.getItem('studyrun-theme')).toBe('mocha');
    expect(themeColor()).toBe('#181825');
  });

  it('restores a stored theme', async () => {
    localStorage.setItem('studyrun-theme', 'latte');
    const { theme } = await load();
    expect(get(theme)).toBe('latte');
  });

  it('falls back to mocha for an invalid stored value', async () => {
    localStorage.setItem('studyrun-theme', 'solarized');
    const { theme } = await load();
    expect(get(theme)).toBe('mocha');
    expect(document.documentElement.dataset.theme).toBe('mocha');
  });

  it('falls back to mocha and still toggles when storage throws', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const { theme, toggleTheme } = await load();
    expect(get(theme)).toBe('mocha');
    expect(document.documentElement.dataset.theme).toBe('mocha');
    toggleTheme();
    expect(get(theme)).toBe('latte');
    expect(document.documentElement.dataset.theme).toBe('latte');
    expect(themeColor()).toBe('#e6e9ef');
  });
});
