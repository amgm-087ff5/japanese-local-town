## 現在の世界・保存・シグナル・設定・Undo(architecture.md 5章・15章)。autoload 名 "Game"。
extends Node

signal world_loaded
signal object_added(uid: int)
signal object_changed(uid: int)
signal object_removed(uid: int)
signal terrain_changed(rect: Rect2i)   # 頂点 index の範囲。高さの変更
signal surface_changed(rect: Rect2i)   # splat の変更
signal forest_changed(rect: Rect2i)
signal env_changed
signal settings_changed
signal mode_changed(mode: String)
signal undo_changed

const MODES := ["edit", "terrain", "walk", "photo"]
const WORLD_DIR := "user://worlds"
const SETTINGS_PATH := "user://settings.json"
const UNDO_LIMIT := 30
const UNDO_BYTES_LIMIT := 24 * 1024 * 1024
const AUTOSAVE_DELAY := 5.0
const RETRY_DELAY := 1.0
const OBJECT_ENTRY_BYTES := 256

# 川(南北に流れる浅い川)の設定。x 中心 = RIVER_X + RIVER_AMP * sin(z * RIVER_FREQ)
const RIVER_X := -40.0
const RIVER_AMP := 8.0
const RIVER_FREQ := 0.02
const RIVER_HALF_WIDTH := 4.0
const RIVER_BED_HALF := 1.5         # 川底(平ら)の半幅
const RIVER_BANK_W := 5.5           # 川底の縁から岸の上端までの幅(なだらかな岸)
const RIVER_BED := -1.0
const RIVER_SMOOTH_PASSES := 6      # 川べりのぼかしの回数
const RIVER_SMOOTH_MARGIN := 4.0    # 川の縁より外側へ、ぼかしをかける幅(m)
const RIVER_PIN := 1.2              # 川底(中心からこの距離まで)はぼかさない(水面より下を保つ)
const PLATEAU_HEIGHT := 2.0
const PAINT_SOFT_SAMPLES := 8       # 地表の縁のなじませ: 中心の外側に置く標本の方向の数

# 見本の神社の配置(中心線 x=0、南(+Z)から北(-Z)へ参道)
const SHRINE_CENTER := Vector2(0.0, -10.0)
const FOREST_RADIUS := 58.0

var world: WorldData = null
var mode := "edit"
var settings := {"quality": 1, "snap": true, "invert_look": false, "sound": true}  # quality 0軽量 1標準 2高
var last_world_id := ""

var _undo: Array[Dictionary] = []
var _redo: Array[Dictionary] = []
var _stroke_layer := ""
var _stroke_before: Array[PackedByteArray] = []
var _drag_uid := -1
var _dirty := false
var _save_timer: Timer


func _ready() -> void:
	_ensure_timer()
	_load_settings()


## 自動保存タイマー(初回に作る。_ready より前に呼ばれても動くように遅延生成する)。
func _ensure_timer() -> Timer:
	if _save_timer == null:
		_save_timer = Timer.new()
		_save_timer.one_shot = true
		_save_timer.wait_time = AUTOSAVE_DELAY
		_save_timer.timeout.connect(_on_autosave_timeout)
		add_child(_save_timer)
	return _save_timer


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_PAUSED or what == NOTIFICATION_WM_CLOSE_REQUEST:
		if world != null and _dirty and not is_busy():
			save_world()
		_save_settings()


## ストローク中・ドラッグ中か(この間は保存しない)。
func is_busy() -> bool:
	return _stroke_layer != "" or _drag_uid != -1


## 物をドラッグ中か(update_object(record_undo=false) から commit_move まで true)。Forest はこの間、再生成しない。
func is_dragging() -> bool:
	return _drag_uid != -1


## 世界を保存対象にする(位置など、物以外の世界データを変えたとき。自動保存の予約が入る)。
func mark_dirty() -> void:
	if world != null:
		_mark_dirty()


## 起動時: 最後に開いた世界を読む。無ければ見本の世界を作る。Main が各モジュールを接続した後に呼ぶ。
func open_last_or_sample() -> void:
	if not last_world_id.is_empty() and load_world(last_world_id):
		return
	new_world("sample")


