<script lang="ts">
  import { untrack } from 'svelte';
  import type { GivenAnswer, MockItem } from '#lib/api/models.ts';
  import { KIND_LABEL } from '#lib/mock.ts';

  let {
    item,
    answer,
    disabled = false,
    onanswer
  }: { item: MockItem; answer: GivenAnswer | null; disabled?: boolean; onanswer: (answer: GivenAnswer, typed: boolean) => void } =
    $props();

  let text = $state(untrack(() => answer?.text ?? ''));
</script>

<div class="card stack">
  {#if item.kind !== 'mc'}<p class="muted">{KIND_LABEL[item.kind]}</p>{/if}
  {#if item.kind === 'mc'}
    <h2>{item.prompt}</h2>
    <div class="options">
      {#each item.options as option, i}
        <button
          class="option"
          class:picked={answer?.choice === i}
          aria-pressed={answer?.choice === i}
          {disabled}
          onclick={() => onanswer({ choice: i }, false)}>{option}</button
        >
      {/each}
    </div>
  {:else if item.kind === 'true_false'}
    <h2>{item.statement}</h2>
    <div class="pair">
      {#each [[true, 'Wahr'], [false, 'Falsch']] as const as [value, label] (label)}
        <button
          class="option"
          class:picked={answer?.value === value}
          aria-pressed={answer?.value === value}
          {disabled}
          onclick={() => onanswer({ value }, false)}>{label}</button
        >
      {/each}
    </div>
  {:else if item.kind === 'cloze'}
    <h2>{item.text}</h2>
    <input
      type="text"
      bind:value={text}
      oninput={() => onanswer({ text }, true)}
      {disabled}
      aria-label="Antwort"
      autocomplete="off"
      autocapitalize="off"
      autocorrect="off"
      spellcheck="false"
    />
  {:else}
    <h2>{item.prompt}</h2>
    <textarea bind:value={text} oninput={() => onanswer({ text }, true)} {disabled} aria-label="Antwort" placeholder="In eigenen Worten …"
    ></textarea>
  {/if}
</div>

<style>
  .options { display: grid; gap: 0.6rem; }
  .options button { justify-content: flex-start; text-align: left; font-weight: 500; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
</style>
