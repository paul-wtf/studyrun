import type { MockEntry, MockExam, MockReview } from '#lib/api/models.ts';

export const T0 = new Date('2026-11-24T19:00:00Z');
export const at = (minutes: number) => new Date(T0.getTime() + minutes * 60_000).toISOString();

export function review(extra: Partial<MockReview> = {}): MockReview {
  return {
    score: 0,
    correct: false,
    expected: null,
    explanation: null,
    feedback: null,
    missing: [],
    model_answer: null,
    grading_unavailable: false,
    ...extra
  };
}

export const entries = (): MockEntry[] => [
  {
    n: 0,
    answered: false,
    answer: null,
    item: { id: 21, kind: 'mc', prompt: 'Welcher Faktor ist dispositiv?', options: ['Werkstoffe', 'Planung'] },
    source: null,
    review: null
  },
  {
    n: 1,
    answered: false,
    answer: null,
    item: { id: 22, kind: 'true_false', statement: 'Wasser ist nass.' },
    source: null,
    review: null
  },
  {
    n: 2,
    answered: false,
    answer: null,
    item: { id: 23, kind: 'cloze', text: 'Das ___ hält das Ergebnis fest.' },
    source: null,
    review: null
  },
  {
    n: 3,
    answered: false,
    answer: null,
    item: { id: 24, kind: 'free', prompt: 'Erkläre Effizienz.' },
    source: null,
    review: null
  }
];

export function exam(extra: Partial<MockExam> = {}): MockExam {
  return {
    id: 7,
    subject_id: 1,
    subject_name: 'Rechnungswesen',
    started_at: at(0),
    deadline: at(90),
    finished_at: null,
    finished: false,
    finishing: false,
    expired: false,
    now: new Date().toISOString(),
    entries: entries(),
    result: null,
    ...extra
  };
}

export function finishedExam(extra: Partial<MockExam> = {}): MockExam {
  const [mc, tf, cloze, free] = entries();
  return exam({
    finished_at: at(80),
    finished: true,
    entries: [
      {
        ...mc,
        answered: true,
        answer: { choice: 0 },
        source: '/api/booklets/1/pdf#page=3',
        review: review({ expected: 'Planung', explanation: 'Planung ist ein dispositiver Faktor.' })
      },
      {
        ...tf,
        answered: true,
        answer: { value: true },
        source: '/api/booklets/1/pdf#page=4',
        review: review({ score: 100, correct: true, expected: 'Wahr', explanation: 'Ja.' })
      },
      { ...cloze, source: '/api/booklets/1/pdf#page=5', review: review({ expected: 'Minimalprinzip' }) },
      {
        ...free,
        answered: true,
        answer: { text: 'Ergebnis durch Aufwand.' },
        source: '/api/booklets/1/pdf#page=6',
        review: review({
          score: null,
          correct: null,
          model_answer: 'Effizienz ist das Verhältnis von Ergebnis zu Aufwand.',
          grading_unavailable: true
        })
      }
    ],
    result: {
      score: 25,
      passed: false,
      pass_mark: 50,
      pending_self_rating: 1,
      chapters: [
        { chapter_id: 5, title: 'Grundbegriffe', items: 2, score: 50 },
        { chapter_id: 6, title: 'Prinzipien', items: 2, score: 0 }
      ]
    },
    ...extra
  });
}
