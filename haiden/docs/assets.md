# 境内アセット(鳥居・灯籠ほか) 共通仕様

拝殿以外の単体アセットの置き場・出力・公開の約束事。モデル担当・CI担当の共通の正本。

## 対象(第1弾 2026-11-01)

| ID | 名前 | 種類(category) | スクリプト | 仕上げ(KHR_materials_variants) |
|---|---|---|---|---|
| T-1 | 明神鳥居 | torii(鳥居) | haiden/blender/assets/build_torii.py | nuri=丹塗 / ishi=石(花崗岩) |
| L-1 | 春日灯籠 | toro(灯籠) | haiden/blender/assets/build_toro.py | shin=御影石 / koshoku=古色(苔・風化) |

次候補(未着手): 神明鳥居、狛犬、手水舎、玉垣、注連柱、石段。

## 座標・寸法
- 単位 m。X=幅(正面の左右)、Y=奥行(正面は -Y)、Z=上。拝殿と同じ。
- 原点 = 設置面(地面 Z=0)の中心。鳥居は2本の柱の中点、灯籠は竿の中心。地面より下(根入れ)は作らない(礎石・基壇の地上部分まで)。
- 実寸で作る(鳥居 高さ約4.5m 柱径0.30m、灯籠 全高約2.1m を基準。根拠 research_torii.md / research_toro.md)。

## スクリプトの入出力(build_haiden.py と同じ形)
- `python haiden/blender/assets/<script> --variant <ID> --out haiden/out/<ID>`
  - 定義: `haiden/blender/assets/variants/<ID>.json`(`script` に上表のファイル名)
  - 出力: `<out>/haiden.blend`, `<out>/haiden_web.glb`(Draco)、`<out>/stats.json`
- `python haiden/blender/assets/render_asset.py --out haiden/out/<ID>`(環境変数 HAIDEN_QUALITY=draft|preview|final)
  - `<out>/renders/*.png` を出力し、stats.json の `renders` を更新
  - 汎用(CI担当が作る)。地面(砂利の平面)・Sky+Sun・Cycles CPU+OIDN。視点は variants/<ID>.json の `views`(拝殿 render.py と同じタプル形式: title, camera loc, target, lens, sun elev, sun azim, sun strength, sky strength)。仕上げごとに描く場合は `views` の要素に `"finish":"<id>"` を付ける(KHR 変種を切替えて描画)
  - 仕上げ切替の約束: ビルドスクリプトは仕上げで材質が変わる各オブジェクトに、カスタムプロパティ `finish_mats`(JSON文字列 `{"<finish id>": ["<slot0の材質名>", "<slot1の材質名>", ...]}`)を付け、全仕上げの材質を .blend に残す。render_asset.py はこれを読んで material_slots を差し替えて描く(.blend 保存時の既定は先頭の仕上げ)
  - 品質: draft 640×360/12spp、preview 960×540/24spp、final 1600×900/48spp
- 共通部品(材質・焼き込み・GLB出力)は haiden/blender/hlib を再利用してよいが、拝殿の出力を変えないこと(拝殿の凍結版の差分0を壊さない)。

## stats.json(ビューア・CIが読む)
拝殿と同じキーに `category` と `category_name` を追加する。
```json
{"id":"T-1","name":"明神鳥居","version":"ver1","seq":1,"category":"torii","category_name":"鳥居",
 "title":"...","tris":0,"objects":0,"finishes":[{"id":"nuri","name":"丹塗"},{"id":"ishi","name":"石"}],
 "finish_mode":"khr_variants","renders":["renders/T-1/front.png"]}
```
- 拝殿は `category` が無い → ビューア・CIは `haiden`(拝殿)として扱う。

## 公開(CI・ビューア)
- CI の matrix に T-1, L-1 を追加。variants/<ID>.json が assets/variants にあるものは assets のスクリプトでビルド・レンダ。
- models/index.json の各要素に `category`, `category_name` を載せる。並び順は 拝殿(A-1, A-2, A-2v1, A-1v1) → 鳥居 → 灯籠。
- 互換コピー `models/haiden_web.glb` は拝殿 A-1 のまま(アセットにしない)。
- ビューアのモデル選択は種類ごとに見出し(拝殿/鳥居/灯籠)で区切る。
