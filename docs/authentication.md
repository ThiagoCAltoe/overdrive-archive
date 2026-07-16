# Authentication architecture

Overdrive Archive exposes only the sign-in methods configured by the operator.
Local password login is the default; Telegram and WhatsApp are optional.
One, two, or all three methods may be enabled.

## Local credentials

The administrator password is transformed with `scrypt` using:

- a random 128-bit salt;
- `N=32768`;
- `r=8`;
- `p=1`;
- a 256-bit derived key.

The plain password is never stored in SQLite.

When local login is enabled, startup requires
`ARCHIVE_ADMIN_PASSWORD` to contain at least 12 characters. The public
`.env.example` intentionally leaves it empty. Generate a unique value before
first start:

```bash
openssl rand -base64 32
```

## Sessions

A successful authentication creates a random opaque session token. Only an
HMAC-SHA-256 digest of that token is stored in SQLite.

Sessions have:

- 12-hour absolute expiration;
- one-hour inactivity expiration;
- revocation on logout;
- periodic cleanup;
- `HttpOnly` and `SameSite=Strict` cookies;
- optional `Secure` cookies for HTTPS deployments.

Restarting the container does not silently invalidate every session because
session state is persisted. Deleting the `/data` volume invalidates sessions.

## Brute-force controls

All methods share an authentication event ledger:

- repeated failures introduce progressive server-side delay;
- eight local-password failures lock the local account for 30 minutes across
  all requesting identities;
- eight OTP verification failures lock only that provider and requesting
  identity combination for 30 minutes, so one client cannot globally disable
  an OTP provider;
- twenty failures from one network identity lock that network for one hour;
- OTP delivery is limited to five requests per identity in 15 minutes, with a
  separate provider ceiling of 30 requests in 15 minutes;
- OTP verification attempts are capped per issued code.

Local account limits are global, so changing IP addresses does not bypass a
password lock. OTP codes and verification-failure buckets are bound to the
identity that requested the code.

The server also permits at most four authentication operations concurrently,
which bounds the CPU and outbound-provider work an unauthenticated client can
trigger.

## Telegram

Telegram delivery uses the official bot `sendMessage` endpoint. A single
configured chat ID receives the code.

The bot token is read from an environment variable or Docker secret file and is
never returned by the web API.

## WhatsApp

WhatsApp delivery is intentionally provider-neutral. The application sends one
JSON request to an operator-controlled gateway:

```json
{
  "recipient": "...",
  "message": "...",
  "purpose": "overdrive-archive-login"
}
```

This keeps private gateway implementations and personal phone numbers out of the
public project.

Public webhook hosts must use HTTPS. Plain HTTP is accepted only for local or
private-network gateways. Redirects may not change scheme, host, or port, so a
configured bearer token is never forwarded to another origin.

## Provider selection

To use only Telegram or WhatsApp:

1. keep local login enabled during initial setup;
2. configure the selected provider;
3. sign out and verify that one-time-code delivery and login work;
4. set `ARCHIVE_AUTH_LOCAL_ENABLED=false`;
5. clear `ARCHIVE_ADMIN_PASSWORD` and restart the stack.

The application refuses to start when no authentication provider is configured.
It can detect whether provider settings are present, but it cannot prove that a
remote bot token or webhook is valid during startup. Testing the provider before
disabling local login prevents an avoidable lockout.

## File-backed secrets

The application reads these optional file variables:

- `ARCHIVE_ADMIN_PASSWORD_FILE`;
- `ARCHIVE_TELEGRAM_BOT_TOKEN_FILE`;
- `ARCHIVE_WHATSAPP_WEBHOOK_TOKEN_FILE`.

The referenced path must exist inside the application container. Setting an
`_FILE` variable alone does not mount the host file.

The included `compose.secrets.yaml` override mounts a Docker Compose secret for
the local administrator password:

```bash
mkdir -p secrets
openssl rand -base64 32 > secrets/archive_admin_password
chmod 700 secrets
chmod 600 secrets/archive_admin_password
docker compose -f compose.yaml -f compose.secrets.yaml up -d --build
```

Use the same Compose `secrets` pattern for Telegram or WhatsApp tokens. Never
place provider tokens in a committed Compose file.

## Reverse proxies

The application does not blindly trust `X-Forwarded-For`, because accepting that
header from an untrusted client would allow rate-limit spoofing. A reverse proxy
therefore shares the socket-address rate-limit bucket by default while the
global local-account lock still protects the password credential. OTP codes and
their verification buckets use that same observed requesting identity.

The client must request and verify an OTP through the same observed identity.
An IP change between those two steps can invalidate the code; behind a reverse
proxy, both requests normally share the proxy's socket identity.

Deploy the service behind a trusted VPN or reverse proxy and enable HTTPS before
setting `ARCHIVE_SECURE_COOKIES=true`.

The default Compose configuration binds to `127.0.0.1`. Set
`ARCHIVE_BIND_ADDRESS=0.0.0.0` only when trusted LAN or VPN clients need direct
access.
