#!/usr/bin/env bash
# Godot 4.7.2 の開発環境(ヘッドレステスト / ソフトウェア描画 / Android APK エクスポート)を整える。
# 冪等: 既に入っている物はスキップする。新しいコンテナで1回流せば同じ環境になる。
# 対象: Ubuntu 24.04 (ローカルコンテナ / GitHub Actions ubuntu-latest)。
#
# 使い方:
#   game/tools/setup_env.sh            # 全部
#   SKIP_APT=1 game/tools/setup_env.sh # apt を飛ばす(パッケージ導入済みの CI 等)
#
# 環境変数で上書き可能:
#   GODOT_VERSION   既定 4.7.2
#   ANDROID_HOME    既定 /opt/android-sdk (既に ANDROID_HOME/ANDROID_SDK_ROOT があればそれを使う)
#   JAVA17_HOME     既定 自動検出 (JDK 17)
set -euo pipefail

GODOT_VERSION="${GODOT_VERSION:-4.7.2}"
GODOT_TAG="${GODOT_VERSION}-stable"
BUILD_TOOLS="36.1.0"          # platform/android/java/app/config.gradle の buildTools
PLATFORM="android-36"         # compileSdk 36
CMDLINE_TOOLS_BUILD="13114758"
ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/android-sdk}}"
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
GODOT_DOTTED="${GODOT_VERSION}.stable"   # Godot 本体/テンプレートの表記 (4.7.2.stable)
TEMPLATE_DIR="$XDG_DATA_HOME/godot/export_templates/${GODOT_DOTTED}"
EDITOR_SETTINGS="$XDG_CONFIG_HOME/godot/editor_settings-${GODOT_VERSION%.*}.tres"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

log() { printf '[setup_env] %s\n' "$*"; }
have_pkg() { dpkg -s "$1" >/dev/null 2>&1; }

# ---- 1. apt パッケージ (xvfb, lavapipe, フォント, JDK 17) -------------------
APT_PKGS="xvfb xauth mesa-vulkan-drivers libgl1-mesa-dri libvulkan1 fonts-noto-cjk openjdk-17-jdk-headless unzip zip wget ca-certificates"
if [ "${SKIP_APT:-0}" != "1" ]; then
  missing=""
  for p in $APT_PKGS; do have_pkg "$p" || missing="$missing $p"; done
  if [ -n "$missing" ]; then
    log "apt install:$missing"
    export DEBIAN_FRONTEND=noninteractive
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq $missing
  else
    log "apt: 導入済み"
  fi
fi

# ---- 2. JDK 17 の場所 (Godot の Android 設定に入れる) ----------------------
find_jdk17() {
  if [ -n "${JAVA17_HOME:-}" ] && [ -x "$JAVA17_HOME/bin/javac" ]; then echo "$JAVA17_HOME"; return; fi
  for d in /usr/lib/jvm/java-17-openjdk-amd64 /usr/lib/jvm/temurin-17-jdk-amd64 /usr/lib/jvm/java-17-openjdk; do
    if [ -x "$d/bin/javac" ]; then echo "$d"; return; fi
  done
  if command -v javac >/dev/null 2>&1; then
    local j; j="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
    if javac -version 2>&1 | grep -q '^javac 17'; then echo "$j"; return; fi
  fi
  echo ""
}
JAVA17="$(find_jdk17)"
if [ -z "$JAVA17" ]; then
  log "JDK 17 が見つからない (SKIP_APT=1 の場合は JAVA17_HOME を指定)"; exit 1
fi
log "JDK 17: $JAVA17"

# ---- 3. Godot 本体 (無ければ公式 zip から導入) ------------------------------
if command -v godot >/dev/null 2>&1 && godot --version 2>/dev/null | grep -q "^${GODOT_DOTTED}"; then
  log "godot: $(godot --version 2>/dev/null | head -1)"
else
  GODOT_DIR="/opt/godot"
  BIN_LINK_DIR="/usr/local/bin"
  if [ "$(id -u)" -ne 0 ]; then GODOT_DIR="$HOME/.local/opt/godot"; BIN_LINK_DIR="$HOME/.local/bin"; fi
  mkdir -p "$GODOT_DIR" "$BIN_LINK_DIR"
  BIN="$GODOT_DIR/Godot_v${GODOT_TAG}_linux.x86_64"
  if [ ! -x "$BIN" ]; then
    log "Godot ${GODOT_TAG} をダウンロード"
    tmp="$(mktemp -d)"
    curl -fL --retry 3 -o "$tmp/godot.zip" \
      "https://github.com/godotengine/godot/releases/download/${GODOT_TAG}/Godot_v${GODOT_TAG}_linux.x86_64.zip"
    unzip -q -o "$tmp/godot.zip" -d "$GODOT_DIR"
    chmod +x "$BIN"
    rm -rf "$tmp"
  fi
  ln -sf "$BIN" "$BIN_LINK_DIR/godot"
  log "godot: $("$BIN" --version | head -1) -> $BIN_LINK_DIR/godot"
fi

