# Changelog

## 0.1.0 - 2026-07-16

- Initial self-hosted MVP.
- Docker Compose deployment.
- Configurable manual, interval, and daily synchronization.
- Optional Wi-Fi and SSID gating.
- Recording, trip, charging, automation, key mapping, telemetry, RoadSense,
  and strict-allowlist configuration collectors.
- Local or mounted-NAS archive destination.
- Authenticated web dashboard and media library.
- Visual recording gallery with authenticated thumbnails and HTTP Range
  playback.
- Temporary all-camera and enlarged single-camera views for supported Overdrive
  mosaic layouts.
- English and Brazilian Portuguese interface options, with English as the
  default for new installations.
- Local `ffmpeg` thumbnail fallback when Overdrive does not provide an image.
- Dedicated replay subtype with compatibility for Overdrive PR #150
  (`type=normal` plus `replay_` filename) and PR #152 (`type=replay`).
- Optional import of Overdrive's selected visual profile without a fixed model;
  manual model, color, and drive-side values remain persistent.
- Local password, Telegram code, and WhatsApp webhook authentication options.
