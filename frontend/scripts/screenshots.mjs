// Captures every page of a build against fixture data, at desk and phone width, in each theme
// the build knows. Playwright is not a dependency; point NODE_PATH at a node_modules that has it,
// and have its Chromium installed (npx playwright install chromium):
//
//   pnpm build
//   NODE_PATH=<dir containing the playwright package> node scripts/screenshots.mjs build /tmp/shots
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { extname, join, resolve } from 'node:path';

const { chromium } = createRequire(import.meta.url)('playwright');

const [buildArg, outArg] = process.argv.slice(2);
if (!buildArg || !outArg) {
  console.error('usage: node scripts/screenshots.mjs <buildDir> <outDir>');
  process.exit(2);
}
const buildDir = resolve(buildArg);
const outDir = resolve(outArg);
mkdirSync(outDir, { recursive: true });

const VIEWPORTS = { desktop: { width: 1280, height: 800 }, phone: { width: 360, height: 780 } };
const themed = readFileSync(join(buildDir, 'index.html'), 'utf8').includes('studyrun-theme');
const THEMES = themed ? ['mocha', 'latte'] : [null];

const source = '/api/booklets/1/pdf#page=12';

const modules = [
  {
    id: 1,
    name: 'Betriebswirtschaftslehre',
    position: 0,
    subject_id: 1,
    booklets: [
      { id: 1, filename: 'BWL-Grundlagen.pdf', page_count: 84, status: 'ready', chapters: { pending: 1, generating: 1, verifying: 0, ready: 3, failed: 1, skipped: 0 } },
      { id: 2, filename: 'Kostenrechnung.pdf', page_count: 56, status: 'processing', chapters: { pending: 0, generating: 0, verifying: 0, ready: 0, failed: 0, skipped: 0 } }
    ]
  },
  { id: 2, name: 'Statistik', position: 1, subject_id: 2, booklets: [{ id: 3, filename: 'Deskriptive-Statistik.pdf', page_count: 40, status: 'ready', chapters: { pending: 0, generating: 0, verifying: 0, ready: 4, failed: 0, skipped: 0 } }] },
  { id: 3, name: 'Wirtschaftsrecht', position: 2, subject_id: null, booklets: [] }
];

const chapters = [
  { id: 11, booklet_id: 1, index: 0, title: 'Grundbegriffe der BWL', first_page: 1, last_page: 14, status: 'ready', error: null, waiting_reason: null, active_items: 18 },
  { id: 12, booklet_id: 1, index: 1, title: 'Unternehmensziele', first_page: 15, last_page: 28, status: 'generating', error: null, waiting_reason: null, active_items: 0 },
  { id: 13, booklet_id: 1, index: 2, title: 'Rechtsformen', first_page: 29, last_page: 44, status: 'failed', error: 'Die Prüfung hat zu viele Fragen verworfen.', waiting_reason: null, active_items: 0 },
  { id: 14, booklet_id: 1, index: 3, title: 'Standortwahl', first_page: 45, last_page: 60, status: 'pending', error: null, waiting_reason: 'Wartet auf das Tagesbudget für die Erzeugung.', active_items: 0 },
  { id: 15, booklet_id: 1, index: 4, title: 'Organisation', first_page: 61, last_page: 84, status: 'skipped', error: null, waiting_reason: null, active_items: 0 }
];

const costs = {
  today: { total: 0.42, by_feature: { generate: 0.18, verify: 0.06, grade: 0.15, tutor: 0.03 } },
  month: { total: 7.9, by_feature: { generate: 4.1, verify: 1.2, grade: 2.3, tutor: 0.3 } },
  cap_today: 1,
  remaining_today: 0.82,
  generation_budget_today: 0.5,
  generation_remaining_today: 0.26
};

