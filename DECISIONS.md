# Decisions

Each entry: the decision, why, and what it costs. Newest at the bottom. Reversals are recorded,
not erased.

## D1 — Stack: FastAPI + SQLite backend, Next.js web, Expo mobile, pnpm monorepo
Follows the brief's suggestion. SQLite (WAL) because the product must run from one command with no
services to install; all SQL goes through one thin data layer so Postgres remains a swap, not a
rewrite. Cost: single-writer; fine for a personal-scale product.

## D2 — The pipeline is deterministic and works with no model at all
There is no model API key in the build environment, and the brief demands deterministic tests.
So captioning, moment naming and diary writing each have a deterministic offline implementation
that is the default, and an optional Claude-backed implementation behind the same interface.
Cost: offline prose is plainer than an LLM's. Benefit: the faithfulness guarantee does not depend
on a model behaving; tests are reproducible; privacy-first mode is real rather than aspirational.

## D3 — Faithfulness is enforced by structure, then checked independently
The narrator does not write free text and hope. It writes *sentences that each cite evidence ids*,
and a separate verifier (different code, no shared templates) re-reads the finished text, extracts
checkable claims (places, times, durations, distances, counts, activities, food, weather, people)
and confirms each against the cited evidence. Any model-written sentence that fails is dropped or
replaced by the deterministic sentence. The verifier itself is measured by mutation testing,
because an unmeasured checker proves nothing.

## D4 — Evidence carries confidence, and confidence controls wording
Each evidence row has `confidence` in {high, medium, low}. Low-confidence facts may only be
stated with hedged wording ("somewhere near …", "around …") or omitted. This is how "when
evidence is thin, write less" is implemented rather than promised.

## D5 — Sync: server-authoritative, field-level, with three-way text merge and no silent loss
Mutations carry the base value the client edited from. Scalar fields resolve last-writer-wins by
hybrid logical clock. Diary sentences get a sentence-aware three-way merge; if both sides changed the
same sentence close together, the later edit wins **and the other version is kept on the sentence as a visible
alternative** the user can restore with one tap. Rejected alternatives: CRDT text (heavy, and
character interleaving produces nonsense sentences), whole-document LWW (loses work).

## D6 — User edits are constraints that survive re-processing
New photos arrive mid-trip (the phone uploads daily), so the pipeline re-runs. Manual timeline
edits are stored as constraints (must-link, cannot-link, locked title/kind, hidden) and re-applied
after re-clustering; edited or user-written diary sentences are pinned and never regenerated.

## D7 — Maps: MapLibre GL JS everywhere, in a WebView on native
`@maplibre/maplibre-react-native` needs a custom dev build and cannot run in Expo Go, which the
brief names as an acceptable run target. Hosting MapLibre GL JS in a WebView gives one map
implementation for web, Expo Go, and dev builds. Cost: slightly less native feel, more memory.

## D8 — Bundled offline basemap
OSM raster tiles are the default when reachable, but a small Natural Earth vector basemap ships
with the clients so maps work offline, in privacy-first mode, and in this network-restricted build
environment. Cost: coarse coastlines/borders only when offline.

## D9 — Offline gazetteer as the default geocoder in tests and privacy mode
Nominatim is behind a `Geocoder` interface with caching and rate limiting, but it is unreachable
here and non-deterministic. Tests use a bundled gazetteer that includes **decoy POIs** near the
visited ones, so place resolution can actually be wrong and is therefore measurable.

## D10 — Synthetic photos are procedurally rendered, and the offline scene tagger is only validated on them
Photos need real pixels (for perceptual hashing, bursts, duplicates, screenshots, thumbnails,
the photo book). The generator paints scenes procedurally. The offline visual tagger is a
colour/texture heuristic; its accuracy on synthetic scenes says little about real photos, and
`METRICS.md` / `KNOWN_LIMITATIONS.md` say so. Real deployments should enable the vision provider.

## D11 — Mobile verification without a simulator
See PLAN.md constraints. The same Expo app is run via Expo web in Chromium for end-to-end tests;
native modules are wrapped behind small interfaces with web fallbacks so the logic above them is
the same code on every platform. What was not executed natively is listed, not implied.

## D12 — On-device data is encrypted at the application layer
SQLCipher is unavailable in Expo Go. Instead the offline cache and the pending-location buffer are
sealed with XChaCha20-Poly1305 (`@noble/ciphers`, audited, pure JS) using a key held in the
platform keystore (`expo-secure-store`). Works in Expo Go, dev builds and tests alike.

## D13 — Evening notification is a local scheduled notification
Remote push needs APNs/FCM credentials that cannot be committed. A local daily notification
(off by default, user-chosen time) plus a foreground refresh gives the user-visible behaviour
with no server secret. Cost: the notification fires at the chosen time, not at the exact moment
the server finishes drafting.

## D14 — Text merges are sentence-aware and conservative (revises D5 after prototype R3)
A word-level merge of two edits to the same sentence can produce a grammatical chimera nobody
wrote. Edits now merge automatically only when they fall in different sentences, insert whole
sentences at different places, or are at least 4 unchanged words apart; anything closer is a
surfaced conflict. Cost: more conflicts shown to the user than strictly necessary, and the 4-word
gap is an untested guess. Property fuzzing found two real loss paths around "Use this" (F1, F2 in
`docs/prototypes/R3-sync.md`); both are fixed and kept as seeded-bug regression checks.

## D15 — Captions and moment notes are merge fields too
Last-writer-wins on typed prose loses text silently, so `assets.caption` and `moments.note` get
the same merge-with-alternatives treatment as diary text. Other scalars stay last-writer-wins and
the loser is reported as `lost`.

## D16 — The diary writer obeys a closed vocabulary (from prototype R2)
The verifier only reaches its recall because every content word in a generated sentence must be
licensed by cited evidence, the traveller's own note, or a versioned safe-word list
(`diary/lexicon_safe.txt`). The price is plainer prose and rejection of about half of true
sentences that ignore the contract. Faithfulness is the brief's top bar, so the writer adapts to
the verifier, not the reverse.
