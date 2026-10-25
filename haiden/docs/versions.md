# 拝殿モデル バージョン

| ID | 名前 | 内容 | commit |
|---|---|---|---|
| A-1 | 拝殿A-1 ver1 | 入母屋造・平入・3間×2間・1間向拝(軒唐破風)・銅板段葺・丹塗(凍結) | 7b7b936 |
| A-2 | 拝殿A-2 ver1 | A-1 の屋根を本瓦葺(いぶし銀)に、正面に千鳥破風を追加 | fbbade4 |

- 生成: `python3 haiden/blender/build_haiden.py --variant <ID> --out haiden/out/<ID>`、レンダ: `python3 haiden/blender/render.py --out haiden/out/<ID>`
- 定義: `haiden/blender/variants/<ID>.json`(params.json への差分)。A-1 の差分は空で、A-1 ver1 と同一形状を出力する(頂点・面の一致を確認済み)
- 公開: `models/<ID>/haiden_web.glb`, `models/<ID>/stats.json`, `renders/<ID>/*.png`, `models/index.json`(新しい順)。`models/haiden_web.glb` は最新(A-2)の互換コピー