func set_mode(m: String) -> void:
	if not MODES.has(m) or m == mode:
		return
	mode = m
	if world != null and _dirty and not is_busy():
		save_world()
	mode_changed.emit(m)


## 世界を新規作成して開く。kind は "flat"(平地) "hills"(丘) "sample"(丘+見本の神社)。
func new_world(kind: String, name := "") -> void:
	var w := WorldData.new()
	w.id = _new_id()
	w.seed = randi()
	match kind:
		"hills":
			w.name = "あたらしい丘" if name.is_empty() else name
			_gen_hills(w)
		"sample":
			w.name = "見本の里" if name.is_empty() else name
			_gen_hills(w)
			_build_sample(w)
		_:
			if kind != "flat":
				push_warning("未知の kind '%s'。平地にします。" % kind)
			w.name = "あたらしい平地" if name.is_empty() else name
			w.reset_terrain(0.5)
	_set_world(w)
	save_world()
	world_loaded.emit()


## 保存: 一時ファイルに書いてから rename。成功で true。
func save_world() -> bool:
	if world == null:
		return false
	var path := _world_path(world.id)
	var text := JSON.stringify(world.to_dict())
	if not _write_atomic(path, text):
		push_error("世界の保存に失敗: %s" % path)
		return false
	_dirty = false
	_ensure_timer().stop()
	last_world_id = world.id
	_save_settings()
	return true


## 読込。壊れたJSON・存在しない id は false(現在の世界は変えない)。未知の version は読める範囲で読む。
func load_world(id: String) -> bool:
	var path := _world_path(id)
	if not FileAccess.file_exists(path):
		return false
	var text := FileAccess.get_file_as_string(path)
	var data = JSON.parse_string(text) if not text.is_empty() else null
	if not (data is Dictionary):
		push_warning("世界ファイルが壊れています: %s" % path)
		return false
	var w := WorldData.from_dict(data)
	if w.version > WorldData.CURRENT_VERSION:
		push_warning("新しい version の世界です(%d)。読める範囲で開きます。" % w.version)
	w.id = id
	_set_world(w)
	last_world_id = id
	_save_settings()
	world_loaded.emit()
	return true


## 保存済みの世界一覧。modified の新しい順。
func list_worlds() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	if DirAccess.open(WORLD_DIR) == null:
		return out
	for f in DirAccess.get_files_at(WORLD_DIR):
		if not f.ends_with(".json"):
			continue
		var id := f.get_basename()
		var data = JSON.parse_string(FileAccess.get_file_as_string(WORLD_DIR + "/" + f))
		if data is Dictionary:
			out.append({"id": id, "name": str(data.get("name", id)), "modified": float(data.get("modified", 0.0))})
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a["modified"] > b["modified"])
	return out


## 世界を削除。開いている世界を消した場合は残りの先頭を開き、無ければ見本を作る。
func delete_world(id: String) -> void:
	var path := _world_path(id)
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
	if last_world_id == id:
		last_world_id = ""
		_save_settings()
	if world != null and world.id == id:
		world = null
		var rest := list_worlds()
		if rest.is_empty() or not load_world(rest[0]["id"]):
			new_world("sample")


func get_object(uid: int) -> Dictionary:
	var i := _find_object(uid)
	if i < 0:
		return {}
	return world.objects[i].duplicate()


## 物を追加(Undo 1件)。uid を返す。
func add_object(type: String, x: float, z: float, rot: float) -> int:
	if world == null:
		return -1
	var uid := world.next_uid
	world.next_uid += 1
	var obj := {"uid": uid, "type": type, "x": x, "z": z, "rot": rot}
	var index := world.objects.size()
	world.objects.append(obj)
	_push_undo({"kind": "obj_add", "uid": uid, "obj": obj.duplicate(), "index": index, "bytes": OBJECT_ENTRY_BYTES})
	object_added.emit(uid)
	_mark_dirty()
	return uid


