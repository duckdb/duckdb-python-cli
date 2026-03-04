#!/usr/bin/env python3
"""Build platform-specific wheels for the duckdb-cli package.

Usage:
    uv run --group dist scripts/build_wheels.py --version 1.4.4
    uv run --group dist scripts/build_wheels.py --version 1.4.4 --platform osx-arm64
"""

import argparse
import base64
import csv
import glob as globmod
import hashlib
import io
import os
import stat
import sys
import tempfile
import zipfile

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# Ensure the project source is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from duckdb_cli.downloader import AVAILABLE_PLATFORMS, download

PLATFORM_TAGS = {
    "linux-amd64": "manylinux_2_17_x86_64.manylinux2014_x86_64",
    "linux-arm64": "manylinux_2_17_aarch64.manylinux2014_aarch64",
    "osx-amd64": "macosx_12_0_x86_64",
    "osx-arm64": "macosx_12_0_arm64",
    "windows-amd64": "win_amd64",
    "windows-arm64": "win_arm64",
}

REPRODUCIBLE_DATE = (1980, 1, 1, 0, 0, 0)


def _read_pyproject():
    pyproject_path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def _record_hash(data):
    """Return sha256=<urlsafe-base64-nopad> digest for RECORD."""
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_metadata(project, version):
    """Generate PEP 566 METADATA content from pyproject.toml [project] table."""
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project['name']}",
        f"Version: {version}",
    ]
    if "description" in project:
        lines.append(f"Summary: {project['description']}")
    if "requires-python" in project:
        lines.append(f"Requires-Python: {project['requires-python']}")
    if "license" in project:
        lic = project["license"]
        if isinstance(lic, dict):
            lines.append(f"License: {lic.get('text', '')}")
        else:
            lines.append(f"License: {lic}")
    for author in project.get("authors", []):
        if "name" in author:
            lines.append(f"Author: {author['name']}")
        if "email" in author:
            lines.append(f"Author-email: {author['email']}")
    for maintainer in project.get("maintainers", []):
        if "name" in maintainer:
            lines.append(f"Maintainer: {maintainer['name']}")
        if "email" in maintainer:
            lines.append(f"Maintainer-email: {maintainer['email']}")
    if project.get("keywords"):
        lines.append(f"Keywords: {','.join(project['keywords'])}")
    for classifier in project.get("classifiers", []):
        lines.append(f"Classifier: {classifier}")
    for label, url in project.get("urls", {}).items():
        lines.append(f"Project-URL: {label}, {url}")

    # README as long description
    readme = project.get("readme")
    if isinstance(readme, str):
        content_type = "text/markdown" if readme.endswith(".md") else "text/plain"
        readme_path = os.path.join(os.path.dirname(__file__), "..", readme)
        if os.path.isfile(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_text = f.read()
            lines.append(f"Description-Content-Type: {content_type}")
            return "\n".join(lines) + "\n\n" + readme_text + "\n"

    return "\n".join(lines) + "\n"


def _add_file(zf, arcname, data, executable=False):
    """Add a file to the zip with reproducible timestamps."""
    info = zipfile.ZipInfo(arcname, date_time=REPRODUCIBLE_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    if executable:
        info.external_attr = (stat.S_IFREG | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH) << 16
    else:
        info.external_attr = (stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH) << 16
    zf.writestr(info, data)


def build_wheel(plat, version, project, out_dir, download_version=None):
    """Build a single platform-specific wheel (PEP 427)."""
    platform_tag = PLATFORM_TAGS[plat]
    dist_name = project["name"].replace("-", "_")
    wheel_tag = f"py3-none-{platform_tag}"
    wheel_name = f"{dist_name}-{version}-{wheel_tag}.whl"
    dist_info = f"{dist_name}-{version}.dist-info"

    # Download the binary to a temp directory
    with tempfile.TemporaryDirectory() as tmp:
        extracted = download(plat, version=download_version or version, out_dir=tmp)
        if not extracted:
            print(f"  WARNING: No files extracted for {plat}, skipping")
            return None

        # Build wheel contents in memory, tracking for RECORD
        records = []  # (arcname, hash, size)
        wheel_path = os.path.join(out_dir, wheel_name)

        with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add Python source files from src/duckdb_cli/ (exclude downloader.py)
            src_dir = os.path.join(os.path.dirname(__file__), "..", "src", "duckdb_cli")
            for py_path in sorted(globmod.glob(os.path.join(src_dir, "*.py"))):
                basename = os.path.basename(py_path)
                if basename == "downloader.py":
                    continue
                arcname = f"duckdb_cli/{basename}"
                data = open(py_path, "rb").read()
                _add_file(zf, arcname, data, executable=False)
                records.append((arcname, _record_hash(data), str(len(data))))

            # Add binary inside the package directory
            for fpath in extracted:
                fname = os.path.basename(fpath)
                arcname = f"duckdb_cli/{fname}"
                data = open(fpath, "rb").read()
                _add_file(zf, arcname, data, executable=True)
                records.append((arcname, _record_hash(data), str(len(data))))

            # METADATA
            metadata_content = generate_metadata(project, version)
            metadata_bytes = metadata_content.encode("utf-8")
            arcname = f"{dist_info}/METADATA"
            _add_file(zf, arcname, metadata_bytes)
            records.append((arcname, _record_hash(metadata_bytes), str(len(metadata_bytes))))

            # WHEEL
            wheel_content = (
                "Wheel-Version: 1.0\n"
                f"Generator: duckdb-cli-build\n"
                f"Root-Is-Purelib: false\n"
                f"Tag: {wheel_tag}\n"
            )
            wheel_bytes = wheel_content.encode("utf-8")
            arcname = f"{dist_info}/WHEEL"
            _add_file(zf, arcname, wheel_bytes)
            records.append((arcname, _record_hash(wheel_bytes), str(len(wheel_bytes))))

            # entry_points.txt
            entry_points_content = "[console_scripts]\nduckdb = duckdb_cli.__main__:main\n"
            entry_points_bytes = entry_points_content.encode("utf-8")
            arcname = f"{dist_info}/entry_points.txt"
            _add_file(zf, arcname, entry_points_bytes)
            records.append((arcname, _record_hash(entry_points_bytes), str(len(entry_points_bytes))))

            # top_level.txt
            top_level_content = "duckdb_cli\n"
            top_level_bytes = top_level_content.encode("utf-8")
            arcname = f"{dist_info}/top_level.txt"
            _add_file(zf, arcname, top_level_bytes)
            records.append((arcname, _record_hash(top_level_bytes), str(len(top_level_bytes))))

            # RECORD (must be last, lists itself without hash)
            record_buf = io.StringIO()
            writer = csv.writer(record_buf, lineterminator="\n")
            for row in records:
                writer.writerow(row)
            writer.writerow([f"{dist_info}/RECORD", "", ""])
            record_bytes = record_buf.getvalue().encode("utf-8")
            arcname = f"{dist_info}/RECORD"
            _add_file(zf, arcname, record_bytes)

    print(f"  Built: {wheel_path}")
    return wheel_path


def main():
    parser = argparse.ArgumentParser(description="Build platform-specific wheels for duckdb-cli.")
    parser.add_argument("--version", required=True, help="DuckDB version (e.g. 1.4.4)")
    parser.add_argument("--out-dir", default="dist", help="Output directory (default: dist)")
    parser.add_argument(
        "--platform",
        choices=AVAILABLE_PLATFORMS,
        default=None,
        help="Build for a single platform (default: all)",
    )
    parser.add_argument(
        "--download-version",
        default=None,
        help="DuckDB version to download (defaults to --version; useful for post-releases)",
    )
    args = parser.parse_args()

    pyproject = _read_pyproject()
    project = pyproject["project"]

    platforms = [args.platform] if args.platform else AVAILABLE_PLATFORMS

    if not os.path.isdir(args.out_dir):
        os.makedirs(args.out_dir)

    wheels = []
    for plat in platforms:
        print(f"\nBuilding wheel for {plat}...")
        w = build_wheel(plat, args.version, project, args.out_dir, args.download_version)
        if w:
            wheels.append(w)

    print(f"\nBuilt {len(wheels)} wheel(s) in {args.out_dir}/")


if __name__ == "__main__":
    main()
