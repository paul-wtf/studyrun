import type { ClozeEntry, FreeEntry, McEntry, TrueFalseEntry } from '#lib/api/models.ts';

const base = { n: 0, type: 'item' as const, done: false, grading_unavailable: false };
const source = '/api/booklets/3/pdf#page=12';

export function mcEntry(extra: Partial<McEntry['item']> = {}): McEntry {
  return { ...base, item: { id: 7, kind: 'mc', prompt: '', options: [], source, ...extra } };
}

export function trueFalseEntry(extra: Partial<TrueFalseEntry['item']> = {}): TrueFalseEntry {
  return { ...base, item: { id: 7, kind: 'true_false', statement: '', source, ...extra } };
}

export function clozeEntry(extra: Partial<ClozeEntry['item']> = {}): ClozeEntry {
  return { ...base, item: { id: 7, kind: 'cloze', text: '', source, ...extra } };
}

export function freeEntry(extra: Partial<FreeEntry['item']> = {}): FreeEntry {
  return { ...base, item: { id: 7, kind: 'free', prompt: '', source, ...extra } };
}