## 物の位置を変える。record_undo=false はドラッグ中(Undo に積まず、保存もストローク後まで待つ)。
## ドラッグを終えたら commit_move を呼ぶこと。
func update_object(uid: int, x: float, z: float, rot: float, record_undo := true) -> void:
	var i := _find_object(uid)
	if i < 0:
		return
	var o: Dictionary = world.objects[i]
	var before := {"x": o["x"], "z": o["z"], "rot": o["rot"]}
	o["x"] = x
	o["z"] = z
	o["rot"] = rot
	if record_undo:
		_push_undo({"kind": "obj_move", "uid": uid, "before": before,
			"after": {"x": x, "z": z, "rot": rot}, "bytes": OBJECT_ENTRY_BYTES})
	else:
		_drag_uid = uid
	object_changed.emit(uid)
	_mark_dirty()


## ドラッグ終了。from_* はドラッグ開始時の値。1件の Undo にまとめる。
func commit_move(uid: int, from_x: float, from_z: float, from_rot: float) -> void:
	if _drag_uid == uid:
		_drag_uid = -1
	var i := _find_object(uid)
	if i < 0:
		return
	var o: Dictionary = world.objects[i]
	var before := {"x": from_x, "z": from_z, "rot": from_rot}
	var after := {"x": o["x"], "z": o["z"], "rot": o["rot"]}
	if is_equal_approx(before["x"], after["x"]) and is_equal_approx(before["z"], after["z"]) \
			and is_equal_approx(before["rot"], after["rot"]):
		return
	_push_undo({"kind": "obj_move", "uid": uid, "before": before, "after": after, "bytes": OBJECT_ENTRY_BYTES})
	object_changed.emit(uid)
	_mark_dirty()


## 物を削除(Undo 1件)。
func remove_object(uid: int) -> void:
	if _drag_uid == uid:
		_drag_uid = -1   # ドラッグ中の物が消えたら、ドラッグ中のまま固まらないようにする
	var i := _find_object(uid)
	if i < 0:
		return
	var obj: Dictionary = world.objects[i].duplicate()
	world.objects.remove_at(i)
	_push_undo({"kind": "obj_remove", "uid": uid, "obj": obj, "index": i, "bytes": OBJECT_ENTRY_BYTES})
	object_removed.emit(uid)
	_mark_dirty()


## 環境の値(season, weather, time_flow など)を変える。時刻の毎フレーム進行は world.env["time"] へ直接書く。
func set_env(key: String, value) -> void:
	if world == null:
		return
	world.env[key] = value
	env_changed.emit()
	_mark_dirty()


func set_setting(key: String, value) -> void:
	if not settings.has(key):
		push_warning("未知の設定キー: %s" % key)
		return
	settings[key] = value
	_save_settings()
	settings_changed.emit()


## 地形・地表・森の1ストローク開始。変更前の全体を控える。layer は "height" "surface" "forest"。
func begin_stroke(layer: String) -> void:
	if world == null or _stroke_layer != "":
		if _stroke_layer != "":
			push_warning("ストロークが既に進行中です。")
		return
	if not (layer in ["height", "surface", "forest"]):
		push_error("未知の layer: %s" % layer)
		return
	_stroke_layer = layer
	_stroke_before = _layer_parts(layer)


## ストローク終了。rect の差分を Undo に積み、対応するシグナルを1回出す。rect が空なら何もしない。
func end_stroke(rect: Rect2i) -> void:
	if _stroke_layer == "":
		return
	var layer := _stroke_layer
	var before := _stroke_before
	_stroke_layer = ""
	_stroke_before = []
	var r := WorldData.clamp_rect(rect)
	if r.size == Vector2i.ZERO or before.is_empty():
		return
	var bpt := _layer_bpt(layer)
	var now := _layer_parts(layer)
	var before_rect: Array[PackedByteArray] = []
	var after_rect: Array[PackedByteArray] = []
	var changed := false
	for k in now.size():
		var b := _rect_read(before[k], bpt, r)
		var a := _rect_read(now[k], bpt, r)
		if b != a:
			changed = true
		before_rect.append(b)
		after_rect.append(a)
	if not changed:
		return
	var bytes := 0
	for p in before_rect:
		bytes += p.size()
	for p in after_rect:
		bytes += p.size()
	_push_undo({"kind": "patch", "layer": layer, "rect": r, "before": before_rect, "after": after_rect, "bytes": bytes})
	_emit_layer(layer, r)
	_mark_dirty()


