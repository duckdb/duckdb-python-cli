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
    return ext_dir


def _build_ext_cmd(ext_dir):
    """Build the SQL command to configure the extension search path.

    The idea is:
    - If extension_directories already has something set, we can assume duckdb
      will not install extensions in our pip-managed ext dir;
    - If extension_directory already has something set, then we can assume the
      same;
    - Only otherwise, we must prepend a default extension directory that duckdb
      may install extensions to. The risk is of course that our default is
      somehow invalid. But we just do not have a way to query the default right
      now, so this will have to do.
    """
    escaped = ext_dir.replace("'", "''")
    return f"""
    SET extension_directories = list_concat(
      CASE
          WHEN current_setting('extension_directories') != '[]' THEN current_setting('extension_directories')::VARCHAR[]
          WHEN current_setting('extension_directory') != '' THEN []
          ELSE ['~/.duckdb/extensions']
      END,
      ['{escaped}']
    );
    """


def main():
    exe = _find_binary()
    ext_dir = _get_extensions_dir()
    cmd = [exe, "-cmd", _build_ext_cmd(ext_dir)]
    cmd += sys.argv[1:]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
