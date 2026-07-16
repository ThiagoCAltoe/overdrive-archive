## Summary

Describe the user-visible behavior and why the change is needed.

## Validation

List the commands, environments, and device or mock scenarios used.

## Privacy and security

Describe any effect on authentication, vehicle access, recordings, telemetry,
network exposure, storage permissions, or redaction.

## Checklist

- [ ] Source UI copy and documentation are in English, and affected pt-BR
      translations were updated.
- [ ] Tests were added or updated where behavior changed.
- [ ] `make check` passes.
- [ ] `node --check app/static/app.js` passes when browser code changed.
- [ ] No real access codes, tokens, domains, IP addresses, coordinates,
  recordings, thumbnails, databases, or logs are included.
- [ ] New settings are configurable and have safe defaults.
- [ ] Overdrive API or recording-type compatibility is documented.
- [ ] Documentation and the changelog were updated when appropriate.
