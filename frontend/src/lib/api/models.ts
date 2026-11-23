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
