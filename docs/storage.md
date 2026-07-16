# Storage configuration

The storage design deliberately separates host authority from application
organization.

## Host or NAS path

Docker Compose reads:

```dotenv
ARCHIVE_HOST_PATH=/mnt/nas/overdrive-archive
```

and mounts that path to `/archive`.

Application state is separate:

```dotenv
ARCHIVE_DATA_PATH=./data
```

That directory contains SQLite, settings, login sessions, and the session
signing key. Back it up and protect it like the archive itself.

The host administrator controls mounts and filesystem permissions. The
application runs as UID/GID `10001` by default. A short one-shot
`storage-init` service checks `/data` and `/archive`, adjusts only the ownership
of those two root directories when the filesystem permits it, and exits before
the application starts. The long-running service secures a new or empty
default-mode archive root to `0700`; it preserves non-empty archives and custom
root modes such as `0770`.

If a NAS expects another numeric identity, configure:

```dotenv
ARCHIVE_UID=1026
ARCHIVE_GID=100
```

The application service then runs with that identity. Existing archive
subdirectories are never recursively changed by the initializer.

The long-running application process is unprivileged. The initializer is a
short root process with networking disabled and only the `CHOWN`, `SETUID`, and
`SETGID` capabilities needed to prepare and test the two mount roots.

## Web destination

The web interface stores an archive subdirectory such as:

```text
vehicles
```

or:

```text
family/byd
```

Path validation rejects empty path segments, `.` and `..`, and characters
outside a conservative allowlist. Every resolved file is checked to remain
under `/archive`.

## Changing destinations

Changing the web destination affects new artifacts. Existing inventory entries
continue to reference their original relative paths.

Changing `ARCHIVE_HOST_PATH` moves the entire mounted archive. Copy the existing
files to the new host directory before restarting if the library should remain
available.

## Capacity and retention

Local retention is disabled by default. The web settings provide independent
age policies for recordings, trips, charging, automations, key mappings,
telemetry, RoadSense, and sanitized configuration. Each rule accepts minutes,
hours, or days and can protect the newest configured number of items. Age uses
the original source timestamp when available, with local archive time as the
fallback. Saving settings applies enabled rules immediately to local files.

An optional global archive-size limit is also available. The interface reads
the mounted filesystem capacity and does not offer a larger value. With the
limit disabled, the application does not impose a quota and may use the entire
available filesystem. `ARCHIVE_MAX_RECORDING_GB` remains a separate safety
limit for one incoming recording.

When a policy applies, the application deletes only local primary content and
known sidecars, including resumable partials. For recordings it keeps a
zero-byte **Deleted locally** placeholder while the vehicle still reports the
original. The placeholder blocks automatic redownload and offers **Download
again**. A restored file is pinned against automatic retention until **Use
retention rules** removes that pin; current rules may then apply immediately.

The placeholder is removed only after a complete, internally consistent remote
listing confirms that the recording left the vehicle. Failed, partial, timed-out,
or cancelled listings never purge it. The application never calls a deletion
endpoint on the vehicle. Protected newest or manually restored items are not
removed to satisfy the global limit. Save responses and synchronization details
report when protected or unmanaged files prevent the configured target from
being reached.

Continue monitoring free space for both:

- `ARCHIVE_DATA_PATH`, which contains SQLite and authentication state;
- `ARCHIVE_HOST_PATH`, which contains recordings, JSON exports, resumable
  partials, and sidecars.

Filesystem or NAS snapshots remain recommended because retention is not a
backup. If the archive volume fills before cleanup can run, a synchronization
can still finish as partial or failed.

## Recommended NAS setup

1. Mount NFS or SMB on the Docker host.
2. Set `ARCHIVE_UID` and `ARCHIVE_GID` when the share uses a specific identity.
3. Set `ARCHIVE_HOST_PATH` to that mounted directory.
4. Start the container.
5. Set the logical subdirectory in the web interface.

The container does not require `SYS_ADMIN`, privileged mode, or network
filesystem credentials. If the storage initializer reports a permission error,
grant the configured UID/GID write access on the host or NAS and start the
stack again.
