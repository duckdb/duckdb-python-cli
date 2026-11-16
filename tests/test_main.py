"""Tests for duckdb_cli.__main__."""

import os
from unittest.mock import patch

import pytest

from duckdb_cli.__main__ import _build_ext_cmd, _get_extensions_dir, main


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


def _dirs_after(ext_dir, setup_sql=None):
    duckdb = pytest.importorskip("duckdb", reason="the SQL is checked on a real engine")
    con = duckdb.connect()
    if setup_sql:
        con.execute(setup_sql)
    con.execute(_build_ext_cmd(ext_dir))
    return con.execute("select current_setting('extension_directories')").fetchone()[0]


class TestBuildExtCmd:
    def test_default_then_pip_dir(self):
        assert _dirs_after("/sp/.duckdb_extensions") == ["~/.duckdb/extensions", "/sp/.duckdb_extensions"]

    def test_user_list_then_pip_dir(self):
        assert _dirs_after("/sp/.duckdb_extensions", setup_sql="SET extension_directories = ['/a', '/b']") == ["/a", "/b", "/sp/.duckdb_extensions"]

    def test_deprecated_singular_setting_adds_only_pip_dir(self):
        assert _dirs_after("/sp/.duckdb_extensions", setup_sql="SET extension_directory = '/single'") == ["/sp/.duckdb_extensions"]

    def test_quotes_and_backslashes_round_trip(self):
        path = "C:\\Users\\Jan O'Brien\\site-packages\\.duckdb_extensions"
        assert _dirs_after(path)[-1] == path


@pytest.mark.skipif(not os.environ.get("DUCKDB_CLI_NETWORK"), reason="downloads an extension; set DUCKDB_CLI_NETWORK=1")
def test_a_wheel_extension_loads_from_the_pip_dir_through_an_explicit_load(tmp_path):
    """The directory is last in the list, and LOAD still finds the extension there without a download."""
    import gzip
    import urllib.request

    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    version = con.execute("select version()").fetchone()[0].lstrip("v")
    platform = con.execute("pragma platform").fetchone()[0]
    ext_dir = tmp_path / ".duckdb_extensions"
    target = ext_dir / f"v{version}" / platform
    target.mkdir(parents=True)
    url = f"https://extensions.duckdb.org/v{version}/{platform}/tpch.duckdb_extension.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "duckdb-cli-tests/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        (target / "tpch.duckdb_extension").write_bytes(gzip.decompress(resp.read()))

    con.execute("set autoinstall_known_extensions = false")
    con.execute(_build_ext_cmd(str(ext_dir)))
    con.execute("load tpch")
    name, loaded, path = con.execute("select extension_name, loaded, install_path from duckdb_extensions() where extension_name = 'tpch'").fetchone()
    assert loaded and str(ext_dir) in path
    assert con.execute("select count(*) from tpch_queries()").fetchone()[0] == 22


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

    def test_extensions_dir_adds_cmd_before_user_args(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value="/sp/.duckdb_extensions"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb", "-c", "SELECT 1"]):
            with pytest.raises(SystemExit):
                main()

        args = call.call_args[0][0]
        assert args[0] == "/fake/duckdb"
        assert args[1] == "-cmd"
        assert args[2] == _build_ext_cmd("/sp/.duckdb_extensions")
        assert args[3:] == ["-c", "SELECT 1"]

    def test_forwards_exit_code(self):
        with patch("duckdb_cli.__main__._find_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__._get_extensions_dir", return_value=None), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=42), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 42