const flags = [
  {
    id: 31, kind: 'mc', source_page: 18, reason: 'wrong', chapter_title: 'Grundbegriffe der BWL', source,
    payload: { prompt: 'Welcher Produktionsfaktor zählt zu den dispositiven Faktoren?', options: ['Werkstoffe', 'Betriebsmittel', 'Planung', 'Ausführende Arbeit'], answer_index: 2, explanation: 'Planung, Organisation und Kontrolle sind dispositive Faktoren.' }
  },
  {
    id: 32, kind: 'true_false', source_page: 22, reason: null, chapter_title: 'Grundbegriffe der BWL', source,
    payload: { statement: 'Das ökonomische Prinzip verlangt immer den maximalen Gewinn.', correct: false, explanation: 'Es verlangt Maximal- oder Minimalprinzip, nicht Gewinnmaximierung.' }
  }
];

const intro = {
  n: 0, type: 'intro', done: false, grading_unavailable: false,
  chapter: {
    id: 11, title: 'Grundbegriffe der BWL', source,
    summary: 'Das Kapitel klärt, womit sich die Betriebswirtschaftslehre beschäftigt und wie Betriebe Güter und Dienstleistungen erstellen.',
    concepts: [
      { term: 'Betrieb', explanation: 'planvoll organisierte Wirtschaftseinheit, die Güter erstellt' },
      { term: 'Ökonomisches Prinzip', explanation: 'mit gegebenen Mitteln den größten Erfolg erzielen, oder einen Erfolg mit den geringsten Mitteln' }
    ]
  }
};
const item = (n, view, extra = {}) => ({ n, type: 'item', done: false, grading_unavailable: false, model_answer: null, item: { source, ...view }, ...extra });
const mc = (n) => item(n, { id: 21, kind: 'mc', prompt: 'Welcher Produktionsfaktor zählt zu den dispositiven Faktoren?', options: ['Werkstoffe', 'Betriebsmittel', 'Planung', 'Ausführende Arbeit'] });
const tf = (n) => item(n, { id: 22, kind: 'true_false', statement: 'Das Minimalprinzip strebt ein festes Ergebnis mit möglichst geringem Mitteleinsatz an.' });
const cloze = (n) => item(n, { id: 24, kind: 'cloze', text: 'Das ___ strebt ein festes Ergebnis mit möglichst geringem Mitteleinsatz an.' });
const free = (n) =>
  item(n, { id: 23, kind: 'free', prompt: 'Erkläre den Unterschied zwischen Effektivität und Effizienz.' }, {
    grading_unavailable: true,
    model_answer: 'Effektivität fragt, ob ein Ziel erreicht wird. Effizienz fragt, wie günstig das Verhältnis von Ergebnis zu Aufwand ist.'
  });
const run = (...entries) => ({ id: 5, entries });
const done = (e) => ({ ...e, done: true });

const mcResult = (correct) => ({
  correct,
  expected: 'Planung',
  explanation: 'Planung, Organisation und Kontrolle sind dispositive Faktoren; Werkstoffe und Betriebsmittel sind Elementarfaktoren.'
});

const tfResult = (correct) => ({ correct, expected: 'Wahr', explanation: 'Beim Minimalprinzip ist das Ergebnis fest und der Einsatz wird minimiert.' });
const clozeResult = (correct) => ({ correct, expected: 'Minimalprinzip', explanation: 'Das Maximalprinzip hält dagegen den Einsatz fest.' });

const json = (body, status = 200) => ({ status, body });

// The browser clock is pinned to this day, and the plan fixtures are dated around it.
const TODAY = new Date('2026-11-24T10:00:00+01:00');

