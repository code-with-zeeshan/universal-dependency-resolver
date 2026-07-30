"""Per-ecosystem benchmark.

For each resolvable ecosystem:
  - If manifest needs non-existent versions → create consumer manifest
  - If ecosystem works with source-repo clone → shallow clone and test
  - Run `udr lock --dry-run --json`, measure time, record results
  - Delete clone, repeat
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
UDR = [sys.executable, "-m", "backend.cli"]

ENV = {
    **os.environ,
    "PYTHONPATH": str(REPO_ROOT),
    "SOLVER_TIMEOUT": "300",
}

RESULTS_DIR = Path("/tmp/opencode/benchmark_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Config per ecosystem ──────────────────────────────────────────
# Each entry describes how to prepare the benchmark directory.
#   "source": "clone" → shallow clone from repo_url
#   "source": "consumer" → create a manifest that mimics "npm install <pkg>"
#   "source": "synthetic" → create a manifest with popular packages

CONFIG = [
    # pypi — sherlock is a real Python project with requirements.txt
    ("pypi", {"mode": "clone", "repo": "https://github.com/sherlock-project/sherlock"}),
    # conda — no single large repo; create consumer manifest
    (
        "conda",
        {
            "mode": "consumer",
            "file": "environment.yml",
            "content": """name: bench
channels:
  - conda-forge
dependencies:
  - python>=3.11
  - numpy>=1.24
  - pandas>=2.0
  - scipy>=1.11
  - scikit-learn>=1.3
  - matplotlib>=3.7
  - seaborn>=0.12
  - flask>=2.3
  - django>=4.2
  - fastapi>=0.100
  - requests>=2.28
  - sqlalchemy>=2.0
  - pytest>=7.0
  - jupyter>=1.0
  - sphinx>=7.0
  - redis>=4.5
  - celery>=5.3
  - alembic>=1.11
  - gunicorn>=20.1
  - uvicorn>=0.22
  - pre-commit>=3.0
  - black>=23.0
  - mypy>=1.0
  - psycopg2>=2.9
