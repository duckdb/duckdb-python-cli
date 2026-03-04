#!/usr/bin/env python3
"""Download the DuckDB CLI binary for the current or specified platform."""

import argparse
import io
import json
import os
import platform
import stat
import sys
import urllib.request
import zipfile

AVAILABLE_PLATFORMS = [
    "linux-amd64",
    "linux-arm64",
    "osx-amd64",
    "osx-arm64",
    "windows-amd64",
    "windows-arm64",
]

_RELEASES_URL = "https://github.com/duckdb/duckdb/releases"


def detect_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()

    os_map = {"darwin": "osx", "linux": "linux", "windows": "windows"}
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}

    os_name = os_map.get(system)
    arch = arch_map.get(machine)
    if not os_name or not arch:
        sys.exit(f"Unsupported platform: {platform.system()} {platform.machine()}")

    return f"{os_name}-{arch}"


def _get_latest_version():
    url = "https://api.github.com/repos/duckdb/duckdb/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))["tag_name"]


def download(plat, version=None, out_dir="bin"):
    if version is None:
        version = _get_latest_version()
    elif not version.startswith("v"):
        version = "v" + version

    asset = f"duckdb_cli-{plat}.zip"
    url = f"{_RELEASES_URL}/download/{version}/{asset}"

    print(f"Downloading DuckDB {version} for {plat}...")
    with urllib.request.urlopen(url) as resp:
        data = resp.read()

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    extracted = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            dest = os.path.join(out_dir, info.filename)
            with open(dest, "wb") as f:
                f.write(zf.read(info))
            if sys.platform != "win32":
                mode = os.stat(dest).st_mode
                os.chmod(dest, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  -> {dest}")
            extracted.append(dest)

    print("Done.")
    return extracted


def ensure_binary():
    pkg_dir = os.path.dirname(__file__)
    bin_name = "duckdb.exe" if sys.platform == "win32" else "duckdb"
    bin_path = os.path.join(pkg_dir, bin_name)

    if os.path.isfile(bin_path):
        return bin_path

    print("DuckDB CLI binary not found. Downloading...")
    download(detect_platform(), out_dir=pkg_dir)
    return bin_path


def _main():
    parser = argparse.ArgumentParser(description="Download the DuckDB CLI binary.")
    parser.add_argument(
        "--platform",
        choices=AVAILABLE_PLATFORMS,
        default=None,
        help="Target platform (default: auto-detect)",
    )
    args = parser.parse_args()
    plat = args.platform or detect_platform()
    download(plat)


if __name__ == "__main__":
    _main()
