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
    booklets: [
      { id: 1, filename: 'BWL-Grundlagen.pdf', page_count: 84, status: 'ready', chapters: { pending: 1, generating: 1, verifying: 0, ready: 3, failed: 1, skipped: 0 } },
      { id: 2, filename: 'Kostenrechnung.pdf', page_count: 56, status: 'processing', chapters: { pending: 0, generating: 0, verifying: 0, ready: 0, failed: 0, skipped: 0 } }
    ]
  },
  { id: 2, name: 'Statistik', position: 1, booklets: [{ id: 3, filename: 'Deskriptive-Statistik.pdf', page_count: 40, status: 'ready', chapters: { pending: 0, generating: 0, verifying: 0, ready: 4, failed: 0, skipped: 0 } }] },
  { id: 3, name: 'Wirtschaftsrecht', position: 2, booklets: [] }
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

const json = (body, status = 200) => ({ status, body });

function base(method, path) {
  if (method === 'GET' && path === '/api/modules') return json(modules);
  if (method === 'GET' && path === '/api/costs') return json(costs);
  if (method === 'GET' && path === '/api/flags') return json(flags);
  if (method === 'GET' && /^\/api\/modules\/\d+\/chapters$/.test(path)) return json(chapters);
  if (method === 'GET' && path === '/api/runs/current') return json({ run: run(done(intro), mc(1)) });
  return undefined;
}

const tabTo = (name) => async (page) => {
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    if ((await page.evaluate(() => document.activeElement?.textContent?.trim())) === name) return;
  }
  throw new Error(`could not tab to ${name}`);
};

const SCENARIOS = [
  { name: 'home', path: '/', wait: 'a[href="/run"]' },
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
  { name: 'run-free-unavailable', path: '/run', runs: [run(free(0))], wait: 'text=Wusste ich nicht' },
  {
    name: 'run-stale', path: '/run', runs: [run(mc(0), tf(1)), run(done(mc(0)), tf(1))], answer: json({ detail: 'Schon beantwortet' }, 409),
    act: (page) => page.getByRole('button', { name: 'Werkstoffe' }).click(), wait: 'text=anderen Gerät'
  },
  { name: 'run-summary', path: '/run', runs: [run(done(intro), done(mc(1)))], wait: 'text=Geschafft' },
  { name: 'session-expired', path: '/modules', expired: true, wait: 'text=Sitzung abgelaufen' },
  { name: 'modules', path: '/modules', wait: 'text=Statistik' },
  { name: 'module-detail', path: '/modules/1', wait: 'text=Rechtsformen' },
  { name: 'flags', path: '/flags', wait: 'text=Im Heft nachlesen' },
  { name: 'costs', path: '/costs', wait: 'text=Dieser Monat' }
];

let current = SCENARIOS[0];
let runCalls = 0;

function api(method, path) {
  if (current.expired) return { status: 401, body: { detail: 'unauthorized' } };
  if (method === 'POST' && path === '/api/runs') {
    const runs = current.runs ?? [run(mc(0))];
    return json(runs[Math.min(runCalls++, runs.length - 1)]);
  }
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
    const { status, body } = api(req.method, url.pathname);
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
        if (theme) await context.addInitScript((t) => localStorage.setItem('studyrun-theme', t), theme);
        const page = await context.newPage();
        await page.goto(origin + scenario.path, { waitUntil: 'networkidle' });
        if (scenario.act) {
          await page.locator('main button, main a').first().waitFor();
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
  server.close();
}
