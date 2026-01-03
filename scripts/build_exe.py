#!/usr/bin/env python
"""Build script for creating standalone executables.

Usage:
    python scripts/build_exe.py [--nuitka|--pyinstaller]

Requires:
    pip install nuitka  # recommended
    # or
    pip install pyinstaller
"""

import argparse
import subprocess
import sys
from pathlib import Path


def build_with_nuitka(root: Path, dist_dir: Path):
    """Build using Nuitka (recommended - smaller, faster)."""
    common_args = [
        "--onefile",
        "--assume-yes-for-downloads",
        f"--output-dir={dist_dir}",
    ]

    print("Building stache-mcp with Nuitka...")
    subprocess.run([
        sys.executable, "-m", "nuitka",
        *common_args,
        "--output-filename=stache-mcp",
        str(root / "scripts" / "mcp_entry.py"),
    ], check=True)

    print("Building stache with Nuitka...")
    subprocess.run([
        sys.executable, "-m", "nuitka",
        *common_args,
        "--output-filename=stache",
        str(root / "scripts" / "cli_entry.py"),
    ], check=True)


def build_with_pyinstaller(root: Path, dist_dir: Path):
    """Build using PyInstaller."""
    common_args = [
        "--onefile",
        "--clean",
        f"--distpath={dist_dir}",
        f"--workpath={root / 'build'}",
        f"--specpath={root / 'build'}",
    ]

    # Hidden imports needed for dynamic imports in dependencies
    mcp_hidden = [
        # MCP library internals
        "--hidden-import=mcp",
        "--hidden-import=mcp.server",
        "--hidden-import=mcp.server.stdio",
        "--hidden-import=mcp.server.lowlevel",
        "--hidden-import=mcp.types",
        # Pydantic (uses dynamic imports)
        "--hidden-import=pydantic",
        "--hidden-import=pydantic.deprecated",
        "--hidden-import=pydantic.deprecated.decorator",
        "--hidden-import=pydantic_settings",
        # Async/networking
        "--hidden-import=httpx",
        "--hidden-import=httpcore",
        "--hidden-import=anyio",
        "--hidden-import=anyio._backends",
        "--hidden-import=anyio._backends._asyncio",
        # stache_tools internals
        "--hidden-import=stache_tools.mcp",
        "--hidden-import=stache_tools.mcp.server",
        "--hidden-import=stache_tools.mcp.tools",
        "--hidden-import=stache_tools.mcp.formatters",
        "--hidden-import=stache_tools.client",
        "--hidden-import=stache_tools.client.api",
        "--hidden-import=stache_tools.client.config",
        "--hidden-import=stache_tools.client.http",
        "--hidden-import=stache_tools.client.factory",
    ]

    cli_hidden = [
        # Click and Rich for CLI
        "--hidden-import=click",
        "--hidden-import=rich",
        "--hidden-import=rich.console",
        "--hidden-import=rich.table",
        "--hidden-import=rich.panel",
        "--hidden-import=rich.syntax",
        # Pydantic
        "--hidden-import=pydantic",
        "--hidden-import=pydantic.deprecated",
        "--hidden-import=pydantic.deprecated.decorator",
        "--hidden-import=pydantic_settings",
        # Networking
        "--hidden-import=httpx",
        "--hidden-import=httpcore",
        # stache_tools internals
        "--hidden-import=stache_tools.cli",
        "--hidden-import=stache_tools.cli.main",
        "--hidden-import=stache_tools.cli.search",
        "--hidden-import=stache_tools.cli.ingest",
        "--hidden-import=stache_tools.cli.namespaces",
        "--hidden-import=stache_tools.cli.documents",
        "--hidden-import=stache_tools.cli.health",
        "--hidden-import=stache_tools.cli.models",
        "--hidden-import=stache_tools.client",
        "--hidden-import=stache_tools.loaders",
        "--hidden-import=stache_tools.loaders.registry",
    ]

    print("Building stache-mcp with PyInstaller...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        *common_args,
        *mcp_hidden,
        "--name=stache-mcp",
        str(root / "scripts" / "mcp_entry.py"),
    ], check=True)

    print("Building stache with PyInstaller...")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        *common_args,
        *cli_hidden,
        "--name=stache",
        str(root / "scripts" / "cli_entry.py"),
    ], check=True)


def main():
    """Build stache and stache-mcp executables."""
    parser = argparse.ArgumentParser(description="Build standalone executables")
    parser.add_argument("--nuitka", action="store_true", help="Use Nuitka (default)")
    parser.add_argument("--pyinstaller", action="store_true", help="Use PyInstaller")
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    dist_dir = root / "dist"
    dist_dir.mkdir(exist_ok=True)

    if args.pyinstaller:
        build_with_pyinstaller(root, dist_dir)
    else:
        build_with_nuitka(root, dist_dir)

    print(f"\nExecutables built in {dist_dir}/")
    print("  - stache-mcp (MCP server for Claude Desktop)")
    print("  - stache (CLI tool)")


if __name__ == "__main__":
    main()
