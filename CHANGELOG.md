# Changelog

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
