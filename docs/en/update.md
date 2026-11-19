# Update an existing installation

Since v1.4.2, user-local history is decoupled from addresses and installation paths, including ad-hoc --endpoint. [Inspect and associate missing legacy records once](commands.md#replace-a-server-and-retain-sessions); ordinary server switching only selects an endpoint.

v2.0.0 updates include templates/ as replaceable program files. Personal AGENTS.md lives in the user configuration directory and is not overwritten. If the old updater lacks templates in its allowlist, obtain the newer scripts/update.py from the same target archive first. The updater does not apply rules. After updating client source, run ./local-ai install --role client as the actual chat user (optionally --instructions bcm) to apply new templates without redownloading verified binaries. Use --instructions none for self-managed rules, then exit/resume OpenCode after applying. See [persistent instruction setup](../../templates/opencode/en/agent-instructions.md).

Use this for program-only upgrades of an installed local-ai directory. See [README](../../README.en.md) for first installation and [offline deployment](offline.md) for complete resource migration. The updater downloads a small source archive and invokes no install, Docker, model download or OpenCode installation commands.

Update the GPU001 and bcm-headnode program directories separately. Examples use /raid/local-ai; replace --root if the actual program lives elsewhere. It must contain local-ai and src/, not just model data. Python 3.10+ and write permission on the installation and its parent are required; online script retrieval needs curl.

## Check active clients before updating

These capabilities ship in v2.0.0. Obtain scripts/update.py from the target source when using an older helper. Run on the machine containing the installation:

    python3 scripts/update.py --root /raid/local-ai --check

The check is read-only: no download, update lock, backup or conversation-body access. JSON activity_check lists this installation's PIDs, kind, executable and UID. ready=true exits 0; activity or incomplete visibility exits 3 (ready=null when unavailable). This is a snapshot, not a barrier against later launches.

Updates/rollbacks check before downloading; updates check again before replacement. Detected activity exits 1 by default without replacement or signals. To deliberately retain running clients during a program-only update/rollback, add --allow-active-clients to the original command. It never stops, detaches, restarts or upgrades native OpenCode. Exit and resume later to load changed code/instructions.

Linux detection uses visible /proc entries for native OpenCode under clients/ and Bash/Python launchers in this installation, not similar path prefixes. External --client-dir locations, other hosts, invisible processes and later launches are not fully covered. Unavailable/incomplete visibility is warned about; failure to inspect unrelated processes does not establish safety or cause automatic stops. Confirm manually.

New backups also contain backup/update.py. JSON returns rollback_command as arguments; stderr prints the shell-quoted command. Recovery works even if the installed launcher/scripts are missing. backup_scope=program-and-installation-metadata, history_backed_up=false and native_client_changed=false. Program backups exclude private chat databases and personal AGENTS.md. Native OpenCode upgrades are separate: exit sessions and protect full private state first; program rollback cannot downgrade its database.

## Bootstrap and upgrade

v2.0.0 includes scripts/update.py. For an older installation without the helper, obtain it separately using the commands below. Exit local chat and avoid launching management commands during replacement. GPU inference can remain running.

On GPU001, and separately on BCM for its own installation:

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v2.0.0/scripts/update.py -o /tmp/local-ai-update.py
python3 /tmp/local-ai-update.py --root /raid/local-ai --version v2.0.0
/raid/local-ai/local-ai --version
```

--version explicitly selects a Git tag. Substitute the next target version when appropriate; the updater neither tracks main automatically nor treats v2.0.0 as an allowlist. Success exits 0 with state=updated, version=1.4.4, resources_changed=false, service_restarted=false and the actual backup path.

The helper is retained at scripts/update.py inside the installation. Later updates can use it directly:

```bash
cd /raid/local-ai
python3 scripts/update.py --root /raid/local-ai --version v2.0.0
```

This example still selects v2.0.0; replace the version for a later upgrade. Repeating it verifies source and creates another program backup without handling large resources. When an old tag lacks the updater, the currently running helper is retained for future updates and exports.

## Check the result

v2.0.0 includes the GB200 TP4 candidate and Rubin TP2 framework. Retain custom catalogs and
explicitly merge new recipes. Updating does not clear Rubin's planning_only or supply an image;
see the [dedicated guide](gb200-rubin.md).

On GPU001, inspect the existing instance:

```bash
cd /raid/local-ai
./local-ai server status --name a
```

On BCM, inspect the saved connection:

```bash
cd /raid/local-ai
./local-ai chat --check
```

Both should report ready=true. Program updates do not change running profiles, ports or launch arguments. Enable DSpark separately through [instance replacement and warmup](deployment.md#single-user-dspark-and-explicit-warmup). If a later version selects different weights/images, prepare those resources separately; the updater never downloads them.

v2.0.0 includes server benchmarks and client diagnostics; update each host to use its new commands.
After deploying source containing the feature, run the [local performance benchmark](commands.md#local-performance-benchmark) on GPU001 only;
no BCM update or model/image download is needed. Updating does not run a benchmark. Historical benchmark JSON under instances/ is retained;
measure again after changes to program/image or other test conditions.

## Preserved state and backups

- models/, images/, clients/, instances/, dist/ and config/ are not replaced. Private histories and the installed OpenCode release remain unchanged.
- installation.json retains role, endpoint, model, default profile and other fields; only the program version changes and the old bundle_sha256 is removed.
- Ordinary program files and src/, docs/, scripts/, tests/ and related source directories are replaced. Local source edits are backed up, not merged; keep business files outside program directories.
- Old bundle.json is saved in the backup and removed from the active root because it describes pre-update source checksums. Run export again for a new deployment bundle; the old manifest does not validate updated source.
- Backups are siblings named local-ai-backup-RANDOM/, containing program files and installation metadata only. program/ holds old code, metadata/ holds installation records/bundle manifests, and update.json records source/target versions and archive SHA256. Weights, images, client assets and runtime caches are not copied.
- Progress and backup paths use stderr; results use JSON stdout. Successful update/rollback also appends to install.log in the installation root. Argument-parsing errors exit 2; execution/validation errors exit 1; interruption exits 130. Caught replacement failures restore the previous program. After forced termination or power loss, recover using the backup.

Custom config/catalog.json or LOCAL_AI_CATALOG still fully replaces built-in recipes. If a new profile is absent, merge it using the [development guide](development.md#model-and-client-compatibility), preserving custom configuration.

## Offline program update

On an online preparation host, put the helper, small source archive and checksums on media. No model export is needed:

```bash
mkdir -p /media/local-ai/update
cd /media/local-ai/update
curl -fL --retry 3 https://raw.githubusercontent.com/junli-nv/local-ai/v2.0.0/scripts/update.py -o update.py
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v2.0.0.tar.gz -o local-ai-v2.0.0-source.tar.gz
sha256sum update.py local-ai-v2.0.0-source.tar.gz > SHA256SUMS
```

Mount that media at /media/local-ai on the target, then run:

```bash
cd /media/local-ai/update
sha256sum -c SHA256SUMS
python3 update.py --root /raid/local-ai --archive local-ai-v2.0.0-source.tar.gz
/raid/local-ai/local-ai --version
```

--archive is offline and accepts source tar archives only. Complete deployment bundles containing models/, images/ or other resources are rejected. Optional --sha256 HEX checks an expected source-archive checksum from a trusted manifest. Without it, the actual digest is recorded without claiming independent provenance verification. Use the same post-update service/client checks above.

## Rollback

Replace /raid/local-ai-backup-EXAMPLE below with the actual backup value. Copy the helper into /tmp first because restoring an older program can remove its installed helper:

```bash
cp /raid/local-ai/scripts/update.py /tmp/local-ai-update.py
python3 /tmp/local-ai-update.py --root /raid/local-ai --rollback /raid/local-ai-backup-EXAMPLE
/raid/local-ai/local-ai --version
```

If interruption removed the launcher or scripts directory, use the bootstrap helper already saved in /tmp, or obtain it again using the first section. Rollback does not require working installed modules. Offline recovery can use the helper on the media.

Success reports state=rolled-back. It restores pre-update code, installation.json and bundle.json without changing weights, images or running containers. Record any endpoint/model changes made since updating and reapply them with config set if needed. Use the backup belonging to this installation; the script checks the root path, not host identity, so do not mix backups between nodes.

Help and complete options:

```bash
python3 /raid/local-ai/scripts/update.py --help
```

| Option | Meaning |
|---|---|
| --root | Required actual installation directory |
| --version | Download a numeric version tag from this repository, optionally prefixed v |
| --archive | Local source tar archive; offline |
| --rollback | Restore a backup created by the updater |
| --sha256 | Optional expected source checksum; incompatible with --rollback/--check |
| --check | v2.0.0: read-only check, no download/replacement; exit 3 if not ready |
| --allow-active-clients | v2.0.0: explicitly allow detected activity for program-only update/rollback without stopping or upgrading native clients |

For updates/rollbacks select one of --version, --archive and --rollback; v2.0.0 --check is a separate mutually exclusive read-only mode. This updates an unpacked source installation, not system drivers, container runtimes or Python environments.

[中文（默认）](../update.md)


Private conversation backups are separate: [history backup/restore](automation.md). v2.0.0 keeps OpenCode 1.19.5; exit/resume chat to load changed plugins. No inference restart is needed.
