# Troubleshooting

Start with:

```bash
docker compose ps
docker compose logs storage-init archive
curl --fail http://127.0.0.1:8088/healthz
```

## The application does not start

- **Administrator password is missing:** set a unique value of at least 12
  characters in `.env` as `ARCHIVE_ADMIN_PASSWORD`.
- **`storage-init` fails:** verify that `ARCHIVE_DATA_PATH` and
  `ARCHIVE_HOST_PATH` exist or can be created, and that the configured
  `ARCHIVE_UID`/`ARCHIVE_GID` can own the mount roots.
- **NAS permission or root-squash error:** create the destination on the NAS
  with the intended numeric UID/GID, then rerun Compose. The initializer does
  not recursively change existing content.
- **Port already in use:** change `ARCHIVE_HTTP_PORT` in `.env`.

## The page opens on the server but not from another computer

The default `ARCHIVE_BIND_ADDRESS=127.0.0.1` accepts connections only on the
Docker host. Use an SSH tunnel, or bind to a specific trusted LAN/private-VPN
address. Binding to `0.0.0.0` exposes the port on every host interface; pair it
with an intentional firewall policy and never publish the service directly to
the internet.

## Test connection says the vehicle is unreachable

- Confirm that the URL in **Settings** resolves and is reachable from the
  Docker host, not only from your laptop.
- Confirm that the vehicle is online and Overdrive is running.
- If using Tailscale or another VPN, verify that the Docker host is connected
  to the correct network and can route to the vehicle.
- Use the Overdrive access code/full device token, or replace an expired bearer
  JWT.

## Manual synchronization is skipped

Manual and scheduled runs use the same network policy. When **Wi-Fi only** is
enabled, `/status` must report Wi-Fi; when an SSID allowlist is also configured,
the reported SSID must match it. Disable the switch temporarily only if using
the current reachable network is acceptable.

## A recording is missing immediately after it was created

Overdrive Archive downloads only finalized items already present in
`/api/recordings`. Wait for Overdrive to finish and index the recording, then
run synchronization again. Replay creation, key mappings, and the in-car
Replays view are controlled by Overdrive itself.

## A recording has no thumbnail

The archive first tries the thumbnail exposed by Overdrive and then uses the
`ffmpeg` included in the container to generate a local JPEG. A corrupt,
incomplete, or unsupported source file can still appear without a thumbnail.
Check the synchronization run and container logs.

## A recording downloads but does not play in the browser

The project preserves the original MP4 and does not transcode it. Inline
playback depends on codec support in the browser and operating system. Try a
different browser or download the original file and open it in a compatible
player.

## Synchronization stops because storage is full

`ARCHIVE_MAX_RECORDING_GB` limits one incoming file; it is not a library quota.
Monitor free space for both `ARCHIVE_DATA_PATH` and `ARCHIVE_HOST_PATH`.
Overdrive Archive does not yet delete old archive content automatically.
