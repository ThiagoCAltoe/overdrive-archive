# Security policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose vehicle
access tokens, recordings, telemetry, location history, or archived
configuration. Submit a
[private vulnerability report](../../security/advisories/new) through GitHub
Security Advisories and include:

- the affected version or commit;
- reproduction steps;
- the expected impact;
- a suggested mitigation, if available.

## Deployment expectations

Overdrive Archive handles private vehicle data. Operators should:

- use a long, unique `ARCHIVE_ADMIN_PASSWORD`;
- enable only the authentication providers they intend to use;
- keep the default `ARCHIVE_BIND_ADDRESS=127.0.0.1` unless trusted LAN or VPN
  clients require direct access;
- expose the service only through a trusted LAN, VPN, or authenticated reverse
  proxy;
- enable HTTPS before setting `ARCHIVE_SECURE_COOKIES=true`;
- keep the `/data` and `/archive` volumes private;
- use host, dataset, or full-disk encryption for `/data`, because it contains
  the saved vehicle credential needed for scheduled synchronization;
- avoid committing `.env`, databases, recordings, exports, or logs;
- rotate the Overdrive device access token if it may have been disclosed.

The long-running application service runs as a non-root user, drops every Linux
capability, uses a read-only root filesystem, and does not require privileged
mode or access to the Docker socket. A one-shot storage initializer runs as root
with networking disabled and only `CHOWN`, `SETUID`, and `SETGID`; it prepares
the `/data` and `/archive` mount roots, then exits before the application starts.

The Compose defaults also limit the application to 256 processes/threads and
768 MiB of memory. Operators may tune `ARCHIVE_PIDS_LIMIT` and
`ARCHIVE_MEMORY_LIMIT` for their host after observing normal workloads.

## Authentication protections

- Local passwords are stored as salted `scrypt` hashes.
- Sessions are random, revocable, server-side records with absolute and idle
  expiration.
- Local-password failures are limited globally by account and by network
  identity.
- OTP verification failures are isolated by provider and requesting identity;
  delivery also has per-identity and higher provider-wide ceilings.
- Repeated failures trigger progressive delays and temporary lockouts.
- Authentication work is limited to four concurrent operations.
- Telegram and WhatsApp codes expire after ten minutes and can be used once.
- Provider tokens are read from environment variables or secret files and are
  never returned to the browser.

Environment variables are visible to Docker administrators. For production,
prefer file-backed values mounted with Docker Compose secrets. The supplied
`compose.secrets.yaml` is a local-password example; site-specific overrides can
use the same pattern for Telegram and WhatsApp tokens.

See [docs/authentication.md](docs/authentication.md) for the threat model and
operational details.