const attempt = (id, sitting, status) => ({ id, sitting, status });
const subject = (id, name, extra) => ({
  id, name, duration_minutes: 90, earliest_semester: '3a', recommended_semester: 3, not_before: null, pass_mark: 50,
  module_ids: [], attempts: [], introduced_share: 0, unlocked: false, ...extra
});
const subjects = [
  subject(1, 'Kosten- und Leistungsrechnung', { sittings: ['2026-12-20', '2027-03-21'], module_ids: [1], introduced_share: 0.86, unlocked: true }),
  subject(2, 'Statistik', { duration_minutes: 120, sittings: ['2026-12-20', '2027-02-14', '2027-05-16'], module_ids: [2], introduced_share: 0.4, attempts: [attempt(21, '2027-02-14', 'registered')] }),
  subject(3, 'Personalwirtschaft', { recommended_semester: 4, sittings: ['2027-01-17', '2027-03-21'], attempts: [attempt(31, '2027-03-21', 'planned')] }),
  subject(4, 'Wirtschaftsrecht', { sittings: ['2027-01-17', '2027-04-18'] }),
  subject(5, 'Marketing', { earliest_semester: '6a', recommended_semester: 6, sittings: ['2027-01-17', '2027-05-16'] }),
  subject(6, 'Grundlagen der BWL', { sittings: ['2026-06-14', '2026-11-15', '2027-02-14'], attempts: [attempt(62, '2026-06-14', 'planned'), attempt(61, '2026-11-15', 'registered')] }),
  subject(7, 'Wirtschaftsmathematik', { sittings: ['2026-10-11', '2027-01-17'], attempts: [attempt(71, '2026-06-14', 'failed'), attempt(72, '2026-10-11', 'passed')] })
];
const semesters = [
  { label: '3a', starts_on: '2026-04-01' },
  { label: '3b', starts_on: '2026-10-01' },
  { label: '4a', starts_on: '2027-04-01' }
];
const entry = (s, state, extra = {}) => ({
  subject_id: s.id, subject_name: s.name, state, sitting: null, register_by: null, feasible: true, study_from: null, study_until: null, ...extra
});
const plan = {
  entries: [
    entry(subjects[0], 'open', { sitting: '2026-12-20', register_by: '2026-11-29', study_from: '2026-11-24', study_until: '2026-12-14' }),
    entry(subjects[1], 'registered', { sitting: '2027-02-14', study_from: '2026-12-14', study_until: '2027-01-26' }),
    entry(subjects[2], 'planned', { sitting: '2027-03-21', register_by: '2027-02-28', feasible: false, study_from: '2027-01-26', study_until: '2027-03-30' }),
    entry(subjects[3], 'no_material'),
    entry(subjects[4], 'not_plannable'),
    entry(subjects[5], 'needs_result', { sitting: '2026-11-15' }),
    entry(subjects[6], 'passed', { sitting: '2026-10-11' })
  ],
  conflicts: [
    { subject_id: 3, subject_name: 'Personalwirtschaft', kind: 'squeezes_other', message: 'Dein Termin für Personalwirtschaft macht die Vorbereitung auf Statistik zu knapp.' },
    { subject_id: 4, subject_name: 'Wirtschaftsrecht', kind: 'no_material', message: 'Stoff fehlt: Für dieses Fach gibt es noch kein Heft.' },
    { subject_id: 5, subject_name: 'Marketing', kind: 'missing_semester', message: 'Für Semester 6a fehlt das Startdatum.' }
  ],
  order: [1, 2, 3],
  pace_per_day: 6.4
};
const progress = {
  week: {
    days: ['23', '24', '25', '26', '27', '28', '29'].map((d, i) => ({ date: `2026-11-${d}`, done: i < 2 })),
    goal: 4,
    done_count: 2
  },
  subjects: subjects.map((s) => ({ subject_id: s.id, introduced: s.introduced_share, solid: s.introduced_share / 2 }))
};
const mocks = [
  { id: 14, started_at: '2026-11-21T17:05:00Z', deadline: '2026-11-21T18:35:00Z', finished_at: '2026-11-21T18:21:00Z', score: 63, passed: true },
  { id: 11, started_at: '2026-11-12T18:40:00Z', deadline: '2026-11-12T20:10:00Z', finished_at: '2026-11-12T20:09:00Z', score: 44, passed: false }
];
const openRuns = [
  { id: 41, subject_id: 1, subject_name: subjects[0].name, created_at: '2026-11-24T07:40:00Z', open_items: 3 },
  { id: 37, subject_id: 2, subject_name: subjects[1].name, created_at: '2026-11-20T20:15:00Z', open_items: 1 }
];
const openMock = { id: 15, started_at: '2026-11-24T08:00:00Z', deadline: '2026-11-24T09:30:00Z', finished_at: null, score: null, passed: null };

