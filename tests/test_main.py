"""Tests for duckdb_cli.__main__."""

from unittest.mock import patch

import pytest

from duckdb_cli.__main__ import main, _get_extensions_dir, _build_ext_cmd


class TestGetExtensionsDir:
    def test_returns_path_when_dir_exists(self, tmp_path):
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir()
        ext_dir = tmp_path / ".duckdb_extensions"
        ext_dir.mkdir()

        with patch("duckdb_cli.__main__.os.path.abspath", return_value=str(pkg_dir / "__main__.py")):
            result = _get_extensions_dir()
        assert result == str(ext_dir)

    def test_returns_none_when_dir_missing(self, tmp_path):
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir()

        with patch("duckdb_cli.__main__.os.path.abspath", return_value=str(pkg_dir / "__main__.py")):
            result = _get_extensions_dir()
        assert result is None


class TestBuildExtCmd:
    def test_plural_setting_v15(self):
        with patch("duckdb_cli.__main__._get_version", return_value=(1, 5, 0)):
            result = _build_ext_cmd("/site-packages/.duckdb_extensions")
        assert result == "SET extension_directories=['/site-packages/.duckdb_extensions', '~/.duckdb/extensions'];"

    def test_singular_setting_v14(self):
        with patch("duckdb_cli.__main__._get_version", return_value=(1, 4, 4)):
            result = _build_ext_cmd("/site-packages/.duckdb_extensions")
        assert result == "SET extension_directory='/site-packages/.duckdb_extensions';"

    def test_escapes_single_quotes(self):
        with patch("duckdb_cli.__main__._get_version", return_value=(1, 4, 4)):
            result = _build_ext_cmd("/path/with'quote")
        assert "with''quote" in result

    def test_v16_uses_plural(self):
        with patch("duckdb_cli.__main__._get_version", return_value=(1, 6, 0)):
            result = _build_ext_cmd("/ext")
        assert "extension_directories" in result


class TestMain:
    def test_no_extensions_dir_no_cmd(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value=None), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

            args = mock_call.call_args[0][0]
            assert args == ["/fake/duckdb", "-c", "SELECT 1"]

    def test_with_extensions_dir_adds_cmd(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value="/sp/.duckdb_extensions"), \
             patch("duckdb_cli.__main__._build_ext_cmd", return_value="SET extension_directory='/sp/.duckdb_extensions';") as mock_build, \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

            mock_build.assert_called_once_with("/sp/.duckdb_extensions")
            args = mock_call.call_args[0][0]
            assert args[0] == "/fake/duckdb"
            assert args[1] == "-cmd"
            assert "extension_directory" in args[2]
            assert args[3:] == ["-c", "SELECT 1"]

    def test_forwards_exit_code(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value=None), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=42), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 42
