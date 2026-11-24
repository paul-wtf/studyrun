import { describe, expect, it } from 'vitest';
import { addDays, countdown, deDate, deDateTime, monthLabel, today } from './dates.ts';

describe('dates', () => {
  it('takes today from the Berlin calendar', () => {
    expect(today(new Date('2026-11-24T23:30:00Z'))).toBe('2026-11-25');
    expect(today(new Date('2026-07-01T21:59:00Z'))).toBe('2026-07-01');
  });

  it('adds days across a month and a clock change', () => {
    expect(addDays('2026-10-20', 14)).toBe('2026-11-03');
    expect(addDays('2027-03-27', 2)).toBe('2027-03-29');
  });

  it('writes dates the German way', () => {
    expect(deDate('2026-11-08')).toBe('08.11.2026');
    expect(monthLabel('2027-01-31')).toBe('Januar 2027');
    expect(deDateTime('2026-11-24T22:45:00Z')).toBe('24.11.2026, 23:45');
  });

  it('counts down in days', () => {
    expect(countdown('2026-11-24', '2026-11-24')).toBe('heute');
    expect(countdown('2026-11-24', '2026-11-25')).toBe('morgen');
    expect(countdown('2026-11-24', '2026-12-06')).toBe('in 12 Tagen');
  });
});
