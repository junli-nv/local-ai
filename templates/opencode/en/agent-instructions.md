# Persistent instructions on the client

These maintained references reduce repeated correction in new conversations; prompts cannot guarantee compliance.
They are separate from repository development instructions. Since v1.4.3, client installation applies the general template by default.

## Files and host

Combine the [general template](AGENTS.general.md) with the [BCM template](AGENTS.bcm.md) when appropriate.
The general template covers response language, user-source attribution, and waiting/progress updates for long tasks without imposing a default language.
It also includes project locations and chat working-directory constraints, so copying it carries those rules into personal instructions.
The template's own language does not determine the response language.
Adapt cluster paths, especially /cm and /cm/images. Use either language, not both copies.
See [Claude Code prompt references and adaptations](../../../docs/en/prompt-references.md) for pinned third-party sources, official-source scope, the change mapping and evaluation limits; external prompts are not loaded directly.
[中文](../agent-instructions.md).

Run on bcm-headnode as the actual chat user, not on GPU001. Examples use installation /raid/local-ai and
existing task directory /home/alice/project; replace them with actual paths.
The personal file defaults to ~/.config/opencode/AGENTS.md; for root it is /root/.config/opencode/AGENTS.md.
When XDG_CONFIG_HOME is set before local-ai starts, use $XDG_CONFIG_HOME/opencode/AGENTS.md.
Changing the user/HOME through sudo changes the personal location; check the actual launch environment.

v1.4.0 resolves that personal path before isolating OpenCode's session configuration.
An existing personal file is explicitly appended to instructions after built-in operations.md.
Other personal model/plugin/connection settings are not imported; chat startup itself does not rewrite personal rules.
The native client still discovers project AGENTS.md. Instructions are combined: resolve conflicts explicitly
rather than relying on order. Original v1.3.7 source lacks this loading bridge; use v1.4.0 or later, and record the commit for development branches.

## Apply during installation

Run on the client as the actual chat user. Do not switch to root merely to configure personal rules. A sudo/root installation configures only its running user, not an inferred account or every user. Templates default to Chinese; their language does not determine the response language.

```bash
cd /raid/local-ai
./local-ai install --role client --endpoint http://GPU001:18000/v1
# General plus BCM rules
./local-ai install --role client --instructions bcm
# English rules
./local-ai install --role client --instructions bcm --instructions-language en
# Prepare client assets without creating or modifying personal rules
./local-ai install --role client --instructions none
```

Both install --role client/both and lower-level client install accept these options. Server-only installation does not configure personal rules. Offline behavior is identical and needs no template download. Use --instructions none on preparation hosts that only package assets. Reinstallation reuses verified client binaries and does not start GPUs.

JSON client.instructions (instructions for the lower-level command) reports path, status (created/updated/unchanged/skipped), template and language, plus backup when an existing file changes. Skipping returns only status. Progress and backup paths go to stderr and install.log.

- Create a missing file; otherwise append one local-ai managed block while retaining existing content.
- Reinstallation replaces only the block between `<!-- local-ai:instructions:begin -->` and `<!-- local-ai:instructions:end -->`. Identical contents cause no write or additional backup.
- Before changing an existing file, save AGENTS.md.bak-RANDOM in the same directory with mode 0600, then replace the target atomically without granting other users read/write access.
- Keep personal customizations outside the managed block. Edits inside it are replaced on reinstall. Original v2.0.0 retains hand-copied templates. v2.0.1 backs up and migrates exact selected-template copies; edited/unrecognized rules still need manual review.
- --instructions none neither changes nor removes an existing block. Pass it on each installation if you maintain all rules yourself.
- Symlinks, files owned by another user, malformed markers and write failures cause an installation error instead of a false success. Repair and retry, or use --instructions none for self-managed rules.

To restore, first back up the current file, then copy backup from the JSON/install log to path and exit/restart OpenCode. Keep private machine paths and credentials out of templates/, which source updates replace.

## Verify loading

After installation applies rules or you edit the actual personal AGENTS.md, exit and restart OpenCode so the new session reads them again. Use the same user/environment, with the client installed and API reachable:

```bash
cd /raid/local-ai
./local-ai chat --project /home/alice/project --check
```

ready=true verifies connectivity only. Substitute the returned log_directory below:

```bash
python3 - /absolute/log_directory <<'PYTHON'
import json
import sys
from pathlib import Path

cfg = json.loads((Path(sys.argv[1]) / 'opencode.json').read_text())
for name in cfg['instructions']:
    print(name)
PYTHON
```

Expect private-session operations.md and your personal AGENTS.md; only the former when no personal file exists.
The list proves configuration forwarding, not final model-context delivery.
Run `PYTHONPATH=src python3 scripts/check-instructions.py --client-dir /raid/local-ai/clients/amd64`,
substituting the actual client architecture directory, for a disposable local mock-API check of personal/project/built-in
instructions in real native-client requests. It neither contacts a GPU nor changes personal files, and runs in native-client CI. Temporarily add a distinctive
verification marker, test its instruction in a new conversation or inspect a local mock API request,
then remove it and start another session. One correct response does not prove permanent compliance.
Use disposable fixtures and inspect actual tool arguments to validate search exclusions; never scan
/cm/images as a test. For missing instructions, check user, environment, commit and generated configuration.

Choose a small --project directory, not /cm, / or a parent containing all compute-node images.
With mock images inside the project, native OpenCode internal threads also read project files independently
of model tool choices. Prompts cannot constrain that client behavior. Keep image fixtures outside the project
and grant only the external-directory access needed for those disposable samples; do not label a noninteractive
automatic denial as a user rejection. Prompts are not mandatory file isolation; enforced access boundaries
require separate account permissions or execution-layer controls.

## Maintenance and distribution

The general template calls for reasonably segmented waits, updates based on significant changes and waiting conditions, combined repetitive information, and log files for large outputs. It sets no fixed reporting interval, line count or required heading. These are model behavioral instructions, not a timer or background notification mechanism; blocking calls may prevent messages until they return. Updating source alone does not change personal rules. Rerun client installation to apply updated templates, then exit/restart OpenCode.

Client installation applies templates by default. The standalone scripts/update.py and export only update/carry program templates, leaving personal rules untouched. After upgrading, rerun client installation as the actual chat user to apply new templates; existing files are backed up automatically.
Complete offline bundles include templates/, not personal files under ~/.config/opencode; transfer personal rules separately and securely.
Old updaters may omit templates/: obtain the newer scripts/update.py from the same feature-bearing source archive before updating.
Do not replace session XDG_CONFIG_HOME isolation with global configuration, or edit generated session configs as permanent settings.

[README](../../../README.en.md) · [中文](../agent-instructions.md)


v2.0.1 migrates exact unmarked copies of the selected template after a private full backup, supporting LF/CRLF. Custom text and fenced examples are retained. Edited/unrecognized legacy rules need manual review. Original v2.0.0 does not migrate these copies. Changed installation results report legacy_copies_removed; unchanged installs make no new backup.
