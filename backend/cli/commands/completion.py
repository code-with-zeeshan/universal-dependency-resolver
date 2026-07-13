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
            COMPREPLY=( $(compgen -W "text json spdx cyclonedx" -- "${{cur}}") )
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
        lock)
            local lock_flags="--directory --manifest --export --yes --dry-run --interactive --cuda --device --json --report --include-dev --timeout --extras --pin --pin-mode --block --freeze --workspace --prefix --force --target --platform --auto-sync --sign --provenance --check"
            COMPREPLY=( $(compgen -W "${{lock_flags}}" -- "${{cur}}") )
            ;;
        check)
            local check_flags="--verbose --deps --json --cuda --cve --license --deprecated --device --directory --workspace --lock-file --policy"
            COMPREPLY=( $(compgen -W "${{check_flags}}" -- "${{cur}}") )
            ;;
        update)
            local update_flags="--directory --workspace --lock-file --interactive --dry-run --cuda --device --target --platform --fix-cve"
            COMPREPLY=( $(compgen -W "${{update_flags}}" -- "${{cur}}") )
            ;;
        verify)
            local verify_flags="--json --directory --workspace --signature"
            COMPREPLY=( $(compgen -W "${{verify_flags}}" -- "${{cur}}") )
            ;;
        sbom)
            local sbom_flags="--directory --workspace --lock-file --format --output"
            COMPREPLY=( $(compgen -W "${{sbom_flags}}" -- "${{cur}}") )
            ;;
        install)
            local install_flags="--directory --lock-file --workspace --ecosystem --dry-run --yes --restore --production --cuda --target --platform"
            COMPREPLY=( $(compgen -W "${{install_flags}}" -- "${{cur}}") )
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
                        "--json[JSON output]" \\
                        "--cve[Check lock file for known CVEs]" \\
                        "--license[Check lock file for license compliance]" \\
                        "--deprecated[Check for deprecated/yanked packages]" \\
                        "--policy=[Policy YAML file]" \\
                        "--directory=[Project directory]" \\
                        "--workspace=[Workspace name]" \\
                        "--lock-file=[Explicit lock file path]"
                    ;;
                resolve|scan)
                    _arguments \\
                        "--ecosystem=[Ecosystem]:eco:({ecos})" \\
                        "--format=[Format]:fmt:(text json)" \\
                        "--cuda=[CUDA version]" \\
                        "--device=[Device]:dev:(cpu cuda mps)"
                    ;;
                lock)
                    _arguments \\
                        "--ecosystem=[Ecosystem]:eco:({ecos})" \\
                        "--format=[Format]:fmt:(text json)" \\
                        "--cuda=[CUDA version]" \\
                        "--device=[Device]:dev:(cpu cuda mps)" \\
                        "--directory=[Project directory]" \\
                        "--workspace=[Workspace name]" \\
                        "--manifest=[Manifest file]" \\
                        "--export=[Export format]" \\
                        "--dry-run[Dry run mode]" \\
                        "--json[JSON output]" \\
                        "--report[Write report file]" \\
                        "--include-dev[Include dev manifests]" \\
                        "--timeout=[Resolution timeout]" \\
                        "--sign[Sign lock file]" \\
                        "--provenance[Add SLSA provenance]" \\
                        "--check[Check if lock file is up to date (CI mode)]"
                    ;;
                sbom)
                    _arguments \\
                        "--directory=[Project directory]" \\
                        "--workspace=[Workspace name]" \\
                        "--lock-file=[Explicit lock file path]" \\
                        "--format=[SBOM format]:fmt:(spdx cyclonedx)" \\
                        "--output=[Output file path]"
                    ;;
                verify)
                    _arguments \\
                        "--json[JSON output]" \\
                        "--directory=[Project directory]" \\
                        "--workspace=[Workspace name]" \\
                        "--signature[Verify Ed25519 signature]"
                    ;;
                update)
                    _arguments \\
                        "--directory=[Project directory]" \\
                        "--workspace=[Workspace name]" \\
                        "--lock-file=[Explicit lock file path]" \\
                        "--interactive[Interactive mode]" \\
                        "--dry-run[Dry run mode]" \\
                        "--cuda=[CUDA version]" \\
                        "--device=[Device]:dev:(cpu cuda mps)" \\
                        "--target=[Target OS]:os:(linux windows darwin)" \\
                        "--platform=[Target arch]:arch:(x86_64 aarch64 arm64 i386 amd64)" \\
                        "--fix-cve[Fix vulnerable packages]"
                    ;;
                install)
                    _arguments \\
                        "--directory=[Project directory]" \\
                        "--lock-file=[Lock file path]" \\
                        "--workspace=[Workspace name]" \\
                        "--ecosystem=[Ecosystem]:eco:({ecos})" \\
                        "--dry-run[Dry run mode]" \\
                        "--production[Skip dev deps]" \\
                        "--cuda=[CUDA version]" \\
                        "--target=[Target OS]:os:(linux windows darwin)" \\
                        "--platform=[Target arch]:arch:(x86_64 aarch64 arm64 i386 amd64)"
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
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l ssl-keyfile -d 'SSL key file path'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l ssl-certfile -d 'SSL certificate file path'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l workers -d 'Number of worker processes'
    complete -c {prog} -n "__fish_seen_subcommand_from serve" -l log-level -xa 'debug info warning error critical'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l verbose -d 'Verbose'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l deps -d 'Show deps'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l json -d 'JSON output'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l cve -d 'Check lock file for known CVEs'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l license -d 'Check license compliance'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l deprecated -d 'Check for deprecated/yanked packages'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l policy -d 'Policy YAML file'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l directory -d 'Project directory'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l workspace -d 'Workspace name'
    complete -c {prog} -n "__fish_seen_subcommand_from check" -l lock-file -d 'Explicit lock file path'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l ecosystem -xa '$ecos'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l format -xa 'text json'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l cuda -d 'CUDA version'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve lock scan" -l device -xa 'cpu cuda mps'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l sign -d 'Sign lock file'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l provenance -d 'Add SLSA provenance'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l check -d 'Check if lock file is up to date (CI mode)'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l workspace -d 'Workspace name'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l directory -d 'Project directory'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l manifest -d 'Manifest file'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l export -d 'Export format'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l dry-run -d 'Dry run mode'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l report -d 'Write report file'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l include-dev -d 'Include dev manifests'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l timeout -d 'Resolution timeout'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l force -d 'Force full re-resolution'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l target -xa 'linux windows darwin'
    complete -c {prog} -n "__fish_seen_subcommand_from lock" -l platform -xa 'x86_64 aarch64 arm64 i386 amd64'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve" -l target -xa 'linux windows darwin'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve" -l platform -xa 'x86_64 aarch64 arm64 i386 amd64'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve" -l timeout -d 'Resolution timeout'
    complete -c {prog} -n "__fish_seen_subcommand_from resolve" -l interactive -d 'Interactive mode'
    complete -c {prog} -n "__fish_seen_subcommand_from verify" -l json -d 'JSON output'
    complete -c {prog} -n "__fish_seen_subcommand_from verify" -l directory -d 'Project directory'
    complete -c {prog} -n "__fish_seen_subcommand_from verify" -l workspace -d 'Workspace name'
    complete -c {prog} -n "__fish_seen_subcommand_from verify" -l signature -d 'Verify Ed25519 signature'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l directory -d 'Project directory'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l workspace -d 'Workspace name'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l lock-file -d 'Explicit lock file path'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l interactive -d 'Interactive mode'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l dry-run -d 'Dry run mode'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l cuda -d 'CUDA version'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l device -xa 'cpu cuda mps'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l target -xa 'linux windows darwin'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l platform -xa 'x86_64 aarch64 arm64 i386 amd64'
    complete -c {prog} -n "__fish_seen_subcommand_from update" -l fix-cve -d 'Fix vulnerable packages'
    complete -c {prog} -n "__fish_seen_subcommand_from sbom" -l directory -d 'Project directory'
    complete -c {prog} -n "__fish_seen_subcommand_from sbom" -l workspace -d 'Workspace name'
    complete -c {prog} -n "__fish_seen_subcommand_from sbom" -l lock-file -d 'Explicit lock file path'
    complete -c {prog} -n "__fish_seen_subcommand_from sbom" -l format -xa 'spdx cyclonedx'
    complete -c {prog} -n "__fish_seen_subcommand_from sbom" -l output -d 'Output file path'
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
