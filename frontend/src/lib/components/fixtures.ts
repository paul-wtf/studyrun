import type { ItemEntry } from '#lib/api/types.ts';

export function itemEntry(kind: ItemEntry['item']['kind'], extra: Partial<ItemEntry['item']> = {}): ItemEntry {
  return {
    n: 0,
    type: 'item',
    done: false,
    grading_unavailable: false,
    item: { id: 7, kind, source: '/api/booklets/3/pdf#page=12', ...extra }
  };
}
