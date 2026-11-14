# 鎮守の里(仮称→決定案) 設計書 v0.1

和風箱庭ゲーム本体(Android)。このファイルが実装の正本。各担当は**自分の担当ファイルだけ**を書き、ここに書かれたAPI・名前を変えない(変える必要があれば統括に報告)。

- 作成 2026-11-14 / 統括が管理
- エンジン: **Godot 4.7.2-stable**(GDScript、Mobileレンダラ)。選定理由は `research_engine.md`
- アプリID(固定・変更禁止): `io.github.amgm087ff5.japaneselocaltown`
- タイトル: 鎮守の里(ちんじゅのさと)

## 1. v0.1 の範囲

| 入れる | 内容 |
|---|---|
| 地形操作 | 上げる・下げる・平ら・なめらか。水位より下は水面(池・川) |
| 地表 | 草(既定)・土・砂利・石畳・苔・白砂・畑・舗装をブラシで塗る。境目はグラデーション。急斜面は自動で崖(岩肌) |
| 森 | 森ブラシで範囲を塗ると木が自動生成(MultiMesh)。建物の占有領域内は自動で生えない |
| 配置 | 自由座標・自由回転。占有領域の辺スナップ(辺に吸着→辺に沿って平行移動、回転は基準辺と平行を保つ)。複製・削除・整地・元に戻す |
| カメラ | 自由(パン・ズーム・回転・傾き)+定位置(真上・真横・斜め・北向き) |
| 歩行 | 作った世界に降りて歩く。一人称/地面に近い三人称の切替。仮想スティック |
| 環境 | 時刻(0-24時、自動進行)、方角(北=-Z、太陽は東→南→西)、四季、天気(晴・曇・雨・雪)、夜は灯籠と家の窓が灯る、遠景の山並み(行動範囲の約10倍の距離) |
| 保存 | 複数の世界。自動保存。見本の世界つき |
| 画面 | 縦・横の両対応(センサーで回転)、日本語UI、撮影モード(UIを隠す) |
| 画質設定 | 軽量・標準・高 |

入れない(将来): お金・職業・祭事などのゲーム要素、エリア(多角形)と外周、ベジェ曲線の道、オンライン、自作アセット取込、高精細モデル(haiden/ の拝殿など)の組込み。

## 2. 座標・単位

- Godot標準。Y上、単位m。**北=-Z、東=+X**。
- 世界は 256m×256m、原点中心(x,z ∈ [-128,128])。
- ハイトマップ: N=257(1m格子)。`idx = iz*257 + ix`、`ix = x+128`, `iz = z+128`。高さ範囲 [-8, 40]。水位 `WATER_LEVEL = -0.6`。
- モデルの正面=+Z(Blenderの-Y)。原点=設置面の中心。回転 `rot` はY軸まわり(rad)。

## 3. ファイル構成(game/ 以下)

```
project.godot  export_presets.cfg  icon.svg  main.tscn
scripts/main.gd                    ルート。World・UI・モードを組み立てる
scripts/core/world_data.gd         class_name WorldData  純データ+直列化
scripts/core/game.gd               autoload "Game"  現在の世界・保存・シグナル・設定・Undo
scripts/core/catalog.gd            autoload "Catalog"  data/catalog.json を読む
scripts/core/geom.gd               class_name Geom  2D幾何・スナップ計算(純関数)
scripts/terrain/terrain.gd         class_name Terrain  地形メッシュ・ブラシ・当たり
scripts/terrain/terrain.gdshader   地表の合成(8種+崖+雪+濡れ)
scripts/terrain/water.gdshader
scripts/objects/object_layer.gd    class_name ObjectLayer  配置物のノード生成
scripts/objects/forest.gd          class_name Forest  森(MultiMesh)
scripts/objects/foliage.gdshader   葉(季節色・密度・雪)
scripts/env/env_controller.gd      class_name EnvController  時刻・季節・天気
scripts/env/sky.gdshader  scripts/env/backdrop.gd  scripts/env/weather_fx.gd
scripts/modes/camera_rig.gd        class_name CameraRig
scripts/modes/edit_mode.gd         class_name EditMode   配置
scripts/modes/terrain_mode.gd      class_name TerrainMode 地形・地表・森
scripts/modes/walk_mode.gd         class_name WalkMode   歩行
scripts/ui/hud.gd ほか             class_name Hud  画面UI(縦横対応)
data/catalog.json                  アセット定義(モデル担当が作る)
assets/models/*.glb  assets/fonts/NotoSansJP-Regular.otf(または .ttf)
tools/  tests/run_tests.gd  docs/
```

