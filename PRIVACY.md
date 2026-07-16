# Privacy

Overdrive Archive is self-hosted and does not include analytics or telemetry
sent to the project maintainers.

The data selected by an operator may still be highly sensitive:

- recordings can contain faces, plates, homes, and conversations;
- trips and RoadSense data can reveal precise locations;
- telemetry can contain vehicle identifiers and location;
- a full upstream configuration export could contain credentials or
  device-bound key material.

For that reason, full configuration backup is intentionally not implemented by
this project.
The `configuration` collector stores a strict-allowlist settings snapshot. It
keeps only explicitly approved scalar keys inside approved sections and
discards unknown fields, unapproved containers, URLs, long strings, and
arbitrary nested values. It does not rely on recognizing sensitive field names.
The retained snapshot can still reveal vehicle behavior and preferences and
must be treated as sensitive.

The Overdrive access code or token entered in Settings is retained inside the
private SQLite state under `/data` so scheduled synchronization can reconnect
without operator input. The application creates that state with restrictive
filesystem permissions, but it is not application-level encrypted. Protect and
encrypt the host filesystem and every backup containing `/data`.

HTTP access logs omit client IP addresses by default. Connector errors shown in
the interface and stored in run history use project-controlled messages rather
than copying arbitrary response bodies returned by the vehicle.

Retention, access control, encryption of the host filesystem, and compliance
with local surveillance/privacy law remain the operator's responsibility.
