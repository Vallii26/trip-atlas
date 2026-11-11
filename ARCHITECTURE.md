# Atlas — Architecture

This file is the contract between the parts of the system. If code and this file disagree, one
of them is a bug.

## 1. Shape of the system

```
                        ┌─────────────────────────── backend (Python, FastAPI) ───────────────────────────┐
 web studio  ──┐        │  API v1 ── jobs ── pipeline: ingest → timefix → cluster → enrich → evidence      │
 (Next.js)     ├─ HTTPS ┤                              → diary (plan → realize → verify gate) → stats       │
 mobile        │  JSON  │  sync service (push / pull, merge)      exports: share page, photo book PDF      │
 (Expo RN)   ──┘        │  providers (swappable): Geocoder · Vision · Transcriber · Narrator LLM           │
                        │  storage: SQLite (WAL) + media directory                                          │
                        └───────────────────────────────────────────────────────────────────────────────────┘
        both clients import packages/shared: generated API types, API client, SyncEngine, sealed store
```

The pipeline exists **once**, in the backend. Clients never cluster, geocode, or write diary text.

### Repository layout

```
backend/
  atlas/
    config.py            env-driven settings (ATLAS_* variables)
    pipeline/
      models.py          the data contracts of every stage (pydantic) — read this first
      ingest.py          stage 1a: read files, EXIF, decode, thumbnails, hashes, junk detection
      timefix.py         stage 1b: recover UTC time, timezone, and missing positions
      cluster.py         stage 2: moments
      enrich.py          stage 3: place + kind + title
      evidence.py        stage 4: evidence store
      diary/             stage 5: plan.py, realize.py, voice.py, verify.py, llm.py, prompts/
      stats.py           stage 6: stats, firsts, atlas layers
      run.py             orchestrates stages, writes per-stage artifacts
    providers/           geocoder.py, vision.py, transcriber.py, llm.py (interfaces + implementations)
    sync/                hlc.py, textmerge.py, merge.py (pure) + service.py (DB-backed)
    api/                 FastAPI routers
    export/              share.py (static share page), photobook.py (PDF)
    data/gazetteer/      offline places used by the fixture geocoder
    eval/                metrics against ground truth, mutation harness, hostile-input runs
    cli.py               `python -m atlas.cli …` — every stage runnable on its own
  atlas_synth/           synthetic trip generator (never imported by `atlas`)
  tests/
packages/shared/         TypeScript: api types (generated from OpenAPI), client, SyncEngine, sealed store
apps/web/                Next.js studio
apps/mobile/             Expo companion
data/                    generated synthetic trips, local DB, media (git-ignored)
```

### Why this stack
- **Python/FastAPI**: the work is image and geodata processing (Pillow, numpy, timezone lookup);
  FastAPI gives a typed OpenAPI schema for free, which is the single source of client types.
- **SQLite (WAL)**: zero-install, one command to run. All SQL lives in `atlas/db.py` +
  repositories; nothing SQLite-specific leaks into the pipeline, which works on plain models.
- **Next.js + Expo with a shared TS package**: one API client and one sync engine, used by both.
- **pnpm workspaces** (hoisted linker, which Expo/Metro needs).

## 2. Pipeline contracts

Every stage is a pure function over the models in `atlas/pipeline/models.py`, takes its
dependencies (geocoder, vision, …) as arguments, and is deterministic given the same inputs.
`run.py` persists each stage's output as JSON in a work directory so any stage can be re-run or
tested alone:

| # | Stage | Input → Output | Runnable as |
|---|---|---|---|
| 1a | ingest | files → `list[Asset]` (raw EXIF, hashes, junk flags, thumbnails) | `atlas.cli ingest` |
| 1b | timefix | assets + track → assets with `taken_utc`, `tz_offset_min`, position, confidences | `atlas.cli timefix` |
| 2 | cluster | assets + track + constraints → `list[Moment]` | `atlas.cli cluster` |
| 3 | enrich | moments → moments with `place`, `kind`, `title` | `atlas.cli enrich` |
| 4 | evidence | everything above + voice notes → `list[Evidence]` | `atlas.cli evidence` |
| 5 | diary | evidence + style profile → `list[DiaryBlock]` per day | `atlas.cli diary` |
| 6 | stats | assets, moments, track, user history → `TripStats` | `atlas.cli stats` |