シーンツリー(main.gd が `_ready` でコード生成。.tscn は main.tscn のみ):

```
Main (Node, main.gd)
├─ World (Node3D)
│  ├─ Env (EnvController)        … WorldEnvironment, Sun, Moon, Backdrop, WeatherFx を子に持つ
│  ├─ Terrain (Terrain)          … group "terrain"
│  ├─ Forest (Forest)
│  ├─ Objects (ObjectLayer)
│  ├─ CameraRig (CameraRig)      … 編集用カメラ
│  └─ Modes: EditMode, TerrainMode, WalkMode (Node)
└─ UI (CanvasLayer) └─ Hud (Control, hud.gd)
```
各ノードは `Main` の同名プロパティ(`main.terrain`, `main.forest`, `main.objects`, `main.env`, `main.camera_rig`, `main.edit_mode`, `main.terrain_mode`, `main.walk_mode`, `main.hud`)で参照。`Main` は group "main"(`get_tree().get_first_node_in_group("main")`)。

## 4. データ: WorldData (RefCounted)

```gdscript
const N := 257; const SIZE := 256.0; const HALF := 128.0
const WATER_LEVEL := -0.6; const H_MIN := -8.0; const H_MAX := 40.0
var version := 1
var id := ""            # 保存ファイル名(英数字)
var name := "あたらしい里"
var heights: PackedFloat32Array   # N*N
var splat_a: PackedByteArray      # N*N*4  R=土 G=砂利 B=石畳 A=苔   (0-255の重み)
var splat_b: PackedByteArray      # N*N*4  R=白砂 G=畑 B=舗装 A=予備
var forest: PackedByteArray       # N*N  森の濃さ 0-255
var objects: Array[Dictionary]    # {uid:int, type:String, x:float, z:float, rot:float}
var next_uid := 1
var env := {"time": 9.0, "time_flow": true, "day_minutes": 12.0, "season": 0, "weather": 0}
var player := {"x": 0.0, "z": 20.0, "yaw": 0.0}
func to_dict() -> Dictionary      # 配列は圧縮+Base64
static func from_dict(d: Dictionary) -> WorldData
static func idx(ix:int, iz:int) -> int
func height_at(x: float, z: float) -> float   # 双線形。範囲外は端の値
```
- 地表の種類ID: 0=草(既定・重みの残り) 1=土 2=砂利 3=石畳 4=苔 5=白砂 6=畑 7=舗装。草の重み = 1 - Σ(他)。塗るときは対象を増やし他を比例で減らす(合計≤255)。
- 季節: 0春 1夏 2秋 3冬。天気: 0晴 1曇 2雨 3雪。
- 保存先 `user://worlds/<id>.json`。

## 5. autoload: Game

```gdscript
signal world_loaded
signal object_added(uid: int)
signal object_changed(uid: int)
signal object_removed(uid: int)
signal terrain_changed(rect: Rect2i)   # 格子範囲(頂点index)。高さの変更
signal surface_changed(rect: Rect2i)   # splat の変更
signal forest_changed(rect: Rect2i)
signal env_changed                     # 季節・天気・time_flow など(毎フレームの時刻進行では出さない)
signal settings_changed
signal mode_changed(mode: String)      # "edit" "terrain" "walk" "photo"
signal undo_changed
var world: WorldData
var mode := "edit"
var settings := {"quality": 1, "snap": true, "invert_look": false, "sound": true}  # quality 0軽量 1標準 2高
func set_mode(m: String)
func new_world(kind: String, name := "") -> void   # "hills" "flat" "sample"
func save_world() -> bool; func load_world(id: String) -> bool
func list_worlds() -> Array[Dictionary]  # {id,name,modified}
func delete_world(id: String) -> void
func get_object(uid: int) -> Dictionary
func add_object(type: String, x: float, z: float, rot: float) -> int
func update_object(uid: int, x: float, z: float, rot: float, record_undo := true) -> void
func remove_object(uid: int) -> void
func set_env(key: String, value) -> void          # env_changed を出す
func set_setting(key: String, value) -> void      # 保存して settings_changed
# Undo/Redo(配置物の追加・移動・削除、地形/地表/森の1ストローク単位。最大30)
func begin_stroke(layer: String) -> void          # "height" "surface" "forest"  変更前を控える
func end_stroke(rect: Rect2i) -> void             # rect の差分パッチをUndoに積む
func undo() -> void; func redo() -> void; func can_undo() -> bool; func can_redo() -> bool
```
- 自動保存: 変更から5秒後、アプリの一時停止時(`NOTIFICATION_APPLICATION_PAUSED`)、モード切替時。
- 起動時: 最後に開いた世界を読む。無ければ `new_world("sample")`。