""",
        },
    ),
    # npm — consumer manifest: "npm install express@^4.18.0"
    # Source repo's package.json references deps that don't exist (e.g. accepts ^2.0.0)
    (
        "npm",
        {
            "mode": "consumer",
            "file": "package.json",
            "content": '{"dependencies":{"express":"^4.18.2","lodash":"^4.17.21","react":"^18.2.0","commander":"^11.0.0","chalk":"^5.3.0"}}\n',
        },
    ),
    # crates — rust-lang/regex has Cargo.toml with published deps
    ("crates", {"mode": "clone", "repo": "https://github.com/rust-lang/regex"}),
    # maven — apache commons-lang has pom.xml with standard deps
    ("maven", {"mode": "clone", "repo": "https://github.com/apache/commons-lang"}),
    # gomodules — cilium go.mod + go.sum (already benchmarked at 225s)
    ("gomodules", {"mode": "clone", "repo": "https://github.com/cilium/cilium"}),
    # apt — synthetic manifest of popular apt packages
    (
        "apt",
        {
            "mode": "synthetic",
            "file": "apt-packages.txt",
            "content": "\n".join(
                f"{pkg}>={ver}"
                for pkg, ver in [
                    ("build-essential", "12.9"),
                    ("curl", "7.88"),
                    ("git", "2.39"),
                    ("python3", "3.11"),
                    ("python3-pip", "23.0"),
                    ("nodejs", "18.0"),
                    ("gcc", "12.0"),
                    ("g++", "12.0"),
                    ("make", "4.3"),
                    ("cmake", "3.25"),
                    ("openssl", "3.0"),
                    ("libssl-dev", "3.0"),
                    ("zlib1g-dev", "1.2"),
                    ("libffi-dev", "3.4"),
                    ("libreadline-dev", "8.2"),
                    ("libsqlite3-dev", "3.40"),
                    ("libbz2-dev", "1.0"),
                    ("liblzma-dev", "5.4"),
                    ("uuid-dev", "2.38"),
                    ("libncursesw5-dev", "6.4"),
                    ("libxml2-dev", "2.10"),
                    ("libxslt1-dev", "1.1"),
                    ("libgdbm-dev", "1.23"),
                    ("nginx", "1.24"),
                    ("postgresql", "15.0"),
                    ("redis", "7.0"),
                    ("mysql-server", "8.0"),
                    ("docker.io", "24.0"),
                    ("htop", "3.2"),
                    ("vim", "9.0"),
                    ("tmux", "3.3"),
                    ("ssh", "9.0"),
                    ("rsync", "3.2"),
                    ("wget", "1.21"),
                    ("unzip", "6.0"),
                    ("sqlite3", "3.40"),
                    ("jq", "1.6"),
                    ("tree", "2.1"),
                ]
            )
            + "\n",
        },
    ),
    # apk — synthetic manifest
    (
        "apk",
        {
            "mode": "synthetic",
            "file": "apk-packages.txt",
            "content": "\n".join(
                f"{pkg}>={ver}"
                for pkg, ver in [
                    ("alpine-base", "3.18"),
                    ("build-base", "0.5"),
                    ("gcc", "12.0"),
                    ("g++", "12.0"),
                    ("make", "4.4"),
                    ("cmake", "3.26"),
                    ("python3", "3.11"),
                    ("py3-pip", "23.0"),
                    ("nodejs", "18.0"),
                    ("npm", "9.0"),
                    ("go", "1.20"),
                    ("rust", "1.70"),
                    ("cargo", "1.70"),
                    ("openssl", "3.1"),
                    ("openssl-dev", "3.1"),
                    ("zlib-dev", "1.2"),
                    ("libffi-dev", "3.4"),
                    ("readline-dev", "8.2"),
                    ("sqlite-dev", "3.41"),
                    ("ncurses-dev", "6.4"),
                    ("libxml2-dev", "2.11"),
                    ("libxslt-dev", "1.1"),
                    ("nginx", "1.24"),
                    ("postgresql15", "15.0"),
                    ("redis", "7.0"),
                    ("mysql", "10.11"),
                    ("curl", "8.0"),
                    ("git", "2.40"),
                    ("vim", "9.0"),
                    ("tmux", "3.3"),
                    ("bash", "5.2"),
                    ("sudo", "1.9"),
                    ("openssh", "9.3"),
                    ("rsync", "3.2"),
                    ("busybox", "1.36"),
                ]
            )
            + "\n",
        },
    ),
    # cocoapods — Alamofire has Podfile with real deps
    (
        "cocoapods",
        {
            "mode": "consumer",
            "file": "Podfile",
            "content": 'platform :ios, "15.0"\ntarget "App" do\n  pod "Alamofire", "~> 5.8"\n  pod "Firebase/Core", "~> 10.0"\n  pod "Kingfisher", "~> 7.0"\n  pod "SnapKit", "~> 5.6"\n  pod "SwiftyJSON", "~> 5.0"\n  pod "RealmSwift", "~> 10.0"\nend\n',
        },
    ),
    # homebrew — synthetic Brewfile with popular formulae
    (
        "homebrew",
        {
            "mode": "synthetic",
            "file": "Brewfile",
            "content": "\n".join(
                ['tap "homebrew/core"', 'tap "homebrew/cask"']
                + [
                    f'brew "{pkg}"'
                    for pkg in [
                        "python@3.11",
                        "node@18",
                        "go",
                        "rust",
                        "git",
                        "curl",
                        "wget",
                        "cmake",
                        "make",
                        "openssl@3",
                        "readline",
                        "sqlite",
                        "xz",
                        "zlib",
                        "nginx",
                        "postgresql@15",
                        "mysql@8.0",
                        "redis",
                        "vim",
                        "tmux",
                        "htop",
                        "jq",
                        "tree",
                        "ripgrep",
                        "fd",
                        "bat",
                        "fzf",
                        "neovim",
                        "docker",
                        "kubectl",
                        "helm",
                        "terraform",
                    ]
                ]
                + [
                    f'cask "{pkg}"'
                    for pkg in [
                        "visual-studio-code",
                        "docker",
                        "google-chrome",
                        "firefox",
                        "slack",
                        "zoom",
                        "spotify",
                    ]
                ]
            )
            + "\n",
        },
    ),
    # nuget — Newtonsoft.Json repo has packages.config with its own deps
    # But for a consumer benchmark, download just the manifest from a well-known .NET project
    (
        "nuget",
        {
            "mode": "consumer",
            "file": "packages.config",
            "content": """<?xml version="1.0"?>
