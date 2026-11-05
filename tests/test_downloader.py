"""Tests for duckdb_cli.downloader."""

import io
import os
import stat
import sys
import tarfile
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from duckdb_cli.downloader import (
    AVAILABLE_PLATFORMS,
    _get_latest_version,
    _main,
    detect_platform,
    download,
    ensure_binary,
)


def _make_zip(filenames):
    """Create an in-memory zip with dummy files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in filenames:
            zf.writestr(name, b"fake-binary-content")
    return buf.getvalue()


def _make_tar(filenames):
    """Create an in-memory tar.gz with dummy files, directories included as entries."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in filenames:
            if name.endswith("/"):
                info = tarfile.TarInfo(name.rstrip("/"))
                info.type = tarfile.DIRTYPE
                tf.addfile(info)
                continue
            content = b"fake-binary-content"
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _response(data):
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "error", {}, None)


def _fake_releases(assets):
    """urlopen stand-in serving the given {asset name: bytes}; other URLs get 404."""
    calls = []

    def urlopen(url, *args, **kwargs):
        calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name in assets:
            return _response(assets[name])
        raise _http_error(url, 404)

    return urlopen, calls


class TestDetectPlatform:
    @patch("duckdb_cli.downloader.platform")
    def test_linux_x86_64(self, mock_plat):
        mock_plat.system.return_value = "Linux"
        mock_plat.machine.return_value = "x86_64"
        assert detect_platform() == "linux-amd64"

    @patch("duckdb_cli.downloader.platform")
    def test_darwin_arm64(self, mock_plat):
        mock_plat.system.return_value = "Darwin"
        mock_plat.machine.return_value = "arm64"
        assert detect_platform() == "osx-arm64"

    @patch("duckdb_cli.downloader.platform")
    def test_windows_amd64(self, mock_plat):
        mock_plat.system.return_value = "Windows"
        mock_plat.machine.return_value = "AMD64"
        assert detect_platform() == "windows-amd64"

    @patch("duckdb_cli.downloader.platform")
    def test_linux_aarch64(self, mock_plat):
        mock_plat.system.return_value = "Linux"
        mock_plat.machine.return_value = "aarch64"
        assert detect_platform() == "linux-arm64"

    @patch("duckdb_cli.downloader.platform")
    def test_unsupported_exits(self, mock_plat):
        mock_plat.system.return_value = "FreeBSD"
        mock_plat.machine.return_value = "riscv64"
        with pytest.raises(SystemExit):
            detect_platform()


class TestDownload:
    def test_download_latest_tarball(self, tmp_path):
        urlopen, calls = _fake_releases({"duckdb-cli-linux-amd64.tar.gz": _make_tar(["duckdb"])})

        with patch("duckdb_cli.downloader._get_latest_version", return_value="v2.0.0"), \
             patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            result = download("linux-amd64", out_dir=str(tmp_path / "bin"))

        assert calls == ["https://github.com/duckdb/duckdb/releases/download/v2.0.0/duckdb-cli-linux-amd64.tar.gz"]
        assert [os.path.basename(r) for r in result] == ["duckdb"]
        with open(result[0], "rb") as f:
            assert f.read() == b"fake-binary-content"
        if sys.platform != "win32":
            assert os.stat(result[0]).st_mode & stat.S_IXUSR

    def test_falls_back_to_zip_when_tarball_missing(self, tmp_path):
        urlopen, calls = _fake_releases({"duckdb_cli-osx-arm64.zip": _make_zip(["duckdb"])})

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            result = download("osx-arm64", version="1.4.4", out_dir=str(tmp_path / "bin"))

        assert calls == [
            "https://github.com/duckdb/duckdb/releases/download/v1.4.4/duckdb-cli-osx-arm64.tar.gz",
            "https://github.com/duckdb/duckdb/releases/download/v1.4.4/duckdb_cli-osx-arm64.zip",
        ]
        assert [os.path.basename(r) for r in result] == ["duckdb"]

    def test_no_asset_raises(self, tmp_path):
        urlopen, calls = _fake_releases({})

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen), \
             pytest.raises(RuntimeError, match="v9.9.9 on linux-amd64"):
            download("linux-amd64", version="9.9.9", out_dir=str(tmp_path / "bin"))

        assert len(calls) == 2
        assert not os.path.exists(tmp_path / "bin")

    def test_non_404_error_propagates(self, tmp_path):
        def urlopen(url, *args, **kwargs):
            raise _http_error(url, 503)

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen), \
             pytest.raises(urllib.error.HTTPError) as excinfo:
            download("linux-amd64", version="2.0.0", out_dir=str(tmp_path / "bin"))

        assert excinfo.value.code == 503
        assert excinfo.value.url.endswith("duckdb-cli-linux-amd64.tar.gz")

    def test_download_version_with_v_prefix(self, tmp_path):
        urlopen, calls = _fake_releases({"duckdb-cli-osx-arm64.tar.gz": _make_tar(["duckdb"])})

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            download("osx-arm64", version="v1.2.3", out_dir=str(tmp_path / "bin"))

        assert "/v1.2.3/" in calls[0]
        assert "vv1.2.3" not in calls[0]

    def test_download_creates_out_dir(self, tmp_path):
        urlopen, _ = _fake_releases({"duckdb-cli-linux-amd64.tar.gz": _make_tar(["duckdb"])})

        out = str(tmp_path / "new" / "dir")
        with patch("duckdb_cli.downloader._get_latest_version", return_value="v2.0.0"), \
             patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            download("linux-amd64", out_dir=out)

        assert os.path.isdir(out)

    def test_tarball_flattens_paths_and_skips_directories(self, tmp_path):
        urlopen, _ = _fake_releases({
            "duckdb-cli-windows-amd64.tar.gz": _make_tar(["./", "./duckdb.exe", "./LICENSE"]),
        })

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            result = download("windows-amd64", version="2.0.0", out_dir=str(tmp_path / "bin"))

        assert sorted(os.path.basename(r) for r in result) == ["LICENSE", "duckdb.exe"]
        assert sorted(os.listdir(tmp_path / "bin")) == ["LICENSE", "duckdb.exe"]

    def test_zip_returns_multiple_files_and_skips_directories(self, tmp_path):
        urlopen, _ = _fake_releases({"duckdb_cli-linux-amd64.zip": _make_zip(["dir/", "duckdb", "LICENSE"])})

        with patch("duckdb_cli.downloader.urllib.request.urlopen", side_effect=urlopen):
            result = download("linux-amd64", version="1.4.4", out_dir=str(tmp_path / "bin"))

        assert sorted(os.path.basename(r) for r in result) == ["LICENSE", "duckdb"]


