#!/usr/bin/env bash
# 全テストを順に流し、PASS / FAIL を集計する。
#
# 使い方:
#   game/tools/run_all_tests.sh
#
# 環境変数:
#   GODOT_BIN  godot 実行ファイル (既定 godot)
#
# 終了コード: 0 = 全 PASS かつ SCRIPT ERROR なし / 1 = FAIL あり、SCRIPT ERROR あり、
#             またはテストが結果行を出さずに終わった。
# 初回・ファイルを増減した後は先に --import する (このスクリプトが行う)。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # game/
GODOT="${GODOT_BIN:-godot}"
command -v "$GODOT" >/dev/null 2>&1 || { echo "::error::godot が見つかりません ($GODOT)" >&2; exit 1; }

# 名前 | 起動方法 (--script は SceneTree、--scene は Node のテストシーン)
TESTS=(
  "run_tests|--script res://tests/run_tests.gd"
  "test_terrain|--script res://tests/test_terrain.gd"
  "test_env|--script res://tests/test_env.gd"
  "test_objects|--script res://tests/test_objects.gd"
  "test_edit|--script res://tests/test_edit.gd"
  "test_walk|--script res://tests/test_walk.gd"
  "test_ui|--scene res://tests/test_ui.tscn"
)

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[run_all_tests] godot --import"
if ! "$GODOT" --headless --path "$ROOT" --import >"$WORK/import.log" 2>&1; then
  tail -40 "$WORK/import.log"
  echo "::error::godot --import が失敗しました"
  exit 1
fi

total_pass=0
total_fail=0
bad=0
printf '%-14s %6s %6s %8s  %s\n' "test" "PASS" "FAIL" "errors" "note"
for entry in "${TESTS[@]}"; do
  name="${entry%%|*}"
  args="${entry#*|}"
  log="$WORK/$name.log"
  # shellcheck disable=SC2086  # args は意図的に単語分割する
  "$GODOT" --headless --path "$ROOT" $args >"$log" 2>&1
  rc=$?

  summary="$(sed -n 's/^---- PASS \([0-9]*\) \/ FAIL \([0-9]*\).*/\1 \2/p' "$log" | tail -1)"
  script_err="$(grep -c 'SCRIPT ERROR\|Parse Error' "$log" || true)"
  note=""
  if [ -z "$summary" ]; then
    p=0; f=0
    note="結果行が無い (exit $rc)"
  else
    read -r p f <<<"$summary"
    if [ "$rc" -ne 0 ] && [ "$f" -eq 0 ]; then
      note="exit $rc だが FAIL 0"
    fi
  fi
  if [ "$f" -gt 0 ]; then note="${note:+$note; }FAIL $f"; fi
  if [ "$script_err" -gt 0 ]; then note="${note:+$note; }SCRIPT ERROR $script_err 件"; fi

  total_pass=$((total_pass + p))
  total_fail=$((total_fail + f))
  this_bad=0
  if [ -z "$summary" ] || [ "$f" -gt 0 ] || [ "$script_err" -gt 0 ] || { [ "$rc" -ne 0 ] && [ "$f" -eq 0 ]; }; then
    this_bad=1
    bad=1
  fi
  printf '%-14s %6s %6s %8s  %s\n' "$name" "$p" "$f" "$script_err" "$note"

  if [ "$this_bad" -eq 1 ]; then
    grep -E '^\s*FAIL|SCRIPT ERROR|Parse Error' "$log" | head -20 | sed 's/^/    /'
    tail -5 "$log" | sed 's/^/    | /'
  fi
done

echo "----"
echo "TOTAL PASS $total_pass / FAIL $total_fail"
if [ "$bad" -ne 0 ] || [ "$total_fail" -gt 0 ]; then
  echo "::error::テストに失敗があります (FAIL $total_fail / 上の表を参照)"
  exit 1
fi
echo "全テスト通過"
