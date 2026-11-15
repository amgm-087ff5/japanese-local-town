#!/usr/bin/env bash
# 鎮守の里の Android APK を書き出し、固定鍵で署名し、結果を検証する。
#
# 使い方:
#   game/tools/build_apk.sh <出力apk>
#
# 必須の環境変数 (署名鍵。値はログに出さない):
#   GODOT_ANDROID_KEYSTORE_RELEASE_PATH      PKCS12 の keystore ファイル
#   GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD  ストア兼キーのパスワード (PKCS12 はキーPW=ストアPW)
# 任意の環境変数:
#   GODOT_ANDROID_KEYSTORE_RELEASE_USER  キーのエイリアス (既定 jlt)
#   EXPECTED_CERT_SHA256                 署名証明書の SHA-256。不一致なら exit 1
#   GODOT_BIN                            godot 実行ファイル (既定 godot)
#   ANDROID_HOME                         Android SDK (既定 /opt/android-sdk)
#   GITHUB_OUTPUT                        CI のとき version_code / cert_sha256 / apk_bytes を書く
#
# versionCode はエポック分 ($(date +%s)/60)。export_presets.cfg の version/code は
# ビルド中だけ書き換え、終了時(成功・失敗とも)に元の内容へ戻す。
# デバッグ鍵には落ちない: 鍵の環境変数が無ければ何もせず exit 1。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # game/
PRESETS="$ROOT/export_presets.cfg"
APP_ID="io.github.amgm087ff5.japaneselocaltown"
VERSION_NAME="0.1.0"
MIN_SDK="24"
PRESET_NAME="Android"
GODOT_BIN="${GODOT_BIN:-godot}"
ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/android-sdk}}"
: "${GODOT_ANDROID_KEYSTORE_RELEASE_USER:=jlt}"
export GODOT_ANDROID_KEYSTORE_RELEASE_USER

err() { echo "::error::$*" >&2; }
note() { echo "[build_apk] $*"; }

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <out.apk>" >&2
  exit 2
fi

# ---- 1. 署名鍵の確認 (無ければ失敗。デバッグ鍵に落ちない) ------------------
if [ -z "${GODOT_ANDROID_KEYSTORE_RELEASE_PATH:-}" ] || [ -z "${GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD:-}" ]; then
  err "署名鍵が未設定です。GODOT_ANDROID_KEYSTORE_RELEASE_PATH と GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD を設定してください (デバッグ鍵では作りません)"
  exit 1
fi
if [ ! -f "$GODOT_ANDROID_KEYSTORE_RELEASE_PATH" ]; then
  err "署名鍵ファイルが見つかりません (GODOT_ANDROID_KEYSTORE_RELEASE_PATH)"
  exit 1
fi

# ---- 2. ツールの場所 ---------------------------------------------------------
# 最新の build-tools を使う (無ければ PATH 上の apksigner / aapt2)
BT_DIR="$(ls -d "$ANDROID_HOME"/build-tools/*/ 2>/dev/null | sort -V | tail -1 || true)"
APKSIGNER=apksigner
AAPT2=aapt2
if [ -n "$BT_DIR" ]; then
  APKSIGNER="$BT_DIR/apksigner"
  AAPT2="$BT_DIR/aapt2"
fi
for t in "$APKSIGNER" "$AAPT2"; do
  if ! command -v "$t" >/dev/null 2>&1; then
    err "build-tools が見つかりません ($ANDROID_HOME/build-tools)。game/tools/setup_env.sh を実行してください"
    exit 1
  fi
done
command -v "$GODOT_BIN" >/dev/null 2>&1 || { err "godot が見つかりません ($GODOT_BIN)"; exit 1; }

# ---- 3. 出力先・一時ファイル・versionCode の一時置換 -------------------------
mkdir -p "$(dirname "$1")"
OUT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
rm -f "$OUT" "$OUT.idsig"
WORK="$(mktemp -d)"
BACKUP="$WORK/export_presets.cfg.orig"
cp "$PRESETS" "$BACKUP"
cleanup() {
  cp "$BACKUP" "$PRESETS"   # 元の内容に戻す (version/code は 1 のまま)
  rm -rf "$WORK"
}
trap cleanup EXIT

VERSION_CODE=$(( $(date +%s) / 60 ))
sed -i -E "s|^version/code=[0-9]+\$|version/code=${VERSION_CODE}|" "$PRESETS"
grep -qx "version/code=${VERSION_CODE}" "$PRESETS" || { err "versionCode の書き換えに失敗"; exit 1; }
note "versionCode=${VERSION_CODE} versionName=${VERSION_NAME}"

# ---- 4. import -> export (release) ------------------------------------------
note "godot --import"
if ! "$GODOT_BIN" --headless --path "$ROOT" --import >"$WORK/import.log" 2>&1; then
  tail -40 "$WORK/import.log" >&2
  err "godot --import が失敗しました"
  exit 1