## 6. autoload: Catalog / data/catalog.json

```json
{"items":[{"id":"haiden","name":"拝殿","category":"shrine","model":"res://assets/models/haiden.glb",
  "footprint":[9.0,8.0],            // 占有領域 幅x 奥行z(中心原点の矩形)
  "colliders":[{"pos":[0,2,0],"size":[7,4,6]}],   // 歩行時の当たり(箱)。省略時は占有領域×高さ
  "height":7.5, "walkable":false,   // walkable=true は当たり無し(石畳の飛び石など)
  "glow":"lantern",                 // 夜に灯る材質を持つ("lantern"|"window"|省略)
  "tree":false, "order":10}]}
```
- category: `shrine`(神社) `town`(街) `nature`(自然)。UIの並びは order 昇順。
- 木(tree=true)は葉の材質名を `leaf_<種>`(例 `leaf_sakura`)、幹を `trunk` にする。葉と幹は1メッシュ2サーフェスでも別メッシュでもよい。種: `sugi` `matsu` `take`(常緑) / `sakura` `kaede`(落葉)。
- 夜に灯る材質名: `glow_lantern` / `glow_window`。
- API: `Catalog.items() -> Array[Dictionary]`, `Catalog.get_item(id) -> Dictionary`, `Catalog.by_category(cat)`, `Catalog.footprint_polygon(id) -> PackedVector2Array`(ローカル x,z の4頂点・反時計回り), `Catalog.instantiate(id) -> Node3D`(モデルが無ければ占有領域サイズの箱を返す), `Catalog.tree_ids()`。

## 7. Geom(純関数・テスト対象)

```gdscript
static func to_world(poly_local: PackedVector2Array, pos: Vector2, rot: float) -> PackedVector2Array
static func point_in_polygon(p: Vector2, poly: PackedVector2Array) -> bool
static func polygons_overlap(a, b) -> bool        # 凸多角形 SAT
static func compute_snap(poly_local, pos: Vector2, rot: float, others: Array, threshold: float) -> Dictionary
#  others = [PackedVector2Array(ワールド座標), ...]
#  戻り {snapped:bool, pos:Vector2, rot:float, edge_from:Vector2, edge_to:Vector2}
```
スナップの仕様(要望DB「スナップ基準」「占有領域」):
1. 動かす物の各辺と、他の物の各辺の組で、(a)向きの差が45°以内で平行にできる (b)辺どうしの距離が threshold 以内 (c)辺に沿った射影が重なる(または端の差が threshold 以内)ものを探し、最も近い組を選ぶ。
2. 動かす物を、その辺が基準辺と平行になるよう最小角で回す。辺と辺がぴったり接する(同一直線上・外側どうし)よう垂直方向だけ動かす。**辺に沿った方向の位置は指の位置のまま**(=辺に沿って平行移動できる)。
3. 角どうしが threshold/2 以内なら角も合わせる。
4. スナップ中の回転操作は 90° 刻み(基準辺と平行を保つ)。スナップを外すには threshold より離す。
- threshold は既定 1.2m(ズームに応じて 0.6〜2.5m)。`Game.settings.snap` が false なら使わない。
- 回転は Godot の rot(Y軸、+で反時計回り=上から見て)。2D は (x, z) 平面。`to_world` は `Vector2(x*cos(rot)+z*sin(rot), -x*sin(rot)+z*cos(rot)) + pos`(= Node3D.rotation.y と一致させること。テストで確認)。

