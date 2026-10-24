# 拝殿モデル仕様

- 形式: 入母屋造・平入・桁行3間×梁間2間・正面1間向拝(軒唐破風)・銅板葺(段葺)・丹塗り
- 座標: X=桁行、Y=梁間(正面 -Y)、Z=上。単位 m。パラメータは `haiden/blender/params.json`

## 寸法表
| 部位 | 値 |
|---|---|
| 柱間 桁行 | 2.12 + 2.42 + 2.12 = 6.66 |
| 柱間 梁間 | 2.12 + 2.12 = 4.24 |
| 基壇 | 高0.35、身舎から1.95張出、正面+0.45 |
| 礎石/亀腹 | 礎石h0.12, 亀腹h0.30 |
| 床/縁高 | 1.05 / 1.00、縁幅0.95 |
| 柱 | 円柱φ0.25、柱頂4.00 |
| 地長押/内法長押/頭貫 | 1.05-1.21 / 2.92-3.09 / 3.80-4.00 |
| 組物 | 出三斗(大斗+肘木+巻斗+実肘木)+丸桁 |
| 軒 | 二軒繁垂木、軒の出1.65、反り0.32 |
| 屋根 | 照り屋根(勾配0.32→1.30)、入母屋妻 側柱から1.80内、箱棟、鬼板 |
| 向拝 | 出2.0、面取角柱0.21、海老虹梁、手挟、虹梁、蟇股、軒唐破風 |

## 部材一覧(オブジェクト名の接頭辞)
Kidan_Platform, Soseki_Base, Kamebara, Hashira_Pillar, Nageshi_Ji/Uchi, Kashiranuki, Kibana, Masugumi(Daito/Hijiki/Makito), Gagyo/Keta, Jidaruki, Hiendaruki, Kioi, Kayaoi, Uragou, Sumiki, Yane_Roof(Doban), Hakomune, Onita, Hafu, Gegyo, Kohai_Pillar, Ebikoryo, Tabasami, Koryo, Kaerumata, Karahafu, Kizahashi, Koran, Giboshi, En, Entsuka, Koshi_Door, Hengaku, Saisenbako, Suzu, Suzuo, Shimenawa, Shide
