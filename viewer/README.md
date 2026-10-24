# viewer

ブラウザで GLB を確認するための静的ページ。ビルド不要(three.js r170 を jsDelivr から読込)。

## 構成

| ファイル | 公開先 (GitHub Pages) | 役割 |
|---|---|---|
| `quick.html` | `/` (`index.html`) | 爆速確認用。`models/haiden_web.glb` を自動読込・自動回転。視点リセット / 回転 / ワイヤー / アプリ版リンクのみ |
| `index.html` | `/app/index.html` | アプリ版。ファイル選択・D&D、DRACO/KTX2/Meshopt、視点プリセット、影・露出・背景、部材ツリー、スクショ |
| `test/` | (公開しない) | テスト GLB、スモークテスト、スクショ |

Pages の想定レイアウト:

```
_site/
  index.html            ← viewer/quick.html
  app/index.html        ← viewer/index.html
  models/haiden_web.glb ← haiden/out/haiden_web.glb
  models/stats.json     ← 任意
  renders/*.png         ← 任意
```

### models/stats.json(任意)

あれば quick 版の左上に小さく表示する。認識するキー(どれも省略可):
`triangles`(`tris`/`polys`/`faces`), `vertices`, `objects`(`meshes`/`parts`), `materials`, `glb_bytes`(`size_bytes`), `dimensions`(`[x,y,z]` m), `generated`(日時文字列),
`renders`: レンダ画像の配列。`"front.png"` のような文字列(`renders/` からの相対)か `{ "src": "...", "title": "..." }`。無ければサムネ欄は出ない。

## URL パラメータ(アプリ版)

- `?model=<URL>` … 読み込む GLB/GLTF(ページからの相対 or 絶対 URL)。例: `/app/?model=../models/haiden_web.glb`
- 指定なしの場合 `../models/haiden_web.glb` → `haiden_web.glb` → `../haiden/out/haiden_web.glb` の順に自動で探す。

## ローカル確認

```sh
# リポジトリ直下で
python3 -m http.server 8000
# アプリ版: http://localhost:8000/viewer/  (haiden/out/haiden_web.glb を自動検出)
#           http://localhost:8000/viewer/?model=test/test_shrine_draco.glb
```

Pages と同じ構成での自動テスト(`pip install playwright` と Chromium が必要):

```sh
python3 viewer/test/smoke_test.py            # _site を一時ディレクトリに組み立てて / と /app/ を PC 幅・380px 幅で撮影
python3 viewer/test/smoke_test.py --mock-cdn # CDN に出られない環境用(npm の three で代替)
```

GLB は `haiden/out/haiden_web.glb`、無ければ `viewer/test/test_shrine_draco.glb` を使う。スクショは `viewer/test/screenshots/site_*.png`。