## 8. Terrain

```gdscript
func rebuild_all() -> void                       # world_loaded で
func height_at(x, z) -> float; func normal_at(x, z) -> Vector3
func raycast(from: Vector3, dir: Vector3, max_dist := 2000.0) -> Variant   # Vector3 か null(レイマーチ+2分法。物理に依存しない)
func screen_to_ground(camera: Camera3D, screen_pos: Vector2) -> Variant
func brush_height(kind: String, center: Vector2, radius: float, strength: float, dt: float) -> Rect2i  # "raise" "lower" "flatten" "smooth"
func brush_surface(type_id: int, center: Vector2, radius: float, strength: float, dt: float) -> Rect2i
func brush_forest(center: Vector2, radius: float, add: bool, dt: float) -> Rect2i
func flatten_polygon(poly_world: PackedVector2Array, margin := 1.5) -> Rect2i   # 占有領域を中心の高さで整地(縁はなだらかに)
func update_collision() -> void                  # HeightMapShape3D を更新(ストローク終了時・歩行開始時)
```
- 32×32セルのチャンク(8×8=64個)の ArrayMesh。変更チャンクだけ作り直す。法線は高さから計算。
- splat は ImageTexture 2枚(257×257 RGBA8)をシェーダに渡し、UV=ワールド座標で引く(頂点属性にしない→塗りは texture 更新だけで速い)。
- シェーダ: 各地表の色+手続きノイズ模様(石畳は目地、砂利は粒、畑は畝)。傾き(法線.y)<0.72 で崖(岩肌)へ。uniform `snow`(0-1 冬・雪), `wet`(0-1 雨), `season_tint`(草の色)。Mobile と Compatibility の両方で動くこと(テクスチャ配列・ループ依存を避ける)。
- 水: WATER_LEVEL の大きな平面1枚(波の法線・空の反射色・浅瀬の透け)。
- 当たり: StaticBody3D + HeightMapShape3D(レイヤー1)。

## 9. ObjectLayer / Forest

- ObjectLayer: `Game.object_*` と `world_loaded` に応じて `Catalog.instantiate` したノードを置く。Y は `terrain.height_at(x,z)`(地形変更時に範囲内を追従)。各ノードに `uid` メタ。StaticBody3D(レイヤー2)に colliders の箱。
  `func node_of(uid) -> Node3D`, `func pick(camera, screen_pos) -> int`(占有領域と高さの箱へのレイ判定。無ければ -1), `func set_highlight(uid, on)`, `func world_footprint(uid) -> PackedVector2Array`, `func all_footprints(except_uid) -> Array`.
- Forest: forest 濃度から決定的(世界seed+格子座標のハッシュ)に木を生成。チャンク単位の MultiMeshInstance3D、樹種ごと。濃度しきい値・最小間隔約2.5m、種の混合(杉45% 楓20% 桜15% 松10% 竹10%)。水面下・急斜面・配置物の占有領域(+1m)には生やさない。画質設定で描画距離と密度を変える。歩行時の当たりは近くの木だけ(幹の円柱)。
- 葉シェーダ(foliage.gdshader)を配置物の木と森の両方に使う。uniform: `leaf_color`, `density`(0-1、冬の落葉樹は疎ら), `snow`, `wind`。

## 10. EnvController

```gdscript
var time: float           # 0-24。world.env.time と同期。time_flow なら進む(day_minutes 実分で1日)
func apply_all() -> void  # 季節・天気・時刻を反映
func sun_direction() -> Vector3
func is_night() -> bool
```
- 太陽: 北緯35°相当。季節で南中高度を変える(夏78° 春秋55° 冬32°)。東(+X)から昇り南(+Z)を通り西(-X)に沈む。DirectionalLight3D(影あり・画質で設定)。夜は月の弱い光。
- 空: sky.gdshader(昼の青・朝夕の茜・夜の星・雲量 uniform)。天気で雲量・霧・光量・彩度。HDR+トーンマップ(ACES/AgX)、Glow は標準以上。
- 季節: 草色・葉色・雪(冬)を Terrain/葉シェーダの uniform(グローバルシェーダ uniform `g_season_grass`, `g_snow`, `g_wet`, `g_wind`, `g_leaf_*`, `g_leaf_density_deciduous`)で配る。桜は春に桃色、楓は秋に紅、冬は落葉。
- 天気: 雨・雪の GPUParticles3D(カメラ追従)。雪は冬以外でも選べる(積雪 `g_snow` は徐々に)。
- 夜: `glow_lantern` `glow_window` 材質の emission を上げる。灯籠の近く(カメラから近い最大8個)に OmniLight3D。
- 遠景: Backdrop = 半径約2200mの山並みリング(手続き生成のシルエット2〜3層、霞)+夏は入道雲のビルボード。カメラの far は 4000。

