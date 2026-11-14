#!/usr/bin/env bash
# ソフトウェア描画 (Mesa lavapipe / llvmpipe) で Godot をウィンドウ付き起動するラッパ。
# GPU が無い CI やコンテナでスクリーンショット取得に使う。
#
# 使い方:
#   game/tools/xvfb_godot.sh <幅> <高さ> -- <godotの引数...>
#   例: game/tools/xvfb_godot.sh 720 1560 -- --path game -- --shot=/tmp/a.png
#   例: XVFB_RENDERER=opengl3 game/tools/xvfb_godot.sh 1560 720 -- --path game --scene res://x.tscn
#
# 環境変数:
#   XVFB_RENDERER  vulkan (既定, Mobile レンダラ, lavapipe) | opengl3 (Compatibility, llvmpipe, 約4倍速)
#   GODOT_BIN      godot 実行ファイル (既定 godot)
#
# 注意: --headless を付けると描画が走らず frame_post_draw が来ないので付けないこと。
# 動作確認済み: game/tools/setup_env.sh で入る Godot 4.7.2 + Mesa 25.2 (Ubuntu 24.04)。
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$3" != "--" ]; then
  echo "usage: $0 <width> <height> -- <godot args...>" >&2
  exit 2
fi
W="$1"; H="$2"; shift 3
case "$W$H" in (*[!0-9]*|'') echo "width/height must be integers" >&2; exit 2;; esac

RENDERER="${XVFB_RENDERER:-vulkan}"
GODOT_BIN="${GODOT_BIN:-godot}"
case "$RENDERER" in
  vulkan|opengl3) ;;
  *) echo "XVFB_RENDERER must be vulkan or opengl3" >&2; exit 2;;
esac
command -v xvfb-run >/dev/null || { echo "xvfb-run が無い (apt install xvfb xauth)" >&2; exit 1; }

# 仮想画面はウィンドウより大きくする (縦横どちらの向きでも収まるよう長辺に合わせる)
SCREEN=$(( W > H ? W : H ))
exec xvfb-run -a -s "-screen 0 ${SCREEN}x${SCREEN}x24" \
  "$GODOT_BIN" --windowed --resolution "${W}x${H}" \
  --audio-driver Dummy --rendering-driver "$RENDERER" "$@"
