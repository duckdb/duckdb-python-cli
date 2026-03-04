import os
import subprocess
import sys

from duckdb_cli.downloader import ensure_binary


def main():
    exe = ensure_binary()
    pkg_dir = os.path.dirname(os.path.abspath(__file__))

    ext_dir = os.path.join(pkg_dir, "extensions")
    secret_dir = os.path.join(pkg_dir, "secrets")

    # Escape single quotes for SQL string literals
    ext_dir_escaped = ext_dir.replace("'", "''")
    secret_dir_escaped = secret_dir.replace("'", "''")

    cmd = [
        exe,
        "-cmd",
        "SET extension_directory='%s'; SET secret_directory='%s';" % (ext_dir_escaped, secret_dir_escaped),
    ] + sys.argv[1:]

    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
