# R3 — Offline-first two-way sync: prototype results

Status: prototype complete. Core is pure Python with no I/O (`backend/atlas/sync/`), tests in
`backend/tests/sync/`. ARCHITECTURE §5 was right in outline but wrong or silent in eleven places;
the exact edits are in the last section.

| File | What it is |
|---|---|
| `atlas/sync/hlc.py` | hybrid logical clock, `clamp`, `successor` |
| `atlas/sync/textmerge.py` | tokeniser + sentence-aware three-way prose merge |
| `atlas/sync/merge.py` | `Doc`, `Mutation`, `CollectionSchema`, `apply_mutation` — all merge rules |
| `atlas/sync/server.py` | `SyncServer` (push / pull / apply_pipeline) over a `Store` protocol, `InMemoryStore` |
| `atlas/sync/sim.py` | reference client = executable spec for the TypeScript `SyncEngine` (rules R1–R8) |

Run: `cd backend && uv run pytest tests/sync` (106 tests, ~30 s, 300 fuzz examples).
Deep run: `ATLAS_SYNC_FUZZ=5000 uv run pytest tests/sync/test_fuzz.py -s`
(`ATLAS_SYNC_FUZZ_STEPS` sets steps per example, default 50; `ATLAS_SYNC_FUZZ_NOSHRINK=1` skips
shrinking, which otherwise takes minutes on a failure).

## 1. Final rules

### Clock
- HLC string `"<ms:013d>-<counter:04d>-<device>"`, ordered by string comparison. Device ids match
  `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`; `pipeline` is reserved.
- **Future clocks**: the server clamps any timestamp more than 5 min ahead to server time (counter
  and device kept). Clamping does not preserve order within one device, so **two writes from the
  same device are never compared by HLC — the later arrival wins** (a device's ops arrive in the
  order it made them). Across devices the higher HLC wins.
- **Past clocks**: (1) an edit whose `base` equals the server value applies whatever its clock
  says, and is stored with `max(hlc, successor(previous hlc))`, so it is causally after what it
  replaced; (2) clients `observe` the hlc of every doc they receive; (3) responses carry
  `server_ms` and the client corrects its wall clock by the offset. Remaining, accepted: an edit
  made *offline* by a slow-clock device that is *concurrent* with another device's edit loses the
  race even if it was later in real time. For text the loser is kept as an alternative; for
  scalars it is dropped and reported.

