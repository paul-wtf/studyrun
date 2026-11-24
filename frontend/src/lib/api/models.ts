import type { components } from './schema';

type S = components['schemas'];

export type Module = S['ModuleOut'];
export type Booklet = S['BookletOut'];
export type Chapter = S['ChapterOut'];
export type Costs = S['CostsOut'];
export type Period = S['Period'];
export type Flag = S['FlagOut'];
export type FlagReason = S['FlagReason'];
export type ItemKind = S['ItemKind'];
export type BookletStatus = Booklet['status'];
export type Run = S['RunOut'];
export type RunEntry = Run['entries'][number];
export type IntroEntry = S['IntroEntryOut'];
export type ItemEntry = S['ItemEntryOut'];
type ItemView = ItemEntry['item'];
type ViewEntry<K extends ItemView['kind']> = Omit<ItemEntry, 'item'> & {
  item: Extract<ItemView, { kind: K }>;
};
export type McEntry = ViewEntry<'mc'>;
export type TrueFalseEntry = ViewEntry<'true_false'>;
export type ClozeEntry = ViewEntry<'cloze'>;
export type FreeEntry = ViewEntry<'free'>;
export type ObjectiveResult = S['ObjectiveResultOut'];
export type FreeResult = S['FreeResultOut'];
export type GradingUnavailable = S['GradingUnavailableOut'];
export type RunSummaryData = S['RunSummaryOut'];
