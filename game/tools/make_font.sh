#!/usr/bin/env bash
# 日本語フォントのサブセット (game/assets/fonts/NotoSansJP-Regular.otf) を作り直す。
#
# 元: Noto Sans CJK JP の Regular (apt: fonts-noto-cjk の NotoSansCJK-Regular.ttc、フォント番号 0 = JP)
# 収録: ASCII・ラテン補助・句読点/記号・ひらがな・カタカナ・全角英数記号・JIS X 0208 第1水準漢字、
#       それに game/scripts/**/*.gd と game/data/*.json に出てくる非ASCII文字すべて。
# 字形は変えない(サブセット化のみ)。ライセンスは SIL OFL 1.1 (game/assets/fonts/OFL.txt)。
#
# 使い方:
#   game/tools/make_font.sh                          # 既定の出力先へ上書き
#   OUT=/tmp/NotoSansJP-Regular.otf game/tools/make_font.sh   # 試し出し (リポジトリを変えない)
#   SRC=/path/to/NotoSansCJK-Regular.ttc game/tools/make_font.sh
#
# 文字を足したら(UI文字列・データを変えたら)このスクリプトを流し直す。
# 最後に、収録文字のうちフォントに字形が無いものを表示する (字形が無い文字は豆腐になる)。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # game/
SRC="${SRC:-/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc}"
OUT="${OUT:-$ROOT/assets/fonts/NotoSansJP-Regular.otf}"
FONT_NUMBER="${FONT_NUMBER:-0}"            # TTC 内の JP フェイス

err() { echo "::error::$*" >&2; }
command -v pyftsubset >/dev/null 2>&1 || { err "pyftsubset が無い (apt install python3-fonttools / pip install fonttools)"; exit 1; }
[ -f "$SRC" ] || { err "元フォントが無い: $SRC (apt install fonts-noto-cjk)"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$(dirname "$OUT")"

# ---- 1. 収録文字の一覧を作る -------------------------------------------------
python3 -I - "$ROOT" "$WORK/chars.txt" <<'PY'
import glob, os, sys
root, out = sys.argv[1], sys.argv[2]
chars = set()
chars.update(chr(c) for c in range(0x20, 0x7F))          # ASCII
chars.update(chr(c) for c in range(0xA0, 0x100))         # ラテン補助 1
chars.update(chr(c) for c in range(0x3000, 0x3040))      # CJK 記号・句読点
chars.update(chr(c) for c in range(0x3040, 0x3100))      # ひらがな・カタカナ
chars.update(chr(c) for c in range(0xFF00, 0xFFF0))      # 全角英数・記号
chars.update("·…―‐–—‘’“”•※℃×÷±°〒￥★☆●○△▲□■◆◇→←↑↓↶↷⟲⟳☰✓✕↺↻⊕▶▼◀⚠")
# JIS X 0208 第1水準漢字 (EUC-JP 0xB0A1-0xCFFE)
for row in range(0xB0, 0xD0):
    for col in range(0xA1, 0xFF):
        try:
            ch = bytes([row, col]).decode("euc_jp")
        except UnicodeDecodeError:
            continue
        if len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
            chars.add(ch)
# ゲーム本体のソースとデータに出てくる非ASCII文字
used = 0
paths = glob.glob(os.path.join(root, "scripts", "**", "*.gd"), recursive=True)
paths += glob.glob(os.path.join(root, "data", "*.json"))
for p in paths:
    with open(p, encoding="utf-8") as f:
        for c in f.read():
            if ord(c) > 127:
                chars.add(c)
                used += 1
for c in ["\n", "\r", "\t"]:
    chars.discard(c)
with open(out, "w", encoding="utf-8") as f:
    f.write("".join(sorted(chars, key=ord)))
kanji = sum(1 for c in chars if 0x4E00 <= ord(c) <= 0x9FFF)
print(f"[make_font] 収録文字 {len(chars)} 種 (うち漢字 {kanji})、ソース/データの非ASCII出現 {used} 箇所", file=sys.stderr)
PY

# ---- 2. サブセット化 --------------------------------------------------------
pyftsubset "$SRC" --font-number="$FONT_NUMBER" --text-file="$WORK/chars.txt" \
  --layout-features='palt,kern,vert,vrt2,ccmp,locl,mark,mkmk' \
  --no-hinting --desubroutinize --output-file="$OUT" \
  --name-IDs='*' --name-legacy --name-languages='*'
echo "[make_font] 出力: $OUT ($(stat -c %s "$OUT") bytes)"

# ---- 3. 字形の確認 (収録したのに字形が無い文字を表示) -------------------------
python3 -I - "$OUT" "$WORK/chars.txt" <<'PY'
import sys
from fontTools.ttLib import TTFont
font = TTFont(sys.argv[1], fontNumber=0, lazy=True)
cmap = font.getBestCmap() or {}
with open(sys.argv[2], encoding="utf-8") as f:
    want = [c for c in f.read() if ord(c) not in (0x20,)]
missing = [c for c in want if ord(c) not in cmap]
print(f"[make_font] 字形あり {len(want) - len(missing)} / {len(want)}")
if missing:
    print("[make_font] 字形が無い文字 (元フォントに無い。豆腐になる): " + "".join(missing[:200]))
PY