<packages>
  <package id="Newtonsoft.Json" version="13.0.3"/>
  <package id="Microsoft.Extensions.DependencyInjection" version="8.0.0"/>
  <package id="Serilog" version="3.1.0"/>
  <package id="AutoMapper" version="12.0.0"/>
  <package id="FluentValidation" version="11.0.0"/>
  <package id="Moq" version="4.20.0"/>
</packages>
""",
        },
    ),
    # packagist — laravel/laravel has composer.json but may reference unpublished sub-deps
    (
        "packagist",
        {
            "mode": "consumer",
            "file": "composer.json",
            "content": json.dumps(
                {
                    "require": {
                        "laravel/framework": "^10.0",
                        "laravel/tinker": "^2.8",
                        "spatie/laravel-permission": "^5.10",
                        "barryvdh/laravel-debugbar": "^3.9",
                        "maatwebsite/laravel-excel": "^3.1",
                    }
                }
            )
            + "\n",
        },
    ),
    # rubygems — rails/rails Gemfile references specific rails internal deps
    (
        "rubygems",
        {
            "mode": "consumer",
            "file": "Gemfile",
            "content": "\n".join(
                [
                    'source "https://rubygems.org"',
                    'gem "rails", "~> 7.1"',
                    'gem "pg", "~> 1.5"',
                    'gem "puma", "~> 6.4"',
                    'gem "devise", "~> 4.9"',
                    'gem "sidekiq", "~> 7.2"',
                    'gem "rack-attack", "~> 6.7"',
                    'gem "kaminari", "~> 1.2"',
                    'gem "rspec-rails", "~> 6.1"',
                    'gem "factory_bot_rails", "~> 6.4"',
                ]
            )
            + "\n",
        },
    ),
    # pub — consumer manifest for a Flutter/Dart project
    (
        "pub",
        {
            "mode": "consumer",
            "file": "pubspec.yaml",
            "content": """name: bench
environment:
  sdk: ">=3.0.0 <4.0.0"
dependencies:
  flutter:
    sdk: flutter
  provider: ^6.0.0
  http: ^1.1.0
  shared_preferences: ^2.2.0
  firebase_core: ^2.24.0
  firebase_auth: ^4.16.0
  cloud_firestore: ^4.14.0
  flutter_riverpod: ^2.4.0
  dio: ^5.4.0
  json_annotation: ^4.8.0
  intl: ^0.19.0
  url_launcher: ^6.2.0
  cached_network_image: ^3.3.0
  flutter_svg: ^2.0.0
  equatable: ^2.0.0
  freezed_annotation: ^2.4.0
""",
        },
    ),
    # gradle — consumer manifest for a Java/Kotlin project
    (
        "gradle",
        {
            "mode": "consumer",
            "file": "build.gradle",
            "content": """plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.0'
    id 'io.spring.dependency-management' version '1.1.4'
}
repositories { mavenCentral() }
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.2.0'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa:3.2.0'
    implementation 'org.springframework.boot:spring-boot-starter-security:3.2.0'
    implementation 'com.google.guava:guava:32.1.3-jre'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.16.0'
    implementation 'org.apache.commons:commons-lang3:3.13.0'
    implementation 'ch.qos.logback:logback-classic:1.4.14'
    implementation 'org.slf4j:slf4j-api:2.0.9'
    implementation 'commons-io:commons-io:2.15.0'
    implementation 'org.projectlombok:lombok:1.18.30'
    annotationProcessor 'org.projectlombok:lombok:1.18.30'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.2.0'
}
""",
        },
    ),
    # swift — consumer manifest (Package.swift) for an iOS app
    (
        "swift",
        {
            "mode": "consumer",
            "file": "Package.swift",
            "content": """// swift-tools-version:5.9
