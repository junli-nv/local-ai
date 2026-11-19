# v2.0.2: job recovery and output fixes

- Preserve confirmed terminal state and exit code when log reads fail.
- Report missing Slurm logs so collection can be retried when they appear. Recheck invalid empty caches left by v2.0.1.
- Verify the live backend before collecting missing terminal output. Return backend_unverified while preserving the terminal state if verification fails.
- Use the generic vMAJOR.MINOR.PATCH tag format in updater help and errors.

[Execution guide](execution.md) · [中文](../release-2.0.2.md)
