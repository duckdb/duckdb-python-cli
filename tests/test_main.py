"""Tests for duckdb_cli.__main__."""

import os
from unittest.mock import patch

import pytest

from duckdb_cli.__main__ import main


class TestMain:
    def test_calls_binary_with_config_flags(self):
        with patch("duckdb_cli.__main__.ensure_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

            args = mock_call.call_args[0][0]
            assert args[0] == "/fake/duckdb"
            assert args[1] == "-cmd"
            assert "extension_directory" in args[2]
            assert "secret_directory" in args[2]
            assert args[3] == "--version"

    def test_forwards_exit_code(self):
        with patch("duckdb_cli.__main__.ensure_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=42), \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 42

    def test_config_paths_contain_extensions_and_secrets(self):
        with patch("duckdb_cli.__main__.ensure_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]):
            with pytest.raises(SystemExit):
                main()

            cmd_arg = mock_call.call_args[0][0][2]
            assert "extensions" in cmd_arg
            assert "secrets" in cmd_arg

    def test_single_quote_escaping(self):
        with patch("duckdb_cli.__main__.ensure_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli"]), \
             patch("duckdb_cli.__main__.os.path.dirname") as mock_dirname, \
             patch("duckdb_cli.__main__.os.path.abspath", side_effect=lambda x: x):
            # Simulate a path with single quotes
            mock_dirname.return_value = "/path/with'quote"
            with pytest.raises(SystemExit):
                main()

            cmd_arg = mock_call.call_args[0][0][2]
            assert "''" in cmd_arg  # single quotes should be escaped

    def test_user_args_appended(self):
        with patch("duckdb_cli.__main__.ensure_binary", return_value="/fake/duckdb"), \
             patch("duckdb_cli.__main__.subprocess.call", return_value=0) as mock_call, \
             patch("duckdb_cli.__main__.sys.argv", ["duckdb-cli", "-c", "SELECT 1", "--readonly"]):
            with pytest.raises(SystemExit):
                main()

            args = mock_call.call_args[0][0]
            assert args[3:] == ["-c", "SELECT 1", "--readonly"]