import PackageDescription
let package = Package(
    name: "Bench",
    dependencies: [
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
        .package(url: "https://github.com/onevcat/Kingfisher.git", from: "7.10.0"),
        .package(url: "https://github.com/SnapKit/SnapKit.git", from: "5.6.0"),
        .package(url: "https://github.com/realm/realm-swift.git", from: "10.45.0"),
        .package(url: "https://github.com/firebase/firebase-ios-sdk.git", from: "10.19.0"),
        .package(url: "https://github.com/pointfreeco/swift-composable-architecture.git", from: "1.6.0"),
    ]
)
""",
        },
    ),
    # hex — elixir mix.exs with popular deps
    (
        "hex",
        {
            "mode": "consumer",
            "file": "mix.exs",
            "content": """defmodule Bench.MixProject do
  use Mix.Project
  def project do
    [app: :bench, version: "0.1.0", deps: deps()]
  end
  defp deps do
    [
      {:phoenix, "~> 1.7.0"},
      {:phoenix_live_view, "~> 0.20.0"},
      {:ecto_sql, "~> 3.11"},
      {:postgrex, "~> 0.17.0"},
      {:jason, "~> 1.4"},
      {:bandit, "~> 1.0"},
      {:tesla, "~> 1.7"},
      {:credo, "~> 1.7", only: [:dev, :test]},
      {:ex_doc, "~> 0.31", only: :dev},
    ]
  end
end
""",
        },
    ),
    # haskell — cabal file with popular packages
    (
        "haskell",
        {
            "mode": "consumer",
            "file": "bench.cabal",
            "content": """cabal-version: 3.8
name: bench
version: 0.1.0
library
  build-depends:
    base >=4.17 && <5,
    text >=2.0,
    bytestring >=0.11,
    aeson >=2.1,
    http-conduit >=0.3.8,
    warp >=3.3,
    wai >=3.2,
    scotty >=0.12,
    unordered-containers >=0.2,
    vector >=0.13,
    lens >=5.2,
    mtl >=2.3,
    transformers >=0.6,
    exceptions >=0.10,
    time >=1.12,
    directory >=1.3,
    filepath >=1.4,
    containers >=0.6
