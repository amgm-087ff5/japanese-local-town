# ビルド・配布 (APK / CI)

鎮守の里 (`io.github.amgm087ff5.japaneselocaltown`, versionName `0.1.0`) の APK をローカルと CI で作る手順。
環境の導入は `docs/dev_env.md` (`tools/setup_env.sh`)。

## 固定の値

| 項目 | 値 |
| --- | --- |
| applicationId | `io.github.amgm087ff5.japaneselocaltown` |
| アプリ名 | 鎮守の里 |
| versionName | `0.1.0` (人が読む版数。手で上げる) |
| versionCode | エポック分 `$(date +%s) / 60` (ビルドのたびに自動) |
| 署名鍵 | PKCS12。alias `jlt` (定数。秘密ではない) |
| ABI | arm64-v8a, armeabi-v7a |
| minSdk | 24 |
| 権限 | なし (INTERNET も false) |
| 向き | 自動回転 (`display/window/handheld/orientation=6`) |

`export_presets.cfg` の `version/code` はコミット上 `1` のまま。ビルドスクリプトが一時的に
エポック分へ置換し、終了時 (成功・失敗とも) に元の内容へ戻す。

## 署名鍵 (絶対条件)

- APK は**必ず同じ鍵で署名する**。鍵が変わると既存のインストールに上書きできなくなる (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`)。
- 鍵が無いときは失敗する。デバッグ鍵には落ちない。
- 期待する証明書 SHA-256:
  `68:64:C3:4E:CC:B7:1E:8B:36:9B:5B:AD:17:50:90:85:F0:D3:EC:B3:C5:A8:45:E3:DB:5F:A9:8D:35:52:09:35`
  (CI の `EXPECTED_CERT_SHA256` と `tools/build_apk.sh` に使う。一致しない APK は作られない)
- 鍵ファイル (`*.keystore`) と パスワードは**リポジトリに入れない** (`.gitignore` で除外済み)。

### 鍵の準備 (ローカル)

環境変数で渡す。値はシェルの履歴やログに残さないこと。

```bash
export GODOT_ANDROID_KEYSTORE_RELEASE_PATH=/安全な場所/jlt.keystore
export GODOT_ANDROID_KEYSTORE_RELEASE_USER=jlt          # 省略可 (既定 jlt)
export GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD="$(cat /安全な場所/GAME_KEYSTORE_PASSWORD)"
```

## ローカルでの APK ビルド

```bash
game/tools/setup_env.sh                       # 初回のみ (Godot 4.7.2 / テンプレート / Android SDK)
game/tools/run_all_tests.sh                   # テスト (任意。先に流すと安心)
EXPECTED_CERT_SHA256=68:64:C3:4E:CC:B7:1E:8B:36:9B:5B:AD:17:50:90:85:F0:D3:EC:B3:C5:A8:45:E3:DB:5F:A9:8D:35:52:09:35 \
  game/tools/build_apk.sh /tmp/chinju-no-sato.apk
```

スクリプトは次を行い、結果を表示する。

1. `godot --headless --import` → `--export-release "Android"` (`versionCode` は一時的に書き換え)
2. `apksigner verify --print-certs` で署名 SHA-256 を表示 (`EXPECTED_CERT_SHA256` と不一致なら exit 1)
3. `aapt2 dump badging` で package / versionCode / versionName / minSdk / native-code / 権限 を確認
4. APK のサイズを表示

失敗時は APK を残さず非0で終わる。

## CI (GitHub Actions) の Secrets

ワークフロー `.github/workflows/game.yml`。Secret は次の **2つだけ**。

| Secret 名 | 中身 |
| --- | --- |
| `GAME_KEYSTORE_B64` | 鍵ファイルを base64 にしたもの (改行なし) |
| `GAME_KEYSTORE_PASSWORD` | 鍵のパスワード (末尾改行なし) |

登録手順:

1. GitHub のリポジトリを開く → **Settings** → **Secrets and variables** → **Actions**。
2. **New repository secret** で `GAME_KEYSTORE_B64` を作る。値は次の出力を貼る (手元の鍵ファイルから作る)。
   ```bash
   base64 -w0 /安全な場所/jlt.keystore
   ```
3. 同じ画面で `GAME_KEYSTORE_PASSWORD` を作る。値はパスワードそのもの。

Secret が空なら android ジョブが `::error::` で止まる。鍵が開けない・alias `jlt` が無いときも止まる。

ジョブの流れ:

- `test`: Godot 本体を取得 → `tools/run_all_tests.sh`。
- `android` (test の後): JDK 17 → `setup_env.sh` (テンプレートと SDK は actions/cache) → 鍵の復元と確認 → `tools/build_apk.sh` → artifact `chinju-no-sato-apk`。
- `release` (main への push のときだけ): 固定タグ `game-latest` のプレリリースを作り直す。本文に versionCode・署名 SHA-256・コミットを載せる。

## versionCode の決め方

- エポック分 (`date +%s / 60`) なので、CI でもローカルでも単調増加する。2026-11 時点で約 3000 万。Android の上限 (約 21 億) まで十分ある。
- 手でオフセットを足す必要はない。
- 既にインストールされている版の最大 versionCode より小さくなることは無い。ただし、**過去にエポック分より大きい値で配布したことがある場合**は、その値を超えるまで手で調整する (現時点で配布実績は無い)。

## インストール方法 (端末)

1. `game-latest` の Release (または artifact) から APK を端末に入れる。
2. 初回だけ、ブラウザやファイル管理アプリに「**提供元不明のアプリのインストール**」を許可する
   (設定 → アプリ → 対象のアプリ → 「不明なアプリのインストール」)。
3. APK を開いて上書きインストールする。署名が同じなら、既存のセーブデータは残る。

**注意:** このリポジトリは公開。Release の APK は誰でもダウンロードできる。APK に秘密情報 (鍵・API キー) を入れないこと。署名鍵とパスワードは APK に入らない。

## 鍵のバックアップ

- 鍵とパスワードは、リポジトリの外の**2か所以上**に保管する (紛失すると、以後の上書きアップデートができなくなる)。
- 鍵を公開してしまった場合は、その鍵を破棄して作り直す (ローテーション)。履歴に残っていても使わない。鍵を変えたら `EXPECTED_CERT_SHA256` も変える。
- 鍵を変えると既存インストールには上書きできない。利用者に一度アンインストールしてもらう必要がある。

## アイコン

`assets/icons/` の PNG (192px / 432px / 背景) は `icon.svg` から作った。作り直すとき:

```bash
rsvg-convert -w 192 -h 192 icon.svg -o assets/icons/icon_192.png
rsvg-convert -w 432 -h 432 icon.svg -o assets/icons/icon_432.png
convert -size 432x432 xc:'#F4EEDF' PNG24:assets/icons/bg_432.png
```

## フォント

`tools/make_font.sh` で `assets/fonts/NotoSansJP-Regular.otf` (Noto Sans CJK JP のサブセット、SIL OFL 1.1) を作り直す。
文字を足したら流し直す。字形が無い文字は最後に表示される。試し出しは `OUT=/tmp/x.otf tools/make_font.sh`。

## 確認済みの出力 (2026-11-14)

- package `io.github.amgm087ff5.japaneselocaltown`、versionName `0.1.0`、minSdk 24、native-code `arm64-v8a` と `armeabi-v7a`、権限なし。
- APK 約 54MB (大部分は Godot 本体の .so 2つ)。`tests/` `tools/` `docs/` は含まない。
- 署名 SHA-256 は上の期待値と一致。
