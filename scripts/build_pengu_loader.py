#!/usr/bin/env python3
"""Build the vendored Pengu Loader source and refresh Veil's runtime loader."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "PenguLoader-1.1.6"
PROJECT = VENDOR / "loader" / "loader.csproj"
CORE_PROJECT = VENDOR / "core" / "core.vcxproj"
PRELOAD_DIR = VENDOR / "plugins"
BUILD_OUTPUT = ROOT / "build" / "pengu-loader"
RUNTIME_DIR = ROOT / "Pengu Loader"
# The preload UI's lockfile is pnpm 9's format
PNPM = ["npx", "--yes", "pnpm@9.15.9"]


def _run_vswhere(requires: list[str]) -> list[str]:
    """MSBuild.exe paths of the latest Visual Studio install that has every component in requires."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        return []
    result = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-requires", *requires, "-find", r"MSBuild\**\Bin\MSBuild.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and Path(line.strip()).exists()]


def _find_cpp_msbuild() -> list[str] | None:
    """An MSBuild that can build core.vcxproj: one from an install with the C++ toolset."""
    found = _run_vswhere(["Microsoft.Component.MSBuild", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"])
    return [found[0]] if found else None


def _find_msbuild() -> list[str] | None:
    configured = os.environ.get("MSBUILD_EXE")
    if configured and Path(configured).exists():
        return [configured]

    msbuild = shutil.which("msbuild")
    if msbuild:
        return [msbuild]

    # The loader is an SDK-style project: an install without the .NET SDK can't build it
    found = _run_vswhere(["Microsoft.Component.MSBuild", "Microsoft.NetCore.Component.SDK"])
    if found:
        return [found[0]]

    dotnet = shutil.which("dotnet")
    if dotnet:
        return [dotnet, "msbuild"]

    return None


def _build_environment() -> dict[str, str]:
    """Avoid duplicate case variants of PATH in child .NET processes."""
    environment = dict(os.environ)
    path_value = next((value for key, value in environment.items() if key.lower() == "path"), "")
    for key in list(environment):
        if key.lower() == "path":
            del environment[key]
    environment["Path"] = path_value
    return environment


def build_core() -> int:
    """Build the preload UI, then core.dll, which embeds it, into BUILD_OUTPUT."""
    npx = shutil.which("npx")
    if not npx:
        print("[ERROR] npx was not found: core.dll's preload UI needs Node.js")
        return 1
    pnpm = [npx, *PNPM[1:]]

    print(f"Building the preload UI in {PRELOAD_DIR}")
    for step in (["install", "--frozen-lockfile"], ["build"]):
        result = subprocess.run(pnpm + step, cwd=PRELOAD_DIR, check=False)
        if result.returncode != 0:
            print(f"[ERROR] pnpm {' '.join(step)} failed with exit code {result.returncode}.")
            return result.returncode
    if not (PRELOAD_DIR / "dist" / "preload.g.h").is_file():
        print("[ERROR] The preload UI build did not produce dist/preload.g.h")
        return 1

    msbuild = _find_cpp_msbuild()
    if not msbuild:
        print('[ERROR] core.dll needs the Visual Studio C++ build tools: install the "Desktop development with C++" workload')
        return 1

    command = msbuild + [
        str(CORE_PROJECT),
        "/t:Build",
        "/m",
        "/v:minimal",
        "/p:Configuration=Release",
        "/p:Platform=x64",
        # The project writes to $(SolutionDir)bin, as it's normally built from pengu.sln
        f"/p:SolutionDir={VENDOR}{os.sep}",
    ]
    print(f"Building core.dll from {CORE_PROJECT}")
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=CORE_PROJECT.parent, env=_build_environment(), check=False)
    if result.returncode != 0:
        print(f"[ERROR] core.dll build failed with exit code {result.returncode}.")
        return result.returncode

    built = VENDOR / "bin" / "core.dll"
    if not built.is_file():
        print(f"[ERROR] Build succeeded but did not produce {built}")
        return 1
    shutil.copy2(built, BUILD_OUTPUT / "core.dll")
    return 0


def build_loader() -> int:
    if not PROJECT.exists():
        print(f"[ERROR] Pengu Loader project not found: {PROJECT}")
        return 1

    msbuild = _find_msbuild()
    if not msbuild:
        print("[ERROR] MSBuild was not found.")
        print("        Install the Visual Studio .NET desktop build tools, or set MSBUILD_EXE.")
        return 1

    if BUILD_OUTPUT.exists():
        shutil.rmtree(BUILD_OUTPUT)
    BUILD_OUTPUT.mkdir(parents=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    output_path = str(BUILD_OUTPUT) + os.sep
    command = msbuild + [
        str(PROJECT),
        "/t:Restore,Build",
        "/m",
        "/v:minimal",
        "/p:Configuration=Release",
        "/p:Platform=AnyCPU",
        f"/p:OutputPath={output_path}",
        # The upstream project expects a signing key that is not distributed.
        # Signing does not affect loader behavior or the generated executable.
        "/p:SignAssembly=false",
        "/p:UseSharedCompilation=false",
        "/p:NuGetAudit=false",
        "/p:RestoreIgnoreFailedSources=true",
    ]

    print(f"Building Pengu Loader from {PROJECT}")
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=PROJECT.parent, env=_build_environment(), check=False)
    if result.returncode != 0:
        print(f"[ERROR] Pengu Loader build failed with exit code {result.returncode}.")
        return result.returncode

    generated_exe = BUILD_OUTPUT / "Pengu Loader.exe"
    if not generated_exe.exists():
        print(f"[ERROR] Build succeeded but did not produce {generated_exe}")
        return 1

    core_result = build_core()
    if core_result != 0:
        return core_result

    copied = []
    try:
        for source in BUILD_OUTPUT.iterdir():
            if source.is_file() and source.suffix.lower() in {".exe", ".config", ".dll"}:
                destination = RUNTIME_DIR / source.name
                shutil.copy2(source, destination)
                copied.append(destination.name)
    except PermissionError as exc:
        print(f"[ERROR] Could not update the runtime loader: {exc}")
        print("        Close Veil/Pengu Loader and run the build again.")
        return 1

    if "Pengu Loader.exe" not in copied or "core.dll" not in copied:
        print("[ERROR] Generated Pengu Loader.exe or core.dll was not copied to the runtime directory.")
        return 1

    print(f"[OK] Installed source-built Pengu Loader ({', '.join(sorted(copied))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(build_loader())