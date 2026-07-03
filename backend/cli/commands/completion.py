"""Shell completion script generation for bash, zsh, and fish."""

import os
import sys

_BASH_COMPLETION = """_{prog}_completion() {{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    opts="{opts}"

    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
        return 0
    fi

    case "${{prev}}" in
        -e|--ecosystem)
            local ecos="{ecos}"
            COMPREPLY=( $(compgen -W "${{ecos}}" -- "${{cur}}") )
            ;;
        --format|-f)
            COMPREPLY=( $(compgen -W "text json" -- "${{cur}}") )
            ;;
        --host)
            COMPREPLY=( $(compgen -A hostname -- "${{cur}}") )
            ;;
        --device)
            COMPREPLY=( $(compgen -W "cpu cuda mps" -- "${{cur}}") )
            ;;
        --mode)
            COMPREPLY=( $(compgen -W "local saas" -- "${{cur}}") )
            ;;
        --cuda)
            COMPREPLY=( $(compgen -W "12.8 12.7 12.6 12.5 12.4 12.3 12.2 12.1 12.0 11.8 11.7 11.6 11.4 11.3 11.2 11.1 11.0" -- "${{cur}}") )
            ;;
    esac
    return 0
}}
complete -F _{prog}_completion {prog}
"""

_ZSH_COMPLETION = """#compdef {prog}
_{prog}() {{
    local -a subcommands
    subcommands=(
        {zsubs}
    )
    _arguments \\
        "--version[Show version]" \\
        "--offline[Offline mode]" \\
        "1: :(({zsubs}))" \\
        "*::arg:->args"

    case $state in
        (args)
            case $words[1] in
                serve)
                    _arguments \\
                        "--host=[Bind address]" \\
                        "--port=[Bind port]" \\
                        "--reload[Enable hot-reload]" \\
                        "--mode=[Run mode]:mode:(local saas)"
                    ;;
                check)
                    _arguments \\
                        "-v[Verbose]" \\
                        "--deps[Show deps]" \\
                        "--json[JSON output]"
                    ;;
                resolve|lock|scan)
                    _arguments \\
                        "--ecosystem=[Ecosystem]:eco:({ecos})" \\
                        "--format=[Format]:fmt:(text json)" \\
                        "--cuda=[CUDA version]" \\
                        "--device=[Device]:dev:(cpu cuda mps)"
                    ;;
                completion)
                    _arguments "1:shell:(bash zsh fish)"
                    ;;
            esac
            ;;
    esac
}}
_{prog} "$@"
"""

_FISH_COMPLETION = """function _{prog}_completion
    set -l subcmds {fish_subs}
    set -l ecos {fish_ecos}

    complete -c {prog} -f

    complete -c {prog} -n "not __fish_seen_subcommand_from $subcmds" -a "$subcmds"

    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l host -d 'Bind address'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l port -d 'Bind port'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l reload -d 'Enable hot-reload'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l mode -xa 'local saas'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l verbose -d 'Verbose'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l deps -d 'Show deps'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l json -d 'JSON output'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l ecosystem -xa '$ecos'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l format -xa 'text json'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l cuda -d 'CUDA version'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l device -xa 'cpu cuda mps'
    complete -c {prog} -n "__fish_seen_subcommand_from completion" -xa 'bash zsh fish'
end

_{prog}_completion
"""


def _list_commands():
    """List commands."""
    from ..main import _build_parser

    parser = _build_parser()
    return sorted(parser._subparsers._group_actions[0].choices.keys())


def _ecosystem_list():
    """Ecosystem list."""
    from backend.settings import ECOSYSTEMS

    return [e for e in ECOSYSTEMS if e not in ("docs", "custom_db")]


def cmd_completion(args):
    """Cmd completion."""
    shell = args.shell
    if not shell:
        try:
            import shellingham

            shell = shellingham.detect_shell()[0]
        except (ImportError, Exception):
            shell = "bash"

    prog = os.path.basename(sys.argv[0]) or "udr"
    cmds = _list_commands()
    ecos = _ecosystem_list()
    opts = " ".join(cmds)
    ecos_str = " ".join(ecos)

    cuda_versions = (
        " ".join(f"12.{i}" for i in range(8, 0, -1)) + " 11.8 11.7 11.6 11.4 11.3 11.2 11.1 11.0"
    )

    if shell == "bash":
        bash = _BASH_COMPLETION
        bash = bash.replace(
            "12.8 12.7 12.6 12.5 12.4 12.3 12.2 12.1 12.0 11.8 11.7 11.6 11.4 11.3 11.2 11.1 11.0",
            cuda_versions,
        )
        script = bash.format(prog=prog, opts=opts, ecos=ecos_str)
    elif shell == "zsh":
        zsubs = " ".join(f'"{c}:cmd"' for c in cmds)
        script = _ZSH_COMPLETION.format(prog=prog, ecos=ecos_str, zsubs=zsubs)
    elif shell == "fish":
        fish_subs = " ".join(cmds)
        fish_ecos = " ".join(ecos)
        script = _FISH_COMPLETION.format(prog=prog, fish_subs=fish_subs, fish_ecos=fish_ecos)
    else:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        sys.exit(1)

    print(script)
