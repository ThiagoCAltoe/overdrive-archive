# Architecture

```text
Overdrive in the vehicle
  └─ authenticated HTTP API
         │ LAN or private VPN
         ▼
Overdrive Archive container
  ├─ connector and collectors
  ├─ scheduler and Wi-Fi policy
  ├─ SQLite inventory and run history
  ├─ authenticated web interface
  └─ filesystem destination
         ▼
local disk or NAS mounted into /archive
```

The MVP uses a pull model: the container initiates every connection to the
vehicle. It never changes Overdrive settings and uses `GET` requests for data;
when an access code or full device token is configured, the only `POST` sent to
the vehicle is authentication at `/auth/token`. An already-issued bearer JWT
skips that exchange.

## Idempotency

Recordings use a stable source key containing the source identity, filename,
and recording timestamp. Expected size is deliberately not part of that
identity, so corrected size metadata does not create a duplicate item. JSON
snapshots are keyed by their SHA-256 digest. Downloads are streamed into a
`.part` file, hashed, flushed, and atomically renamed before being added to the
SQLite inventory. A small durable completion proof binds the source identity,
byte count, and SHA-256 digest until the inventory and optional sidecars are
committed. If the vehicle removes a recording during that window, the next run
can validate and inventory the completed local bytes instead of discarding the
only copy; ambiguous partial data is retained for inspection rather than
inventoried as a recording.

Recording types are normalized into archive subtypes such as `drive`, `replay`,
`surveillance`, `proximity`, and `oem_dashcam`. Overdrive PR #150-era replay
rows are recognized from their `replay_` filename even when the API reports
`type=normal`; PR #152 and later can report the explicit `replay` type.
Unrecognized future source types can be preserved under a safe normalized
subtype instead of being silently discarded.

## Wi-Fi policy

When `Wi-Fi only` is enabled, the sync engine reads `/status` and requires
`network.type == "wifi"`. An optional SSID allowlist can narrow the policy.
The connector checks the network again while downloading large files.

This is best-effort in a server-side pull design. A future vehicle-side push
agent can enforce the policy before and during upload without relying on
periodic status checks.

## Extension points

Collectors are read-only mappings from Overdrive APIs to archived artifacts.
The initial destination is a filesystem, which also supports NAS devices by
mounting NFS or SMB on the Docker host. Future destination adapters can add
SFTP, WebDAV, or S3-compatible object storage without changing collectors.
