# 拝殿モデル バージョン

| ID | 名前 | 内容 | 仕上げ | commit |
|---|---|---|---|---|
| A-2 | 拝殿A-2 ver2 | A-2 ver1 の破風板を作り込み(眉・登り裏甲/茅負の段・拝み・破風尻繰形・破風金具・兎毛通の鰭)、木目方向UV+1Kテクスチャ(base/normal/roughness)、仕上げ3種 | 丹塗/白木/古色(KHR_materials_variants) | (統括が記入) |
| A-2v1 | 拝殿A-2 ver1 | A-1 の屋根を本瓦葺(いぶし銀)に、正面に千鳥破風を追加(凍結) | 丹塗のみ | fbbade4 |
| A-1 | 拝殿A-1 ver1 | 入母屋造・平入・3間×2間・1間向拝(軒唐破風)・銅板段葺・丹塗(凍結) | 丹塗のみ | 7b7b936 |

- **ID 変更**: 旧 `A-2`(拝殿A-2 ver1, commit fbbade4)は `A-2v1` に改称(`variants/A-2v1.json`、params は fbbade4 の `A-2.json` と同一)。ID `A-2` は ver2 が引き継ぐ。
- 生成: `python3 haiden/blender/build_haiden.py --variant <ID> --out haiden/out/<ID>`、レンダ: `python3 haiden/blender/render.py --out haiden/out/<ID>`
- 定義: `haiden/blender/variants/<ID>.json`(params.json への差分)。`seq` が大きいほど新しい(A-2=3, A-2v1=2, A-1=1)
- 凍結の確認(2026-10-25): 現行コードで A-1 / A-2v1 を生成し、凍結 commit(7b7b936 / fbbade4)のコードで生成した .blend と全オブジェクトの頂点座標・ループ(面)・UV・材質名の md5 が一致(差分0、A-1 118 obj・144,986面 / A-2v1 129 obj・486,154面)。haiden_web.glb も同サイズ(A-1 1,043,092 B / A-2v1 3,941,516 B)。ver2 の新機能はすべて params のフラグ(`hafu_detail.enabled`, `render.materials_v2`, `render.uv_mode`, `kawara.kake_shift/kake_drop/kake_ext`)で ON
- 公開: `models/<ID>/haiden_web.glb`, `models/<ID>/stats.json`, `renders/<ID>/*.png`, `models/index.json`(新しい順 A-2, A-2v1, A-1。各要素に `finishes`, `finish_mode`)。`models/haiden_web.glb` は最新(A-2 ver2)の互換コピー
