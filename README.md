# Media Activity Tracker

Local, per-media-player playback analytics for Home Assistant 2025.12+. Companion [dashboard card](https://github.com/thomtom24/HA-Media-Activity-Card).

## Install
Add this repository as an Integration custom repository in HACS, install, restart Home Assistant, then add Media Activity Tracker in Settings → Devices & services. Choose one player per instance. Add another instance for another player. No YAML required.

## Tracking
Playback (default) counts only the reported playing state, excluding common home screens. App activity counts an identified foreground app even when idle/paused; powered-on time counts active source states including menus. Labels always reflect the configured mode; these are device activity metrics, not verified human viewing. App ID is preferred, with name and source fallbacks. Unknown apps are counted in playback/power modes. Configure comma-separated exclusions using app names or id: identifiers. Additional conditions can use any HA entity, raw state equality/inequality or strict numeric above/below, AND/OR. Unknown/unavailable inputs never satisfy a comparison; with OR another valid condition may still permit tracking. Use one comparison per entity. Options can be edited after setup. Wi-Fi trackers and source state updates can lag.

## Statistics
Independent local calendar days, Monday weeks, months, years, rolling 7/30/90/365 days, app totals, sessions, longest daily session contribution and daily averages. Pauses/buffering retain a session for the same app; condition failure, app change, idle/off/unavailability ends it. Session counts represent sessions touching a day (a midnight-spanning session counts on both days). Longest is the longest single-day session contribution within the period. Calendar week/month comparisons use equivalent elapsed calendar days, not equivalent time of day. Averages include zero days before installation; use the recorded-since label to interpret them. Daily aggregates retained until the integration is removed, session details 90 days (last 500 returned). No historical backfill, media titles, telemetry or network access. Checkpoint roughly every 30 seconds; unobserved outages are not counted, abrupt shutdown can lose the last checkpoint interval. Removal deletes that instance's history. Back up HA storage. Changing timezone does not rebucket previously stored days.

## Card API
Authenticated WebSocket command media_activity_tracker/report with entry_id (from Tracking status sensor's tracker_entry_id attribute) and optional days (1–3660, default 366). Requires read permission on the source entity. Schema 1: seconds, stable app keys, periods day/week/month/year/7/30/90/365, history daily rows, sessions and current status. Card polls the local API; no external service. CSV export is client-side.

## Development
Initial v0.1.0 candidate. Run python -m unittest discover -s tests and python -m compileall -q custom_components. Real HA testing required before release. See LICENSE.
