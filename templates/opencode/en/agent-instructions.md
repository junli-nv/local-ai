# Persistent instructions on the client

These maintained references reduce repeated correction in new conversations; prompts cannot guarantee compliance.
They are separate from repository development instructions and are not automatically installed policies.

## Files and host

Combine the [general template](AGENTS.general.md) with the [BCM template](AGENTS.bcm.md) when appropriate.
Adapt cluster paths, especially /cm and /cm/images. Use either language, not both copies.
[中文](../agent-instructions.md).

Run on bcm-headnode as the actual chat user, not on GPU001. Examples use installation /raid/local-ai and
existing task directory /home/alice/project; replace them with actual paths.
The personal file defaults to ~/.config/opencode/AGENTS.md; for root it is /root/.config/opencode/AGENTS.md.
When XDG_CONFIG_HOME is set before local-ai starts, use $XDG_CONFIG_HOME/opencode/AGENTS.md.
Changing the user/HOME through sudo changes the personal location; check the actual launch environment.

Current development source resolves that personal path before isolating OpenCode's session configuration.
An existing personal file is explicitly appended to instructions after built-in operations.md.
Other personal model/plugin/connection settings are not imported; personal rules are never rewritten.
The native client still discovers project AGENTS.md. Instructions are combined: resolve conflicts explicitly
rather than relying on order. Original v1.3.7 source lacks this loading bridge; check the commit, not only the version.

## Configure or merge

In Bash on bcm-headnode, from the installation root, combine these English references.
For a non-BCM client, use only the general template. Existing instructions are backed up and kept;
review and manually merge the candidate into AGENTS.md.

```bash
cd /raid/local-ai
set -e
rules_dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
mkdir -p "$rules_dir"
candidate="$(mktemp "$rules_dir/AGENTS.candidate.XXXXXX")"
cat templates/opencode/en/AGENTS.general.md templates/opencode/en/AGENTS.bcm.md > "$candidate"
chmod 600 "$candidate"
if [ -e "$rules_dir/AGENTS.md" ]; then
  cp -p "$rules_dir/AGENTS.md" "$rules_dir/AGENTS.md.bak-$(date +%Y%m%d-%H%M%S)"
  diff -u "$rules_dir/AGENTS.md" "$candidate" || test "$?" -eq 1
  printf 'Existing rules preserved; manually merge candidate: %s\n' "$candidate"
else
  mv -i "$candidate" "$rules_dir/AGENTS.md"
fi
```

Keep machine/user customizations in the personal file or project AGENTS.md, not in templates/,
which program updates replace. Do not commit credentials or internal raw logs.

## Verify loading

End the old chat and start again under the same user/environment. With the client installed and API reachable:

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

## Maintenance and distribution

Installation, updates and export carry templates without applying them. Compare changes, back up and merge personal rules manually.
Complete offline bundles include templates/, not personal files under ~/.config/opencode; transfer personal rules separately and securely.
Old updaters may omit templates/: obtain the newer scripts/update.py from the same feature-bearing source archive before updating.
Do not replace session XDG_CONFIG_HOME isolation with global configuration, or edit generated session configs as permanent settings.

[README](../../../README.en.md) · [中文](../agent-instructions.md)