func undo() -> void:
	if is_busy() or _undo.is_empty():
		return
	var e: Dictionary = _undo.pop_back()
	_apply(e, false)
	_redo.append(e)
	undo_changed.emit()
	_mark_dirty()


func redo() -> void:
	if is_busy() or _redo.is_empty():
		return
	var e: Dictionary = _redo.pop_back()
	_apply(e, true)
	_undo.append(e)
	undo_changed.emit()
	_mark_dirty()


func can_undo() -> bool:
	return not _undo.is_empty()


func can_redo() -> bool:
	return not _redo.is_empty()


# ---------------------------------------------------------------- 内部: 世界の差し替え・保存

func _set_world(w: WorldData) -> void:
	world = w
	_undo.clear()
	_redo.clear()
	_stroke_layer = ""
	_stroke_before = []
	_drag_uid = -1
	_dirty = false
	_ensure_timer().stop()
	undo_changed.emit()


func _mark_dirty() -> void:
	_dirty = true
	_ensure_timer().start(AUTOSAVE_DELAY)


func _on_autosave_timeout() -> void:
	if world == null or not _dirty:
		return
	if is_busy():
		_ensure_timer().start(RETRY_DELAY)
		return
	save_world()


func _world_path(id: String) -> String:
	return "%s/%s.json" % [WORLD_DIR, id]


func _new_id() -> String:
	return "w%d%04x" % [int(Time.get_unix_time_from_system()), randi() & 0xFFFF]


func _load_settings() -> void:
	if not FileAccess.file_exists(SETTINGS_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS_PATH))
	if not (data is Dictionary):
		push_warning("settings.json が壊れています。既定値を使います。")
		return
	var s = data.get("settings", {})
	if s is Dictionary:
		if s.has("quality"):
			settings["quality"] = clampi(int(s["quality"]), 0, 2)
		for k in ["snap", "invert_look", "sound"]:
			if s.has(k):
				settings[k] = bool(s[k])
	last_world_id = str(data.get("last_world", ""))


func _save_settings() -> void:
	var text := JSON.stringify({"settings": settings, "last_world": last_world_id})
	if not _write_atomic(SETTINGS_PATH, text):
		push_error("設定の保存に失敗")


## 一時ファイルに書いてから rename する。既存ファイルがあって rename できない環境では退避して差し替える。
static func _write_atomic(path: String, text: String) -> bool:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(text)
	f.close()
	if DirAccess.rename_absolute(tmp, path) == OK:
		return true
	var bak := path + ".bak"
	if FileAccess.file_exists(path):
		DirAccess.rename_absolute(path, bak)
	var err := DirAccess.rename_absolute(tmp, path)
	if err == OK:
		if FileAccess.file_exists(bak):
			DirAccess.remove_absolute(bak)
		return true
	if FileAccess.file_exists(bak):
		DirAccess.rename_absolute(bak, path)
	return false


# ---------------------------------------------------------------- 内部: 物・Undo

func _find_object(uid: int) -> int:
	if world == null:
		return -1
	for i in world.objects.size():
		if int(world.objects[i]["uid"]) == uid:
			return i
	return -1


func _push_undo(e: Dictionary) -> void:
	_undo.append(e)
	_redo.clear()
	_trim_undo()
	undo_changed.emit()


func _trim_undo() -> void:
	while _undo.size() > UNDO_LIMIT or _undo_bytes() > UNDO_BYTES_LIMIT:
		if _undo.is_empty():
			break
		_undo.pop_front()


func _undo_bytes() -> int:
	var total := 0
	for e in _undo:
		total += int(e.get("bytes", 0))
	return total