### Stage 1 — ingest and repair
- Never trust a file extension; never let one bad file fail a run. A file that cannot be decoded
  becomes an `Asset` with `status="unreadable"` and a reason, and is shown to the user as such.
- Formats: JPEG, PNG, WebP, HEIC/HEIF (pillow-heif), TIFF; RAW (CR2/NEF/ARW/DNG/RAF…) via the
  embedded preview and EXIF if available, otherwise metadata only.
- Junk: screenshots (no camera EXIF + device-screen dimensions + flat-colour/UI statistics, or
  software tag), exact duplicates (sha256), near duplicates (perceptual hash + same time), bursts
  (same camera, < 2 s apart, near-identical hash). Junk is flagged, not deleted; the user can
  un-flag it.
- **Time repair** resolves, per asset, `taken_utc`, `tz_offset_min`, `time_source`,
  `time_confidence` using, in order of trust:
  1. EXIF `OffsetTimeOriginal` (+ `SubSec`), 2. GPS date/time stamp (UTC by definition),
  3. timezone looked up from the photo's own GPS position, 4. a per-camera clock model: constant
  offset estimated from that camera's photos that do have a trusted time, or — for cameras with no
  trusted photo at all — the offset that best aligns the camera's shots with trusted shots and the
  track (cameras left on home time are the common case), 5. neighbours in the same folder/sequence.
  Whatever was assumed is recorded, so the UI can say "time estimated" and the diary can hedge.
- **Position repair**: EXIF GPS → else track position at `taken_utc` (if the track covers it
  within a tolerance) → else interpolation between same-device neighbours that are close in time →
  else none. `gps_source` records which.

### Stage 2 — clustering
Moments are contiguous-in-time groups, split where the evidence says the activity changed:
a time gap that is large *for the local shooting rhythm*, a jump in position, or a sustained
change of visual signature; and merged back when a gap is explained by movement along the same
activity (a hike is one moment even with 20-minute gaps and 6 km of displacement). Travel legs
(sustained speed on the track) are moments of kind `transit`. Assets with no position join by
time and visual similarity. User constraints (pinned asset→moment, locked moments) are honoured
last and always win. Days are **local** calendar days at the place where the moment happened.

### Stage 3 — enrichment
`Geocoder.reverse(lat, lon)` returns candidates (POIs with category + admin hierarchy).
Place choice weighs distance against the cluster's spread, category plausibility given visual
tags and time of day, and dwell time; ambiguity lowers confidence instead of forcing a guess —
"near Praça do Comércio" is an acceptable answer, a wrong restaurant name is not.

### Stage 4 — evidence store
An `Evidence` row is one atomic, checkable fact with a pointer to where it came from:

```
Evidence { id, trip_id, day, moment_id?, type, payload{…}, sources[SourceRef], confidence }
SourceRef { kind: "asset" | "track" | "voice" | "geocoder" | "derived" | "user", ref: str, detail? }
type ∈ time · place · locality · duration · photo_count · movement · elevation · visual ·
       note · transport · border · timezone_change · first · sequence · kind
confidence ∈ high · medium · low
```
The diary may state only what is in this table. `low` evidence may only be stated hedged.
Evidence ids are stable hashes of their content, so re-running the pipeline keeps links valid.

### Stage 5 — diary
1. **plan**: score moments (dwell, distinct shots, notes, firsts, novelty, user favourites), pick
   a spine of one or two, demote the rest to background, drop what is not worth a clause.
2. **realize**: produce `DiaryBlock`s (one sentence or short group each), each citing the
   evidence ids it uses. Default realizer is deterministic and style-aware; the optional LLM
   realizer receives *only* the planned evidence and must return sentences with citations.
