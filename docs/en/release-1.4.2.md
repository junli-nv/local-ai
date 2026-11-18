# v1.4.2: decouple local session history from server addresses

A fixed user-local identity retains history across saved and ad-hoc endpoints and installation-directory changes. Endpoints select inference routing only; projects and session IDs are retained. Explicit --state-dir provides separate history.

- client history list: read historical addresses, session counts and default markers; --json is available.
- client history update-endpoint --old URL --new URL: recover legacy histories keyed by address, rejecting destinations with separate sessions.
- opencode -s ID: preserve session IDs, original working directories and history, using the current saved server for default history.
- Bilingual contributor guidance requires fetching remote code/tags before changes, preserving edits, testing merged code and rechecking before release.

Databases, snapshots and tool outputs stay in place. Private metadata backups support rollback on caught write failures; the old server need not be online. Updating history does not edit installation.json; use config set endpoint for defaults. Ordinary future server replacement requires no repeated history update.

See the [manual](commands.md#replace-a-server-and-retain-sessions) for recovery and forgotten addresses, and [validation](validation.md) for scope. No cross-BCM migration, nonempty-history merge or GPU backend changes. OpenCode 1.19.5 binaries are retained. Preserve existing tags; create only the requested new tag, without automatically creating a GitHub Release.

[中文](../release-1.4.2.md)
