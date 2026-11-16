import os
import subprocess
import sys


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


def _build_ext_cmd(ext_dir):
    """SQL that appends the pip directory to the extension search path.

    LOAD searches every listed directory, so a pip-installed extension loads from there without a
    download. Autoinstall checks only the first directory before downloading, so an extension that is
    not loaded explicitly may be downloaded again, and offline its autoload fails, until the engine
    treats an extension found in any configured directory as installed. Setting the list replaces the
    engine default, so the default is kept when nothing else is configured.
    """
    escaped = ext_dir.replace("'", "''")
    return f"""SET extension_directories = list_append(
      CASE
          WHEN current_setting('extension_directories') != '[]' THEN current_setting('extension_directories')::VARCHAR[]
          WHEN current_setting('extension_directory') != '' THEN []
          ELSE ['~/.duckdb/extensions']
      END, '{escaped}');"""


def main():
    exe = _find_binary()
    cmd = [exe]
    ext_dir = _get_extensions_dir()
    if ext_dir is not None:
        cmd += ["-cmd", _build_ext_cmd(ext_dir)]
    cmd += sys.argv[1:]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
