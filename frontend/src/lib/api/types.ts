import type { ItemKind } from './models';

export type { ItemKind };

export interface IntroEntry {
  n: number;
  type: 'intro';
  done: boolean;
  grading_unavailable: boolean;
  chapter: { id: number; title: string; summary: string; concepts: string[]; source: string };
}

export interface ItemEntry {
  n: number;
  type: 'item';
  done: boolean;
  grading_unavailable: boolean;
  item: {
    id: number;
    kind: ItemKind;
    source: string;
    prompt?: string;
    options?: string[];
    statement?: string;
    text?: string;
  };
}

export type RunEntry = IntroEntry | ItemEntry;

export interface Run {
  id: number;
  entries: RunEntry[];
}

export interface ObjectiveResult {
  correct: boolean;
  expected: string;
  explanation: string;
}

export interface FreeResult {
  score: number;
  feedback: string;
  missing: string[];
  model_answer: string;
}

export interface GradingUnavailable {
  grading_unavailable: true;
  reason: string;
  model_answer: string;
}

export interface RunSummaryData {
  answered: number;
  correct: number;
  chapters_introduced: string[];
  due_tomorrow: number;
}