3. **verify gate**: `verify.py` independently extracts claims from the final text and checks them
   against the cited evidence. Model output that fails is dropped or replaced by the deterministic
   sentence; the failure is logged. The same verifier computes the fabrication rate in `eval/`.
4. **voice**: `StyleProfile` (person, tense, sentence length, contractions, punctuation habits,
   clock/unit format, preferred words) is fitted from a writing sample and updated from the user's
   edits (`generated_text` → `text` pairs). It is per-user, so it carries across days and trips.

Blocks with `origin` `edited` or `user` are pinned: regeneration never touches them, and the
verifier treats them as the user's own testimony.

Prompts live in `atlas/pipeline/diary/prompts/<name>.v<N>.md`; every model call is logged
(prompt version, input, output, verdict) to the `llm_log` table and `data/logs/llm/`.

### Stage 6 — stats and firsts
Distance by mode, elevation, countries/localities, days, moments by kind, rhythm (earliest start,
latest night), and "firsts" computed against the user's *other* trips. Atlas layers (trains,
hikes, foods, wildlife, sunrises) are evidence queries, so they are as faithful as the diary.

## 3. Providers (everything external is swappable)

| Interface | Default (offline, deterministic) | Optional |
|---|---|---|
| `Geocoder` | `GazetteerGeocoder` (bundled places + world cities) | `NominatimGeocoder` (cached, 1 req/s) |
| `VisionTagger` | `HeuristicVisionTagger` (colour/texture statistics) | `ClaudeVisionTagger` |
| `Transcriber` | `SidecarTranscriber` (transcript supplied with the upload) | `WhisperTranscriber` |
| `NarratorLLM` | none (deterministic realizer) | `ClaudeNarrator`; `ScriptedNarrator` for tests |

Selection is by environment variable (`ATLAS_GEOCODER`, `ATLAS_VISION`, `ATLAS_TRANSCRIBER`,
`ATLAS_NARRATOR`); API keys only ever come from the environment. `ATLAS_PRIVACY_MODE=1` forces
every provider to its offline implementation.

## 4. Storage

SQLite tables: `users`, `sessions`, `devices`, `trips`, `assets`, `track_points`, `docs`
(the sync document store, see §5), `changes` (monotonic change log), `applied_ops`, `jobs`,
`llm_log`. Media on disk under `ATLAS_DATA_DIR/media/<trip>/`: `orig/` (as uploaded, never served
publicly), `thumb/` and `view/` (re-encoded, **all metadata stripped**), `audio/`.

## 5. Sync model

### What syncs
Everything a client shows is a **document** in a collection, scoped to a trip:

| Collection | Mutable by clients | Notes |
|---|---|---|
| `trips` | title, dates_hint, cover_asset_id, deleted | |
| `moments` | title, kind, hidden, note, deleted; create (client-generated id) | user-set fields become locks |
| `assets` | hidden, favorite, caption, pinned_moment_id | moving a photo = setting `pinned_moment_id` |
| `diary_blocks` | text, pos, deleted; create | `text` is a merge field |
| `evidence` | — (read-only) | lets clients show evidence links offline |
| `derived` | — (read-only) | one per trip: stats, route geometry, day summaries |

Binary uploads (photos, voice notes) and location batches are not documents; they go through an
idempotent upload queue (`client_id` + sha256 / `batch_id`), retried until acknowledged.

### Document and clock
```
Doc { id, collection, trip_id, fields{…}, meta{ field → { hlc, device } }, conflicts[…], rev, deleted }
```
`hlc` is a hybrid logical clock string `"<ms:013d>-<counter:04d>-<device>"`, totally ordered by
string comparison. The server never trusts a clock more than 5 minutes ahead of its own: such
timestamps are clamped on receipt, so a phone with a wrong clock cannot win every conflict forever.
`rev` is the server change sequence at the doc's last change.

