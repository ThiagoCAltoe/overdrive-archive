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

This release does not automatically delete archived files and does not enforce a
total archive quota. `ARCHIVE_MAX_RECORDING_GB` is a safety limit for one
download, not a storage budget.

Monitor free space for both:

- `ARCHIVE_DATA_PATH`, which contains SQLite and authentication state;
- `ARCHIVE_HOST_PATH`, which contains recordings and JSON exports.

Use NAS snapshots, filesystem quotas, or external retention tooling until the
planned application retention policies are available. If the archive volume is
full, a synchronization can finish as partial or failed; existing archived
files are not deleted to make room.

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
