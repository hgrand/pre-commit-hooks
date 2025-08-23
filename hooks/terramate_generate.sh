#!/usr/bin/env bash

set -euo pipefail

if ! command -v terramate > /dev/null 2>&1; then
  echo >&2 "terramate is not available on this system."
  echo >&2 "Please install it: 'https://terramate.io/docs/cli/installation'"
  exit 1
fi

terramate generate
