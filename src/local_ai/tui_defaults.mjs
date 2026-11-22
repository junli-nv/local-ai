const appliedKey = "local_ai_thinking_default_applied";

export default {
  id: "local-ai.tui-defaults",
  tui({ kv }, options) {
    const mode = options?.thinking_mode;
    if (mode !== "show" && mode !== "hide") return;
    if (kv.get(appliedKey) === mode) return;
    kv.set("thinking_mode", mode);
    kv.set(appliedKey, mode);
  },
};
