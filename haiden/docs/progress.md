# 拝殿 進捗(2026-10-25)

## 実施
- 調査 research.md / 仕様 spec.md
- build_haiden.py(numpy→bpy直接メッシュ、params.json駆動)/ render.py(Cycles CPU+OIDN、Sky+Sun、参道・灯籠・杉)
- 出力 haiden/out: haiden.blend, haiden.glb(12.9MB), haiden_web.glb(Draco 1.0MB), stats.json, textures/(焼込タイル512px×7)
- 見直しループ4回: 遮蔽木/露出/銅色 → 軸部高↓・照り緩和・反り↑ → 軒付厚・鬼板/懸魚縮小・幹欠落修正 → 木鼻形状・蟇股彫刻・紙垂・注連縄太さ・扁額位置・地面明度
- viewer smoke_test --mock-cdn: pc/sp 全OK
- Actions: .github/workflows/haiden.yml(actionlint OK、_site組立をローカル再現)

## 仕様要点
入母屋造・平入・桁行3間(2.12/2.42/2.12)×梁間2間(2.12×2)・1間向拝(軒唐破風)・銅板段葺・丹塗。
出三斗+丸桁、二軒繁垂木(ピッチ0.175)+隅木、照り屋根+軒反り0.42、箱棟・鬼板・隅棟・懸魚・木連格子、
海老虹梁・手挟・虹梁・蟇股、擬宝珠高欄・木階・浜床・縁・縁束、格子戸、扁額、賽銭箱、鈴・鈴緒(3色)、注連縄・紙垂。

## 数値
- 293,016 tris / 118 objects / 17 materials / 外形 10.62×10.04×7.52m
- レンダ(preview 960×540, 24spp, 2コア): 各60〜71秒、4枚計約4分
- final(1600×900, 64spp): 1枚約400秒(2コア)→ Actions 4コアで1枚約3〜4分見込み

## レンダ
haiden/out/renders/{front_oblique,side,kohai_closeup,sunset}.png(確認用は haiden/out/debug/)

## MCP
ahujasid/blender-mcp: 背景モード非対応 → headless_bridge.py で可。MCP stdio往復とシーン検査を実施(mcp/README.md)。公式版は未取得(ネットワーク外)。

## 既知の課題
- 杉が様式的、地面単調
- 垂木: 平行垂木のみ(隅扇なし)、隅部は隅木で切るだけ
- 手挟・蟇股・木鼻は板状押出し+花彫刻のみ
- 向拝屋根と主屋軒の取合いに小さな段
- 銅板の一文字葺継手なし(段のみ)
- 扁額は正面低視点で向拝組物に隠れる

## 次の改善候補
彫刻ディスプレイスメント、銅板継手法線、杉LOD/インスタンス、苔・落葉、軒先の延び、本殿・狛犬・鳥居
