from pathlib import Path
from typing import Any

def _aggregator_to_resolver_input(
    agg_data: dict,
    ecosystem: str,
    constraint: str | None = None,
    extras: list[str] | None = None,
    system_info: dict | None = None,
    include_optional: bool = False,
) -> dict: ...
def _apply_cuda_variants(
    resolved: dict,
    package_details: dict[str, dict],
    system_info: dict,
) -> dict: ...
async def _download_github_repo(url: str, branch: str) -> Path: ...
def _extract_cuda_variants(versions_info: list[dict], base_version: str) -> list[dict]: ...
def _extract_system_requirements(agg_data: dict, ecosystem: str) -> dict: ...
def _generate_install_command(
    ecosystem: str,
    packages: list[tuple[str, str]],
    cuda_version: str | None = None,
) -> str | None: ...
def _normalize_cuda(cuda_str: str) -> int: ...
def _parse_package_spec(
    spec: str,
    default_ecosystem: str = "pypi",
) -> tuple[str, str, str | None]: ...
async def _resolve_transitive(
    aggregator: Any,
    resolver: Any,
    packages: list[dict],
    system_info: dict,
    max_depth: int = 10,
    lock_data: dict | None = None,
    solver_timeout: int | None = None,
    lock_tree_data: dict[str, dict[str, dict]] | None = None,
    bfs_timeout: int | None = None,
    incremental: bool = True,
    cross_deps: list[dict] | None = None,
    include_optional: bool = False,
) -> dict: ...
def _select_best_cuda_variant(
    variants: list[dict],
    system_cuda: str | None,
) -> str | None: ...
def _system_info_fingerprint(system_info: dict | None) -> dict: ...
def create_solver(*, use_optimization: bool = True, solver_timeout: int | None = None) -> Any: ...
