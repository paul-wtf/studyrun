# studyrun: Zen look

Date: 2026-11-24
Status: draft, awaiting Paul's approval

## Why

studyrun should look like part of Paul's app family (paul.wtf, tidalwave,
linkhop). Those three share one design language, called Zen in their token
files. studyrun shipped with a plain look of its own.

## Goals

- The tokens, typography, frame, header, wallpaper and component shapes match
  the family, so studyrun reads as a sibling of tidalwave and linkhop.
- Peach (`#fab387` on Mocha, `#fe640b` on Latte) is studyrun's single accent,
  in the same way that teal is paul.wtf's, mauve is tidalwave's and blue is
  linkhop's.
- Dark (Mocha) and light (Latte) themes with a toggle, as in tidalwave.
- Desk and phone (360 px) both still work, including the run player's large
  touch targets.

## Non-goals

- No change to behaviour, routes, API calls or copy.
- No shared design package across the apps. Every app keeps its own copy of
  `tokens.css`, and studyrun follows that practice.

## Constraints

- Green and red keep their meaning of correct and wrong (Catppuccin green and
  red, as `--success` and `--error`), so the accent can't be either of them.
- Contrast: body text and muted text keep at least 4.5:1 on their surfaces in
  both themes, the same rule the family's token files state.
- The existing component tests keep passing. Visual changes must not break
  roles, labels or the stale-entry and session-expiry flows.

## Approach

Take `tidalwave/frontend/src/lib/theme/tokens.css` as the base and swap the accent for peach in both themes, plus the moon in the
wallpaper SVG, which uses the accent colour. Port tidalwave's Zen frame (from
`routes/+layout.svelte`), its header bar with the `--bar-h` override, and its
theme store and toggle, trimmed to what studyrun needs. Restyle every studyrun
page and component onto the tokens: opaque surfaces, no decorative borders,
radii of 16, 10 and 8, and a soft shadow only on free cards. Load JetBrains
Mono through `@fontsource-variable/jetbrains-mono`, as tidalwave does.

A shared npm package for the tokens was ruled out: none of the apps has one,
and introducing one would mean changing three deployed apps for this.

## Left to the builder

- Exact layout of the header (brand, navigation for Start, Module, Gemeldet
  and Kosten, the theme toggle) within the family's pattern.
- How quiz states (selected, correct, wrong, disabled) map onto tokens, as
  long as correct and wrong use the success and error colours.
- Before/after screenshots at desk width and 360 px in both themes, for
  Paul to look at.
