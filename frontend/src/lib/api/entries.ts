import type { ClozeEntry, FreeEntry, ItemEntry, McEntry, TrueFalseEntry } from './models';

export const isMc = (e: ItemEntry): e is McEntry => e.item.kind === 'mc';
export const isTrueFalse = (e: ItemEntry): e is TrueFalseEntry => e.item.kind === 'true_false';
export const isCloze = (e: ItemEntry): e is ClozeEntry => e.item.kind === 'cloze';
export const isFree = (e: ItemEntry): e is FreeEntry => e.item.kind === 'free';
