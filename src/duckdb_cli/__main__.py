import os
import subprocess
import sys
import uuid


def _find_binary():
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    bin_name = "duckdb.exe" if sys.platform == "win32" else "duckdb"
    bin_path = os.path.join(pkg_dir, bin_name)
    if os.path.isfile(bin_path):
        return bin_path
    from duckdb_cli.downloader import ensure_binary

    return ensure_binary()


def _get_extensions_dir():
    """The .duckdb_extensions directory next to the package, or None when it does not exist."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    ext_dir = os.path.join(os.path.dirname(pkg_dir), ".duckdb_extensions")
    return ext_dir if os.path.isdir(ext_dir) else None


def _is_writable(directory):
    # os.access grants write on every Windows directory, and tempfile retries an access-denied create
    # up to os.TMP_MAX times there before Python 3.13, so the probe is one explicit create.
    probe = os.path.join(directory, f".write-probe-{os.getpid()}-{uuid.uuid4().hex}")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_TEMPORARY", 0)
    try:
        fd = os.open(probe, flags, 0o600)
    except OSError:
        return False
    os.close(fd)
    if not hasattr(os, "O_TEMPORARY"):
        try:
            os.unlink(probe)
        except OSError:
            pass
    return True


def _build_ext_cmd(ext_dir, writable):
    """SQL that puts the pip directory in the extension search path: first when DuckDB can install into it.

    Autoinstall checks only the first directory before downloading, so a pip-installed extension is
    autoloaded without a download only when its directory comes first; but the first directory is also
    where DuckDB installs, so a read-only one goes last and stays searchable for LOAD. Setting the list
    replaces the engine default, so the default is kept when nothing else is configured. The deprecated
    extension_directory setting always precedes the list in the engine.
    """
    escaped = ext_dir.replace("'", "''")
    others = """
      CASE
          WHEN current_setting('extension_directories') != '[]' THEN current_setting('extension_directories')::VARCHAR[]
          WHEN current_setting('extension_directory') != '' THEN []
          ELSE ['~/.duckdb/extensions']
      END"""
    if writable:
        return f"SET extension_directories = list_prepend('{escaped}', {others});"
    return f"SET extension_directories = list_append({others}, '{escaped}');"


def main():
    exe = _find_binary()
    cmd = [exe]
    ext_dir = _get_extensions_dir()
    if ext_dir is not None:
        cmd += ["-cmd", _build_ext_cmd(ext_dir, _is_writable(ext_dir))]
    cmd += sys.argv[1:]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
