"""Tests for duckdb_cli.__main__."""

import builtins
import types
from unittest.mock import patch, MagicMock

import pytest

from duckdb_cli.__main__ import main, _discover_extensions, _parse_load_ext_args


class TestMain:
    def test_calls_binary_with_config_flags(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._discover_extensions", return_value=[]), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

            args = mock_call.call_args[0][0]
            assert args[0] == "/fake/duckdb"
            assert args[1] == "-cmd"
            assert "extension_directory" in args[2]
            assert "secret_directory" in args[2]
            # User args come after -cmd
            assert args[3:] == ["-c", "SELECT 1"]

    def test_forwards_exit_code(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._discover_extensions", return_value=[]), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=42), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 42

    def test_single_quote_escaping(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._discover_extensions", return_value=[]), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]), \
             patch("duckdb_cli.__main__.os.path.dirname") as mock_dirname, \
             patch("duckdb_cli.__main__.os.path.abspath", side_effect=lambda x: x):
            mock_dirname.return_value = "/path/with'quote"
            with pytest.raises(SystemExit):
                main()

            cmd_arg = mock_call.call_args[0][0][2]
            assert "''" in cmd_arg


def _make_import_mock(fake_modules):
    """Create an __import__ replacement that returns fake modules by name."""
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in fake_modules:
            return fake_modules[name]
        return real_import(name, *args, **kwargs)

    return mock_import


class TestDiscoverExtensions:
    def test_discover_extensions_found(self):
        mock_meta = MagicMock()
        mock_meta.get_all.return_value = ["httpfs"]

        fake_mod = types.ModuleType("duckdb_ext_httpfs")
        fake_mod.get_extension_load_path = lambda: "/path/to/httpfs.duckdb_extension"

        with patch("importlib.metadata.metadata", return_value=mock_meta), \
             patch("importlib.metadata.version", side_effect=lambda pkg: "1.0.0"), \
             patch.object(builtins, "__import__", side_effect=_make_import_mock({"duckdb_ext_httpfs": fake_mod})):
            paths = _discover_extensions()

        assert "/path/to/httpfs.duckdb_extension" in paths

    def test_discover_extensions_version_mismatch(self):
        mock_meta = MagicMock()
        mock_meta.get_all.return_value = ["httpfs"]

        def version_side_effect(pkg):
            if pkg == "duckdb-cli":
                return "1.0.0"
            return "2.0.0"

        with patch("importlib.metadata.metadata", return_value=mock_meta), \
             patch("importlib.metadata.version", side_effect=version_side_effect):
            paths = _discover_extensions()

        assert paths == []

    def test_discover_extensions_not_installed(self):
        from importlib.metadata import PackageNotFoundError

        mock_meta = MagicMock()
        mock_meta.get_all.return_value = ["httpfs"]

        def version_side_effect(pkg):
            if pkg == "duckdb-cli":
                return "1.0.0"
            raise PackageNotFoundError(pkg)

        with patch("importlib.metadata.metadata", return_value=mock_meta), \
             patch("importlib.metadata.version", side_effect=version_side_effect):
            paths = _discover_extensions()

        assert paths == []

    def test_discover_extensions_skips_all_extra(self):
        mock_meta = MagicMock()
        mock_meta.get_all.return_value = ["all", "httpfs"]

        fake_mod = types.ModuleType("duckdb_ext_httpfs")
        fake_mod.get_extension_load_path = lambda: "/path/to/httpfs.duckdb_extension"

        with patch("importlib.metadata.metadata", return_value=mock_meta), \
             patch("importlib.metadata.version", side_effect=lambda pkg: "1.0.0"), \
             patch.object(builtins, "__import__", side_effect=_make_import_mock({"duckdb_ext_httpfs": fake_mod})):
            paths = _discover_extensions()

        # Only httpfs should be found, not "all"
        assert len(paths) == 1
        assert "/path/to/httpfs.duckdb_extension" in paths


class TestParseLoadExtArgs:
    def test_load_ext_flag_parsed(self):
        ext_modules, remaining = _parse_load_ext_args(["--load-ext", "my_ext", "-c", "SELECT 1"])
        assert ext_modules == ["my_ext"]
        assert remaining == ["-c", "SELECT 1"]

    def test_multiple_load_ext_flags(self):
        ext_modules, remaining = _parse_load_ext_args(["--load-ext", "a", "--load-ext", "b", "-c", "SELECT 1"])
        assert ext_modules == ["a", "b"]
        assert remaining == ["-c", "SELECT 1"]

    def test_no_load_ext_flags(self):
        ext_modules, remaining = _parse_load_ext_args(["-c", "SELECT 1"])
        assert ext_modules == []
        assert remaining == ["-c", "SELECT 1"]


class TestLoadExtIntegration:
    def test_load_ext_in_cmd_string(self):
        fake_mod = types.ModuleType("my_ext")
        fake_mod.get_extension_load_path = lambda: "/path/to/my_ext.duckdb_extension"

        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._discover_extensions", return_value=[]), \
             patch.object(builtins, "__import__", side_effect=_make_import_mock({"my_ext": fake_mod})), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "--load-ext", "my_ext", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit):
                main()

            args = mock_call.call_args[0][0]
            cmd_str = args[2]
            assert "LOAD '/path/to/my_ext.duckdb_extension';" in cmd_str
            # --load-ext should be stripped from remaining args
            assert args[3:] == ["-c", "SELECT 1"]

    def test_load_ext_warning_on_bad_module(self, capsys):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._discover_extensions", return_value=[]), \
             patch.object(builtins, "__import__", side_effect=_make_import_mock({})), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "--load-ext", "bad_mod"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "bad_mod" in captured.err
