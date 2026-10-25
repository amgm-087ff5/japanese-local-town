# viewer

ブラウザで GLB を確認するための静的ページ。ビルド不要(three.js r170 を jsDelivr から読込)。

## 構成

| ファイル | 公開先 (GitHub Pages) | 役割 |
|---|---|---|
| `quick.html` | `/` (`index.html`) | 爆速確認用。最新モデルを自動読込・自動回転。モデル切替タブ / 仕上げ切替 / 視点リセット / 回転 / ワイヤー / アプリ版リンク |
| `index.html` | `/app/index.html` | アプリ版。ファイル選択・D&D、サンプルモデルメニュー、仕上げ切替、DRACO/KTX2/Meshopt、視点プリセット、影・露出・背景、部材ツリー、スクショ |
| `test/` | (公開しない) | テスト GLB(`make_finish_glbs.py` で仕上げ付きを生成)、スモークテスト、スクショ |

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
  {"id": "A-2", "name": "拝殿A-2 ver2", "glb": "models/A-2/haiden_web.glb", "stats": "models/A-2/stats.json",
   "finishes": [{"id": "nuri", "name": "丹塗"}, {"id": "shiraki", "name": "白木"}, {"id": "koshoku", "name": "古色"}], "finish_mode": "khr_variants"},
  {"id": "A-2v1", "name": "拝殿A-2 ver1", "glb": "models/A-2v1/haiden_web.glb", "stats": "models/A-2v1/stats.json"},
  {"id": "A-1", "name": "拝殿A-1 ver1", "glb": "models/A-1/haiden_web.glb", "stats": "models/A-1/stats.json"}
]
```

- パスはサイトルート基準(`/app/` からは自動で `../` を補う)。`{"models": [...]}` 形式も可。`stats` は省略可。
- 先頭が初期表示(最新)。表示中のモデルの GLB だけを取得する(他のモデルは選ぶまで読まない)。
- `finishes` / `finish_mode` は任意(stats.json 側にあれば十分。index.json にもあると仕上げ別 GLB を最初から正しく選べる)。

### 仕上げ(finishes)

stats.json(または index.json の要素)に:

```json
"finishes": [{"id": "nuri", "name": "丹塗"}, {"id": "shiraki", "name": "白木", "glb": "models/A-2/haiden_web_shiraki.glb"}, ...],
"finish_mode": "khr_variants"   // または "separate"
```

- `khr_variants`: 1 つの GLB 内の `KHR_materials_variants`。three の examples `webgl_loader_gltf_variants` と同じ方式
  (メッシュの mappings → `parser.getDependency('material', i)` で差し替え)なので切替は即時・再ダウンロードなし。
  バリアントは `id` → `name` の順で名前一致、どちらも無ければ並び順で対応付ける。
- `separate`: 仕上げごとの GLB(`glb`、サイトルート基準。省略した仕上げはモデルの `glb`)。切替時は視点を保って差し替え。
  `finish_mode` 省略時は `glb` を持つ要素があれば separate とみなす。
- `finishes` が無くても GLB に `KHR_materials_variants` があれば、そのバリアント名で切替を出す(アプリ版でファイルを開いた場合も)。
- 仕上げの無いモデルでは切替 UI を出さない。`?f=<id>` で指定・共有(例 `/?f=shiraki`、`/?m=A-2&f=koshoku`)。
  モデルを切り替えても同じ id の仕上げがあれば維持(無いモデルを挟んでも、戻れば復帰)。

### キャッシュ回避(ビルド ID)

`quick.html` / `index.html` の `<meta name="build" content="__BUILD__">` を CI がコミット SHA に置換すると、
`models/index.json`・GLB・stats.json・レンダ画像に `?v=<SHA>` を付けて取得する(デプロイ直後に古いモデルが出ない)。
置換されていなければ(ローカル等)クエリは付けない。

```sh
# _site を組んだ後
sed -i "s/__BUILD__/${GITHUB_SHA::12}/g" _site/index.html _site/app/index.html
```

HTML そのものは GitHub Pages の `Cache-Control: max-age=600` でキャッシュされるため、デプロイ後**最大 10 分**は古いページが出ることがある
(再読み込み/しばらく待つ)。新しい HTML になれば、データは必ず新しいものを取りに行く。

### models/<id>/stats.json(任意)

あれば quick 版の左上に小さく表示する。認識するキー(どれも省略可):
`triangles`(`tris`/`polys`/`faces`), `vertices`, `objects`(`meshes`/`parts`), `materials`, `glb_bytes`(`size_bytes`。進捗表示の分母にも使う), `dimensions`(`[x,y,z]` m)/`dimensions_m`(`{width_x,...}`), `generated`(日時文字列),
`renders`: レンダ画像の配列。`{ "src": "renders/A-2/front.png", "title": "正面" }`(サイトルート基準)か、`"front.png"` のような文字列(`renders/` からの相対)。無ければサムネ欄は出ない。
`id` / `name` / `version` は現状表示に使わない(名前は index.json の `name` をタブに出す)。

## quick 版(`/`)

- index.json があると左上にモデル切替タブ(`name` 表示、多い時は横スクロール)。初期は先頭(最新)。
- 仕上げがあるモデルは左下に「仕上げ」セグメントボタン。
- 全体表示はモデルのバウンディングボックスの 8 隅が、縦横それぞれの画角(縦長画面では水平画角が効く)と、上の情報パネル・下のボタン/サムネに
  隠れない領域に収まる距離で決める。回転中心はボックス中心で、投影の中心を UI の間の領域の中央へずらす。自動回転中は全方位で収まる距離にする。
- スマホ(幅 640px 以下か高さ 520px 以下)では情報パネルを 1 行(タブ+開閉ボタン)に圧縮。統計と「同じ視点で切替」は ▾ で開く(開閉状態は保存)。
- `?m=<id>` で指定・共有(例 `/?m=A-1`、大文字小文字は無視、不明な id は先頭)。タブ切替時は `history.replaceState` で URL を更新。
- 「同じ視点で切替」(既定 ON、localStorage に保存): 切替時にカメラ位置・注視点を保つので比較しやすい。OFF なら新モデルのホーム視点。
- 切替は新モデルの読込完了後に差し替え、前モデルのジオメトリ・マテリアル・テクスチャを dispose。読込中に別タブを押すと前の取得は中断(AbortController)。
- サムネ欄はそのモデルの `stats.json` の `renders`。「アプリ版で開く」は `app/?m=<id>`。
- 読込高速化: head の小さなスクリプトで three.js の取得を待たずに index.json → 表示モデルの GLB を fetch 開始。

## URL パラメータ(アプリ版)

- `?m=<id>` … `../models/index.json` のモデルを開く。例: `/app/?m=A-1`
- `?f=<仕上げ id>` … 仕上げを指定(quick 版と同じ)。仕上げがあると上部バーの下に「仕上げ」切替が出る。
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
python3 viewer/test/smoke_test.py             # variants / legacy 両レイアウトの _site を組み立てて PC 幅・390x844(縦長)で確認
python3 viewer/test/smoke_test.py --mock-cdn  # CDN に出られない環境用(npm の three で代替)
python3 viewer/test/smoke_test.py --real      # haiden/out の実物 GLB(haiden/out/<id>/、A-1 は haiden/out/ 直下も可)を使う。重いので PC 幅のみ・連打試験は省略
```

