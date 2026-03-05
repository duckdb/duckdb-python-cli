import os
import subprocess
import sys


def _find_binary():
    """Find the DuckDB CLI binary, downloading if necessary."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    bin_name = "duckdb.exe" if sys.platform == "win32" else "duckdb"
    bin_path = os.path.join(pkg_dir, bin_name)
    if os.path.isfile(bin_path):
        return bin_path
    # Binary not bundled (dev install) — use downloader
    from duckdb_cli.downloader import ensure_binary
    return ensure_binary()


def _get_extensions_dir():
    """Return path to .duckdb_extensions in site-packages, or None."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    site_packages = os.path.dirname(pkg_dir)
    ext_dir = os.path.join(site_packages, ".duckdb_extensions")
    if os.path.isdir(ext_dir):
        return ext_dir
    return None


def _get_version():
    """Return the duckdb-cli package version as a tuple of ints."""
    from importlib.metadata import version
    return tuple(int(x) for x in version("duckdb-cli").split(".")[:3])


def _build_ext_cmd(ext_dir):
    """Build the SQL command to configure the extension search path."""
    escaped = ext_dir.replace("'", "''")
    if _get_version() >= (1, 5, 0):
        return f"SET extension_directories=['{escaped}', '~/.duckdb/extensions'];"
    else:
        return f"SET extension_directory='{escaped}';"


def main():
    exe = _find_binary()
    cmd_parts = []

    ext_dir = _get_extensions_dir()
    if ext_dir:
        cmd_parts.append(_build_ext_cmd(ext_dir))

    cmd = [exe]
    if cmd_parts:
        cmd += ["-cmd", " ".join(cmd_parts)]
    cmd += sys.argv[1:]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