const mockSource = (page) => `/api/booklets/1/pdf#page=${page}`;
const mockItems = [
  { id: 21, kind: 'mc', prompt: 'Welcher Produktionsfaktor zählt zu den dispositiven Faktoren?', options: ['Werkstoffe', 'Betriebsmittel', 'Planung', 'Ausführende Arbeit'] },
  { id: 22, kind: 'true_false', statement: 'Das Minimalprinzip strebt ein festes Ergebnis mit möglichst geringem Mitteleinsatz an.' },
  { id: 24, kind: 'cloze', text: 'Das ___ strebt ein festes Ergebnis mit möglichst geringem Mitteleinsatz an.' },
  { id: 23, kind: 'free', prompt: 'Erkläre den Unterschied zwischen Effektivität und Effizienz.' },
  { id: 25, kind: 'mc', prompt: 'Welche Kostenart ändert sich mit der Ausbringungsmenge?', options: ['Fixkosten', 'Variable Kosten', 'Sprungfixe Kosten'] },
  { id: 26, kind: 'true_false', statement: 'Gemeinkosten lassen sich einem Kostenträger direkt zurechnen.' },
  { id: 27, kind: 'free', prompt: 'Wozu dient der Betriebsabrechnungsbogen?' },
  { id: 28, kind: 'cloze', text: 'Kosten, die einem Produkt direkt zugerechnet werden, heißen ___.' }
];
const mockAnswers = [{ choice: 1 }, { value: true }, null, { text: 'Effektivität heißt, das richtige Ziel zu erreichen; Effizienz, es mit wenig Aufwand zu erreichen.' }, { choice: 1 }, null, null, null];
const review = (extra) => ({ score: 0, correct: false, expected: null, explanation: null, feedback: null, missing: [], model_answer: null, grading_unavailable: false, ...extra });
const mockReviews = [
  review({ expected: 'Planung', explanation: 'Planung, Organisation und Kontrolle sind dispositive Faktoren; Betriebsmittel sind Elementarfaktoren.' }),
  review({ score: 100, correct: true, expected: 'Wahr', explanation: 'Beim Minimalprinzip ist das Ergebnis fest und der Einsatz wird minimiert.' }),
  review({ expected: 'Minimalprinzip', explanation: 'Das Maximalprinzip hält dagegen den Einsatz fest.' }),
  review({ score: 80, correct: true, feedback: 'Beide Begriffe sind richtig getrennt.', missing: ['ein Beispiel'], model_answer: 'Effektivität fragt, ob ein Ziel erreicht wird. Effizienz fragt, wie günstig das Verhältnis von Ergebnis zu Aufwand ist.' }),
  review({ score: 100, correct: true, expected: 'Variable Kosten', explanation: 'Variable Kosten steigen und fallen mit der Menge.' }),
  review({ expected: 'Falsch', explanation: 'Gemeinkosten werden über Zuschläge verteilt, Einzelkosten direkt zugerechnet.' }),
  review({ score: null, correct: null, grading_unavailable: true, model_answer: 'Er verteilt die Gemeinkosten auf die Kostenstellen und liefert die Zuschlagssätze.' }),
  review({ score: 100, correct: true, expected: 'Einzelkosten', explanation: 'Einzelkosten lassen sich dem Kostenträger direkt zurechnen.' })
];
const mockAnswersDone = [...mockAnswers.slice(0, 6), { text: 'Damit verteilt man die Gemeinkosten auf die Kostenstellen.' }, { text: 'Einzelkosten' }];
const longAnswer = 'Der Betriebsabrechnungsbogen verteilt die Gemeinkosten, die sich keinem Produkt direkt zurechnen lassen, mit Schlüsseln auf die Kostenstellen. Aus den Summen je Stelle ergeben sich die Zuschlagssätze für Material, Fertigung, Verwaltung und Vertrieb. Mit diesen Sätzen rechnet die Kalkulation die Gemeinkosten auf die Kostenträger. Außerdem zeigt er, wo im Betrieb welche Kosten entstehen, und erlaubt so eine Kontrolle der Kostenstellen über die Zeit.';
const minutes = (m) => new Date(TODAY.getTime() + m * 60_000).toISOString();
const mockExam = (extra = {}, finished = false) => ({
  id: 20, subject_id: 1, subject_name: subjects[0].name, started_at: minutes(-43), deadline: minutes(47),
  finished_at: finished ? minutes(-2) : null, finished, finishing: false, expired: false, now: TODAY.toISOString(),
  entries: mockItems.map((item, n) => {
    const answer = (finished ? mockAnswersDone : mockAnswers)[n];
    return { n, answered: answer !== null, answer, item, source: finished ? mockSource(12 + n) : null, review: finished ? mockReviews[n] : null };
  }),
  result: finished
    ? {
        score: 61, passed: true, pass_mark: 50, pending_self_rating: 1,
        chapters: [
          { chapter_id: 11, title: 'Grundbegriffe der BWL', items: 4, score: 70 },
          { chapter_id: 16, title: 'Kostenartenrechnung', items: 4, score: 50 }
        ]
      }
    : null,
  ...extra
});

