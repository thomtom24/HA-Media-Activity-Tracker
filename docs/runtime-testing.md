# Compatibility and runtime testing

The runtime workflow targets HA 2025.12.0 and 2026.11.3 using official container images. It boots the tagged v0.3.0 integration then restarts with the candidate, checking history, independent entries, a condition and reload. Consult Actions for actual results; the workflow does not emulate Marketplace UI or real streaming hardware.

| Source | Evidence | Limitations |
| --- | --- | --- |
| Roku | Initial playing/paused/menu/app change/standby samples | Standby depends on power wiring and source reporting |
| Other media players | Standard HA state and app attributes are used | Manufacturer-specific playback accuracy not verified |
| Independently powered TV sticks | Optional entity gate | Tracker/network state may lag |

Test installation from the repository link, upgrade with existing history, source replacement, mobile layout, restricted user accounts and multiple real devices before submission. Real screenshots should be captured by the owner; the README illustration is not a live screenshot.

The v0.3.1 runtime test also exercises an actual filesystem write failure and retry, private-file permissions, real HA User permission policies (with an in-process connection), and a mode change. The offline backup command is tested using disposable files. These are automated tests, not an actual Marketplace installation or end-to-end authenticated WebSocket session.
