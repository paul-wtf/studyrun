const TIME_ZONE = 'Europe/Berlin';

const isoDay = new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
const month = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', month: 'long', year: 'numeric' });
const weekday = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' });

const stamp = new Intl.DateTimeFormat('de-DE', {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit'
});

const utc = (iso: string) => new Date(`${iso}T00:00:00Z`);

export function today(now = new Date()): string {
  return isoDay.format(now);
}

export function addDays(iso: string, days: number): string {
  const d = utc(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysBetween(from: string, to: string): number {
  return Math.round((utc(to).getTime() - utc(from).getTime()) / 86_400_000);
}

export function deDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export function deShort(iso: string): string {
  const [, m, d] = iso.split('-');
  return `${d}.${m}.`;
}

export function monthLabel(iso: string): string {
  return month.format(utc(iso));
}

export function weekdayShort(iso: string): string {
  return weekday.format(utc(iso)).replace('.', '');
}

export function countdown(from: string, to: string): string {
  const days = daysBetween(from, to);
  if (days === 0) return 'heute';
  if (days === 1) return 'morgen';
  return `in ${days} Tagen`;
}

export function deDateTime(instant: string): string {
  return stamp.format(new Date(instant));
}
