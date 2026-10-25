# viewer

ブラウザで GLB を確認するための静的ページ。ビルド不要(three.js r170 を jsDelivr から読込)。

## 構成

| ファイル | 公開先 (GitHub Pages) | 役割 |
|---|---|---|
| `quick.html` | `/` (`index.html`) | 爆速確認用。最新モデルを自動読込・自動回転。モデル切替タブ / 視点リセット / 回転 / ワイヤー / アプリ版リンク |
| `index.html` | `/app/index.html` | アプリ版。ファイル選択・D&D、サンプルモデルメニュー、DRACO/KTX2/Meshopt、視点プリセット、影・露出・背景、部材ツリー、スクショ |
| `test/` | (公開しない) | テスト GLB、スモークテスト、スクショ |

Pages の想定レイアウト(複数モデル=バリアント):

```
_site/
  index.html                  ← viewer/quick.html
  app/index.html              ← viewer/index.html
  models/index.json           ← モデル一覧(先頭が最新)
  models/<id>/haiden_web.glb
  models/<id>/stats.json      ← 任意
  renders/<id>/*.png          ← 任意
  models/haiden_web.glb       ← 後方互換(最新のコピー、任意)
  models/stats.json           ← 後方互換(任意)
```

`models/index.json` が無ければ従来どおり `models/haiden_web.glb` + `models/stats.json` + `renders/*.png` の単一モデル表示。

### models/index.json

```json
[
  {"id": "A-2", "name": "拝殿A-2 ver1", "glb": "models/A-2/haiden_web.glb", "stats": "models/A-2/stats.json"},
  {"id": "A-1", "name": "拝殿A-1 ver1", "glb": "models/A-1/haiden_web.glb", "stats": "models/A-1/stats.json"}
]
```

- パスはサイトルート基準(`/app/` からは自動で `../` を補う)。`{"models": [...]}` 形式も可。`stats` は省略可。
- 先頭が初期表示(最新)。表示中のモデルの GLB だけを取得する(他のモデルは選ぶまで読まない)。

### models/<id>/stats.json(任意)

あれば quick 版の左上に小さく表示する。認識するキー(どれも省略可):
`triangles`(`tris`/`polys`/`faces`), `vertices`, `objects`(`meshes`/`parts`), `materials`, `glb_bytes`(`size_bytes`。進捗表示の分母にも使う), `dimensions`(`[x,y,z]` m)/`dimensions_m`(`{width_x,...}`), `generated`(日時文字列),
`renders`: レンダ画像の配列。`{ "src": "renders/A-2/front.png", "title": "正面" }`(サイトルート基準)か、`"front.png"` のような文字列(`renders/` からの相対)。無ければサムネ欄は出ない。
`id` / `name` / `version` は現状表示に使わない(名前は index.json の `name` をタブに出す)。

## quick 版(`/`)

- index.json があると左上にモデル切替タブ(`name` 表示)。初期は先頭(最新)。
- `?m=<id>` で指定・共有(例 `/?m=A-1`、大文字小文字は無視、不明な id は先頭)。タブ切替時は `history.replaceState` で URL を更新。
- 「同じ視点で切替」(既定 ON、localStorage に保存): 切替時にカメラ位置・注視点を保つので比較しやすい。OFF なら新モデルのホーム視点。
- 切替は新モデルの読込完了後に差し替え、前モデルのジオメトリ・マテリアル・テクスチャを dispose。読込中に別タブを押すと前の取得は中断(AbortController)。
- サムネ欄はそのモデルの `stats.json` の `renders`。「アプリ版で開く」は `app/?m=<id>`。
- 読込高速化: head の小さなスクリプトで three.js の取得を待たずに index.json → 表示モデルの GLB を fetch 開始。

## URL パラメータ(アプリ版)

- `?m=<id>` … `../models/index.json` のモデルを開く。例: `/app/?m=A-1`
- `?model=<URL>` … 読み込む GLB/GLTF(ページからの相対 or 絶対 URL)。例: `/app/?model=../models/haiden_web.glb`
- 指定なしの場合、index.json があれば先頭(最新)。無ければ `../models/haiden_web.glb` → `haiden_web.glb` → `../haiden/out/haiden_web.glb` の順に自動で探す。
- index.json があるとトップバーに「サンプル」メニュー(とモデル未読込時の画面にボタン)が出る。選ぶと `?m=<id>` に URL 更新。ファイルを開く/D&D はこれまでどおり。

## ローカル確認

```sh
# リポジトリ直下で
python3 -m http.server 8000
# アプリ版: http://localhost:8000/viewer/  (haiden/out/haiden_web.glb を自動検出)
#           http://localhost:8000/viewer/?model=test/test_shrine_draco.glb
```

Pages と同じ構成での自動テスト(`pip install playwright` と Chromium が必要):

```sh
python3 viewer/test/smoke_test.py             # variants / legacy 両レイアウトの _site を組み立てて PC 幅・380px 幅で確認
python3 viewer/test/smoke_test.py --mock-cdn  # CDN に出られない環境用(npm の three で代替)
python3 viewer/test/smoke_test.py --real      # haiden/out の実物 GLB(haiden/out/<id>/、A-1 は haiden/out/ 直下も可)を使う
```

- variants: テスト GLB を A-2(`test_shrine_draco.glb`)/A-1(`test_shrine.glb`)として index.json・ダミー stats/レンダを生成。
  `/`, `/?m=A-1`, `/app/`, `/app/?m=A-1` の表示、quick のタブ切替(視点維持 ON/OFF・URL・メモリ解放・連打)、アプリ版のサンプルメニューを検査。
  quick では表示中モデルの GLB しか取得していないことも確認。
- legacy: index.json なしの従来構成で `/` と `/app/`。
- コンソールエラーがあれば NG。スクショは `viewer/test/screenshots/site_*.png`(`--prefix` で変更)。
