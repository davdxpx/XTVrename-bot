# Changelog

All notable changes to XTV MediaStudio are documented in this file.

## [Unreleased] - 2026-04-16

### Added
- YouTube anti-bot hardening: player client rotation, cookie persistence in DB, typed errors, format fallback (`feat(youtube)` — #292, #298)
- Help menu submenus for File Converter, YouTube, MyFiles, and Dumb Channels (`feat(help)` — `db4a292`)

### Changed
- **Admin panel modularization**: extracted the monolithic `plugins/admin.py` into a clean `plugins/admin/` package with separate domain modules — dumb channels, usage dashboard, user moderation, general settings, feature toggles, thumbnails, templates, public settings, force-sub, MyFiles, payments, premium, text dispatcher, and noop callback (#302)
- Polished admin module after modularization, removed legacy monolith `_legacy.py` (`865acb2`, `f44e032`)

### Fixed
- Admin panel back button navigation targets (#303)
- YouTube `player_client` rotation on "Requested format is not available" error (`652757d`)
- Help tool buttons restored; enriched converter and bot-info guide (#297)

### Documentation
- README updated to document v1.5.2 — new tools, YouTube, dumb-channel wizard (#294)
