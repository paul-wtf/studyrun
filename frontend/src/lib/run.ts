export const RUN_MARKER = 'studyrun.run';

export function localDate(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function markRunStarted(id: number): void {
  localStorage.setItem(RUN_MARKER, JSON.stringify({ id, date: localDate() }));
}

export function clearRunMarker(): void {
  localStorage.removeItem(RUN_MARKER);
}

export function hasRunToday(): boolean {
  try {
    const marker = JSON.parse(localStorage.getItem(RUN_MARKER) ?? 'null');
    return marker?.date === localDate();
  } catch {
    return false;
  }
}

export function euro(n: number): string {
  return n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