""",
        },
    ),
]

TIMEOUTS = {
    "pypi": 300,
    "conda": 120,
    "npm": 300,
    "crates": 300,
    "maven": 300,
    "gomodules": 600,
    "apt": 120,
    "apk": 120,
    "cocoapods": 300,
    "homebrew": 120,
    "nuget": 300,
    "packagist": 300,
    "rubygems": 600,
    "pub": 600,
    "gradle": 600,
    "swift": 300,
    "hex": 300,
    "haskell": 300,
}


# ── Helpers ───────────────────────────────────────────────────────


def prepare_dir(eco: str, cfg: dict) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"bench_{eco}_"))
    mode = cfg["mode"]

    if mode == "clone":
        repo = cfg["repo"]
        dest = d / "repo"
        print(f"  Cloning {repo} ...", end=" ", flush=True)
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", repo, str(dest)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.returncode != 0:
            shutil.rmtree(d)
            raise RuntimeError(f"Clone failed:\n{r.stderr}")
        size = _dir_size(dest)
        print(f"done ({size})", flush=True)
        return dest

    # consumer or synthetic → write file directly
    (d / cfg["file"]).write_text(cfg["content"])
    print(f"  Created {cfg['file']} ({len(cfg['content'])}B)", flush=True)
    return d


def _dir_size(p: Path) -> str:
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    if total > 1024**2:
        return f"{total / 1024**2:.0f}MB"
    return f"{total / 1024:.0f}KB"


def run_benchmark(eco: str, bench_dir: Path, timeout: int) -> dict:
    print(f"  Running udr lock (timeout={timeout}s) ...", end=" ", flush=True)
    env = {**ENV}
    start = time.monotonic()
    r = subprocess.run(
        [*UDR, "lock", "-d", str(bench_dir), "--dry-run", "--json", f"--timeout={timeout}"],
        capture_output=True,
        text=True,
        timeout=timeout + 60,
        env=env,
    )
    elapsed = time.monotonic() - start
    status = "ok" if r.returncode == 0 else "FAIL"
    print(f"{elapsed:.0f}s  exit={r.returncode}", flush=True)

    result: dict = {
        "ecosystem": eco,
        "status": status,
        "exit_code": r.returncode,
        "elapsed_seconds": round(elapsed, 1),
        "timeout": timeout,
    }

    stdout = r.stdout or ""
    stderr = r.stderr or ""

    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass

    if data:
        pkgs = data.get("packages", data.get("resolved_packages", {}))
        result["packages_total"] = len(pkgs)
        eco_counts: dict[str, int] = {}
        for _, v in pkgs.items():
            e = v.get("ecosystem", eco)
            eco_counts[e] = eco_counts.get(e, 0) + 1
        result["packages_by_eco"] = eco_counts
        result["resolver"] = data.get("resolver", "?")
    else:
        result["packages_total"] = 0
        result["packages_by_eco"] = {}
        err = stderr[:3000] if stderr else stdout[:3000]
        result["error_detail"] = err

    if r.returncode != 0:
        result.setdefault("error_detail", stderr[:3000])

    return result


def print_table(results: dict):
    ordered = [eco for eco, _ in CONFIG]
    print(f"\n{'=' * 80}")
    print(f"{'Ecosystem':<14} {'Status':<8} {'Time(s)':<8} {'Pkgs':<6} {'Resolved Pkgs by Eco'}")
    print("-" * 80)
    for eco in ordered:
        r = results.get(eco, {})
        s = r.get("status", "?")
        t = r.get("elapsed_seconds", "-")
        p = r.get("packages_total", "-")
        eco_detail = r.get("packages_by_eco", {})
        detail_str = ", ".join(f"{k}={v}" for k, v in sorted(eco_detail.items()))
        print(f"{eco:<14} {str(s):<8} {str(t):<8} {str(p):<6} {detail_str}")
    print(f"\nFull results: {RESULTS_DIR / 'results.json'}")


def main():
    args = sys.argv[1:]
    target = args[0] if args else "all"
    results: dict[str, dict] = {}
    results_file = RESULTS_DIR / "results.json"

    for eco, cfg in CONFIG:
        if target != "all" and eco != target:
            continue

        print(f"\n{'=' * 60}")
        print(f"[{eco}] mode={cfg['mode']}")
        print(f"{'=' * 60}")

        try:
            bench_dir = prepare_dir(eco, cfg)
        except Exception as e:
            print(f"  SKIP: {e}")
            results[eco] = {"ecosystem": eco, "status": "skip", "error": str(e)}
            _save(results, results_file)
            continue

        try:
            result = run_benchmark(eco, bench_dir, TIMEOUTS.get(eco, 300))
            results[eco] = result
            _save(results, results_file)
        except Exception as e:
            print(f"  ERROR: {e}")
            results[eco] = {"ecosystem": eco, "status": "error", "error": str(e)}
            _save(results, results_file)
        finally:
            shutil.rmtree(bench_dir, ignore_errors=True)

    print_table(results)


def _save(results: dict, path: Path):
    # Save per-ecosystem file separately, and update combined
    for eco, data in results.items():
        (path.parent / f"result_{eco}.json").write_text(json.dumps(data, indent=2, default=str))
    path.write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
