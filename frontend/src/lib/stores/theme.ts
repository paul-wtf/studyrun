import { writable } from 'svelte/store';

export type Theme = 'mocha' | 'latte';
const KEY = 'studyrun-theme';
const browser = typeof document !== 'undefined';

export const MANTLE: Record<Theme, string> = { mocha: '#181825', latte: '#e6e9ef' };

function initial(): Theme {
  if (!browser) return 'mocha';
  try {
    const saved = localStorage.getItem(KEY);
    return saved === 'latte' || saved === 'mocha' ? saved : 'mocha';
  } catch {
    return 'mocha';
  }
}

export const theme = writable<Theme>(initial());

theme.subscribe((value) => {
  if (!browser) return;
  try {
    localStorage.setItem(KEY, value);
  } catch {
    // Storage blocked: the theme still applies, it just isn't remembered.
  }
  document.documentElement.dataset.theme = value;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', MANTLE[value]);
});

export function toggleTheme(): void {
  theme.update((t) => (t === 'mocha' ? 'latte' : 'mocha'));
}