function base(method, path) {
  if (method === 'GET' && path === '/api/modules') return json(modules);
  if (method === 'GET' && path === '/api/costs') return json(costs);
  if (method === 'GET' && path === '/api/flags') return json(flags);
  if (method === 'GET' && /^\/api\/modules\/\d+\/chapters$/.test(path)) return json(chapters);
  if (method === 'GET' && path === '/api/runs/current') return json({ run: run(done(intro), mc(1)) });
  if (method === 'GET' && path.startsWith('/api/runs/current?subject_id=')) return json({ run: current.subjectRun ? run(done(intro), mc(1)) : null });
  if (method === 'GET' && path === '/api/runs/open') return json(current.openRuns ?? []);
  if (method === 'GET' && path === '/api/subjects') return json(subjects);
  if (method === 'GET' && /^\/api\/subjects\/\d+$/.test(path)) return json(subjects.find((s) => `/api/subjects/${s.id}` === path));
  if (method === 'GET' && /^\/api\/subjects\/\d+\/mocks$/.test(path)) return json(current.openMock ? [openMock, ...mocks] : mocks);
  if (method === 'GET' && path === `/api/mock/${openMock.id}`) return json({ ...openMock, subject_id: 1, subject_name: subjects[0].name, finished: false, finishing: !current.expiredMock, expired: true, entries: [], result: null });
  if (method === 'GET' && path === '/api/semesters') return json(semesters);
  if (method === 'GET' && path === '/api/plan') return json(plan);
  if (method === 'GET' && path === '/api/progress') return json(progress);
  return undefined;
}

const tabTo = (name) => async (page) => {
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    if ((await page.evaluate(() => document.activeElement?.textContent?.trim())) === name) return;
  }
  throw new Error(`could not tab to ${name}`);
};

const answerCloze = (text) => async (page) => {
  await page.getByRole('textbox', { name: 'Antwort' }).fill(text);
  await page.getByRole('button', { name: 'Prüfen' }).click();
};

