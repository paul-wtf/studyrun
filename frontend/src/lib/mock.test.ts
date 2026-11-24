import { describe, expect, it } from 'vitest';
import { clock } from './mock';

describe('clock', () => {
  it('shows minutes and seconds below an hour and hours above', () => {
    expect(clock(0)).toBe('00:00');
    expect(clock(2_000)).toBe('00:02');
    expect(clock(1_500)).toBe('00:02');
    expect(clock(47 * 60_000)).toBe('47:00');
    expect(clock(90 * 60_000)).toBe('1:30:00');
    expect(clock(3_600_000 - 1)).toBe('1:00:00');
  });
});