### Protocol
```
POST /v1/sync/push   { device_id, mutations: [Mutation] }  →  { results: [{op_id, status, doc}], cursor }
GET  /v1/sync/pull?cursor=N&limit=M                         →  { docs: [Doc], cursor, has_more }

Mutation { op_id, collection, id, trip_id, kind: "upsert" | "delete",
           fields{ name → new value }, base{ name → value the client edited from }, hlc }
status ∈ applied · merged · conflict · duplicate · rejected
```
- **Idempotent**: `op_id` is recorded; replays return `duplicate` with the current doc.
- **Per field**: if the server value equals `base`, apply. Otherwise both sides changed it:
  - scalar field → the higher `hlc` wins;
  - merge field (diary `text`) → word-level three-way merge of (base, server, client). A clean
    merge is `merged`. If the same words were changed on both sides it is `conflict`: the higher
    `hlc` becomes the text and **the other version is appended to `conflicts`** with its device
    and time. Clients show it under the sentence ("Also written on *Phone*: … — Use this ·
    Dismiss"). Resolving is an ordinary mutation. Nothing a user typed is ever discarded silently.
- Delete vs edit: an edit to a deleted block resurrects it (an edit is evidence the user wants it).
- Pipeline output is written through the same merge path with the pseudo-device `pipeline`, and
  never overwrites a field whose `meta.device` is a user device (D6).

### On the client (`packages/shared` `SyncEngine`)
Local store = last-synced docs + an **outbox** of pending mutations. `mutate()` applies
optimistically, records `base` as the last-synced value, and coalesces repeated edits to the same
field. `sync()` pushes the outbox in order, replaces local docs with the server's answers, then
pulls from the cursor; pulled docs do not clobber fields that still have a pending local edit.
Offline simply means the outbox grows. The web app uses the same engine with an in-memory store
and a short poll; the mobile app persists store and outbox in a sealed (encrypted) store.

### On-device storage (mobile)
Sealed with XChaCha20-Poly1305; key in the platform keystore. Stored: docs, outbox, upload queue
(voice-note files, pending location batches), thumbnails cache, session token. Location points are
never written unencrypted. Signing out wipes the store and the key.

## 6. API (v1)

Bearer session tokens. Everything under `/v1` is in the OpenAPI schema (`/openapi.json`), from
which `packages/shared/src/api/schema.d.ts` is generated — clients never hand-write DTOs.

```
POST /v1/auth/register · /v1/auth/login · /v1/auth/logout      GET/PATCH /v1/me
GET/POST /v1/trips     GET/DELETE /v1/trips/{id}
POST /v1/trips/{id}/assets          multipart upload, one file per request, idempotent
POST /v1/trips/{id}/track           batch of points from the phone, idempotent
POST /v1/trips/{id}/process         start/coalesce a pipeline job    GET /v1/jobs/{id}
POST /v1/trips/{id}/diary/regenerate
GET  /v1/assets/{id}/thumb | view | audio
PUT  /v1/me/voice                   writing sample → style profile
GET  /v1/atlas                      cross-trip layers + firsts
POST/DELETE /v1/trips/{id}/share    GET /v1/trips/{id}/share/export.zip
POST /v1/trips/{id}/photobook       → job → GET /v1/trips/{id}/photobook.pdf
POST /v1/sync/push    GET /v1/sync/pull
GET  /s/{token}                     public, read-only share page (no auth, noindex)
```

## 7. Privacy model
- Originals are private to the owner. Every served or exported image is re-encoded with metadata
  stripped; a test opens every exported byte stream and fails on any EXIF/XMP/GPS.
- A **privacy zone** (home, by default a 500 m circle the user can move) removes photos, moments
  and route geometry inside it from share pages and photo books; the route is clipped at the
  boundary plus a random-but-stable offset so the centre cannot be triangulated.
- Share links are unguessable tokens, revocable, `noindex`, and contain no user email, no
  filenames, no device model.
- `ATLAS_PRIVACY_MODE=1`: no outbound request leaves the backend at all.

## 8. Running
`make dev` — installs, generates the synthetic trips, seeds a demo account with the three trips
processed, starts API (:8000) and web (:3000). `make mobile` starts Expo. `make test`,
`make metrics`. See `README.md`.