## 11. モードと操作

共通ジェスチャ(CameraRig、配置・地形モード): 1本指ドラッグ=地面をつかんで移動(パン) / ピンチ=ズーム / 2本指ひねり=回転 / 2本指上下=傾き。マウス: 左ドラッグ=パン、右ドラッグ=回転・傾き、ホイール=ズーム。
`CameraRig`: `var target: Vector3, yaw, pitch, distance`; `func set_preset(name)`("top" 真上, "side" 真横, "oblique" 斜め, "north" 北を上); `func handle_input(event) -> bool`; `var camera: Camera3D`; `func focus(pos)`.
UI上のタッチは Control が消費する(`_unhandled_input` で受ける)。

- **EditMode(配置)**: パレットで選ぶ→画面中央の地面に仮置き(半透明+占有領域の枠)。物をドラッグ=移動(スナップあり)。空き地ドラッグ=カメラ。決定で確定。既存物タップ=選択→移動・回転(15°刻み/スナップ中90°)・複製・削除・整地。重なり(占有領域どうし)は赤枠で警告するが置ける。
  API: `start_placing(type)`, `confirm()`, `cancel()`, `rotate_selected(step_deg)`, `duplicate_selected()`, `delete_selected()`, `flatten_selected()`, `var selected_uid`, signal `selection_changed`.
- **TerrainMode(地形)**: 道具 `tool`("raise" "lower" "flatten" "smooth" "surface" "forest_add" "forest_remove")、`surface_type`、`radius`(2-30m)、`strength`(0-1)。1本指ドラッグ=ブラシ(地面にブラシの円を表示)、2本指=カメラ。ストローク単位でUndo。
- **WalkMode(歩行)**: CharacterBody3D(カプセル高1.6m、速さ 歩き3.2m/s 走り6m/s)。左下の仮想スティック=移動、画面ドラッグ=見回す。一人称(目の高さ1.5m)/三人称(後方3.2m・高さ1.9m、地形にめり込まない)。開始位置=編集カメラの注視点。水には入れるが深さ1mまで。終了で編集カメラが歩行位置へ。
  API: `enter()`, `exit()`, `toggle_view()`, `set_move_vector(v: Vector2)`, `add_look(delta: Vector2)`, `jump()`.
- **photo(撮影)**: UIを隠す。画面タップで戻る。カメラ操作は可。

## 12. UI(Hud)

