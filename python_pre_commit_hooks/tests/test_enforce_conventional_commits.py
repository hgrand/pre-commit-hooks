#!/usr/bin/env python3

import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, mock_open

sys.path.append("..")

from enforce_conventional_commits import (
    conventional_types,
    get_modified_filepaths,
    is_conventional,
    is_special_commit,
    main,
    r_scope,
    r_types,
)


class TestPreCommit(unittest.TestCase):
    def test_get_modified_filepaths(self):
        result = get_modified_filepaths("modified:   path1\nnew file:   path2\n")
        self.assertEqual(result, [Path("path1"), Path("path2")])

    def test_get_modified_filepaths_empty(self):
        with patch("subprocess.run") as mock_subprocess_run:
            mock_subprocess_run.return_value = subprocess.CompletedProcess(
                args=["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRT"],
                returncode=0,
                stdout="",
                stderr="",
            )
            result = get_modified_filepaths("")
            self.assertEqual(result, [])

    def test_r_types(self):
        result = r_types(["feat", "fix"])
        self.assertEqual(result, "feat|fix")

    def test_r_scope(self):
        result = r_scope(True)
        self.assertEqual(result, r"(\([\w \/:-]+\))?")

    def test_conventional_types_with_custom_types(self):
        result = conventional_types(["custom1", "custom2"])
        self.assertEqual(set(result), set(["feat", "fix", "custom1", "custom2"]))

    def test_is_conventional(self):
        result1 = is_conventional("fix: bug fix", ["feat", "fix"], True)
        result2 = is_conventional("invalid subject", ["feat"], True)
        result3 = is_conventional("fix(scope): subject", ["fix"], False)
        result4 = is_conventional("Merged in feature1", ["fix"], False)
        result5 = is_conventional("Merge branch 'develop'", ["fix"], False)
        result6 = is_conventional("This reverts commit abc123", ["fix"], False)
        result7 = is_conventional("feat!: important change", ["feat"], True)
        result8 = is_conventional(
            "feat(module)!: important `abcd` change", ["feat"], True
        )

        self.assertTrue(result1)
        self.assertFalse(result2)
        self.assertTrue(result3)
        self.assertFalse(result4)
        self.assertFalse(result5)
        self.assertFalse(result6)
        self.assertTrue(result7)
        self.assertTrue(result8)

    def test_is_special_commit(self):
        self.assertTrue(is_special_commit("Merged in feature1"))
        self.assertTrue(is_special_commit("Merge branch 'develop'"))
        self.assertTrue(is_special_commit("This reverts commit abc123"))
        self.assertFalse(is_special_commit("feat: added new feature"))

    @patch("argparse.ArgumentParser.parse_args")
    @patch("enforce_conventional_commits.get_modified_filepaths")
    def test_main_with_limit_to(self, mock_get_modified_filepaths, mock_parse_args):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=["/path/to/dir"],
            optional_scope=True,
            input="commit_msg.txt",
        )
        mock_get_modified_filepaths.return_value = [Path("/path/to/dir/file.txt")]

        with patch(
            "builtins.open",
            new_callable=mock_open,
            read_data="fix: bug fix",
        ):
            result = main()

        self.assertEqual(result, 0)

    @patch("argparse.ArgumentParser.parse_args")
    @patch("builtins.open", new_callable=mock_open, read_data="fix: bug fix")
    def test_main(self, mock_open, mock_parse_args):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=None,
            optional_scope=True,
            input="commit_msg.txt",
        )
        result = main()
        self.assertEqual(result, 0)

    @patch("argparse.ArgumentParser.parse_args")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="bad commit message",
    )
    def test_main_bad_commit_message(self, mock_open, mock_parse_args):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=None,
            optional_scope=True,
            input="commit_msg.txt",
        )
        result = main()
        self.assertEqual(result, 1)

    def test_is_conventional_breaking_changes(self):
        result = is_conventional(
            "feat: new feature\n\nBREAKING CHANGES: changes that break backward compatibility",
            ["feat", "fix"],
            True,
        )
        self.assertTrue(result)

    @patch("argparse.ArgumentParser.parse_args")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="feat: new feature\n\nBREAKING CHANGES: changes that break backward compatibility",
    )
    def test_main_breaking_changes_conventional(self, mock_open, mock_parse_args):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=None,
            optional_scope=True,
            input="commit_msg.txt",
        )
        result = main()
        self.assertEqual(result, 0)

    @patch("argparse.ArgumentParser.parse_args")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="invalid: not a valid message\n\nBREAKING CHANGES: changes that break backward compatibility",
    )
    def test_main_breaking_changes_nonconventional(self, mock_open, mock_parse_args):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=None,
            optional_scope=True,
            input="commit_msg.txt",
        )
        result = main()
        self.assertEqual(result, 1)

    @patch("argparse.ArgumentParser.parse_args")
    @patch("enforce_conventional_commits.get_modified_filepaths")
    def test_main_limit_to_outside_dir(
        self, mock_get_modified_filepaths, mock_parse_args
    ):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=["/path/to/dir"],
            optional_scope=True,
            input="commit_msg.txt",
        )
        mock_get_modified_filepaths.return_value = [Path("/different/path/file.txt")]

        with patch(
            "builtins.open",
            new_callable=mock_open,
            read_data="feat: added feature",
        ):
            result = main()

        self.assertEqual(result, 0)  # modified files outside of what limited to

    @patch("argparse.ArgumentParser.parse_args")
    @patch("enforce_conventional_commits.get_modified_filepaths")
    def test_main_limit_to_multiple_paths(
        self, mock_get_modified_filepaths, mock_parse_args
    ):
        mock_parse_args.return_value = argparse.Namespace(
            types=["feat", "fix"],
            limit_to=["/path/to/dir", "/different/path"],
            optional_scope=True,
            input="commit_msg.txt",
        )
        mock_get_modified_filepaths.return_value = [
            Path("/path/to/dir/file.txt"),
            Path("/different/path/file.txt"),
        ]

        with patch(
            "builtins.open",
            new_callable=mock_open,
            read_data="feat: added feature",
        ):
            result = main()

        self.assertEqual(result, 0)

    @patch("subprocess.run")
    def test_get_modified_filepaths_non_interactive(self, mock_subprocess_run):
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRT"],
            returncode=0,
            stdout="path3\npath4\n",
            stderr="",
        )
        result = get_modified_filepaths("")
        self.assertEqual(result, [Path("path3"), Path("path4")])

    @patch("subprocess.run")
    def test_get_modified_filepaths_from_git_diff_when_commit_does_not_match_regexp(
        self, mock_subprocess_run
    ):
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRT"],
            returncode=0,
            stdout="git_added_path\ngit_modified_path\n",
            stderr="",
        )
        result = get_modified_filepaths("unmatched_commit_status:   commit_path\n")
        self.assertEqual(
            result,
            [
                Path("git_added_path"),
                Path("git_modified_path"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
