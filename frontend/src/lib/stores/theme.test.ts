import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

async function load() {
  vi.resetModules();
  return import('./theme.ts');
}

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

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
    toggleTheme();
    expect(get(theme)).toBe('mocha');
    expect(localStorage.getItem('studyrun-theme')).toBe('mocha');
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
});