fi

note "godot --export-release \"$PRESET_NAME\""
rc=0
"$GODOT_BIN" --headless --path "$ROOT" --export-release "$PRESET_NAME" "$OUT" >"$WORK/export.log" 2>&1 || rc=$?
if [ "$rc" -ne 0 ] || [ ! -s "$OUT" ]; then
  grep -E "ERROR|error" "$WORK/export.log" | tail -20 >&2 || true
  err "APK の書き出しに失敗しました (exit $rc)"
  rm -f "$OUT" "$OUT.idsig"
  exit 1
fi

# ---- 5. 署名の検証 -----------------------------------------------------------
fail() { err "$*"; rm -f "$OUT" "$OUT.idsig"; exit 1; }

note "apksigner verify"
"$APKSIGNER" verify --print-certs "$OUT" >"$WORK/sig.txt" 2>&1 || { cat "$WORK/sig.txt" >&2; fail "apksigner verify に失敗しました"; }
rm -f "$OUT.idsig"   # apksigner verify が書く v4 署名ファイル。成果物ではない
CERT_SHA="$(sed -n 's/^Signer #1 certificate SHA-256 digest: //p' "$WORK/sig.txt" | head -1 | tr -d ':' | tr 'A-F' 'a-f')"
[ -n "$CERT_SHA" ] || fail "署名証明書の SHA-256 を読めませんでした"
grep -E '^Signer #1 certificate (DN|SHA-256)|^Verified using' "$WORK/sig.txt" | sed 's/^/  /'

if [ -n "${EXPECTED_CERT_SHA256:-}" ]; then
  EXP="$(printf '%s' "$EXPECTED_CERT_SHA256" | tr -d ':' | tr 'A-F' 'a-f')"
  if [ "$CERT_SHA" != "$EXP" ]; then
    fail "署名証明書が期待値と一致しません (実際 ${CERT_SHA} / 期待 ${EXP})。別の鍵で署名された可能性があります"
  fi
  note "署名証明書: 期待値と一致"
fi

# ---- 6. manifest の確認 (aapt2) ----------------------------------------------
"$AAPT2" dump badging "$OUT" >"$WORK/badging.txt" 2>"$WORK/badging.err" || { cat "$WORK/badging.err" >&2; fail "aapt2 dump badging に失敗しました"; }
PKG_LINE="$(grep -m1 '^package:' "$WORK/badging.txt" || true)"
PKG="$(printf '%s' "$PKG_LINE" | sed -n "s/^package: name='\([^']*\)'.*/\1/p")"
VC="$(printf '%s' "$PKG_LINE" | sed -n "s/^package: .* versionCode='\([^']*\)'.*/\1/p")"
VN="$(printf '%s' "$PKG_LINE" | sed -n "s/^package: .* versionName='\([^']*\)'.*/\1/p")"
SDK="$(sed -n "s/^minSdkVersion:'\([^']*\)'.*/\1/p" "$WORK/badging.txt" | head -1)"
NATIVE="$(grep -m1 '^native-code:' "$WORK/badging.txt" || true)"
PERMS="$(grep '^uses-permission' "$WORK/badging.txt" || true)"

[ "$PKG" = "$APP_ID" ] || fail "package が想定と違います: $PKG"
[ "$VC" = "$VERSION_CODE" ] || fail "versionCode が想定と違います: $VC (期待 $VERSION_CODE)"
[ "$VN" = "$VERSION_NAME" ] || fail "versionName が想定と違います: $VN"
[ "$SDK" = "$MIN_SDK" ] || fail "minSdk が想定と違います: $SDK"
printf '%s' "$NATIVE" | grep -q "'arm64-v8a'" || fail "arm64-v8a が含まれていません"
printf '%s' "$NATIVE" | grep -q "'armeabi-v7a'" || fail "armeabi-v7a が含まれていません"
[ -z "$PERMS" ] || fail "権限が要求されています (想定は無し):
$PERMS"

APK_BYTES="$(stat -c %s "$OUT")"
APK_HUMAN="$(du -h "$OUT" | cut -f1)"

# ---- 7. 結果 -----------------------------------------------------------------
cat <<EOF
[build_apk] 結果
  apk          : $OUT
  size         : ${APK_HUMAN} (${APK_BYTES} bytes)
  package      : $PKG
  versionCode  : $VC
  versionName  : $VN
  minSdk       : $SDK (targetSdk は Godot 既定)
  native-code  : $(printf '%s' "$NATIVE" | sed "s/^native-code: //")
  permissions  : なし
  cert SHA-256 : $CERT_SHA
EOF

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "version_code=$VC"
    echo "cert_sha256=$CERT_SHA"
    echo "apk_bytes=$APK_BYTES"
  } >> "$GITHUB_OUTPUT"
fi
