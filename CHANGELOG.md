# Changelog

All notable changes to XTV-MediaStudio are documented here. Historical
entries (v1.5.x and earlier) are mirrored from the README release notes.

## [v1.6.0] — 2026-04-18

### Renaming & Auto-Detect

- **Fixed Movie confirmation menu** — "Change Specials", "Change Audio", and
  "Change Codec" buttons now appear reliably for Movies when the user's
  template contains the matching placeholders. Root cause was a singular-vs-plural
  template key mismatch (`"movie"` looked up against `"movies"` default key).
  Series happened to work only because singular == plural there.
  Added `utils.detect.template_key_for()` normalizer used everywhere template
  keys are derived from a detected media type. `database.get_filename_templates()`
  also normalizes legacy `movie` / `subtitles_movie` keys so existing user
  templates keep working.
- **Runtime Dual / Multi audio auto-fill** — before the final rename, the
  bot now probes the actual audio streams of the file via `ffprobe`
  (`utils.detect.probe_audio_streams`). If the user did not set Audio in
  the confirmation screen and did not explicitly lock it, detected 2-stream
  files get `DUAL` and 3+-stream files get `Multi` applied automatically.
  Works for Movies, Series and batch flows.
- **🚫 None (lock) buttons** — every "Change Audio / Codec / Specials" menu
  now has a dedicated lock button. Picking "None (lock)" prevents runtime
  auto-fill from overwriting the empty value. Picking any other value
  clears the lock automatically.
- **Season change FloodWait** — `handle_season_change_prompt` now retries
  on FloodWait the same way `handle_ep_change_prompt` does.
- **Archive password retry** — wrong password attempts no longer abort
  the flow; users get up to 3 tries before the session is cancelled.

### Runtime hardening

- **`utils/tasks.py`** — new `spawn()` wrapper replaces raw
  `asyncio.create_task()` for long-running coroutines. Uncaught exceptions
  now reach the log instead of dying silently; tasks are registered per
  user (and optionally by key) so they can be cancelled.
- **Cancel Task button** — in-progress status messages now carry an
  `❌ Cancel Task` inline button. Presses cancel the corresponding
  `process_file` task via `cancel_by_key()`; the status message is updated
  with a cancellation notice.
- **`utils/tg_safe.py`** — `safe_edit` / `safe_send` / `safe_edit_message_text`
  / `safe_answer` wrap Telegram calls with FloodWait retry and silent
  `MessageNotModified` handling. Available for future adoption in
  user-facing paths.
- **`process_file` outer try / except** — failures before `TaskProcessor.run()`
  (e.g. `db.ensure_user` DB outage) now surface a friendly error message
  instead of silently losing the task. `asyncio.CancelledError` is caught
  and reported as "Task Cancelled".
- **Peer cache logging** — `main.py`'s force-sub / database-channel peer
  caching no longer swallows errors silently. Failures log a warning so
  `PeerIdInvalid` issues are diagnosable.

### State management

- **Sliding TTL** — `utils/state.py::get_state()` / `get_data()` now bump
  the last-activity timestamp on every read. A user who is actively
  clicking through menus will never be cleaned up mid-flow by the 30-min
  janitor task.
- **`session_lock(user_id)`** — per-user `asyncio.Lock` registry exposed
  for handlers that do read-modify-write on `user_data`.
- **`@requires_state(...)` decorator** — optional helper that raises
  `ContinuePropagation` when the user's state doesn't match, so multiple
  text handlers across groups compose cleanly.

### Versioning

- Bumped `config.py::Config.VERSION` → `v1.6.0`
- Bumped `pyproject.toml::project.version` → `1.6.0`

### Files Added

- `CHANGELOG.md`
- `utils/tasks.py`
- `utils/tg_safe.py`

### Files Modified (primary)

- `config.py`
- `database.py`
- `main.py`
- `plugins/flow.py`
- `plugins/myfiles.py`
- `plugins/process.py`
- `pyproject.toml`
- `utils/detect.py`
- `utils/state.py`

---

## [v1.5.2] — 2026-01-xx

- `fix(shim)`: deterministic merge + deep-merge — feature toggles actually persist.
- `fix(admin)`: feature-toggle pagination, per-feature descriptions, cleaner callback grammar.
- Misc stability fixes around settings cache invalidation.

## [v1.5.1] — 2025-12-xx

- Broaden-audience refactor: TMDB API key now optional; affected features
  gracefully degrade via `utils.tmdb_gate`.
- Startup validation cleanup and clearer error messages for missing
  `BOT_TOKEN`, `API_ID`, `API_HASH`, `MAIN_URI`.

## [v1.5.0] — 2025-11-xx

- File Converter "mega edition".
- MyFiles v2.2 (tagging, smart collections, retention).
- Various UI polish.

---

<sub>Maintained for XTV Network Global by @davdxpx — updates posted in
the @XTVbots channel.</sub>
