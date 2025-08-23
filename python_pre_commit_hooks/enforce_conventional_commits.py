#!/usr/bin/env python

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional

RESULT_SUCCESS = 0
RESULT_FAIL = 1

CONVENTIONAL_TYPES = ["feat", "fix"]
DEFAULT_TYPES = [
    # Changes to our CI configuration files and scripts (example scopes:
    # github actions, atlantis)
    "ci",
    # Documentation only changes (readmes, inline docs, diagrams, etc.)
    "docs",
    # A new feature (introduced a new terraform module, a new stack, a new
    # kubernetes application, a new docker image, a new design doc, etc.)
    "feat",
    # A bug fix
    "fix",
    # A code change that neither fixes a bug nor adds a feature (refactor)
    "ref",
    "refactor",
    # Changes that do not affect the meaning of the code (white-space,
    # formatting, missing semi-colons, etc)
    "style",
    # Adding missing tests or correcting existing tests
    "test",
    # Some meta information in the repo changes (example scopes: owner files,
    # editor config etc.)
    "meta",
    # Code changes that do not fall under any other type (scaling up the ASG
    # size)
    "chore",
]


class Colors:
    LBLUE: str = "\033[00;34m"
    LRED: str = "\033[01;31m"
    RESTORE: str = "\033[0m"
    YELLOW: str = "\033[00;33m"


def r_types(types: List[str]) -> str:
    """Join types with pipe "|" to form regex ORs."""
    return "|".join(types)


def r_scope(optional: bool = True) -> str:
    """Regex str for an optional (scope)."""
    return r"(\([\w \/:-]+\))" + ("?" if optional else "")


def r_delim() -> str:
    """Regex str for optional breaking change indicator and colon delimiter."""
    return r"!?:"


def r_subject() -> str:
    """Regex str for subject line, body, footer."""
    return r" .+"


def conventional_types(types: List[str] = []) -> List[str]:
    """
    Return a list of conventional commits types merged with the given types.
    """
    if set(types) & set(CONVENTIONAL_TYPES) == set():
        return CONVENTIONAL_TYPES + types
    return types


def is_special_commit(input: str) -> bool:
    """
    Checks whether the input message is a merge or revert commit
    """
    merge_strings = ["Merged in ", "Merge branch "]
    revert_string = "This reverts commit "

    if any(merge_str in input for merge_str in merge_strings):
        return True
    if revert_string in input:
        return True

    return False


def is_conventional(
    input: str, types: List[str] = DEFAULT_TYPES, optional_scope: bool = True
) -> bool:
    """
    Returns True if input matches conventional commits formatting
    https://www.conventionalcommits.org

    Optionally provide a list of additional custom types.
    """

    if is_special_commit(input):  # if it's a special commit, exit early
        return False

    types = conventional_types(types)
    pattern = f"^({r_types(types)}){r_scope(optional_scope)}{r_delim()}{r_subject()}$"
    regex = re.compile(pattern, re.DOTALL)

    return bool(regex.match(input))


def get_modified_filepaths(input: str) -> List[Path]:
    """
    Get all modified filepaths in the commit from the commit message file.
    Distinguishes between "modified", "new", and other file changes.
    """
    status_tokens = {
        "modified": re.compile(r"(?<=modified:   )\S+"),
        "added": re.compile(r"(?<=new file:   )\S+"),
        "removed": re.compile(r"(?<=deleted:    )\S+"),
        "renamed": re.compile(r"(?<=renamed:    )\S+"),
    }

    modified_files = []

    for regex in status_tokens.values():
        matches = regex.findall(input)
        if matches:
            modified_files.extend(Path(match) for match in matches)

    # If no file paths were found in the commit message, fetch them directly
    # from Git -- at this point the user might be running `git commit -m
    # <commit msg>` non-interactively.

    if not modified_files:
        import subprocess

        try:
            # https://git-scm.com/docs/git-diff#Documentation/git-diff.txt---diff-filterACDMRTUXB82308203

            # - `A`: Added
            # - `C`: Copied
            # - `D`: Deleted
            # - `M`: Modified
            # - `R`: Renamed
            # - `T`: Type changed (e.g., regular file, symlink, submodule)
            # - `U`: Unmerged
            # - `X`: Unknown
            # - `B`: Pairing Broken

            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRT"],
                capture_output=True,
                text=True,
                check=True,
            )
            modified_files.extend(Path(file) for file in result.stdout.splitlines())
        except subprocess.CalledProcessError as e:
            print(f"Failed to get modified files. Error: {e}")

    return modified_files


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main function that implements the pre-commit hook.
    """
    parser = argparse.ArgumentParser(
        prog="conventional-pre-commit",
        description="Check a git commit message for conventional commits formatting.",
    )
    parser.add_argument(
        "--types",
        type=str,
        nargs="*",
        default=DEFAULT_TYPES,
        help="Optional list of types to support",
    )
    parser.add_argument(
        "--limit-to",
        type=str,
        nargs="*",
        default=None,
        help="Directories to limit the commit check",
    )
    parser.add_argument(
        "--force-scope",
        action="store_false",
        default=True,
        dest="optional_scope",
        help="Force commit to have scope defined.",
    )

    parser.add_argument(
        "input", type=str, help="A file containing a git commit message"
    )

    # Defaults to the command-line arguments if not explicitly provided
    argv = argv or sys.argv[1:]

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return RESULT_FAIL

    try:
        with open(args.input, encoding="utf-8") as f:
            message = f.read()
    except UnicodeDecodeError:
        print(
            f"""
        {Colors.LRED}[Bad commit message encoding] {Colors.RESTORE}

        {Colors.YELLOW}conventional-pre-commit couldn't decode your commit message.{Colors.RESTORE}
        {Colors.YELLOW}UTF-8{Colors.RESTORE} encoding is assumed, please configure git to write commit messages in UTF-8.
        See {Colors.LBLUE}https://git-scm.com/docs/git-commit/#_discussion{Colors.RESTORE} for more.
        """
        )
        return RESULT_FAIL

    if args.limit_to:
        modified_directories_for_commit_check = []
        modified_filepaths = get_modified_filepaths(message)
        limited_paths = args.limit_to[0].split(",")

        for modified_filepath in modified_filepaths:
            for single_limited_path in limited_paths:
                limited_path = Path(single_limited_path)
                if (
                    limited_path in modified_filepath.parents
                    or modified_filepath == limited_path
                ):
                    modified_directories_for_commit_check.append(modified_filepath)
                    break  # no need to check other paths if already matched

        # If there are no directories to check, return success
        if not modified_directories_for_commit_check:
            return RESULT_SUCCESS

    if is_conventional(message, args.types, args.optional_scope):
        return RESULT_SUCCESS
    else:
        print(
            f"""
        {Colors.LRED}[Bad commit message] >>{Colors.RESTORE} {message}
        {Colors.YELLOW}Your commit message does not follow conventional commits formatting
        {Colors.LBLUE}https://www.conventionalcommits.org{Colors.YELLOW}

        Conventional commits start with one of the below types, followed by a colon,
        followed by the commit message:{Colors.RESTORE}

            {", ".join(conventional_types(args.types))}

        {Colors.YELLOW}Example commit message adding a feature:{Colors.RESTORE}

            feat: enable `/metrics` endpoint for prometheus

        {Colors.YELLOW}Example commit message fixing an issue:{Colors.RESTORE}

            fix: remove infinite loop

        {Colors.YELLOW}Example commit with scope in parentheses after the type for more context:{Colors.RESTORE}

            fix(atlantis): forbid running `atlantis apply` w/o pr approval"""
        )
        return RESULT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
