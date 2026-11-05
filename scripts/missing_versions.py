#!/usr/bin/env python3
"""Print the stable DuckDB releases that duckdb-cli has not published yet, one per line.

Usage:
    uv run --no-project scripts/missing_versions.py --minimum 1.5.0 [--index https://test.pypi.org]
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

_RELEASES_API = "https://api.github.com/repos/duckdb/duckdb/releases?per_page=100"
_STABLE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse(version):
    return tuple(int(part) for part in version.split("."))


def stable_releases(releases):
    """Versions of the releases that are neither drafts nor pre-releases, as 'X.Y.Z' strings."""
    versions = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        match = _STABLE_TAG.match(release["tag_name"])
        if match:
            versions.append(".".join(match.groups()))
    return versions


def missing_versions(released, published, minimum):
    """Released versions at or above minimum with no published release, oldest first.

    A published post-release such as 1.4.4.post1 counts as 1.4.4 being published.
    """
    done = {re.sub(r"\.post\d+$", "", v) for v in published}
    floor = _parse(minimum)
    wanted = {v for v in released if _parse(v) >= floor and v not in done}
    return sorted(wanted, key=_parse)


def _get_json(url, accept, token=None):
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def published_versions(index):
    """Versions of duckdb-cli on the index, or none when the project does not exist there yet."""
    try:
        page = _get_json(f"{index}/simple/duckdb-cli/", "application/vnd.pypi.simple.v1+json")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        return []
    return page["versions"]


def _main():
    parser = argparse.ArgumentParser(description="List unpublished stable DuckDB releases.")
    parser.add_argument("--minimum", required=True, help="Oldest version to consider (e.g. 1.5.0)")
    parser.add_argument("--index", default="https://pypi.org", help="Package index base URL")
    parser.add_argument("--github-token", default=None, help="Token for the GitHub API (raises the rate limit)")
    args = parser.parse_args()

    released = stable_releases(_get_json(_RELEASES_API, "application/vnd.github+json", token=args.github_token))
    published = published_versions(args.index)
    for version in missing_versions(released, published, args.minimum):
        print(version)


if __name__ == "__main__":
    _main()