func _apply(e: Dictionary, forward: bool) -> void:
	match e["kind"]:
		"patch":
			_apply_patch(e, forward)
		"obj_add":
			# 追加の取り消しは削除、やり直しは同じ uid・位置へ戻す
			if forward:
				world.objects.insert(mini(int(e["index"]), world.objects.size()), e["obj"].duplicate())
				object_added.emit(int(e["uid"]))
			else:
				var i := _find_object(int(e["uid"]))
				if i >= 0:
					world.objects.remove_at(i)
				object_removed.emit(int(e["uid"]))
		"obj_remove":
			if forward:
				var i := _find_object(int(e["uid"]))
				if i >= 0:
					world.objects.remove_at(i)
				object_removed.emit(int(e["uid"]))
			else:
				world.objects.insert(mini(int(e["index"]), world.objects.size()), e["obj"].duplicate())
				object_added.emit(int(e["uid"]))
		"obj_move":
			var j := _find_object(int(e["uid"]))
			if j >= 0:
				var v: Dictionary = e["after"] if forward else e["before"]
				var o: Dictionary = world.objects[j]
				o["x"] = v["x"]
				o["z"] = v["z"]
				o["rot"] = v["rot"]
				object_changed.emit(int(e["uid"]))
		_:
			push_error("未知の Undo 種別: %s" % e["kind"])


func _apply_patch(e: Dictionary, forward: bool) -> void:
	var layer: String = e["layer"]
	var r: Rect2i = e["rect"]
	var data: Array = e["after"] if forward else e["before"]
	var bpt := _layer_bpt(layer)
	match layer:
		"height":
			var b := world.heights.to_byte_array()
			b = _rect_write(b, bpt, r, data[0])
			world.heights = b.to_float32_array()
		"surface":
			world.splat_a = _rect_write(world.splat_a, bpt, r, data[0])
			world.splat_b = _rect_write(world.splat_b, bpt, r, data[1])
		"forest":
			world.forest = _rect_write(world.forest, bpt, r, data[0])
	_emit_layer(layer, r)


func _emit_layer(layer: String, r: Rect2i) -> void:
	match layer:
		"height":
			terrain_changed.emit(r)
		"surface":
			surface_changed.emit(r)
		"forest":
			forest_changed.emit(r)


## レイヤーの配列(コピー)。height は float のバイト列、surface は splat_a / splat_b、forest は1バイト。
func _layer_parts(layer: String) -> Array[PackedByteArray]:
	match layer:
		"height":
			return [world.heights.to_byte_array()]
		"surface":
			return [world.splat_a.duplicate(), world.splat_b.duplicate()]
	return [world.forest.duplicate()]


func _layer_bpt(layer: String) -> int:
	return 1 if layer == "forest" else 4


## 頂点 index の矩形 r(position 以上 position+size 未満)のバイトを取り出す。
static func _rect_read(src: PackedByteArray, bpt: int, r: Rect2i) -> PackedByteArray:
	var out := PackedByteArray()
	var row_len := r.size.x * bpt
	for row in r.size.y:
		var start := ((r.position.y + row) * WorldData.N + r.position.x) * bpt
		out.append_array(src.slice(start, start + row_len))
	return out


static func _rect_write(dst: PackedByteArray, bpt: int, r: Rect2i, data: PackedByteArray) -> PackedByteArray:
	var row_len := r.size.x * bpt
	for row in r.size.y:
		var start := ((r.position.y + row) * WorldData.N + r.position.x) * bpt
		var src_start := row * row_len
		for k in row_len:
			dst[start + k] = data[src_start + k]
	return dst


# ---------------------------------------------------------------- 内部: 世界の生成

