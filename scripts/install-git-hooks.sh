#!/bin/sh
# scripts/git-hooks/ を git のフックとして有効にする。
#
# フックをリポジトリ内に置いて core.hooksPath で指す形にしているので、
# .git/hooks/ へのコピーは要らない（コピーだと更新が反映されない）。
set -e

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

chmod +x scripts/git-hooks/*
git config core.hooksPath scripts/git-hooks

echo "core.hooksPath = $(git config core.hooksPath)"
echo "有効なフック: $(ls scripts/git-hooks | tr '\n' ' ')"
echo
echo "解除するには: git config --unset core.hooksPath"
