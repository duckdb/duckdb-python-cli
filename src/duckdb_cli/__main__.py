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


def _discover_extensions():
    """Discover installed duckdb-ext-* packages with matching versions.

    Reads duckdb-cli's own Provides-Extra metadata to get the list of
    known extension names, then checks which are installed with a
    matching version.
    """
    from importlib.metadata import metadata, version as pkg_version, PackageNotFoundError

    own_version = pkg_version("duckdb-cli")

    # Get known extension names from our own extras
    meta = metadata("duckdb-cli")
    extras = meta.get_all("Provides-Extra") or []
    # Filter out "all" and any non-extension extras
    ext_names = [e for e in extras if e != "all"]

    paths = []
    for name in ext_names:
        pkg = f"duckdb-ext-{name}"
        mod_name = f"duckdb_ext_{name}"
        try:
            ext_version = pkg_version(pkg)
        except PackageNotFoundError:
            continue
        if ext_version != own_version:
            continue
        try:
            mod = __import__(mod_name)
            path = mod.get_extension_load_path()
            paths.append(path)
        except (ImportError, AttributeError):
            continue
    return paths


def _parse_load_ext_args(argv):
    """Extract --load-ext args, return (ext_modules, remaining_argv)."""
    ext_modules = []
    remaining = []
    i = 0
    while i < len(argv):
        if argv[i] == "--load-ext" and i + 1 < len(argv):
            ext_modules.append(argv[i + 1])
            i += 2
        else:
            remaining.append(argv[i])
            i += 1
    return ext_modules, remaining


def main():
    exe = _find_binary()
    pkg_dir = os.path.dirname(os.path.abspath(__file__))

    ext_dir = os.path.join(pkg_dir, "extensions")
    secret_dir = os.path.join(pkg_dir, "secrets")

    # Escape single quotes for SQL string literals
    ext_dir_escaped = ext_dir.replace("'", "''")
    secret_dir_escaped = secret_dir.replace("'", "''")

    extra_modules, remaining_argv = _parse_load_ext_args(sys.argv[1:])

    # Discover installed extension packages
    load_paths = _discover_extensions()

    # Load user-specified extension modules
    for mod_name in extra_modules:
        try:
            mod = __import__(mod_name)
            load_paths.append(mod.get_extension_load_path())
        except (ImportError, AttributeError) as e:
            print(f"Warning: could not load extension module {mod_name}: {e}", file=sys.stderr)

    # Build -cmd string
    cmd_parts = [
        f"SET extension_directory='{ext_dir_escaped}';",
        f"SET secret_directory='{secret_dir_escaped}';",
    ]
    for path in load_paths:
        escaped = path.replace("'", "''")
        cmd_parts.append(f"LOAD '{escaped}';")

    cmd = [exe, "-cmd", " ".join(cmd_parts)] + remaining_argv

    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
