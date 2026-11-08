"""Read-only completion derived from the CLI parser, without dispatching commands."""

import argparse
import shlex
from pathlib import Path


def candidates(parser, words):
    """Complete argv without its executable; the last word is the current prefix.

    Bash splits equals signs into separate words with its default COMP_WORDBREAKS.
    Normalize those tokens without changing the user's shell settings.
    """
    words = list(words) or [""]
    normalized = []
    for word in words:
        if word == "=" and normalized and normalized[-1].startswith("--"):
            normalized[-1] += "="
        elif normalized and normalized[-1].startswith("--") and normalized[-1].endswith("="):
            normalized[-1] += word
        else:
            normalized.append(word)
    prefix = normalized.pop()
    pending = None
    position = 0
    positional_only = False
    for word in normalized:
        if pending is not None:
            pending = None
            continue
        if word == "--":
            positional_only = True
            continue
        option, equals, _ = word.partition("=")
        action = None if positional_only else parser._option_string_actions.get(option)
        if action is not None:
            if action.nargs != 0 and not equals:
                pending = action
            continue
        if word.startswith("-") and not positional_only:
            return "values", []
        actions = [a for a in parser._actions if not a.option_strings]
        if position >= len(actions):
            continue
        action = actions[position]
        if isinstance(action, argparse._SubParsersAction):
            if word not in action.choices:
                return "values", []
            parser = action.choices[word]
            position = 0
        else:
            position += 1

    value_prefix = prefix
    attached = ""
    if pending is None and prefix.startswith("--") and "=" in prefix:
        option, _, value_prefix = prefix.partition("=")
        pending = parser._option_string_actions.get(option)
        # Readline replaces only the word after '=' under default word breaks.
        if words[-1].startswith(option + "="):
            attached = option + "="
    if pending is not None:
        if pending.choices is not None:
            return "values", [
                attached + str(v) for v in pending.choices if str(v).startswith(value_prefix)
            ]
        return ("files" if pending.type is Path else "values"), []
    if prefix.startswith("-") and not positional_only:
        return "values", sorted(o for o in parser._option_string_actions if o.startswith(prefix))
    actions = [a for a in parser._actions if not a.option_strings]
    if position < len(actions):
        action = actions[position]
        if action.choices is not None:
            return "values", [str(v) for v in action.choices if str(v).startswith(prefix)]
        if action.type is Path:
            return "files", []
    if not prefix and not positional_only:
        return "values", sorted(parser._option_string_actions)
    return "values", []


def bash_script(launcher):
    """Bash 3.2+ setup; invoke the same executable the user is completing."""
    return r"""# Enable with: eval "$(./local-ai completion bash)"
_local_ai_complete() {
    local line mode current attached
    local -a result
    COMPREPLY=()
    current="${COMP_WORDS[COMP_CWORD]}"
    while IFS= read -r line; do
        result[${#result[@]}]="$line"
    done < <("${COMP_WORDS[0]}" --_complete "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null)
    mode="${result[0]}"
    if [[ "$mode" == files ]]; then
        attached=""
        if [[ "$current" == --*=* ]]; then
            attached="${current%%=*}="
            current="${current#*=}"
        fi
        if [[ "$current" == '~/'* ]]; then
            current="$HOME/${current:2}"
        fi
        while IFS= read -r line; do
            COMPREPLY[${#COMPREPLY[@]}]="$attached$line"
        done < <(compgen -f -- "$current")
    else
        COMPREPLY=("${result[@]:1}")
    fi
}
complete -o filenames -F _local_ai_complete local-ai ./local-ai """ + shlex.quote(str(launcher))