func _gen_hills(w: WorldData) -> void:
	var noise := FastNoiseLite.new()
	noise.seed = w.seed
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.012
	noise.fractal_octaves = 4
	var mountain_noise := FastNoiseLite.new()
	mountain_noise.seed = w.seed + 1
	mountain_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	mountain_noise.frequency = 0.02
	w.reset_terrain(PLATEAU_HEIGHT)
	for iz in WorldData.N:
		for ix in WorldData.N:
			var x := float(ix) - WorldData.HALF
			var z := float(iz) - WorldData.HALF
			var dist := Vector2(x, z).length()
			var h := PLATEAU_HEIGHT + noise.get_noise_2d(x, z) * 5.0
			# 中央付近は平ら
			h = lerpf(PLATEAU_HEIGHT, h, smoothstep(30.0, 60.0, dist))
			# 周囲は少し高い山
			var m := 0.5 + 0.5 * mountain_noise.get_noise_2d(x, z)
			h += smoothstep(70.0, 125.0, dist) * (16.0 + 6.0 * m)
			# 南北に流れる浅い川
			var d := absf(x - _river_x(z))
			var t := smoothstep(0.0, 1.0, clampf(1.0 - maxf(d - RIVER_BED_HALF, 0.0) / RIVER_BANK_W, 0.0, 1.0))
			h = lerpf(h, RIVER_BED, t)
			w.heights[WorldData.idx(ix, iz)] = clampf(h, WorldData.H_MIN, WorldData.H_MAX)
	_smooth_river_banks(w)


static func _river_x(z: float) -> float:
	return RIVER_X + RIVER_AMP * sin(z * RIVER_FREQ)


## 川べりを数回ぼかして、1m格子の段々を消す(川の縁の外側 RIVER_SMOOTH_MARGIN までの帯だけ)。
## 3x3 の箱ぼかしを RIVER_SMOOTH_PASSES 回。各回は前の回の値を読んで書くので、向きによる偏りが出ない。
## 川底の中心(RIVER_PIN まで)は固定し、ぼかしで持ち上げない(川が消えないように)。
static func _smooth_river_banks(w: WorldData) -> void:
	var reach := RIVER_HALF_WIDTH + RIVER_SMOOTH_MARGIN
	var n := WorldData.N
	for _pass in RIVER_SMOOTH_PASSES:
		var src := w.heights.duplicate()
		for iz in range(1, n - 1):
			var z := float(iz) - WorldData.HALF
			var cx := _river_x(z)
			var ix0 := clampi(int(floor(cx - reach + WorldData.HALF)), 1, n - 2)
			var ix1 := clampi(int(ceil(cx + reach + WorldData.HALF)), 1, n - 2)
			for ix in range(ix0, ix1 + 1):
				var k := WorldData.idx(ix, iz)
				if absf(float(ix) - WorldData.HALF - cx) < RIVER_PIN:
					continue
				var sum := 0.0
				for dz in [-1, 0, 1]:
					for dx in [-1, 0, 1]:
						sum += src[WorldData.idx(ix + dx, iz + dz)]
				w.heights[k] = sum / 9.0


