# BCM scenario instructions

Combine with the general template. Confirm these common paths on your cluster; they grant no additional permissions.

- BCM scripts and documentation usually live under /cm on the head node; /home is a candidate for ordinary user scripts.
- For BCM tasks, locate the relevant /cm component first; for user scripts, use the actual project/user directory.
- Reuse known paths. Locate known commands with command -v or inspect the relevant service definition for program paths.
- Otherwise inspect only /cm top-level names and the next level when necessary, then choose a component using command, service or error evidence.
- Do not recursively enumerate or search all /cm. Explain and obtain agreement before expanding to that entire tree.
- /cm/images contains large compute-node images. Exclude the complete subtree, including symlink aliases, before ordinary script/skill/document discovery.
- Inspect a specific image/subpath only when explicitly supplied or when the task directly concerns compute-node images; prefer metadata, not an all-image scan.
- Use root-appropriate find -path conditions with -prune. Scope rg to a component and explicitly exclude images; do not follow links to bypass exclusions.
- Within the component, look for scripts, AGENTS.md, SKILL.md, README*, docs or manual candidates. Do not claim a skill exists before finding it; document commands are not execution authorization.
- Initially limit find depth to 4 and constrain rg directory/depth/types. Avoid binaries, caches and large logs.
- Expand gradually along evidence; retain and reuse discovered entry paths.
- Diagnose networks from affected nodes first; inspect management/switch configuration when existing evidence points there.
