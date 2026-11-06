"""Tests for duckdb_cli.__main__."""

import os
import sys
from unittest.mock import patch

import pytest

from duckdb_cli.__main__ import _build_ext_cmd, _get_extensions_dir, _is_writable, main


class TestGetExtensionsDir:
    def test_returns_path_when_dir_exists(self, tmp_path):
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir()
        ext_dir = tmp_path / ".duckdb_extensions"
        ext_dir.mkdir()

        with patch("duckdb_cli.__main__.os.path.abspath", return_value=str(pkg_dir / "__main__.py")):
            assert _get_extensions_dir() == str(ext_dir)

    def test_returns_none_when_dir_missing(self, tmp_path):
        pkg_dir = tmp_path / "duckdb_cli"
        pkg_dir.mkdir()

        with patch("duckdb_cli.__main__.os.path.abspath", return_value=str(pkg_dir / "__main__.py")):
            assert _get_extensions_dir() is None


class TestIsWritable:
    def test_writable_dir_leaves_nothing_behind(self, tmp_path):
        assert _is_writable(str(tmp_path)) is True
        assert os.listdir(tmp_path) == []

    @pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs a directory mode the probe cannot write past")
    def test_read_only_dir(self, tmp_path):
        tmp_path.chmod(0o555)
        try:
            assert _is_writable(str(tmp_path)) is False
        finally:
            tmp_path.chmod(0o755)

    def test_access_denied_is_one_attempt(self, tmp_path):
        calls = []

        def denied(path, flags, mode=0o777):
            calls.append(path)
            raise PermissionError(13, "Access is denied", path)

        with patch("duckdb_cli.__main__.os.open", side_effect=denied):
            assert _is_writable(str(tmp_path)) is False
        assert len(calls) == 1
        assert os.path.dirname(calls[0]) == str(tmp_path)


def _dirs_after(ext_dir, writable=True, setup_sql=None):
    duckdb = pytest.importorskip("duckdb", reason="the SQL is checked on a real engine")
    con = duckdb.connect()
    if setup_sql:
        con.execute(setup_sql)
    con.execute(_build_ext_cmd(ext_dir, writable))
    return con.execute("select current_setting('extension_directories')").fetchone()[0]


class TestBuildExtCmd:
    def test_default_becomes_pip_dir_then_engine_default(self):
        assert _dirs_after("/sp/.duckdb_extensions") == ["/sp/.duckdb_extensions", "~/.duckdb/extensions"]

    def test_user_list_is_kept_after_pip_dir(self):
        assert _dirs_after("/sp/.duckdb_extensions", setup_sql="SET extension_directories = ['/a', '/b']") == ["/sp/.duckdb_extensions", "/a", "/b"]

    def test_deprecated_singular_setting_adds_only_pip_dir(self):
        assert _dirs_after("/sp/.duckdb_extensions", setup_sql="SET extension_directory = '/single'") == ["/sp/.duckdb_extensions"]

    def test_read_only_pip_dir_goes_last(self):
        assert _dirs_after("/sp/.duckdb_extensions", writable=False) == ["~/.duckdb/extensions", "/sp/.duckdb_extensions"]
        assert _dirs_after("/sp/.duckdb_extensions", writable=False, setup_sql="SET extension_directories = ['/a']") == ["/a", "/sp/.duckdb_extensions"]

    def test_quotes_and_backslashes_round_trip(self):
        path = "C:\\Users\\Jan O'Brien\\site-packages\\.duckdb_extensions"
        assert _dirs_after(path)[0] == path
        assert _dirs_after(path, writable=False)[-1] == path


class TestMain:
    def test_no_extensions_dir_runs_binary_unchanged(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value=None), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert call.call_args[0][0] == ["/fake/duckdb", "-c", "SELECT 1"]

    @pytest.mark.parametrize("writable", [True, False])
    def test_extensions_dir_adds_cmd_before_user_args(self, writable):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value="/sp/.duckdb_extensions"), \
             patch("duckdb_cli.__main__._is_writable", return_value=writable), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit):
                main()

        args = call.call_args[0][0]
        assert args[0] == "/fake/duckdb"
        assert args[1] == "-cmd"
        assert args[2] == _build_ext_cmd("/sp/.duckdb_extensions", writable)
        assert args[3:] == ["-c", "SELECT 1"]

    def test_forwards_exit_code(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value=None), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=42), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 42
