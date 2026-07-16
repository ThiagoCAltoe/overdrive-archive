# Overdrive compatibility

| Data | API used | MVP support | Notes |
| --- | --- | --- | --- |
| ACC / drive recordings | `/api/recordings` → `normal` | Yes | Archived under the `drive` subtype. |
| Instant replays | `/api/recordings` → `replay` or legacy `normal` | Yes | Supports both PR #150 and PR #152 classifications. |
| Surveillance recordings | `/api/recordings` → `sentry` | Yes | Supports Notice, Alert, and Critical filters. |
| Proximity recordings | `/api/recordings` → `proximity` | Yes | Optional recording type. |
| OEM dashcam recordings | `/api/recordings` → `oemDashcam` | Yes | Optional recording type. |
| Trips | `/api/trips` | Yes | Paginated summary snapshots. |
| Trip telemetry | `/api/trips/{id}/telemetry` | Yes | Archived once per completed trip. |
| Charging | `/api/charging` | Yes | Paginated session snapshots. |
| Automations | `/api/automations/list` | Yes | Read-only JSON snapshot. |
| Key mappings | `/api/keymap/config` | Yes | Read-only JSON snapshot. |
| Live telemetry | `/api/mqtt/telemetry` | Yes | Point-in-time snapshots, not a high-frequency stream. |
| RoadSense | `/api/roadsense/hazards?bbox=...` | Experimental | Best-effort geographic tiles; the viewport endpoint can cap results, so a snapshot may be incomplete. |
| Configuration | `/api/settings/unified` | Yes | Strict-allowlist snapshot only; unknown fields are discarded and full device backup is intentionally excluded. |

Unsupported endpoints are reported as partial sync errors rather than silently
disabling the whole run.

“Yes” means that the connector and archive format are implemented and covered
by synthetic tests. It does not mean that every endpoint has been validated on
every Overdrive release or vehicle installation. Recordings have a dedicated
media experience; the remaining collectors preserve JSON or GeoJSON snapshots
for browsing and download.

The connector accepts an 8-character access code, a full device token, or an
already-issued Overdrive bearer JWT. Access codes and full tokens are exchanged
through `/auth/token`; an existing JWT is used directly and must be replaced
after it expires. Credentials are sent only to the configured origin, and
cross-origin redirects are rejected.

The configuration collector is intentionally conservative. It retains only
explicitly approved scalar keys inside approved settings sections. Unknown
fields, unapproved containers, URLs, long strings, and arbitrary nested values
are discarded rather than copied and then filtered. The retained settings must
still be handled as sensitive data.

## Instant replay generations

[Overdrive PR #150](https://github.com/yash-srivastava/Overdrive-release/pull/150)
introduced manual instant replay:

- the vehicle writes independent
  `replay_YYYYMMDD_HHMMSS[_N].mp4` files;
- replay files share Overdrive's physical recordings directories and recording
  storage quota;
- the recording index exposes them as `type=normal`;
- they can be triggered by an eligible direct key mapping, but not by a key
  mapping sequence in that generation.

[Overdrive PR #152](https://github.com/yash-srivastava/Overdrive-release/pull/152)
is the later layout:

- existing `replay_` index rows are migrated to `type=replay`;
- `/api/recordings?type=replay` becomes the canonical query;
- Overdrive adds dedicated Replays views and replay status indicators;
- the files remain in Overdrive's shared recordings directories and continue
  counting against its recordings quota.

Overdrive Archive handles both. It prefers the explicit API type from PR #152
and falls back to the `replay_` filename when an older PR #150-era build reports
the item as `normal`. Archived files are organized separately:

```text
<archive>/<destination>/<vehicle>/recordings/replay/YYYY/MM/DD/
```

The compatibility logic is covered by local tests. Full device validation
against every Overdrive release and storage backend is still recommended while
this project is in early preview.

## Timestamps and ordering

Overdrive's recording index exposes the recording time in milliseconds. The
archive stores that source timestamp and lists newer recordings first. For
other archived snapshots that do not provide a source time, the library falls
back to the time the snapshot was archived. Seconds-based timestamps are also
normalized for compatibility with future or third-party collectors.

This ordering applies only to the Overdrive Archive web library. It does not
change the order shown by Overdrive inside the vehicle.

## Camera views in the archive player

Overdrive stores composed recordings as one MP4. Overdrive Archive keeps that
file unchanged and offers temporary **All**, **Front**, **Right**, **Rear**, and
**Left** views by cropping the playback surface in the browser.

The player supports the `standard` 2×2 and `dashcam` compositions. It uses
per-recording layout metadata when available, then the read-only layout
discovered from Overdrive. Older Replay files created by the PR #150 generation
may not have layout metadata; those use the same `standard` fallback as
Overdrive. OEM dashcam recordings are treated as a single-camera source.

Camera selection is never written back to Overdrive or to the archived MP4 and
resets to **All** whenever the player is closed.

## Responsibility boundary

Overdrive Archive is a read-only consumer of recordings exposed by the
Overdrive HTTP API. It does not:

- create an instant replay;
- configure physical key code `306` or any other key mapping;
- restart the vehicle camera daemon;
- control the CLIP status indicator;
- change the in-car Replays tab or its ordering.

Those behaviors are implemented by Overdrive PRs #150 and #152. This project
downloads the finalized files after Overdrive indexes them.

## Related upstream changes

[Overdrive PR #153](https://github.com/yash-srivastava/Overdrive-release/pull/153)
is display-only model localization. It keeps the canonical model ID `seagull`
and shows “BYD Dolphin Mini” for Brazilian Portuguese users. It does not change
recording APIs, archive paths, persisted model selection, or this project's
generic vehicle configuration.

[Overdrive PR #154](https://github.com/yash-srivastava/Overdrive-release/pull/154)
localizes Overdrive's in-vehicle Telegram bot. It is separate from the optional
Telegram one-time-code provider used to sign in to Overdrive Archive.

The upstream project is
[yash-srivastava/Overdrive-release](https://github.com/yash-srivastava/Overdrive-release)
and is distributed under the MIT License.
