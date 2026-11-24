<script lang="ts">
  import { untrack } from 'svelte';
  import { clock } from '#lib/mock.ts';

  let { deadline, offset = 0, onexpire }: { deadline: string; offset?: number; onexpire: () => void } = $props();

  let now = $state(Date.now());
  let fired = false;
  const left = $derived(Math.max(0, Date.parse(deadline) - (now + offset)));

  $effect(() => {
    const tick = setInterval(() => (now = Date.now()), 250);
    return () => clearInterval(tick);
  });

  $effect(() => {
    if (left > 0 || fired) return;
    fired = true;
    untrack(onexpire);
  });
</script>

<div class="timer" class:low={left <= 5 * 60_000} role="timer" aria-label="Restzeit">{clock(left)}</div>

<style>
  .timer {
    font-family: var(--font-display);
    font-size: 1.35rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }
  .low { color: var(--error); }
</style>