## 見本の神社・家・畑・川の橋などを置く(hills の地形の上に)。Undo・シグナルは使わない。
func _build_sample(w: WorldData) -> void:
	# 1. 建物の下を整地
	var flatten_list := [
		["haiden", Vector2(0, -30), 0.0],
		["honden", Vector2(0, -42), 0.0],
		["shamusho", Vector2(13, -30), 0.0],
		["chozuya", Vector2(-7, 6), PI * 0.5],
		["ie_kawara", Vector2(26, 6), 0.0],
		["ie_kayabuki", Vector2(32, -14), 0.0],
	]
	for f in flatten_list:
		_flatten_under(w, Geom.to_world(Catalog.footprint_polygon(f[0]), f[1], f[2]), 1.5)

	# 2. 地表: 境内は白砂、参道は石畳、川べりは砂利、畑は畑。縁は境界の両側で少しずつ混ぜる(地表の境目はグラデーション)
	_paint(w, 5, Rect2(-14, -50, 28, 30), 1.0, func(p: Vector2) -> bool: return p.y >= -50 and p.y <= -20 and absf(p.x) <= 14.0)
	_paint(w, 3, Rect2(-1.5, -26, 3, 56), 0.5, func(p: Vector2) -> bool: return absf(p.x) <= 1.5 and p.y >= -26.0 and p.y <= 30.0)
	_paint(w, 2, Rect2(-50, -128, 30, 256), 1.0, func(p: Vector2) -> bool:
		var d := absf(p.x - _river_x(p.y))
		return d >= RIVER_HALF_WIDTH and d <= RIVER_HALF_WIDTH + 3.0)
	_paint(w, 6, Rect2(12, 16, 28, 14), 1.0, func(p: Vector2) -> bool: return p.x >= 12.0 and p.x <= 40.0 and p.y >= 16.0 and p.y <= 30.0)

	# 3. 森: 神社と集落の周りの外側
	for iz in WorldData.N:
		for ix in WorldData.N:
			var p := Vector2(float(ix) - WorldData.HALF, float(iz) - WorldData.HALF)
			if p.distance_to(SHRINE_CENTER) >= FOREST_RADIUS:
				w.forest[WorldData.idx(ix, iz)] = 255

	# 4. 配置物(内部用の追加。Undo には積まない)
	_raw_add(w, "torii", 0.0, 22.0, 0.0)
	for z in [12.0, 2.0, -8.0]:
		_raw_add(w, "toro", -2.6, z, 0.0)
		_raw_add(w, "toro", 2.6, z, 0.0)
	_raw_add(w, "chozuya", -7.0, 6.0, PI * 0.5)
	# 石段は拝殿の正面(+Z 側)に 0.2m 空けて置く(拝殿の占有領域 z ∈ [-35.4, -24.6] と重ならない)
	_raw_add(w, "ishidan", 0.0, -22.9, 0.0)
	_raw_add(w, "komainu_a", 3.4, -23.0, 0.0)
	_raw_add(w, "komainu_un", -3.4, -23.0, 0.0)
	_raw_add(w, "haiden", 0.0, -30.0, 0.0)
	_raw_add(w, "honden", 0.0, -42.0, 0.0)
	_raw_add(w, "tamagaki", -4.0, -48.0, 0.0)
	_raw_add(w, "tamagaki", 0.0, -48.0, 0.0)
	_raw_add(w, "tamagaki", 4.0, -48.0, 0.0)
	_raw_add(w, "tamagaki", -6.0, -44.0, PI * 0.5)
	_raw_add(w, "tamagaki", -6.0, -40.0, PI * 0.5)
	_raw_add(w, "tamagaki", 6.0, -44.0, PI * 0.5)
	_raw_add(w, "tamagaki", 6.0, -40.0, PI * 0.5)
	_raw_add(w, "shamusho", 13.0, -30.0, 0.0)
	_raw_add(w, "ie_kawara", 26.0, 6.0, 0.0)
	_raw_add(w, "ie_kayabuki", 32.0, -14.0, 0.0)
	_raw_add(w, "denchu", 18.0, 2.0, 0.0)
	_raw_add(w, "denchu", -30.0, 16.0, 0.0)
	_raw_add(w, "hashi", RIVER_X, 0.0, 0.0)
	_raw_add(w, "jizo", -26.0, -4.0, 0.0)
	_raw_add(w, "iwa_l", -24.0, 24.0, 0.7)
	_raw_add(w, "iwa_s", -21.0, 28.0, 0.2)
	_raw_add(w, "sakura", -18.0, -54.0, 0.0)
	_raw_add(w, "kaede", 18.0, -54.0, 0.0)


func _raw_add(w: WorldData, type: String, x: float, z: float, rot: float) -> void:
	w.objects.append({"uid": w.next_uid, "type": type, "x": x, "z": z, "rot": rot})
	w.next_uid += 1


## 建物の占有領域を中心の高さで整地する(縁は margin m でなだらかに)。
func _flatten_under(w: WorldData, poly: PackedVector2Array, margin: float) -> void:
	var lo := poly[0]
	var hi := poly[0]
	var center := Vector2.ZERO
	for p in poly:
		lo = lo.min(p)
		hi = hi.max(p)
		center += p
	center /= poly.size()
	var target := w.height_at(center.x, center.y)
	var x0 := clampi(int(floor(lo.x - margin + WorldData.HALF)), 0, WorldData.N - 1)
	var x1 := clampi(int(ceil(hi.x + margin + WorldData.HALF)), 0, WorldData.N - 1)
	var z0 := clampi(int(floor(lo.y - margin + WorldData.HALF)), 0, WorldData.N - 1)
	var z1 := clampi(int(ceil(hi.y + margin + WorldData.HALF)), 0, WorldData.N - 1)
	for iz in range(z0, z1 + 1):
		for ix in range(x0, x1 + 1):
			var p := Vector2(float(ix) - WorldData.HALF, float(iz) - WorldData.HALF)
			var d := _dist_to_poly(p, poly)
			if d > margin:
				continue
			var k := WorldData.idx(ix, iz)
			var weight := 1.0 - smoothstep(0.0, margin, d)
			w.heights[k] = lerpf(w.heights[k], target, weight)


