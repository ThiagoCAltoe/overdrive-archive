# Contributing

Contributions are welcome.

1. Create a focused branch.
2. Write source UI copy and documentation in English. When user-facing copy
   changes, add or update its Brazilian Portuguese translation as well.
3. Add or update tests for behavior changes.
4. Run `make check`.
5. Run `node --check app/static/app.js` when browser code changes.
6. Never include real vehicle data, domains, IP addresses, access codes,
   coordinates, videos, thumbnails, databases, or logs.

New collectors should be read-only and use documented Overdrive HTTP APIs.
New destinations must stream data, write atomically where possible, and avoid
passing user-controlled values to a shell.