- ストレッチ: base 720×720、`canvas_items`、aspect `expand`(短辺が常に720論理px)。向き: `sensor`。
- 縦(幅<高さ): 上=状態バー(メニュー☰・世界名・時刻/季節/天気チップ・元に戻す/やり直す)。下=モードタブ(配置/地形/歩く/撮影)とその上に道具パネル(下からのシート、高さは画面の38%まで)。
- 横: 左=モードタブ(縦並び)、右=道具パネル(幅300)、上=状態バー。
- セーフエリア(`DisplayServer.get_display_safe_area()`)を避ける。タッチ対象は 84論理px 以上。
- 画面サイズ変更(`get_viewport().size_changed`)で即レイアウトし直す。
- パネル: パレット(分類タブ+アイテム、サムネイルは SubViewport で実行時に生成しキャッシュ)、選択中の操作列、地形の道具・地表チップ・ブラシ大きさ/強さ、環境(時刻スライダ・時間の流れ・季節・天気)、メニュー(世界の一覧・新規(丘/平地/見本)・名前変更・削除・画質・スナップ・操作説明)、歩行HUD(スティック・視点切替・走る・ジャンプ・終了)。
- 日本語フォント `assets/fonts/` を Theme の既定に。配色: 生成り・墨・朱(#C8452C)・松葉(#3F6B4F)。角丸、半透明の和紙風パネル。

## 13. テスト・確認

- `godot --headless --path game --script res://tests/run_tests.gd`: Geom(スナップ・to_world と Node3D 回転の一致)、WorldData 直列化の往復、Terrain ブラシ、Game の Undo、Catalog の全モデル読込。失敗で exit 1。
- `tools/shots.gd`: 縦(720×1560)・横(1560×720)で各モード・各季節/時刻/天気のスクリーンショットを `game/out/shots/` に出す(xvfb+ソフトウェア描画)。
- 性能の目安: 標準画質で三角形 60万以下/フレーム、ドローコール 300 以下。

## 14. ビルド・配布

- `tools/build_apk.sh`: versionCode = エポック分。固定keystore(環境変数 `GODOT_ANDROID_KEYSTORE_RELEASE_PATH/_USER/_PASSWORD`)で署名。鍵が無ければ失敗。arm64-v8a + armeabi-v7a。
- CI `.github/workflows/game.yml`: テスト→APK→固定タグ `game-latest` のプレリリース。Secrets: `GAME_KEYSTORE_B64`, `GAME_KEYSTORE_PASSWORD`。alias は `jlt`(定数)。

## 15. 確定事項(2026-11-14 レビュー反映。**上の章と食い違う場合はこの章が優先**)

### 15.1 役割(誰が呼び、誰がシグナルを出すか)
| こと | 呼ぶ側 | 実行 | シグナル |
|---|---|---|---|
| 地形/地表/森のブラシ | TerrainMode が `Game.begin_stroke(layer)` → 毎フレーム `terrain.brush_*()` → 指を離したら `Game.end_stroke(rect)` | Terrain は `Game.world` の配列を書き換え、**自分の見た目だけ**即更新し Rect2i を返す(シグナルは出さない) | `Game.end_stroke` が layer に応じ `terrain_changed/surface_changed/forest_changed(rect)` を1回出す。Undo/Redo 時も Game が出す |
| シグナルを受ける側 | — | Terrain(Undo時の再構築。自分のストローク直後は再構築済みなので軽い処理でよい)、ObjectLayer(高さ追従)、Forest(該当チャンク再生成)、Terrain.update_collision(terrain_changed 時) | — |
| 整地(flatten_polygon) | EditMode が begin_stroke("height") → flatten_polygon → end_stroke | 同上 | 同上 |
| 物の移動 | EditMode。ドラッグ中は `Game.update_object(uid,x,z,rot,false)`、指を離したら `Game.commit_move(uid, from_x, from_z, from_rot)`(Undo 1件) | Game | `object_changed` |
| 物の追加/削除 | EditMode → `Game.add_object / remove_object`(各Undo 1件) | Game | `object_added/removed` |
| Forest の再生成 | Forest が `object_added/changed/removed`, `forest_changed`, `terrain_changed`, `world_loaded`, `settings_changed` を購読 | Forest | — |

- 追加API: `Game.commit_move(uid: int, from_x: float, from_z: float, from_rot: float) -> void`。
- `Terrain.height_at` は `Game.world.height_at` への委譲(実装を二重にしない)。
- `scripts/main.gd` `project.godot` `scripts/core/*` は**骨格担当だけ**が編集。他担当は自分のファイルのみ。必要な変更は報告。

### 15.2 データ・保存
- WorldData に `var seed: int` を追加(森・地形生成に使用)。
- `from_dict`: 欠けたキー・壊れた配列・未知の version でも落ちず既定値で埋める(version が大きい場合も読める範囲で読む)。将来のエリア・道は別配列(`areas`, `paths`)を version 2 で追加する方針(objects は変えない)。
- 保存は一時ファイルに書いて rename。ストローク中・ドラッグ中は保存しない(終わってから)。
- Undo: 最大30件かつ合計約24MBまで(超えたら古い順に破棄)。パッチはストロークの外接矩形ぶんだけ。

### 15.3 スナップ・操作の確定
- スナップ中の回転は「基準辺に対して90°刻み」。
- タッチの優先順は**指を置いた瞬間**に決める: (UIの上)→UI / (配置モード)選択中・仮置き中の物の上→物のドラッグ、それ以外→カメラのパン / (地形モード)1本指→ブラシ。**2本目の指が置かれたら**進行中の物ドラッグ・ブラシは取り消し(物は元の位置へ、ブラシはそこまでで end_stroke)、以後はカメラ操作(ピンチ・ひねり・傾き)。
- 道具パネル(シート)の上のタッチはUIが消費(背面に通さない)。
- 歩行モード中はモードタブ・状態バーを隠し、歩行HUD(スティック・視点切替・走る・ジャンプ・終了)だけ出す。
- 撮影モードは残す。戻るのは画面隅の半透明の「戻る」ボタン(タップ判定の競合を避ける)。
- Android の戻るボタン(`NOTIFICATION_WM_GO_BACK_REQUEST`、`application/config/quit_on_go_back=false`): メニュー/パネルを閉じる → 仮置き・選択を解除 → 歩行/撮影を終了 → それ以外は「もう一度押すと終了」のトースト後に保存して終了。Hud が処理。

### 15.4 描画・性能の確定
- カメラ: near 0.2 / far 4000。
- 法線は世界全体の高さ配列から計算(チャンク境界の継ぎ目を出さない)。
- 地表シェーダの模様は、起動時に1枚だけ作るタイリングのノイズテクスチャ(256px、RGBA に別周波数)を参照。毎ピクセルの多オクターブ手続きノイズは使わない。
- 崖のしきい値は 法線.y < 0.70。歩行の `floor_max_angle` は 46°。
- 夜の灯り: グローバルシェーダ uniform `g_night`(0-1)1個。`glow_*` 材質は ObjectLayer が共有の ShaderMaterial(emission = 色 × g_night)に差し替える(物ごとに材質を複製しない)。OmniLight3D は**高画質のみ**・カメラに近い灯籠最大4個。
- v0.2 送り: 入道雲、浅瀬の透け(水は不透明寄りの単純な色+フレネル+波の法線で可)。積雪は `g_snow` を数秒で補間するだけ。
- サムネイル: SubViewport は `own_world_3d = true`、1回描いたら更新停止、`user://thumbs/<id>.png` にキャッシュ。
- フォント: NotoSansJP-Regular(SubsetOTF/JP)1本のみ(Boldは入れない。太字は使わない)。

| 画質 | 影 | 描画解像度 | Glow | 森の描画距離/密度 | 灯籠ライト | 雨雪の粒 |
|---|---|---|---|---|---|---|
| 0 軽量 | なし | 0.6 | なし | 70m / 50% | 0 | 300 |
| 1 標準 | あり(2分割・80m) | 0.8 | 弱 | 120m / 100% | 0 | 800 |
| 2 高 | あり(4分割・120m) | 1.0 | あり | 180m / 100% | 4 | 1500 |

- 性能目標(参照: 2021年頃の中位Android相当): 配置ドラッグ中のスクリプト処理 4ms/フレーム以下、`compute_snap`(物100個)1ms以下、`brush_height`(半径30m)8ms以下。テストでCPU時間を計測して表示(超過は警告)。

### 15.5 確認方法
- スクリーンショットは `tools/xvfb_godot.sh`(環境担当が用意、使えるレンダラは `docs/dev_env.md`)。Mobile(Vulkan) がソフトウェア描画で動かない場合は Compatibility で撮り、その旨を明記。**シェーダは両方で動く書き方**にする。
- テストは `--script` で autoload が使えない場合、`res://tests/tests.tscn` をシーンとして起動する方式にする(骨格担当が確認して決め、`docs/dev_env.md` ではなく `tests/README.md` に実行コマンドを書く)。
- 追加テスト: 保存の異常系(壊れたJSON・未知version)、ジェスチャ仲裁(InputEventScreenTouch/Drag を流す。モード実装後に各担当が追加)。

### 15.6 実装の順序
- 段階0: 骨格(core 4ファイル・main・スタブ・テスト) ‖ モデル ‖ 環境構築
- 段階1(並列): B 地形(Terrain+シェーダ+TerrainMode) / C 環境(EnvController・空・遠景・天気) / D UI(Hud・Theme) / E 配置物(ObjectLayer・Forest・葉シェーダ・CameraRig・EditMode) / F 歩行(WalkMode)
- 段階2: 統合(main)・テスト・縦横スクリーンショット・修正 → APK・CI
