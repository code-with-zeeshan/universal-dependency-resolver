"""API route for shell completion script generation.

Mirrors ``udr completion {bash,zsh,fish}``.
"""

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import PlainTextResponse

from backend.api.auth import get_current_user
from backend.cli.commands.completion import _ecosystem_list, _list_commands

router = APIRouter()


_SHELL_SCRIPTS: dict[str, str] = {
    "bash": """_{prog}_completion() {{
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
""",
    "zsh": """#compdef {prog}
_{prog}() {{
    local -a subcommands
    subcommands=(
        {zsubs}
    )
    _arguments \\
        "--version[Show version]" \\
        "--offline[Offline mode]" \\
        "1: :(({{zsubs}}))" \\
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
""",
    "fish": """function _{prog}_completion
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
""",
}


@router.get("/completion/{shell}")
async def get_completion_script(
    shell: str,
    current_user=Depends(get_current_user),
):
    """Generate a shell completion script for bash, zsh, or fish.

    Mirrors ``udr completion <shell>``.
    """
    shell = shell.lower()
    if shell not in _SHELL_SCRIPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported shell: {shell}. Choose from: {', '.join(_SHELL_SCRIPTS)}",
        )

    cmds = _list_commands()
    ecos = _ecosystem_list()
    opts = " ".join(cmds)
    ecos_str = " ".join(ecos)

    template = _SHELL_SCRIPTS[shell]
    prog = "udr"

    if shell == "bash":
        script = template.format(prog=prog, opts=opts, ecos=ecos_str)
    elif shell == "zsh":
        zsubs = " ".join(f'"{c}:cmd"' for c in cmds)
        script = template.format(prog=prog, ecos=ecos_str, zsubs=zsubs)
    elif shell == "fish":
        fish_subs = " ".join(cmds)
        fish_ecos = " ".join(ecos)
        script = template.format(prog=prog, fish_subs=fish_subs, fish_ecos=fish_ecos)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported shell: {shell}")

    return PlainTextResponse(content=script, media_type="text/plain")
