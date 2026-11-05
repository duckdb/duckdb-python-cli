"""Tests for scripts/missing_versions.py."""

import os
import sys
import urllib.error
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import missing_versions as mv
from missing_versions import missing_versions, stable_releases


def _http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, None)


class TestStableReleases:
    def test_filters_drafts_prereleases_and_odd_tags(self):
        releases = [
            {"tag_name": "v2.0.0", "draft": False, "prerelease": False},
            {"tag_name": "v2.1.0", "draft": False, "prerelease": True},
            {"tag_name": "v2.0.1", "draft": True, "prerelease": False},
            {"tag_name": "v1.5.6", "draft": False, "prerelease": False},
            {"tag_name": "nightly", "draft": False, "prerelease": False},
            {"tag_name": "v1.5", "draft": False, "prerelease": False},
        ]
        assert stable_releases(releases) == ["2.0.0", "1.5.6"]


class TestMissingVersions:
    RELEASED = ["2.0.0", "1.5.6", "1.5.5", "1.5.4", "1.4.5", "1.5.3", "1.5.0", "1.4.4", "1.3.2"]
    PUBLISHED = ["1.4.4", "1.4.4.post1", "1.5.0", "1.5.4", "1.5.5", "1.5.6"]

    def test_floor_keeps_older_lines_out(self):
        assert missing_versions(self.RELEASED, self.PUBLISHED, "1.5.0") == ["1.5.3", "2.0.0"]

    def test_lower_floor_includes_older_patch_release(self):
        assert missing_versions(self.RELEASED, self.PUBLISHED, "1.4.0") == ["1.4.5", "1.5.3", "2.0.0"]

    def test_post_release_counts_as_published(self):
        assert missing_versions(["1.4.4"], ["1.4.4.post2"], "1.0.0") == []

    def test_sorted_numerically_not_lexically(self):
        assert missing_versions(["1.10.0", "1.9.0", "1.2.0"], [], "1.0.0") == ["1.2.0", "1.9.0", "1.10.0"]

    def test_nothing_published_yet(self):
        assert missing_versions(["2.0.0", "1.5.6"], [], "1.5.0") == ["1.5.6", "2.0.0"]

    def test_all_published(self):
        assert missing_versions(["2.0.0"], ["2.0.0"], "1.5.0") == []


class TestPublishedVersions:
    def test_reads_simple_api_versions(self):
        with patch.object(mv, "_get_json", return_value={"versions": ["1.5.0", "1.5.6"]}) as get:
            assert mv.published_versions("https://test.pypi.org") == ["1.5.0", "1.5.6"]
        assert get.call_args[0] == ("https://test.pypi.org/simple/duckdb-cli/", "application/vnd.pypi.simple.v1+json")

    def test_unknown_project_means_nothing_published(self):
        with patch.object(mv, "_get_json", side_effect=_http_error(404)):
            assert mv.published_versions("https://pypi.org") == []

    def test_other_errors_propagate(self):
        with patch.object(mv, "_get_json", side_effect=_http_error(500)), pytest.raises(urllib.error.HTTPError):
            mv.published_versions("https://pypi.org")


class TestMain:
    def test_prints_one_version_per_line(self, capsys):
        releases = [
            {"tag_name": "v2.0.0", "draft": False, "prerelease": False},
            {"tag_name": "v1.5.6", "draft": False, "prerelease": False},
            {"tag_name": "v1.5.3", "draft": False, "prerelease": False},
            {"tag_name": "v1.4.5", "draft": False, "prerelease": False},
        ]
        with patch.object(mv.sys, "argv", ["missing_versions.py", "--minimum", "1.5.0"]), \
             patch.object(mv, "_get_json", return_value=releases), \
             patch.object(mv, "published_versions", return_value=["1.5.6"]) as published:
            mv._main()
        assert capsys.readouterr().out == "1.5.3\n2.0.0\n"
        published.assert_called_once_with("https://pypi.org")

    def test_prints_nothing_when_all_published(self, capsys):
        releases = [{"tag_name": "v2.0.0", "draft": False, "prerelease": False}]
        with patch.object(mv.sys, "argv", ["missing_versions.py", "--minimum", "1.5.0", "--index", "https://test.pypi.org"]), \
             patch.object(mv, "_get_json", return_value=releases), \
             patch.object(mv, "published_versions", return_value=["2.0.0"]) as published:
            mv._main()
        assert capsys.readouterr().out == ""
        published.assert_called_once_with("https://test.pypi.org")