### Upsert, per field (`s` server value, `b` base, `c` new value)
1. `c == s` → noop.
2. field is unset or pipeline-owned → the user's write applies outright (user always beats pipeline).
3. `b == s` → apply (clock irrelevant).
4. `c == b` → noop (client made no net change; it must not revert someone else's edit).
5. concurrent scalar → winner by the clock rule; a losing mutation is dropped, field outcome `lost`.
6. concurrent merge field → `merge3(b, s, c)`. Clean → merged text. Otherwise the winner by the
   clock rule is the text and the **whole** losing text is appended to `conflicts`.

Status of the mutation: `conflict` if any field is `conflict`/`lost`/`kept`, else `merged` if any
field merged, else `applied`. Results also carry per-field outcomes. A mutation that changes
nothing does not bump `rev`.

### Conflict alternatives
`{id, field, value, hlc, device, base}`. `id = "c_" + sha256(field NUL value)[:16]`, i.e.
content-addressed: identical alternatives dedupe, and resolving an id means "the exact text I
saw", so a resolve cannot race a third edit. An alternative equal to the current text is removed.
If a device keeps editing text of its own that already lost, the new version replaces its
alternative. Cap: 8 per doc; the lowest-hlc alternative is evicted and returned in `evicted`.

### Resolving
An ordinary upsert with `resolve: [ids]`; works offline, idempotent (missing ids are ignored).
- Dismiss: no fields.
- Use this: `fields{text: alt.value}`, `base{text: text on screen}`, `resolve: [alt.id]`.
- Server order: remove resolved alternatives, then apply fields. A resolved alternative whose
  value equals the mutation's value (chosen) or its base (chosen, then edited further) is not a
  dismissal: if that text does not end up as the text it is put back as an alternative.

### Deletes
Tombstone: `deleted = true`, fields kept, `meta._deleted = {hlc, device}`. `deleted` is not a
field; delete is `kind: "delete"`, undo is an upsert with no fields.
- A user delete carries `base` = every client-writable field as seen and `resolve` = every
  alternative seen. It is **refused** (`conflict`) if there is a user edit it did not see: an
  unseen alternative; a merge field ≠ base; a scalar ≠ base that beats the delete; or a later restore.
- An upsert arriving at a tombstone resurrects it if the tombstone is the pipeline's, or the upsert
  carries a merge field, or it beats the tombstone's hlc. Otherwise it is dropped (`conflict`).
- So: delete vs concurrent **text** edit → edit wins in both arrival orders, whatever the clocks;
  delete vs concurrent **scalar** edit → LWW. Why edit wins: a delete is redone with one tap,
  typed text cannot be retyped; and resurrecting a block because another device reordered it
  would surprise.

### Creates
Client-generated ids (UUIDs). The same id created twice is just a concurrent upsert with
`base = null`: scalars LWW, text merge3 against an empty base (different texts → conflict).

### Pipeline
Device `pipeline`, entered through `SyncServer.apply_pipeline` only (a client push claiming that
device is rejected). It may write any field and create/delete in any collection, but: a field
whose `meta.device` is a user device is skipped (`kept`); a doc with any user-owned field or any
alternative is not deleted; a user's tombstone is not resurrected. An untouched generated block is
replaced on regeneration; a user edit that arrives after a regeneration still wins wholesale and
the generated text is not kept as an alternative.

### Server
- Ops are recorded per **(user, op_id)**; a replay returns `duplicate` + the current doc (and
  `original_status`). Rejected ops are recorded too and never return a doc.
- Authorization: every doc belongs to a trip, every trip to one user. Unknown trip → only a
  `trips` upsert with `id == trip_id` is allowed and claims it. Mutation `trip_id` must equal the
  doc's. `hlc` device must equal the pushing `device_id`.
- Pull: docs whose latest change `rev > cursor`, ascending by `rev`, each once in its latest
  state; `cursor` = last returned `rev`; `has_more` by fetching `limit + 1`. A doc that changes
  between pages moves to a later page (may be delivered twice, never skipped).
- The DB service must run each mutation's read → write → seq → op-record in one transaction and
  allocate `seq` in commit order.

### Text merge policy (`textmerge.py`)
Tokens are whitespace runs, words (inner `'`/`-`, digit groups like `17:30`, combining marks) and
punctuation/emoji clusters (ZWJ sequences, skin tones, flags) — a merge can never split a word or
an emoji. Each side is diffed against the base into hunks; two hunks from different sides are
independent when they are the identical edit, or lie in different sentences, or one inserts a
whole new sentence at a sentence boundary, or they are in one sentence with **at least 4 unchanged
words between them**. Anything else is a conflict, and on conflict **nothing** is merged: one whole
typed version is the text, the other whole typed version is the alternative. Whitespace-only
changes never conflict. Both sides appending different sentences at the same place is a conflict
(the order is unknowable).

Why: word-level merge inside a sentence yields text nobody wrote ("We walked to the big market" +
"We ran…" + "…old market" → "We ran to the old market"). The 4-word gap keeps the case users
expect to work (typo fixed at the start, last clause rewritten) and refuses close edits. Sentence
detection is deliberately conservative (abbreviations, initials, lowercase continuation and
decimal times are not boundaries): a missed boundary only costs an extra conflict.
`MIN_GAP_WORDS` is a product knob.

### Client (`sim.py`, to be ported 1:1)
- R1 base = the value on screen when the user edited (synced value + this device's earlier pending ops).
- R2 a new edit folds only into the last op for that doc if that op is an **unsent** upsert; the
  folded op keeps its original base.
- R3 ops are frozen (`sent = true`) before the request leaves and are resent byte-for-byte.
- R4 an op leaves the outbox only on an explicit per-op result.
- R5 a server doc replaces the synced copy only if its `rev` is not older.
- R6 never take a pull cursor from a push.
- R7 `sync()` is single-flight.
- R8 observe every received hlc; correct the wall clock from `server_ms`.
- The view is never stored: `view = synced + outbox replayed`, so a pull cannot clobber a pending edit.

## 2. Invariants (as checked by `test_fuzz.py`)

Checked after all replicas come online and each syncs twice:

**(a) Convergence.** For every replica: outbox empty; `synced` equals the server's docs for that
user exactly (fields, meta, conflicts, deleted, rev); `view == synced`.

**(b) No silent loss.** Every edit of a merge field introduces a fresh marker word `XqN`. For every
marker *m* typed into doc *D*, at quiescence at least one holds:
1. *D* is live and *m* occurs in *D*'s text or in one of *D*'s alternatives;
2. some edit, on any device, whose author's **view** contained *m* produced a text without *m*
   (includes the same device overwriting itself, and "Use this" replacing the text on screen);
3. some dismiss targeted an alternative containing *m*;
4. *D* is deleted and some delete was issued from a view (text + alternatives) containing *m*;
5. an alternative containing *m* was evicted by the cap (never happened in any run).

Text inside a tombstone does not count as present. Limit of this definition: once anyone has
deliberately removed *m* anywhere, a later accidental loss of *m* is not detected.

**(c) Idempotency.** Re-delivering any batch the server has received leaves the store snapshot
identical and returns `duplicate` for every op.

**(d) Cursors.** No pull ever returns a cursor below the one sent; a fresh replica paging from 0
with limit 1–7 receives every doc exactly once and ends equal to the server.

Also asserted every step: the pipeline never changes a user-owned field, deletes a user-touched
doc, or resurrects a user's tombstone; a second user's pushes (including one reusing a victim's
`op_id`) are rejected, return no doc, and change nothing; no legitimate op is ever rejected.

Fuzz actions: 2–4 replicas with skews from {0, ±90 s, +10 min, +2 d, −2 d}, pull limits 1/2/5/100,
server-time correction on or off per replica; create (incl. two shared ids), edit text (rewrite /
append / prepend / replace a word), the same block edited on two devices, edit scalar, delete,
restore, dismiss / use-this, resolve racing another device's edit, online/offline with waits up to
1 h, sync with faults (response lost after the server applied k ops, request delivered twice, pull
fails, user types while the push is in flight), pipeline writes and deletes.

## 3. Numbers

| Run | Result |
|---|---|
| Default suite | 106 tests, 30 s (300 fuzz examples; 9 seeded-bug checks) |
| Deep run (`ATLAS_SYNC_FUZZ=5000`) | 5,124 examples, 225,636 steps, 12,827 quiescence checks, 1 min 51 s, 0 failures |

Deep-run server outcomes: 60,739 applied · 4,033 merged · 19,719 conflict (11,443 text conflicts,
2,167 scalars lost, 3,839 deletes refused "edit wins", 115 "restored later") · 75,592 duplicate ·
0 cap evictions.

`test_fuzz_teeth.py` re-introduces nine bugs and requires the fuzz to catch each: folding into a
sent op; base refreshed at push; cursor taken from push; delete ignoring concurrent edits; delete
ignoring unseen alternatives; conflict loser dropped; resolve applied after fields; text edit not
resurrecting a tombstone; no op log. All nine are caught.

## 4. Bugs found

### Found by the fuzz (in my design, after the unit-level reasoning said it was fine)
- **F1 — "Use this" silently became "Dismiss".** Phone's text loses a conflict while the user is
  still typing (second op, base = the phone's own in-flight text). The user then taps "Use this"
  on their own alternative. The client folded this into the pending op; value now equalled base,
  the client dropped the field as "typed back, no change", and what was left was a bare resolve.
  The server had the same hole (rule 4 no-op after removing the alternative). Fix: client never
  drops a typed-back field; server treats a resolved alternative whose value the mutation writes
  as *chosen* and puts it back if it does not become the text.
- **F2 — "Use this", then more typing, lost the chosen branch.** Coalesced op: base = the
  alternative, value = alternative + a new sentence, resolve = [alt]. Resolve removed the
  alternative, the merge was clean against the server text, and only the new sentence survived.
  Fix: a resolved alternative equal to the mutation's base marks the mutation as a continuation
  of that branch; the device's full version is kept as the alternative.
- **Fuzz blind spot.** The first version passed 3,000 examples and then failed to catch two of the
  seeded bugs: it synchronised everyone too often and spread edits over too many blocks. After
  densifying it (seed blocks, rarer quiescence, two-device edit and resolve-race rules) text
  conflicts per example rose from ~0.07 to ~2.2, all seeded bugs are caught, and F1/F2 appeared.

### Found while designing against §5 (each is now a rule, most have a seeded-bug check)
- Coalescing into an op that was already sent loses the new edit as `duplicate` (R3).
- `base` = "last-synced value" is wrong once an op is in flight: the next edit conflicts with the
  device's own previous edit. Base must be the value on screen (R1).
- Push returning a `cursor` invites skipping other devices' earlier changes (R6).
- Delete as plain LWW loses text typed concurrently; a delete must say what it saw.
- An alternative added after the deleter last synced was lost by the delete.
- Resolve applied after the fields removes the chosen text when it loses a race.
- Op log keyed by `op_id` alone lets another user fetch a doc by replaying a guessed op id.
- Clamping reorders one device's own timestamps (same-device rule).
- A scalar write with value == base reverted another device's edit by LWW (rule 4).
- Trimming trailing whitespace on one side plus an append on the other glued two sentences.

## 5. Known weaknesses

- **Scalars are plain LWW.** A concurrent loser is dropped; the client is told (`lost`) but no UI
  is specified. `pos` in particular: two devices inserting at the same position tie, and a
  reorder is several independent writes. Needs fractional index keys with an id tie-break.
- **Slow-clock devices lose concurrent scalar races** until they have synced once (then
  `server_ms` corrects them). A fast-clock device's offline edits are stamped at receipt time and
  so can beat an edit that was really later.
- **One hlc per op.** Coalescing two fields edited at different times stamps both with the later time.
- **Conflict means whole-block winner.** In a three-sentence block, a clash in sentence 1 puts the
  loser's independent edit to sentence 3 in the alternative as well, not in the text.
- **Merge heuristics are English-shaped.** Sentence detection is punctuation-based; scripts
  without spaces tokenise as one word per run, so almost every concurrent edit conflicts (safe,
  noisy). The 4-word gap is a guess, not tested with users. Two sides independently adding the
  same sentence at different places produce it twice.
- **Alternative cap evicts** the oldest alternative beyond 8 per doc: reported in the result, but
  it is a real loss path. Never hit in the fuzz.
- **Resurrection can duplicate content**: a user edit to a block the pipeline has since replaced
  brings the old block back beside its regenerated successor. The pipeline must reconcile.
- **Tombstones and the op log are never garbage-collected.**
- **Rejected ops are dropped by the client** (surfaced in `Client.rejected`); the typed text is
  gone from the view. Only reachable through authz or schema violations.
- **Invariant (b) is exemption-based** (see §2), and the fuzz covers one user, one trip, one merge
  field, ≤ 4 replicas. `moments.note` / `assets.caption` use the same code path but are not fuzzed.
- **Not covered at all**: the SQLite `Store`, transaction boundaries, concurrent requests,
  JSON validation of field values, the TypeScript port, the binary upload queue.
- Running the tests creates `backend/.hypothesis/` (example database); it should be git-ignored.

## 6. Edits needed in ARCHITECTURE.md §5

1. **"What syncs" table** — remove `deleted` from every "Mutable by clients" cell (delete is
   `kind: "delete"`). Change the `moments` and `assets` notes to say `note` and `caption` are
   merge fields. Add under the table:
   > Fields not listed are read-only to clients and writable by the pipeline. Clients may create
   > and delete `trips`, `moments`, `diary_blocks`; nothing else.

2. **"Document and clock"** — replace the `Doc` line and the paragraph after it with:
   > ```
   > Doc { id, collection, trip_id, fields{…}, meta{ field → { hlc, device } }, conflicts[Alt], rev, deleted }
   > Alt { id, field, value, hlc, device, base }      id = "c_" + sha256(field NUL value)[:16]
   > ```
   > `meta._deleted` holds the hlc/device of the last delete or restore. `hlc` is a hybrid logical
   > clock string `"<ms:013d>-<counter:04d>-<device>"`, totally ordered by string comparison.
   > The server clamps timestamps more than 5 minutes ahead of its own clock to server time, so a
   > phone with a fast clock cannot win every conflict forever. Two writes by the same device are
   > ordered by arrival, never by hlc; across devices the higher hlc wins. A write whose base
   > matches is stored with `max(hlc, successor(previous hlc))`. Clients fold every received hlc
   > into their clock and correct their wall clock from `server_ms`. `rev` is the server change
   > sequence at the doc's last change.

3. **"Protocol"** — replace the code block with:
   > ```
   > POST /v1/sync/push   { device_id, mutations: [Mutation] }
   >                      →  { results: [{op_id, status, doc, fields{name → outcome}, detail, original_status?, evicted[]}], server_ms }
   > GET  /v1/sync/pull?cursor=N&limit=M   →  { docs: [Doc], cursor, has_more, server_ms }
   >
   > Mutation { op_id, collection, id, trip_id, kind: "upsert" | "delete",
   >            fields{ name → new value }, base{ name → value on screen when edited },
   >            resolve[ alternative ids ], hlc }
   > status ∈ applied · merged · conflict · duplicate · rejected
   > outcome ∈ applied · merged · conflict · lost · noop · kept
   > ```
   > Push returns no cursor: a client must only advance its cursor through pull.

4. **"Idempotent" bullet** — replace with:
   > - **Idempotent**: ops are recorded per (user, `op_id`), in the same transaction as the change;
   >   replays return `duplicate` with the current doc. A batch may be cut short and resent whole.

5. **"Per field" bullet** — replace with:
   > - **Per field** (`s` server value, `b` base, `c` new value), first match wins: `c == s` → noop;
   >   field unset or pipeline-owned → apply; `b == s` → apply, whatever the clocks say;
   >   `c == b` → noop; otherwise both sides changed it:
   >   - scalar field → the winner by the clock rule stays; a losing mutation is dropped and
   >     reported as `lost` (status `conflict`);
   >   - merge field → sentence-aware three-way merge of (base, server, client). Edits merge
   >     automatically only if they are in different sentences, or insert whole sentences at
   >     different places, or are at least 4 unchanged words apart; the result is `merged`.
   >     Otherwise it is `conflict`: nothing is merged, the winner by the clock rule becomes the
   >     text and **the other whole version is appended to `conflicts`** with its device and
   >     time. Clients show it under the sentence ("Also written on *Phone*: … — Use this ·
   >     Dismiss"). Alternatives are content-addressed (identical ones dedupe), one equal to the
   >     current text is dropped, and at most 8 are kept per doc.
   > - **Resolving** is an upsert with `resolve: [ids]`: Dismiss sends no fields; Use this sends
   >   `fields{text: alternative}`, `base{text: text on screen}`. The server removes the listed
   >   alternatives first, then applies the fields. An alternative that was chosen (its value is
   >   the mutation's value or base) is put back if it does not end up as the text.
   >   Nothing a user typed is ever discarded silently.

6. **"Delete vs edit" bullet** — replace with:
   > - **Deletes** are tombstones (fields kept). A delete carries `base` = every client-writable
   >   field as seen and `resolve` = every alternative seen, and is refused (`conflict`) if a user
   >   edit it did not see exists: an unseen alternative, a changed merge field, a changed scalar
   >   with a winning clock, or a later restore. An upsert reaching a tombstone resurrects it if it
   >   carries a merge field, or wins by the clock rule, or the tombstone is the pipeline's. So a
   >   concurrent text edit always beats a delete; a concurrent scalar edit is last-writer-wins.
   >   Undo delete is an upsert with no fields.
   > - **Creates** use client-generated ids; the same id created twice merges per field with an
   >   empty base.
   > - **Authorization**: a trip belongs to one user; a mutation for a trip the user does not own,
   >   with a `trip_id` different from the doc's, or with an `hlc` device different from
   >   `device_id`, is `rejected` and returns no doc. An unknown trip can only be created.
   > - **Pull** returns each changed doc once, in its latest state, ordered by `rev`; `cursor` is
   >   the last returned `rev`. A doc that changes between pages is delivered again, never skipped.

7. **"Pipeline output" bullet** — replace with:
   > - Pipeline output goes through the same merge path with the reserved pseudo-device `pipeline`
   >   (internal entry point only). It never overwrites a field whose `meta.device` is a user
   >   device, never deletes a doc with a user-owned field or an alternative, and never resurrects
   >   a user's tombstone (D6). A user write to a pipeline-owned field always wins, even against a
   >   later regeneration.

8. **"On the client" paragraph** — replace the first three sentences (through "…pending local edit.") with:
   > Local store = last-synced docs + an **outbox** of pending mutations; what the UI shows is
   > always computed as synced docs with the outbox replayed on top, so a pull cannot clobber a
   > pending edit. `mutate()` records `base` as the value on screen (synced value plus this
   > device's earlier pending ops). A repeated edit folds into the last op for that doc only if
   > that op has never been sent, and the folded op keeps its original base. Ops are frozen
   > before a push leaves and resent unchanged until the server returns a result for them.
   > `sync()` is single-flight: push the outbox in order, adopt each returned doc if its `rev` is
   > not older, then pull from the client's own cursor until `has_more` is false.
   > `backend/atlas/sync/sim.py` is the executable specification of this engine.

9. **§1 repository layout** — `sync/` line becomes:
   > `sync/                hlc.py, textmerge.py, merge.py, server.py (pure; Store protocol), sim.py (reference client) + service.py (DB-backed Store)`

10. **§4 Storage** — add: "`applied_ops` is keyed by (user, op_id). `changes` only allocates the
    sequence; pull reads `docs` by (owner, rev)."

11. **DECISIONS D5** — "word-level three-way merge; if both sides changed the same words" should
    read "sentence-aware three-way merge; if both sides changed the same sentence close together".
