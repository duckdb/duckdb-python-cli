"""Tests for scripts/build_wheels.py."""

import base64
import csv
import hashlib
import io
import os
import sys
import zipfile
from unittest.mock import patch

# Ensure the scripts directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_wheels

PROJECT = build_wheels._read_pyproject()["project"]


def _fake_download(plat, version, out_dir):
    """Mock download that creates a fake binary."""
    os.makedirs(out_dir, exist_ok=True)
    name = "duckdb.exe" if "windows" in plat else "duckdb"
    path = os.path.join(out_dir, name)
    with open(path, "wb") as f:
        f.write(b"fake-duckdb-binary-content")
    return [path]


class TestGenerateMetadata:
    def test_all_fields(self):
        metadata = build_wheels.generate_metadata(PROJECT, "1.0.0")
        assert "Metadata-Version: 2.1" in metadata
        assert "Name: duckdb-cli" in metadata
        assert "Version: 1.0.0" in metadata
        assert "Summary: The DuckDB CLI" in metadata
        assert "Requires-Python: >=3.6" in metadata
        assert "Author: DuckDB Foundation" in metadata
        assert "Maintainer: DuckDB Foundation" in metadata
        assert "Keywords: DuckDB," in metadata
        assert "Classifier: " in metadata
        assert "Project-URL: Documentation," in metadata
        assert "Description-Content-Type: text/markdown" in metadata
        assert "## DuckDB CLI" in metadata

    def test_license_string(self):
        project = {**PROJECT, "license": "MIT"}
        metadata = build_wheels.generate_metadata(project, "1.0.0")
        assert "License: MIT" in metadata

    def test_license_dict(self):
        project = {**PROJECT, "license": {"text": "MIT License"}}
        metadata = build_wheels.generate_metadata(project, "1.0.0")
        assert "License: MIT License" in metadata

    def test_minimal_project(self):
        metadata = build_wheels.generate_metadata({"name": "test-pkg"}, "0.1.0")
        assert "Name: test-pkg" in metadata
        assert "Version: 0.1.0" in metadata
        assert "Description-Content-Type" not in metadata


class TestRecordHash:
    def test_known_value(self):
        data = b"hello world"
        digest = hashlib.sha256(data).digest()
        expected = "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert build_wheels._record_hash(data) == expected


class TestPlatformTags:
    def test_all_platforms_mapped(self):
        from duckdb_cli.downloader import AVAILABLE_PLATFORMS
        for plat in AVAILABLE_PLATFORMS:
            assert plat in build_wheels.PLATFORM_TAGS


class TestBuildWheel:
    def test_wheel_structure(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("osx-arm64", "1.0.0", PROJECT, out_dir)

        assert whl is not None
        assert whl.endswith(".whl")
        assert "macosx_12_0_arm64" in whl

        with zipfile.ZipFile(whl) as zf:
            names = zf.namelist()

            # Python source files (downloader excluded)
            assert "duckdb_cli/__init__.py" in names
            assert "duckdb_cli/__main__.py" in names
            assert "duckdb_cli/downloader.py" not in names

            # Binary inside package dir (not .data/scripts/)
            assert "duckdb_cli/duckdb" in names
            assert not any(".data/scripts/" in n for n in names)

            # dist-info files
            assert any(n.endswith("METADATA") for n in names)
            assert any(n.endswith("WHEEL") for n in names)
            assert any(n.endswith("RECORD") for n in names)

            # entry_points.txt
            ep_name = [n for n in names if n.endswith("entry_points.txt")][0]
            ep_content = zf.read(ep_name).decode("utf-8")
            assert "[console_scripts]" in ep_content
            assert "duckdb = duckdb_cli.__main__:main" in ep_content

            # top_level.txt
            tl_name = [n for n in names if n.endswith("top_level.txt")][0]
            assert "duckdb_cli" in zf.read(tl_name).decode("utf-8")

    def test_wheel_filename(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("linux-amd64", "1.2.3", PROJECT, out_dir)

        basename = os.path.basename(whl)
        assert basename == "duckdb_cli-1.2.3-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"

    def test_wheel_file_content(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("osx-arm64", "1.0.0", PROJECT, out_dir)

        with zipfile.ZipFile(whl) as zf:
            wheel_name = [n for n in zf.namelist() if n.endswith("WHEEL")][0]
            wheel_content = zf.read(wheel_name).decode("utf-8")

        assert "Wheel-Version: 1.0" in wheel_content
        assert "Tag: py3-none-macosx_12_0_arm64" in wheel_content
        assert "Root-Is-Purelib: false" in wheel_content

    def test_record_hashes_valid(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("osx-arm64", "1.0.0", PROJECT, out_dir)

        with zipfile.ZipFile(whl) as zf:
            record_name = [n for n in zf.namelist() if n.endswith("RECORD")][0]
            record_content = zf.read(record_name).decode("utf-8")

            reader = csv.reader(io.StringIO(record_content))
            for row in reader:
                arcname, hash_str, size_str = row
                if arcname == record_name:
                    assert hash_str == ""
                    continue
                data = zf.read(arcname)
                expected_hash = build_wheels._record_hash(data)
                assert hash_str == expected_hash, f"Hash mismatch for {arcname}"
                assert int(size_str) == len(data), f"Size mismatch for {arcname}"

    def test_windows_wheel(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("windows-amd64", "1.0.0", PROJECT, out_dir)

        assert "win_amd64" in os.path.basename(whl)

        with zipfile.ZipFile(whl) as zf:
            assert "duckdb_cli/duckdb.exe" in zf.namelist()

    def test_reproducible_timestamps(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=_fake_download):
            whl = build_wheels.build_wheel("osx-arm64", "1.0.0", PROJECT, out_dir)

        with zipfile.ZipFile(whl) as zf:
            for info in zf.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0), f"Non-reproducible timestamp in {info.filename}"

    def test_empty_download_returns_none(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        os.makedirs(out_dir)

        with patch.object(build_wheels, "download", side_effect=lambda p, version, out_dir: []):
            result = build_wheels.build_wheel("osx-arm64", "1.0.0", PROJECT, out_dir)

        assert result is None


class TestMainCli:
    def test_main_single_platform(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        with patch("sys.argv", ["build_wheels.py", "--version", "1.0.0", "--platform", "osx-arm64", "--out-dir", out_dir]), \
             patch.object(build_wheels, "download", side_effect=_fake_download):
            build_wheels.main()

        wheels = os.listdir(out_dir)
        assert len(wheels) == 1
        assert "macosx_12_0_arm64" in wheels[0]

    def test_main_all_platforms(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        with patch("sys.argv", ["build_wheels.py", "--version", "1.0.0", "--out-dir", out_dir]), \
             patch.object(build_wheels, "download", side_effect=_fake_download):
            build_wheels.main()

        assert len(os.listdir(out_dir)) == 6

    def test_main_creates_out_dir(self, tmp_path):
        out_dir = str(tmp_path / "new_dist")
        with patch("sys.argv", ["build_wheels.py", "--version", "1.0.0", "--platform", "osx-arm64", "--out-dir", out_dir]), \
             patch.object(build_wheels, "download", side_effect=_fake_download):
            build_wheels.main()

        assert os.path.isdir(out_dir)