const SCENARIOS = [
  { name: 'home', path: '/', wait: 'a[href="/run"]' },
  { name: 'home-open-runs', path: '/', openRuns, wait: 'text=Offene Fach-Runs' },
  { name: 'nav-focus', path: '/costs', ready: 'text=Dieser Monat', act: tabTo('Module'), wait: 'text=Dieser Monat' },
  { name: 'run-intro', path: '/run', runs: [run(intro, mc(1))], wait: 'text=Neues Kapitel' },
  {
    name: 'run-mc-wrong', path: '/run', runs: [run(mc(0), tf(1))], answer: mcResult(false),
    act: (page) => page.getByRole('button', { name: 'Betriebsmittel' }).click(), wait: 'text=Richtige Antwort'
  },
  {
    name: 'run-mc-correct', path: '/run', runs: [run(mc(0), tf(1))], answer: mcResult(true),
    act: (page) => page.getByRole('button', { name: 'Planung' }).click(), wait: 'text=Richtig'
  },
  { name: 'run-mc-focus', path: '/run', runs: [run(mc(0), tf(1))], act: tabTo('Betriebsmittel'), wait: 'text=Werkstoffe' },
  {
    name: 'run-tf-correct', path: '/run', runs: [run(tf(0))], answer: tfResult(true),
    act: (page) => page.getByRole('button', { name: 'Wahr' }).click(), wait: 'h2:text-is("Richtig")'
  },
  {
    name: 'run-tf-wrong', path: '/run', runs: [run(tf(0))], answer: tfResult(false),
    act: (page) => page.getByRole('button', { name: 'Falsch' }).click(), wait: 'text=Richtige Antwort'
  },
  { name: 'run-cloze-correct', path: '/run', runs: [run(cloze(0))], answer: clozeResult(true), act: answerCloze('Minimalprinzip'), wait: 'h2:text-is("Richtig")' },
  { name: 'run-cloze-wrong', path: '/run', runs: [run(cloze(0))], answer: clozeResult(false), act: answerCloze('Maximalprinzip'), wait: 'text=Richtige Antwort' },
  { name: 'run-free-unavailable', path: '/run', runs: [run(free(0))], wait: 'text=Wusste ich nicht' },
  {
    name: 'run-stale', path: '/run', runs: [run(mc(0), tf(1)), run(done(mc(0)), tf(1))], answer: json({ detail: 'Schon beantwortet' }, 409),
    act: (page) => page.getByRole('button', { name: 'Werkstoffe' }).click(), wait: 'text=anderen Gerät'
  },
  { name: 'run-summary', path: '/run', runs: [run(done(intro), done(mc(1)))], wait: 'text=Geschafft' },
  { name: 'session-expired', path: '/modules', expired: true, wait: 'text=Sitzung abgelaufen' },
  { name: 'modules', path: '/modules', wait: 'a:text-is("Statistik")' },
  { name: 'module-detail', path: '/modules/1', wait: 'text=Rechtsformen' },
  { name: 'flags', path: '/flags', wait: 'text=Im Heft nachlesen' },
  { name: 'costs', path: '/costs', wait: 'text=Dieser Monat' },
  { name: 'plan', path: '/plan', wait: 'text=Termine' },
  { name: 'subjects', path: '/subjects', wait: 'text=Semesterstarts' },
  { name: 'subject', path: '/subjects/1', wait: 'text=Bosskämpfe' },
  { name: 'subject-open', path: '/subjects/1', subjectRun: true, openMock: true, wait: 'text=Auswertung abschließen' },
  { name: 'subject-results', path: '/subjects/7', wait: 'text=Prüfungsversuche' },
  { name: 'subject-attempts', path: '/subjects/6', wait: 'text=Verwerfen' },
  { name: 'subject-expired', path: '/subjects/1', openMock: true, expiredMock: true, wait: 'text=Abgelaufen' },
  { name: 'mock-exam', path: '/mock/20', mock: mockExam(), wait: '[role=timer]' },
  { name: 'mock-free', path: '/mock/20', mock: mockExam(), ready: '[role=timer]', act: (page) => page.getByRole('button', { name: 'Frage 4, beantwortet' }).click(), wait: 'textarea' },
  {
    name: 'mock-overview-tap', path: '/mock/20', mock: mockExam(), ready: '[role=timer]',
    act: async (page) => {
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.getByRole('button', { name: 'Frage 7, offen' }).click();
    },
    wait: 'text=Betriebsabrechnungsbogen'
  },
  {
    name: 'mock-long-answer', path: '/mock/20', mock: mockExam(), ready: '[role=timer]',
    act: async (page) => {
      await page.getByRole('button', { name: 'Frage 7, offen' }).click();
      await page.getByRole('textbox', { name: 'Antwort' }).fill(longAnswer);
      await page.getByRole('textbox', { name: 'Antwort' }).evaluate((el) => (el.style.height = `${el.scrollHeight}px`));
      await page.evaluate(() => window.scrollBy(0, 520));
    },
    wait: 'textarea'
  },
  { name: 'mock-low-time', path: '/mock/20', mock: mockExam({ deadline: minutes(3.5) }), ready: '[role=timer]', act: (page) => page.getByRole('button', { name: 'Frage 3, offen' }).click(), wait: 'input[type=text]' },
  { name: 'mock-confirm', path: '/mock/20', mock: mockExam(), ready: '[role=timer]', act: (page) => page.getByRole('button', { name: 'Abgeben', exact: true }).click(), wait: 'text=Jetzt abgeben' },
  { name: 'mock-finishing', path: '/mock/20', mock: mockExam({ deadline: minutes(-1), expired: true }), finish: 'hang', waitUntil: 'load', wait: 'text=Wird ausgewertet' },
  { name: 'mock-stalled', path: '/mock/20', mock: mockExam({ finishing: true }), finish: json({ detail: 'Gateway Timeout' }, 504), wait: 'text=Auswertung fortsetzen' },
  { name: 'mock-result', path: '/mock/20', mock: mockExam({}, true), wait: 'text=Wusste ich nicht' },
  {
    name: 'plan-choose', path: '/plan', ready: 'text=Termine',
    act: (page) => page.getByRole('article', { name: 'Kosten- und Leistungsrechnung' }).getByRole('button', { name: 'Anderen Termin wählen' }).click(),
    wait: 'text=Termin übernehmen'
  },
  { name: 'run-subject', path: '/run?subject=1', runs: [{ ...run(mc(0), tf(1)), subject_id: 1, subject_name: subjects[0].name }], wait: 'text=Fach-Run' }
];