- variants: A-2(ver2・`KHR_materials_variants` 付き `test_shrine_variants.glb`)/ A-2v1(仕上げ別 GLB、仕上げは stats.json にだけ記載)/ A-1(仕上げなし)。
  `__BUILD__` を CI と同様に置換し、全リクエストに `?v=` が付くことを確認。
  `/`, `/?m=A-1`, `/?f=koshoku`, `/app/`, `/app/?m=A-1`, `/app/?f=koshoku` の表示と、モデルが UI に隠れず収まっていること、
  自動回転で一周しても収まること(PC・縦長・横長)、quick のタブ切替(視点維持 ON/OFF・URL・メモリ解放・連打)、
  仕上げ切替(khr → separate で同じ仕上げ維持 → separate 内切替で視点維持 → 仕上げなし → 戻ると復帰)、アプリ版のサンプルメニューと仕上げを検査。
  quick では表示中モデル(仕上げ)の GLB しか取得していないことも確認。
- legacy: index.json なしの従来構成で `/` と `/app/`(`__BUILD__` 未置換 → `?v=` なし)。
- `python3 viewer/test/make_finish_glbs.py [DIR]` で仕上げテスト用 GLB を単体生成できる。
- コンソールエラーがあれば NG。スクショは `viewer/test/screenshots/site_*.png`(`--prefix` で変更)。
