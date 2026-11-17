# v1.4.1 release notes

This version clarifies offline deployment and aligns user-confirmed four-GPU hardware status.

- Both offline client routes include the npm offline variable, distinguish API readiness from complete chat success, and provide a `LOCAL_AI_OK` smoke command.
- Dedicated air-gapped client nodes can use `/etc/profile.d/local-ai.sh` for PATH, interactive Bash completion and npm offline mode; individuals can use `~/.profile`. Set `npm_config_offline=true` only offline/air-gapped. Installation does not persist it automatically.
- Prepare Docker `.deb` files and OS dependencies for the target Ubuntu release and CPU architecture before entering an air gap. Preparation examples focus on B300/GB300.
- The user confirmed physical-hardware validation of `b200-tp4-cpu`, `b200-tp4` and `gb300-tp4`. Retain `gb300-tp2` as unvalidated. Preserve existing methods and coverage without new performance or sustained-stability claims.
- Align program version and current installation/update examples to 1.4.1, including earlier main-branch documentation corrections without moving the v1.4.0 tag.

Inference parameters, models, container images and client runtime logic are unchanged. The GB300 TP4 status update is based on user confirmation; no remote hardware test was rerun. See [v1.4.0 notes](release-1.4.0.md) for earlier client features and [validation](validation.md) for methods and limits.

Use [README](../../README.en.md) for installation, [program updates](update.md) on existing hosts, or the [offline guide](offline.md).

[中文](../release-1.4.1.md)
