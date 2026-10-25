# 拝殿モデル仕様

- 形式: 入母屋造・平入・桁行3間×梁間2間・正面1間向拝(軒唐破風)・銅板葺(段葺)・丹塗り
- 座標: X=桁行、Y=梁間(正面 -Y)、Z=上。単位 m。パラメータは `haiden/blender/params.json`

## 寸法表
| 部位 | 値 |
|---|---|
| 柱間 桁行 | 2.12 + 2.42 + 2.12 = 6.66 |
| 柱間 梁間 | 2.12 + 2.12 = 4.24 |
| 基壇 | 高0.35、身舎から1.95張出、正面+1.15 |
| 礎石/亀腹 | 亀腹h0.45(漆喰), 礎石h0.08 |
| 床/縁高 | 1.05 / 1.00、縁幅0.95 |
| 柱 | 円柱φ0.25、柱頂3.60 |
| 地長押/内法長押/頭貫 | 1.05-1.21 / 2.72-2.88 / 3.40-3.60 |
| 組物 | 出三斗(大斗+肘木+巻斗+実肘木)+丸桁 |
| 軒 | 二軒繁垂木(ピッチ0.175)、軒の出1.65(+裏甲0.05)、木負位置1.00、反り0.42 |
| 屋根 | 照り屋根(勾配0.32→1.05)、段葺0.30、軒付厚0.27、入母屋 妻は軒先から1.80内・破風出0.45、箱棟、鬼板 |
| 向拝 | 出2.0、面取角柱0.21(柱頂3.08)、海老虹梁、手挟、虹梁、蟇股、軒唐破風(高0.55) |

## 部材一覧(オブジェクト名の接頭辞)
Kidan_Platform, Soseki_Base, Kamebara, Hashira_Pillar, Nageshi_Ji/Uchi, Kashiranuki, Kibana, Masugumi(Daito/Hijiki/Makito), Gagyo/Keta, Jidaruki, Hiendaruki, Kioi, Kayaoi, Uragou, Sumiki, Yane_Roof(Doban), Hakomune, Onita, Hafu, Gegyo, Kohai_Pillar, Ebikoryo, Tabasami, Koryo, Kaerumata, Karahafu, Kizahashi, Koran, Giboshi, En, Entsuka, Koshi_Door, Hengaku, Saisenbako, Suzu, Suzuo, Shimenawa, Shide

## 外形(stats.json)
約10.62(W)×10.04(D)×7.52(H) m、棟高(屋根面頂)6.8 m
