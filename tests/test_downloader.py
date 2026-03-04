"""Tests for duckdb_cli.downloader."""

import io
import os
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
    def test_download_latest(self, tmp_path):
        zip_data = _make_zip(["duckdb"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("duckdb_cli.downloader._get_latest_version", return_value="v1.0.0"), \
             patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp):
            result = download("linux-amd64", out_dir=str(tmp_path / "bin"))

        assert len(result) == 1
        assert os.path.basename(result[0]) == "duckdb"
        assert os.path.isfile(result[0])

    def test_download_specific_version(self, tmp_path):
        zip_data = _make_zip(["duckdb"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = download("osx-arm64", version="1.2.3", out_dir=str(tmp_path / "bin"))

        call_url = mock_urlopen.call_args[0][0]
        assert "v1.2.3" in call_url
        assert len(result) == 1

    def test_download_version_with_v_prefix(self, tmp_path):
        zip_data = _make_zip(["duckdb"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            download("osx-arm64", version="v1.2.3", out_dir=str(tmp_path / "bin"))

        call_url = mock_urlopen.call_args[0][0]
        assert "v1.2.3" in call_url
        assert "vv1.2.3" not in call_url

    def test_download_creates_out_dir(self, tmp_path):
        zip_data = _make_zip(["duckdb"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        out = str(tmp_path / "new" / "dir")
        with patch("duckdb_cli.downloader._get_latest_version", return_value="v1.0.0"), \
             patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp):
            download("linux-amd64", out_dir=out)

        assert os.path.isdir(out)

    def test_download_returns_multiple_files(self, tmp_path):
        zip_data = _make_zip(["duckdb", "LICENSE"])
        mock_resp = MagicMock()
        mock_resp.read.return_value = zip_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("duckdb_cli.downloader._get_latest_version", return_value="v1.0.0"), \
             patch("duckdb_cli.downloader.urllib.request.urlopen", return_value=mock_resp):
            result = download("linux-amd64", out_dir=str(tmp_path / "bin"))

        assert len(result) == 2


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
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"tag_name": "v1.5.0"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

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