let current = SCENARIOS[0];
let runCalls = 0;

function api(method, path) {
  if (current.expired) return { status: 401, body: { detail: 'unauthorized' } };
  if (method === 'POST' && path === '/api/runs') {
    const runs = current.runs ?? [run(mc(0))];
    return json(runs[Math.min(runCalls++, runs.length - 1)]);
  }
  if (current.mock && path === '/api/mock/20') return json(current.mock);
  if (current.mock && method === 'POST' && /^\/api\/mock\/20\/answers\/\d+$/.test(path)) return json({ n: Number(path.split('/').pop()), answered: true });
  if (current.mock && method === 'POST' && path === '/api/mock/20/finish') return current.finish ?? json(mockExam({}, true));
  if (method === 'POST' && /\/entries\/\d+\/answer$/.test(path)) {
    const a = current.answer ?? mcResult(true);
    return 'status' in a ? a : json(a);
  }
  if (method === 'POST' && /\/finish$/.test(path)) {
    return json({ answered: 9, correct: 7, chapters_introduced: ['Grundbegriffe der BWL'], due_tomorrow: 4 });
  }
  return base(method, path) ?? json({ detail: `no fixture for ${method} ${path}` }, 404);
}

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json', '.json': 'application/json' };

const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/api/')) {
    const reply = api(req.method, url.pathname + url.search);
    if (reply === 'hang') return;
    const { status, body } = reply;
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
    return;
  }
  let file = join(buildDir, decodeURIComponent(url.pathname));
  if (!file.startsWith(buildDir) || !existsSync(file) || statSync(file).isDirectory()) file = join(buildDir, 'index.html');
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(res);
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const origin = `http://127.0.0.1:${server.address().port}`;
console.log(`serving ${buildDir} on ${origin}, themes: ${THEMES.map((t) => t ?? 'default').join(', ')}`);

const browser = await chromium.launch();
try {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    for (const theme of THEMES) {
      for (const scenario of SCENARIOS) {
        current = scenario;
        runCalls = 0;
        const context = await browser.newContext({ viewport, deviceScaleFactor: 2 });
        await context.clock.setFixedTime(TODAY);
        if (theme) await context.addInitScript((t) => localStorage.setItem('studyrun-theme', t), theme);
        const page = await context.newPage();
        await page.goto(origin + scenario.path, { waitUntil: scenario.waitUntil ?? 'networkidle' });
        if (scenario.act) {
          await page.locator(scenario.ready ?? 'main button, main a').first().waitFor();
          await scenario.act(page);
        }
        await page.locator(scenario.wait).first().waitFor({ timeout: 5000 });
        await page.waitForTimeout(300);
        const stem = [scenario.name, vpName, theme].filter(Boolean).join('-');
        await page.screenshot({ path: join(outDir, `${stem}.png`) });
        const tall = await page.evaluate(() => document.documentElement.scrollHeight > innerHeight);
        if (tall) await page.screenshot({ path: join(outDir, `${stem}-full.png`), fullPage: true });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        console.log(`${stem}${tall ? ' (+full)' : ''}${overflow > 0 ? ` OVERFLOW ${overflow}px` : ''}`);
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
  server.closeAllConnections();
  server.close();
}