## 地表 type を inside の内側に塗る。bbox は範囲の目安、inside は点の判定。
## feather(m)>0 のときは境界の両側 feather 幅で混ぜる(周りの標本のうち内側の割合を、その種の重みにする)。
func _paint(w: WorldData, type_id: int, bbox: Rect2, feather: float, inside: Callable) -> void:
	var box := bbox.grow(feather + 0.5) if feather > 0.0 else bbox
	var x0 := clampi(int(floor(box.position.x + WorldData.HALF)), 0, WorldData.N - 1)
	var x1 := clampi(int(ceil(box.end.x + WorldData.HALF)), 0, WorldData.N - 1)
	var z0 := clampi(int(floor(box.position.y + WorldData.HALF)), 0, WorldData.N - 1)
	var z1 := clampi(int(ceil(box.end.y + WorldData.HALF)), 0, WorldData.N - 1)
	for iz in range(z0, z1 + 1):
		for ix in range(x0, x1 + 1):
			var p := Vector2(float(ix) - WorldData.HALF, float(iz) - WorldData.HALF)
			if feather <= 0.0:
				if inside.call(p):
					w.set_surface_hard(ix, iz, type_id)
				continue
			var t := _inside_fraction(p, feather, inside)
			if t > 0.0:
				_blend_surface(w, ix, iz, type_id, t)


## 中心と、その周りの PAINT_SOFT_SAMPLES 方向(半径 f)のうち、内側の割合(0〜1)。
func _inside_fraction(p: Vector2, f: float, inside: Callable) -> float:
	var hits := 1 if inside.call(p) else 0
	for k in PAINT_SOFT_SAMPLES:
		var a := TAU * float(k) / float(PAINT_SOFT_SAMPLES)
		if inside.call(p + Vector2(cos(a), sin(a)) * f):
			hits += 1
	return float(hits) / float(PAINT_SOFT_SAMPLES + 1)


## 頂点の地表の重みを、type を t(0-1)だけ混ぜた値にする。他の種は (1-t) 倍。合計は 255 を超えない。
static func _blend_surface(w: WorldData, ix: int, iz: int, type_id: int, t: float) -> void:
	if t >= 1.0:
		w.set_surface_hard(ix, iz, type_id)
		return
	var total := 0
	for k in range(1, WorldData.SURFACE_COUNT):
		var v := (1.0 - t) * float(w.get_surface_weight(ix, iz, k))
		if k == type_id:
			v += t * 255.0
		var iv := mini(roundi(v), 255 - total)
		total += iv
		_write_weight(w, ix, iz, k, iv)


static func _write_weight(w: WorldData, ix: int, iz: int, type_id: int, v: int) -> void:
	var i := WorldData.idx(ix, iz) * 4
	if type_id <= 4:
		w.splat_a[i + type_id - 1] = v
	else:
		w.splat_b[i + type_id - 5] = v


static func _dist_to_poly(p: Vector2, poly: PackedVector2Array) -> float:
	if Geom.point_in_polygon(p, poly):
		return 0.0
	var best := INF
	var n := poly.size()
	for i in n:
		best = minf(best, _dist_to_segment(p, poly[i], poly[(i + 1) % n]))
	return best


static func _dist_to_segment(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var len2 := ab.dot(ab)
	if len2 < 1e-9:
		return p.distance_to(a)
	var t := clampf((p - a).dot(ab) / len2, 0.0, 1.0)
	return p.distance_to(a + ab * t)
