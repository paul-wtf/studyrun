import type { GivenAnswer, MockItem } from '#lib/api/models.ts';

const pad = (n: number) => String(n).padStart(2, '0');

export function clock(ms: number): string {
  const total = Math.ceil(Math.max(0, ms) / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export function answerText(item: MockItem, answer: GivenAnswer | null): string | null {
  if (!answer) return null;
  if (item.kind === 'mc') return answer.choice == null ? null : (item.options[answer.choice] ?? null);
  if (item.kind === 'true_false') return answer.value == null ? null : answer.value ? 'Wahr' : 'Falsch';
  return answer.text?.trim() ? answer.text : null;
}

export function questionText(item: MockItem): string {
  if (item.kind === 'true_false') return item.statement;
  if (item.kind === 'cloze') return item.text;
  return item.prompt;
}

export const KIND_LABEL: Record<MockItem['kind'], string> = {
  mc: 'Auswahl',
  true_false: 'Wahr oder falsch?',
  cloze: 'Lücke füllen',
  free: 'Freie Antwort'
};
