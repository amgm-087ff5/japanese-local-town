## ルート。World・UI・モードを組み立てる(architecture.md 3章)。
## モジュールは XXX.new() + add_child で作り、他からはこの Main のプロパティで参照する。
extends Node

const FONT_PATH := "res://assets/fonts/NotoSansJP-Regular.otf"
const SYSTEM_FONT_NAMES := ["Noto Sans CJK JP", "Noto Sans JP", "Hiragino Sans", "Yu Gothic", "Meiryo", "sans-serif"]

var world: Node3D
var env: EnvController
var terrain: Terrain
var forest: Forest
var objects: ObjectLayer
var camera_rig: CameraRig
var edit_mode: EditMode
var terrain_mode: TerrainMode
var walk_mode: WalkMode
var ui: CanvasLayer
var hud: Hud

var _last_mode := ""


func _ready() -> void:
	add_to_group("main")
	_setup_font()

	world = Node3D.new()
	world.name = "World"
	add_child(world)

	env = EnvController.new()
	env.name = "Env"
	world.add_child(env)

	terrain = Terrain.new()
	terrain.name = "Terrain"
	world.add_child(terrain)

	forest = Forest.new()
	forest.name = "Forest"
	world.add_child(forest)

	objects = ObjectLayer.new()
	objects.name = "Objects"
	world.add_child(objects)

	camera_rig = CameraRig.new()
	camera_rig.name = "CameraRig"
	world.add_child(camera_rig)

	edit_mode = EditMode.new()
	edit_mode.name = "EditMode"
	world.add_child(edit_mode)

	terrain_mode = TerrainMode.new()
	terrain_mode.name = "TerrainMode"
	world.add_child(terrain_mode)

	walk_mode = WalkMode.new()
	walk_mode.name = "WalkMode"
	world.add_child(walk_mode)

	ui = CanvasLayer.new()
	ui.name = "UI"
	add_child(ui)

	hud = Hud.new()
	hud.name = "Hud"
	ui.add_child(hud)

	Game.world_loaded.connect(_on_world_loaded)
	Game.mode_changed.connect(_on_mode_changed)

	# モジュールの接続が済んでから世界を開く(world_loaded で各モジュールを再構築する)
	Game.open_last_or_sample()
	_on_mode_changed(Game.mode)


## 世界の読込で作り直すのは各モジュール自身(Terrain・ObjectLayer・Forest・EnvController が world_loaded を購読)。
## ここでは二重に作らず、編集カメラの位置だけを決める。
func _on_world_loaded() -> void:
	camera_rig.set_preset("oblique")
	camera_rig.focus(Vector3(Game.world.player["x"], 0.0, Game.world.player["z"]))


## モードごとに有効なノードを切り替える。歩行中は CameraRig を止め、WalkMode のカメラを使う。
func _on_mode_changed(m: String) -> void:
	_set_active(edit_mode, m == "edit")
	_set_active(terrain_mode, m == "terrain")
	_set_active(walk_mode, m == "walk")
	_set_active(camera_rig, m != "walk")
	if _last_mode == "walk" and m != "walk":
		walk_mode.exit()
	if m == "walk":
		walk_mode.camera.make_current()
		walk_mode.enter()
	else:
		camera_rig.camera.make_current()
	_last_mode = m


func _set_active(node: Node, on: bool) -> void:
	node.process_mode = Node.PROCESS_MODE_INHERIT if on else Node.PROCESS_MODE_DISABLED


## 日本語フォント。assets/fonts に無ければ端末のシステムフォントを使う(開発用の代替)。
func _setup_font() -> void:
	var font: Font
	if ResourceLoader.exists(FONT_PATH):
		font = load(FONT_PATH)
	else:
		var sf := SystemFont.new()
		sf.font_names = PackedStringArray(SYSTEM_FONT_NAMES)
		font = sf
		push_warning("%s が無いためシステムフォントを使います。" % FONT_PATH)
	ThemeDB.fallback_font = font