# ---- 4. エクスポートテンプレート (Android 用だけ展開) -----------------------
if [ -f "$TEMPLATE_DIR/version.txt" ] && [ "$(tr -d '\r\n ' < "$TEMPLATE_DIR/version.txt")" = "$GODOT_DOTTED" ] \
   && [ -f "$TEMPLATE_DIR/android_release.apk" ] && [ -f "$TEMPLATE_DIR/android_source.zip" ]; then
  log "export templates: 導入済み ($TEMPLATE_DIR)"
else
  log "export templates をダウンロード (約1.3GB。Android 分だけ展開)"
  tmp="$(mktemp -d)"
  curl -fL --retry 3 -o "$tmp/templates.tpz" \
    "https://github.com/godotengine/godot/releases/download/${GODOT_TAG}/Godot_v${GODOT_TAG}_export_templates.tpz"
  mkdir -p "$TEMPLATE_DIR"
  unzip -q -o "$tmp/templates.tpz" \
    'templates/android_debug.apk' 'templates/android_release.apk' 'templates/android_source.zip' \
    'templates/icudt_godot.dat' 'templates/version.txt' -d "$tmp/x"
  mv "$tmp/x/templates/"* "$TEMPLATE_DIR/"
  rm -rf "$tmp"
  log "export templates: 展開完了 ($TEMPLATE_DIR)"
fi

# ---- 5. Android SDK (cmdline-tools / platform-tools / build-tools / platform) --
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
if [ ! -x "$SDKMANAGER" ]; then
  log "Android cmdline-tools をダウンロード -> $ANDROID_HOME"
  tmp="$(mktemp -d)"
  curl -fL --retry 3 -o "$tmp/cmdline-tools.zip" \
    "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS_BUILD}_latest.zip"
  $SUDO mkdir -p "$ANDROID_HOME/cmdline-tools"
  $SUDO unzip -q -o "$tmp/cmdline-tools.zip" -d "$tmp/x"
  $SUDO rm -rf "$ANDROID_HOME/cmdline-tools/latest"
  $SUDO mv "$tmp/x/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
  rm -rf "$tmp"
fi
need_sdk=0
[ -d "$ANDROID_HOME/build-tools/$BUILD_TOOLS" ] || need_sdk=1
[ -d "$ANDROID_HOME/platforms/$PLATFORM" ] || need_sdk=1
[ -x "$ANDROID_HOME/platform-tools/adb" ] || need_sdk=1
if [ "$need_sdk" = "1" ]; then
  log "Android SDK パッケージを導入 (licenses 同意 + platform-tools, build-tools;$BUILD_TOOLS, platforms;$PLATFORM)"
  export JAVA_HOME="$JAVA17"
  export PATH="$JAVA17/bin:$PATH"
  $SUDO mkdir -p "$ANDROID_HOME"
  yes | $SUDO "$SDKMANAGER" --sdk_root="$ANDROID_HOME" --licenses >/dev/null 2>&1 || true
  $SUDO "$SDKMANAGER" --sdk_root="$ANDROID_HOME" "platform-tools" "build-tools;$BUILD_TOOLS" "platforms;$PLATFORM" >/dev/null
else
  log "Android SDK: 導入済み ($ANDROID_HOME)"
fi

# ---- 6. Godot エディタ設定 (ヘッドレスエクスポートが読む) -------------------
# 既存ファイルの他の設定は残し、対象キーだけ入れ替える。
mkdir -p "$(dirname "$EDITOR_SETTINGS")"
python3 - "$EDITOR_SETTINGS" "$ANDROID_HOME" "$JAVA17" <<'PY'
import sys, os, re
path, sdk, jdk = sys.argv[1], sys.argv[2], sys.argv[3]
want = {
    "export/android/android_sdk_path": '"%s"' % sdk,
    "export/android/java_sdk_path": '"%s"' % jdk,
}
header = '[gd_resource type="EditorSettings" format=3]\n\n[resource]\n'
if os.path.exists(path):
    lines = open(path, encoding="utf-8").read().splitlines()
else:
    lines = header.splitlines()
if "[resource]" not in lines:
    lines += ["", "[resource]"]
out, seen = [], set()
for ln in lines:
    m = re.match(r'^([^=\s][^=]*?)\s*=', ln)
    if m and m.group(1) in want:
        out.append('%s = %s' % (m.group(1), want[m.group(1)])); seen.add(m.group(1))
    else:
        out.append(ln)
for k, v in want.items():
    if k not in seen:
        out.append('%s = %s' % (k, v))
text = "\n".join(out).rstrip("\n") + "\n"
if not text.startswith("[gd_resource"):
    text = header + text.split("[resource]", 1)[-1].lstrip("\n")
open(path, "w", encoding="utf-8").write(text)
PY
log "editor settings: $EDITOR_SETTINGS"

# ---- 7. 確認 --------------------------------------------------------------
log "確認:"
godot --version | head -1 | sed 's/^/  godot: /'
ls "$TEMPLATE_DIR/android_release.apk" >/dev/null && echo "  templates: OK"
"$ANDROID_HOME/build-tools/$BUILD_TOOLS/apksigner" --version 2>/dev/null | head -1 | sed 's/^/  apksigner: /' || true
echo "  JDK 17: $JAVA17"
log "完了"
