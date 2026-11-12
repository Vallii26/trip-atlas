# Atlas — Plan

Living document. Status markers: `[ ]` todo, `[~]` in progress, `[x]` done and verified by execution.

## What we are building

A trip tracker that writes its own story: one backend "brain" (ingest → repair → cluster → enrich →
evidence → diary → stats), a web studio, and a mobile companion, with two-way offline-capable sync.
See `ARCHITECTURE.md` for the contracts and `DECISIONS.md` for every judgment call.

## Constraints discovered in this build environment (affect how things are verified)

| Constraint | Consequence |
|---|---|
| No `/dev/kvm`, no Android SDK, no macOS | The mobile app cannot be run in a simulator **here**. It is verified by (a) type-check, (b) unit tests of all non-UI logic, (c) Metro bundling for iOS and Android, (d) running the same app through Expo web in headless Chromium at phone size. Native-only behaviour (background location, photo-library permission sheets, push) is implemented but **not executed here**; listed in `KNOWN_LIMITATIONS.md`. |
| No model API key available to the app | The default narrator, captioner and transcriber are deterministic offline implementations. The Claude-backed providers are implemented behind the same interfaces and exercised with a scripted fake (including a deliberately *lying* fake to test the faithfulness gate), but never against the live API. |
| Nominatim / Photon / OSM tiles / Hugging Face unreachable | Geocoding is tested with a bundled offline gazetteer; the Nominatim adapter is contract-tested against recorded-shape fixtures only. Maps ship a bundled vector basemap (Natural Earth) and use OSM raster tiles when reachable. Whisper transcription is an optional adapter, untested here. |

## The three riskiest unknowns (prototyped before any UI)

1. **Time repair + clustering under broken metadata.** Can we recover true UTC time for photos with
   wrong camera clocks / mid-trip timezone changes / no GPS, and then cluster to real moments?
   *Test:* synthetic trips with ground truth; metrics = time-repair error, pairwise F1 and
   Adjusted Rand Index of moments, junk (screenshot/duplicate) detection P/R.
   *Kill criterion:* pairwise F1 < 0.85 on any trip → redesign.
2. **Automatic faithfulness checking.** Can a checker that is independent of the generator reliably
   decide whether each diary sentence is supported by evidence? Without that, "fabrication rate"
   is a guess. *Test:* mutation testing — inject known fabrications (wrong place, invented meal,
   wrong time, invented weather, inflated numbers, invented companions) into faithful diaries and
   measure detection recall, plus false-positive rate on faithful text.
   *Kill criterion:* recall < 0.95 or false-positive rate > 2% → redesign the claim model.
3. **Offline two-way sync with sentence-level merge.** Can phone and web edit the same trip
   offline and converge with nothing lost, including the same sentence edited on both sides?
   *Test:* property-based convergence tests on the merge core (random op interleavings from N
   replicas must converge and preserve every user-typed string either in the text or in a
   surfaced conflict alternative), then an end-to-end round trip against the real API.

A fourth, environmental risk — "can the mobile app be exercised at all here?" — is answered by an
early Expo-web smoke test before investing in mobile screens.

## Milestones

### M0 — Plan and contracts
- [x] Read brief, probe environment
- [x] `PLAN.md`, `ARCHITECTURE.md`, `DECISIONS.md`
- [x] Monorepo scaffold (backend imports, Next.js builds, Expo bundles for web and Android)

### M1 — Synthetic trips with ground truth (Phase 1)
- [ ] Generator: Lisbon city weekend, Alpine hut-to-hut hike (poor signal), London→Istanbul rail journey (3 timezones)
- [ ] Broken cases in every trip: no GPS, clock skew, stale-timezone camera, duplicates, bursts, screenshots, corrupted file, HEIC
- [ ] `truth.json` per trip: true time, moment membership, places, diary facts, forbidden facts (decoys)
- [ ] Hostile sets: 5,000-photo trip, 3-photo trip, 15-year-old photos, RAW/HEIC/corrupt

### M2 — Risk prototypes
- [ ] R1 time repair + clustering prototype with metrics
- [x] R2 faithfulness verifier + mutation harness — recall 1.000 (1374/1374), 0/47 FP blocks on fixtures; 70/76 adversarial
- [x] R3 sync merge core + convergence property tests — 106 tests; deep fuzz 5,124 examples, 0 failures

### M3 — Pipeline, stage by stage (Phase 2), each with its own CLI and tests
- [ ] 1 Ingest + metadata repair
- [ ] 2 Moment clustering
- [ ] 3 Place and context enrichment
- [ ] 4 Evidence store
- [ ] 5 Diary generation constrained to evidence (+ voice profile, + gate)
- [ ] 6 Stats and firsts
- [ ] `METRICS.md` baseline

### M4 — API + sync service
- [ ] Auth, trips, uploads, jobs, timeline edits, diary, stats, share, photo book, sync push/pull
- [ ] OpenAPI schema exported and type-generated into `packages/shared`

### M5 — Web studio (Phase 3)
- [ ] Upload, timeline editor, map, diary editor with evidence links, stats, life atlas, share page, PDF photo book
- [ ] Empty / loading / error states; visual review via screenshots

### M6 — Mobile companion (Phase 3b)
- [ ] Library import (incl. limited access), background tracking with pause, voice notes offline, Today screen, offline browse/edit, evening notification, share link
- [ ] Phone → web → phone round trip incl. offline and same-sentence conflict

### M7 — Adversarial review (Phase 4)
- [ ] Fabrication hunt on all trips; hostile inputs; privacy review; mobile risk review
- [ ] Independent reviewer agents (no knowledge of how the code was produced)
- [ ] Fix, re-run, update metrics

### M8 — Polish and handover (Phase 5)
- [ ] Fresh-clone run from one command
- [ ] Docs accurate: README, ARCHITECTURE, DECISIONS, METRICS, KNOWN_LIMITATIONS
- [ ] Final report

## How each milestone is tested

| Area | Test |
|---|---|
| Generator | Determinism (same seed → same bytes), EXIF round-trip, truth file schema validation |
| Ingest/repair | Per-photo UTC error vs truth; junk detection P/R; corrupted files never crash a run |
| Clustering | Pairwise P/R/F1, ARI, moment-count error per trip; day assignment accuracy across timezones |
| Enrichment | Place-name accuracy and category accuracy vs truth, with decoy POIs nearby |
| Evidence | Every evidence row has a resolvable source pointer; evidence accuracy vs truth |
| Diary | Independent verifier: unsupported-claim rate; truth-level check: contradicted/forbidden facts; key-fact coverage; voice-consistency metrics |
| Stats | Exact values vs truth (distance within tolerance, countries, firsts) |
| API | Contract tests on every route; authz tests (user A cannot read user B) |
| Sync | Property tests on merge core; scripted two-replica round trip against live server; browser E2E web + mobile-web |
| Web/mobile UI | Playwright flows + screenshot review |
| Privacy | EXIF absent from every exported byte stream; home zone absent from share output |
| Performance | Seconds per 1,000 photos, memory ceiling on the 5,000-photo trip |
