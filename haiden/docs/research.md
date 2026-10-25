# 拝殿 調査メモ(調査日: 2026-10-25)

## 1. 拝殿の代表形式
| 形式 | 要点 | 出典 |
|---|---|---|
| 入母屋造・平入・向拝付き | 地方社で最も一般的。例: 神明社拝殿(宮城)桁行3間・梁間2間、入母屋造、銅板葺(元茅葺か)、正面1間向拝、元禄11年 | [宮城県 神明社拝殿](https://www.pref.miyagi.jp/soshiki/bunkazai/29sinmei.html) |
| 切妻造・平入 | 例: 山縣神社拝殿(山梨)桁行3間・梁間2間、銅板葺切妻、一軒疎垂木、円柱、内法長押・地長押 | [山梨の文化財ガイド](https://www.pref.yamanashi.jp/bunka/bunkazaihogo/bunkazai_data/yamanashinobunkazai_ty0074.html) |
| 割拝殿 | 長い一棟の中央を馬道(めどう)で割り、土間通路とする。最古例 石上神宮摂社出雲建雄神社拝殿 | [JAANUS warihaiden](https://projects.mcah.columbia.edu/jaanus/node/289) |
| 本殿+拝殿の構成 | 拝殿は神事・参拝の建物。屋根は檜皮葺など植物性が多い。本来は組物・彫刻を用いない簡素な意匠 | [岡山市 社寺建築解説PDF](https://www.city.okayama.jp/cmsfiles/contents/0000062/62881/syajikentiku.pdf) |

→ 本モデルは **入母屋造・平入・桁行3間×梁間2間・正面1間向拝(軒唐破風付き)・銅板葺** を採用(近世〜近代の地方八幡社に典型、意匠は丹塗り)。

## 2. 部材(定義と位置)
- 二軒: 地垂木+飛檐垂木の二段。地垂木上に木負、飛檐垂木上に茅負(反りを持つ)。[JAANUS futanoki](https://projects.mcah.columbia.edu/jaanus/node/4512)
- 垂木配り: 繁垂木。本繁=間隔が垂木幅に等しい、小間返し=間隔が成に等しい。一般住宅の間隔は30〜45cm、古建築はより狭い。[コトバンク 垂木](https://kotobank.jp/word/垂木)
- 木割: 垂木寸法を基本単位に柱間・軒の出等を割り出す。比率は建物ごとに異なる。[JAANUS kiwari](https://aisf.or.jp/~jaanus/deta/k/kiwari.htm)
- 海老虹梁: 向拝柱と身舎柱(頭貫位置)を繋ぐS字曲線の繋梁。[JAANUS ebikoryo](https://projects.mcah.columbia.edu/jaanus/node/4712)
- 手挟: 向拝柱上、組物と下る垂木の間の楔形の隙間を埋める彫刻板。[JAANUS tabasami](https://aisf.or.jp/~jaanus/deta/t/tabasami.htm)
- その他(長押・貫・頭貫・木鼻・舟肘木/三斗組/出組・蟇股・虹梁・茅負・裏甲・箱棟・鬼板・懸魚・千鳥破風/唐破風・浜床・木階・擬宝珠高欄・縁・縁束・格子戸/蔀戸・賽銭箱・鈴・鈴緒・注連縄・扁額)は一般的な社寺建築の知識による(個別出典 要確認)。

## 3. 寸法目安(本モデル採用値。数値は一般知識による目安で **要確認**)
| 項目 | 目安 | 採用 |
|---|---|---|
| 1間 | 6.5〜7尺(1.97〜2.12m) | 中央2.42m、脇・梁間2.12m |
| 柱径 | 柱間の1/8〜1/10 | 円柱φ0.25m(向拝柱は面取角柱0.21m) |
| 内法高(床〜内法長押下) | 6尺前後 | 1.87m |
| 軒の出(側柱芯〜茅負外) | 柱間の0.7〜0.9 | 1.65m(二軒) |
| 地垂木/飛檐勾配 | 3〜4寸/2〜3寸 | 3.6寸/2.4寸 |
| 垂木 | 幅2.4〜3寸、間隔 本繁〜半繁 | 75×90mm、ピッチ約175mm |
| 屋根勾配 | 軒先3寸 → 棟付近 10寸以上の照り屋根 | 0.32→1.30(冪曲線) |
| 軒反り(隅の反り上がり) | 柱間の1/6〜1/8 | 0.32m |
| 基壇高 | 1〜2尺 | 0.35m(+亀腹0.30m) |
| 縁高 | 床高とほぼ同じ | 1.00m |

## 4. Blender MCP 検証結果(結論: ブリッジ経由で可。シーン検査に使用)
- 対象: [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp)(GitHubからclone)。Blender公式 lab/blender_mcp(projects.blender.org)はネットワーク許可外で取得不可。公式readmeでは背景モードは同期処理のみ対応との記述あり [readme](https://projects.blender.org/lab/blender_mcp/raw/branch/main/readme.md)。
- ahujasid版アドオンは `BlenderMCPServer.start()` で `bpy.app.background` の場合に起動を拒否(背景モードでは `bpy.app.timers` が回らずコマンドキューが処理されないため)。
- 対策: `haiden/blender/mcp/headless_bridge.py` でアドオンを読み込み、同じソケット(localhost:9876)を開き、メインスレッドのループで `_drain_command_queue()` を直接呼ぶ。→ `ping`/`get_scene_info`/`execute_code` が動作。
- さらに PyPI 相当のMCPサーバー(`mcp-for-blender`, stdio)を venv に入れ、自作の最小MCPクライアント `mcp_client.py` から `get_scene_info` / `execute_blender_code` の往復に成功。
- 使い方: 最終 haiden.blend を開いたブリッジに MCP 経由で execute_blender_code を送り、コレクション別オブジェクト数・地面下めり込み(z<-0.01)を検査 → 問題なし。モデリング本体は再現性のためCLI(build_haiden.py)。手順は haiden/blender/mcp/README.md。
- 判断: GUI依存ツール(viewport screenshot)は不可、長時間レンダは同期ブロック。CIではMCP不要のためCLIのみ。

## 5. 本瓦葺(A-2)調査(調査日: 2026-10-25)
| 項目 | 内容 | 出典 |
|---|---|---|
| 本瓦葺の構成 | 凹形の平瓦(女瓦)を先に葺き、継ぎ目を半円筒の丸瓦(男瓦)で覆う。軒先から葺き上げる。軒平瓦・軒丸瓦は雨水を切る瓦当を持つ。棟・棟端・けらば・隅には別形の役物を用いる | [JAANUS hongawarabuki](https://www.aisf.or.jp/~jaanus/deta/h/hongawarabuki.htm) / [GSJ 地質ニュース(瓦)](https://www.gsj.jp/data/chishitsunews/99_04_06.pdf) |
| 平瓦寸法・葺足 | 定寸なし。平均で広端幅 約30cm・長さ 約40cm、葺足は3枚重ねで約15cm(約2/3が覆われる) | [JAANUS fukiashi](https://aisf.or.jp/~jaanus/deta/f/fukiashi.htm) |
| 瓦の厚さ | 一般に 15〜20mm | [GSJ 地質ニュース](https://www.gsj.jp/data/chishitsunews/99_04_06.pdf) |
| 丸瓦寸法 | 径 約15cm前後・長さ 約35cm・玉縁 5〜6cm(一般知識による目安 **要確認**) | 要確認 |
| 冠瓦(雁振瓦) | 大棟・降棟・稚児棟の熨斗瓦積みの頂部を覆う、わずかに凸の瓦。別名 伏間瓦・冠瓦 | [JAANUS ganburigawara](https://aisf.or.jp/~jaanus/deta/g/ganburigawara.htm) / [伏間瓦](https://projects.mcah.columbia.edu/jaanus/record/fusumagawara) |
| 棟瓦 | 社寺は角桟伏間瓦(角ばる縁)、民家は箱冠瓦(丸桟) | [JAANUS munegawara](https://aisf.or.jp/~jaanus/deta/m/munegawara.htm) |
| 稚児棟 | 入母屋・寄棟の隅で、隅降棟の外側(下)に続く短い棟。軒先近くまで延び、先端は「一の鬼」。隅棟の端は鬼瓦または獅子口で「二の鬼」 | [JAANUS chigomune](https://projects.mcah.columbia.edu/jaanus/node/4975) |
| 熨斗瓦の段数 | 奇数段(3・5・7…)とするのが通例、棟の格で増やす(一般知識 **要確認**) | 要確認 |
| 獅子口 | 経の巻(3本の筒)と綾筋を持つ棟端飾り。檜皮葺・神社系の意匠で、瓦葺の神社でも大棟端に用いる(一般知識 **要確認**) | 要確認 |
| 千鳥破風 | 屋根の流れ面に載せた三角形の小破風(棟は大屋根の流れに突き当たる)。両脇は大屋根との谷になる。妻飾り(懸魚・木連格子)を持つ(一般知識 **要確認**) | 要確認 |

### A-2 採用値(spec.md A-2 節と同じ)
- 平瓦: 長さ0.40・広端幅0.27・狭端幅0.25・反り(凹)0.028・厚0.018、葺足0.135(3枚重ね)
- 丸瓦: 長さ0.36(玉縁0.055)・外径0.156(R0.078)・厚0.016、葺足0.305
- 瓦割(丸瓦芯々)0.27。軒瓦の出 0.08(瓦座より前へ)
- 大棟 熨斗7段+冠瓦、降棟・隅棟 5段、稚児棟 3段、雨押え 2段、唐破風棟 2段、千鳥破風棟 5段・同降棟 3段
- 棟端: 大棟=獅子口、降棟・千鳥破風・唐破風=鬼瓦(雲形鬼板+巴+鳥衾)、隅棟=二の鬼、稚児棟=一の鬼、隅の軒先=巴蓋
