# Changelog

## v0.3.1
- Restore comparable periods after mode/source changes; track hourly coverage and show observed-day averages and gaps separately.
- Reconcile continuous name-only sessions with unambiguous app IDs without rewriting unrelated history.
- Strengthen history and whole-number validation, report snapshots and frontend error recovery.
- Add storage/backup recovery, permissions and upgrade regression checks; validate release tags.

## v0.3.0
- Consolidated Marketplace preparation and audit hardening: branding, categories, unrestricted validation, version checks and documentation.
- Private atomic history, validation, storage error reporting, dirty checkpoints and shutdown save.
- Shared sensor snapshot, clock-jump protection, session timeout and cap, app ID fallback, source reconfiguration and mode-change warnings.
- Tracker and source read permissions, direct condition-loop protection, safer card configuration and CSV export, retries and responsive layout.
- Expand regression and runtime tests. Compatibility and user migration still require verification.

Note: v0.2.4 was tagged with internal version 0.2.1; this release restores version alignment.

## v0.2.1
- Classify Media Activity Tracker as a service so it appears in the main Integrations list instead of Helpers.
- Keep existing configuration entries, history, sensor identifiers and card settings unchanged.
- Synchronise the bundled card version and update installation instructions.

## v0.2.0
- Fix daily averages to exclude pre-installation dates; compare equivalent completed days and clock hours.
- Add configurable detailed session retention, anonymised condition diagnostics and clearer tracking states.
- Add real HTTP asset-serving and multiple-entry tests; isolate optional frontend registration failures.
- Bundle the existing dashboard card and editor in the tracker integration; one installation and release.
- Serve a versioned card module and register it once in storage-mode dashboards after loading resources.
- Keep tracker storage, report schema, sensor IDs and card configuration unchanged.
- Document migration from the standalone card and YAML resource setup.
- Combine Python, HA, JavaScript and browser tests.

## 0.1.1

- Fix initial config flow crash caused by assigning to Home Assistant's read-only `source` property.
- Add a regression test using the actual Home Assistant config flow base class.

## 0.1.0 (candidate)

Initial per-player tracking, conditions, persistent aggregates, sensors and card API.
