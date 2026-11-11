# Atlas — design language

One product on four surfaces: web studio, mobile companion, public share page, printed photo book.
They must look like the same thing. This file is the source of truth for tokens and tone.

## Idea
A well-kept travel journal: warm paper, dark ink, one confident accent, generous whitespace,
photographs doing the talking. Calm and editorial, not "dashboard". The diary is the hero and is
set like a book, in a serif. Interface chrome is quiet and sans-serif.

## Colour tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `paper` | `#FAF7F2` | `#16130F` | page background |
| `surface` | `#FFFFFF` | `#1F1B16` | cards, sheets |
| `sunken` | `#F1ECE3` | `#110F0C` | wells, inputs, skeletons |
| `ink` | `#1F1B16` | `#F3EEE6` | primary text |
| `ink-2` | `#5C5348` | `#B9AFA1` | secondary text |
| `ink-3` | `#8C8273` | `#7F7668` | hints, captions |
| `line` | `#E4DCCF` | `#332D25` | hairlines, borders |
| `accent` | `#C2552D` | `#E8845C` | primary actions, the route, active state (terracotta) |
| `accent-soft` | `#F6E2D8` | `#3A2218` | accent backgrounds, selected chips |
| `teal` | `#1F5F5B` | `#6FB9B1` | evidence links, secondary data colour |
| `teal-soft` | `#DCEBE9` | `#16302E` | evidence highlight |
| `gold` | `#B8862B` | `#D9AE5A` | "firsts", favourites |
| `danger` | `#B3261E` | `#F2867E` | destructive, errors |
| `ok` | `#2E7D4F` | `#7CC79A` | synced, success |
| `warn` | `#9A6700` | `#E0B252` | estimated / low-confidence markers |

Moment-kind colours (map markers, timeline dots) are drawn from: accent (sights, viewpoints),
teal (transit, stations), gold (meals, cafés, bars), `#4F7A3A` green (hikes, parks, wildlife),
`#3E6C99` blue (water, beach, swim), ink-2 (lodging, unknown). Never rely on colour alone: every
kind also has an icon.

## Type
- **Fraunces** (600, 400) — display: trip titles, day headings, numbers in stats.
- **Newsreader** (400, 400 italic, 600) — diary body, quotes from voice notes (italic), captions
  in the photo book.
- **Inter** (400, 500, 600) — all interface text.

Scale (px): 12 · 13 · 15 · 17 · 20 · 24 · 32 · 44 · 60. Diary body 19/1.65 on web, 18/1.6 on
mobile, max line length 68 characters. Font files (OFL) are in `assets/fonts/`; nothing is
fetched from a font CDN at runtime.

## Shape and space
4-px grid. Radius: 6 (chips, inputs), 12 (cards, photos), 20 (sheets), full (pills).
Shadows are soft and rare (`0 1px 2px rgba(31,27,22,.06), 0 8px 24px rgba(31,27,22,.06)`);
prefer hairlines. Photos have 12-px radius in the app, square corners in print.

## Voice of the interface
Plain, warm, short. No exclamation marks, no "Oops". Say what happened and what the user can do:
"3 photos had no time or place. We put them where they most likely belong — check them."
Uncertainty is shown, never hidden: an "estimated" marker (warn colour, dotted underline) on
times and places the pipeline inferred.

## Signature elements
- **Evidence link**: tapping/hovering a diary sentence highlights it in `teal-soft` and reveals
  the photos, place, time and notes it rests on. Sentences the user wrote or edited carry a small
  pen mark instead.
- **Spine**: the one or two moments that carry a day are larger in the timeline.
- **Conflict alternative**: an inset card under the sentence, "Also written on *Phone*, 21:14",
  with *Use this* and *Dismiss*.
- **Sync pill**: "Saved" / "Saving…" / "Offline — 3 changes waiting" — always visible, never modal.

## States (every screen must have all four)
Empty (an invitation with one action), loading (skeletons in `sunken`, no spinners on content),
error (what failed, a retry, and nothing lost), partial (e.g. processing 312 of 420 photos, with
the timeline filling in as it goes).

## Accessibility
Text contrast ≥ 4.5:1 (ink-3 only for non-essential captions ≥ 13 px). Hit targets ≥ 44 px on
touch. Visible focus rings (2 px accent, 2 px offset). Respects reduced motion. Every image has
alt text built from the moment title and place. Full keyboard operation on web.

## Mobile specifics
One hand: primary actions within the bottom third; bottom tab bar (Today · Trips · Record ·
Atlas · Settings); sheets instead of pages for quick edits; large record button; never a blank
screen offline — show cached content and the sync pill.
