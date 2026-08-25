#!/bin/sh
# scripts/git-hooks/ を git のフックとして有効にする。
#
# フックをリポジトリ内に置いて core.hooksPath で指す形にしているので、
# .git/hooks/ へのコピーは要らない（コピーだと更新が反映されない）。
#
# 引き換えに、**作業ツリーにあるスクリプトが push のたびに実行される**。
# 信頼できないブランチ（fork からの PR 等）を checkout した状態で push
# すると、そのブランチ版のフックが動く。checkout する前に diff を見る。
set -e

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

prev=$(git config --get core.hooksPath || true)
if [ -n "$prev" ] && [ "$prev" != "scripts/git-hooks" ]; then
    echo "警告: core.hooksPath は既に $prev を指しています。上書きします"
    echo "      元に戻すには: git config core.hooksPath $prev"
fi
# linked worktree では .git はファイルなので、パスは git に解決させる。
hooks_dir=$(git rev-parse --git-path hooks)
if [ -z "$prev" ] && [ -d "$hooks_dir" ]; then
    # 実行可能ファイルだけを数える（*.sample は git の雛形）。
    n=$(find "$hooks_dir" -type f -perm -u+x ! -name '*.sample' | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
        echo "警告: $hooks_dir に $n 個のフックがあります。core.hooksPath を"
        echo "      張ると、それらは呼ばれなくなります"
    fi
fi

chmod +x scripts/git-hooks/*
git config core.hooksPath scripts/git-hooks

echo "core.hooksPath = $(git config core.hooksPath)"
echo "有効なフック: $(ls scripts/git-hooks | tr '\n' ' ')"
echo
echo "注意: フックは作業ツリーのスクリプトを実行します。信頼できない"
echo "      ブランチを checkout した状態で push しないでください"
echo "解除するには: git config --unset core.hooksPath"