class TestEnsureBinary:
    def test_returns_existing_binary(self, tmp_path):
        """When binary already exists, return path without downloading."""
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir(parents=True)
        binary = pkg_dir / "duckdb"
        binary.write_bytes(b"fake")

        with patch("duckdb_cli.downloader.os.path.dirname", return_value=str(pkg_dir)), \
             patch("duckdb_cli.downloader.sys.platform", "linux"):
            result = ensure_binary()

        assert result == str(pkg_dir / "duckdb")

    def test_downloads_when_missing(self, tmp_path):
        """When binary doesn't exist, download it to pkg_dir."""
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir(parents=True)

        def fake_download(plat, out_dir):
            os.makedirs(out_dir, exist_ok=True)
            binary = os.path.join(out_dir, "duckdb")
            with open(binary, "wb") as f:
                f.write(b"fake-binary")
            return [binary]

        with patch("duckdb_cli.downloader.os.path.dirname", return_value=str(pkg_dir)), \
             patch("duckdb_cli.downloader.sys.platform", "linux"), \
             patch("duckdb_cli.downloader.download", side_effect=fake_download), \
             patch("duckdb_cli.downloader.detect_platform", return_value="linux-amd64"):
            result = ensure_binary()

        assert result == str(pkg_dir / "duckdb")

    def test_windows_binary_name(self, tmp_path):
        """On Windows, look for duckdb.exe."""
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir(parents=True)
        binary = pkg_dir / "duckdb.exe"
        binary.write_bytes(b"fake")

        with patch("duckdb_cli.downloader.os.path.dirname", return_value=str(pkg_dir)), \
             patch("duckdb_cli.downloader.sys.platform", "win32"):
            result = ensure_binary()

        assert result == str(pkg_dir / "duckdb.exe")


class TestGetLatestVersion:
    def test_parses_tag_name(self):
        mock_resp = _response(b'{"tag_name": "v1.5.0"}')

        with patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp):
            assert _get_latest_version() == "v1.5.0"


class TestMainCli:
    def test_main_auto_detect(self):
        with patch("duckdb_cli.downloader.argparse.ArgumentParser.parse_args") as mock_parse, \
             patch("duckdb_cli.downloader.detect_platform", return_value="osx-arm64") as mock_detect, \
             patch("duckdb_cli.downloader.download") as mock_dl:
            mock_parse.return_value = MagicMock(platform=None)
            _main()
            mock_detect.assert_called_once()
            mock_dl.assert_called_once_with("osx-arm64")

    def test_main_explicit_platform(self):
        with patch("duckdb_cli.downloader.argparse.ArgumentParser.parse_args") as mock_parse, \
             patch("duckdb_cli.downloader.download") as mock_dl:
            mock_parse.return_value = MagicMock(platform="linux-amd64")
            _main()
            mock_dl.assert_called_once_with("linux-amd64")
