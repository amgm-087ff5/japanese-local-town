## 配置モード(architecture.md 11章・15.3)。class_name EditMode。
##
## タッチの担当は指を置いた瞬間に決める(_on_pressed):
##   仮置き中の物・選択中の物の上 → 物のドラッグ(移動)。それ以外 → カメラ(CameraRig.handle_input へ渡す)。
##   2本目の指が来たら、物のドラッグは取り消して元の位置へ戻し、以後の指はすべてカメラ。
##   タップ(短時間・動かさない): 物 → 選択 / 空き地 → 選択解除(仮置き中は仮置きをそこへ移す)。
## マウス左は emulate_touch_from_mouse でタッチとしても届くので無視する。右ドラッグ・ホイールはカメラへ。
##
## 仮置き(ghost)は Game に入れず自前で保持する。選択中の物だけ Game.update_object / commit_move を使う。
## ドラッグ中は重い処理をしない: 他の物の占有領域はドラッグ開始時に1回だけ取得してキャッシュする。
class_name EditMode
extends Node

signal selection_changed
signal placing_changed

const WORLD_LIMIT := 126.0
const TAP_MS := 300
const TAP_PX := 18.0
const SELECT_PX := 40.0          # 仮置き・選択中の物の中心を画面でこの距離内なら当たりとみなす
const FLOOR_LIFT := 0.15         # 枠の各頂点を、その点の地形の高さからこの高さ上に置く(傾いた地面で潜らない)
const LINE_H := 0.1
const SNAP_MIN := 0.6
const SNAP_MAX := 2.5
const GHOST_TRANSPARENCY := 0.5
const DEFAULT_DISTANCE := 60.0

const OWNER_CAMERA := 0
const OWNER_OBJECT := 1

var selected_uid: int = -1
var placing_type: String = ""
var continuous: bool = true      # 確定後も同じ種類の仮置きを続ける

# 仮置きまたは選択中の物の現在の姿勢(仮置きの authority は自分。選択中は Game と同期)
var _subj_pos := Vector2.ZERO
var _subj_rot := 0.0
var _subj_type := ""
var _snapped := false
var _edge_a := Vector2.ZERO
var _edge_b := Vector2.ZERO

var _ghost: Node3D = null
var _visuals: Node3D
var _frame: MeshInstance3D
var _snap_line: MeshInstance3D
var _unit_box: BoxMesh
var _mat_cream: StandardMaterial3D
var _mat_ghost: StandardMaterial3D
var _mat_bad: StandardMaterial3D
var _mat_snap: StandardMaterial3D

# ドラッグ開始時に1回だけ取る他の物の占有領域(ワールド座標)
var _others_all: Array = []      # スナップ用(all_footprints 相当。自分を除く)
var _others_solid: Array = []    # 重なり判定用(木以外。自分を除く)

var _touches: Dictionary = {}    # index -> {owner, start, pos, ms, tap, tap_uid, multi}
var _drag_active := false
var _drag_index := -1
var _drag_offset := Vector2.ZERO
var _drag_from := Vector3.ZERO   # x, z, rot(ドラッグ開始時の値。commit / 取り消しに使う)


func _ready() -> void:
	_visuals = Node3D.new()
	_visuals.name = "EditVisuals"
	add_child(_visuals)
	_frame = MeshInstance3D.new()
	_frame.name = "Frame"
	_frame.visible = false
	_frame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_visuals.add_child(_frame)
	_unit_box = BoxMesh.new()
	_unit_box.size = Vector3.ONE
	_mat_cream = _make_material(Color(0.96, 0.93, 0.85))
	_mat_ghost = _make_material(Color(0.25, 0.42, 0.31))
	_mat_bad = _make_material(Color(0.85, 0.15, 0.12))
	_mat_snap = _make_material(Color(0.78, 0.27, 0.17))
	_snap_line = MeshInstance3D.new()
	_snap_line.name = "SnapLine"
	_snap_line.mesh = _unit_box
	_snap_line.material_override = _mat_snap
	_snap_line.visible = false
	_visuals.add_child(_snap_line)
	Game.object_added.connect(_on_object_added)
	Game.object_changed.connect(_on_object_changed)
	Game.object_removed.connect(_on_object_removed)
	Game.mode_changed.connect(_on_mode_changed)


## 種類 type の仮置きを始める。画面中央の地面に置く。選択は解除する。
func start_placing(type: String) -> void:
	if Catalog.get_item(type).is_empty():
		push_warning("未知の種類: %s" % type)
		return
	_end_drag(false)
	_drop_ghost()
	if selected_uid >= 0:
		_set_selected(-1)
	placing_type = type
	_subj_type = type
	_subj_pos = _center_xz()
	_subj_rot = 0.0
	_snapped = false
	_ghost = _make_ghost(type)
	_visuals.add_child(_ghost)
	_refresh_others()
	_refresh_visuals()
	placing_changed.emit()


## 仮置きを確定する。continuous なら同じ種類の仮置きを画面中央に続ける。そうでなければ確定した物を選択する。
## 選択中(仮置き無し)で呼ぶと選択を解除する。
func confirm() -> void:
	if placing_type == "":
		if selected_uid >= 0:
			select_object(-1)
		return
	_end_drag(true)
	var type := placing_type
	var uid := Game.add_object(type, _subj_pos.x, _subj_pos.y, _subj_rot)
	if uid < 0:
		return
	if continuous:
		start_placing(type)
	else:
		_drop_ghost()
		placing_changed.emit()
		select_object(uid)


## 仮置き・選択・ドラッグを解除する。
func cancel() -> void:
	_end_drag(false)
	var was_placing := placing_type != ""
	_drop_ghost()
	_snapped = false
	if was_placing:
		placing_changed.emit()
	if selected_uid >= 0:
		_set_selected(-1)
	_refresh_visuals()


## 物を選ぶ(-1 で解除)。仮置きがあれば取り消す。
func select_object(uid: int) -> void:
	if uid >= 0 and Game.get_object(uid).is_empty():
		return
	_end_drag(false)
	if placing_type != "":
		_drop_ghost()
		placing_changed.emit()
	_set_selected(uid)


## 仮置き・選択中の物の現在の姿勢(テスト・画面確認用)。
func get_subject_pose() -> Dictionary:
	return {"pos": _subj_pos, "rot": _subj_rot, "uid": selected_uid, "type": _subj_type, "placing": placing_type}


## 回転。step_deg は度(UI は ±15)。吸着中は 90° 刻みで基準辺と平行を保つ。
func rotate_selected(step_deg: float) -> void:
	if not _has_subject() or is_zero_approx(step_deg):
		return
	var snapping := _snapped and _snap_enabled()
	var step := deg_to_rad(step_deg)
	if snapping:
		step = signf(step_deg) * PI * 0.5
	var new_rot := _subj_rot + step
	var pos := _subj_pos
	_snapped = false
	if snapping:
		var res := _solve_pose(pos, new_rot)
		if res["snapped"]:
			pos = res["pos"]
			new_rot = float(res["rot"])
			_snapped = true
			_edge_a = res["a"]
			_edge_b = res["b"]
	pos = _clamp_xz(pos)
	_subj_pos = pos
	_subj_rot = new_rot
	if selected_uid >= 0:
		Game.update_object(selected_uid, pos.x, pos.y, new_rot, true)
	_refresh_visuals()


## 選択中の物を、占有領域の幅ぶん自分の右(ローカル +X)にずらして複製し、複製を選択する。
func duplicate_selected() -> void:
	if selected_uid < 0:
		return
	var o := Game.get_object(selected_uid)
	if o.is_empty():
		return
	var type := str(o["type"])
	var rot := float(o["rot"])
	var width := _footprint_size(type).x
	var dir := Vector2(cos(rot), -sin(rot))
	var np := _clamp_xz(Vector2(float(o["x"]), float(o["z"])) + dir * width)
	var uid := Game.add_object(type, np.x, np.y, rot)
	if uid >= 0:
		select_object(uid)


## 選択中の物(仮置き中は仮置き)を削除する。仮置き中は仮置きを取り消す。
func delete_selected() -> void:
	if placing_type != "":
		cancel()
		return
	if selected_uid < 0:
		return
	var uid := selected_uid
	_end_drag(false)
	_set_selected(-1)
	Game.remove_object(uid)


## 占有領域を中心の高さで整地する(1ストローク・Undo 1件)。
func flatten_selected() -> void:
	if not _has_subject():
		return
	var t := _terrain()
	if t == null:
		return
	var poly := Geom.to_world(Catalog.footprint_polygon(_subj_type), _subj_pos, _subj_rot)
	Game.begin_stroke("height")
	var rect: Rect2i = t.flatten_polygon(poly, 1.5)
	Game.end_stroke(rect)
	_refresh_visuals()


# ---------------------------------------------------------------- 入力

func _unhandled_input(event: InputEvent) -> void:
	if Game.mode != "edit":
		return
	if event is InputEventScreenTouch:
		_on_touch(event as InputEventScreenTouch)
		get_viewport().set_input_as_handled()
	elif event is InputEventScreenDrag:
		if _on_drag(event as InputEventScreenDrag):
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			return
		var rig := _rig()
		if rig != null and rig.handle_input(event):
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		var rig2 := _rig()
		if (mm.button_mask & MOUSE_BUTTON_MASK_RIGHT) != 0 and rig2 != null and rig2.handle_input(event):
			get_viewport().set_input_as_handled()


func _on_touch(ev: InputEventScreenTouch) -> void:
	if ev.pressed:
		_on_pressed(ev)
	else:
		_on_released(ev)


func _on_pressed(ev: InputEventScreenTouch) -> void:
	var idx := ev.index
	var p := ev.position
	if not _touches.is_empty():
		# 2本目以降の指: 物のドラッグを取り消し、以後はカメラ
		_hand_over_to_camera()
		_touches[idx] = _new_touch(OWNER_CAMERA, p, true)
		_rig_input(ev)
		return
	var hit := _hit_test(p)
	if hit["kind"] == "subject":
		_touches[idx] = _new_touch(OWNER_OBJECT, p, false)
		_begin_drag(idx, p)
		return
	var t := _new_touch(OWNER_CAMERA, p, false)
	t["tap_uid"] = int(hit["uid"])
	_touches[idx] = t
	_rig_input(ev)


func _on_released(ev: InputEventScreenTouch) -> void:
	var idx := ev.index
	if not _touches.has(idx):
		return
	var t: Dictionary = _touches[idx]
	_touches.erase(idx)
	match int(t["owner"]):
		OWNER_OBJECT:
			if _drag_active and idx == _drag_index:
				_end_drag(true)
		OWNER_CAMERA:
			_rig_input(ev)
			var moved := (ev.position - (t["start"] as Vector2)).length()
			var quick := Time.get_ticks_msec() - int(t["ms"]) <= TAP_MS
			if bool(t["tap"]) and quick and moved <= TAP_PX:
				_on_tap(t["start"], int(t["tap_uid"]))


func _on_drag(ev: InputEventScreenDrag) -> bool:
	var idx := ev.index
	if not _touches.has(idx):
		return false
	var t: Dictionary = _touches[idx]
	t["pos"] = ev.position
	if (ev.position - (t["start"] as Vector2)).length() > TAP_PX:
		t["tap"] = false
	match int(t["owner"]):
		OWNER_OBJECT:
			if _drag_active and idx == _drag_index:
				_drag_to(ev.position)
			return true
		OWNER_CAMERA:
			_rig_input(ev)
			return true
	return true


func _new_touch(owner: int, p: Vector2, multi: bool) -> Dictionary:
	return {"owner": owner, "start": p, "pos": p, "ms": Time.get_ticks_msec(),
		"tap": not multi, "tap_uid": -1, "multi": multi}


## 2本目の指が来た: 物のドラッグを取り消し(元の位置へ)、物の担当だった指をカメラへ渡す。
func _hand_over_to_camera() -> void:
	var rig := _rig()
	for idx in _touches.keys():
		var t: Dictionary = _touches[idx]
		t["multi"] = true
		t["tap"] = false
		if int(t["owner"]) == OWNER_OBJECT:
			t["owner"] = OWNER_CAMERA
			if rig != null:
				var press := InputEventScreenTouch.new()
				press.index = int(idx)
				press.position = t["pos"]
				press.pressed = true
				rig.handle_input(press)
	_end_drag(false)


func _rig_input(ev: InputEvent) -> void:
	var rig := _rig()
	if rig != null:
		rig.handle_input(ev)


## タップ: 物なら選択。空き地なら仮置きをそこへ移す(仮置き中)か、選択を解除する。
func _on_tap(p: Vector2, tap_uid: int) -> void:
	if tap_uid >= 0:
		select_object(tap_uid)
		return
	if placing_type != "":
		var g = _ground_at(p)
		if g != null:
			_subj_pos = _clamp_xz(Vector2(g.x, g.z))
			_snapped = false
			_refresh_visuals()
		return
	if selected_uid >= 0:
		select_object(-1)


# ---------------------------------------------------------------- 物のドラッグ

func _begin_drag(idx: int, p: Vector2) -> void:
	_drag_active = true
	_drag_index = idx
	_refresh_others()
	var g = _ground_at(p)
	_drag_offset = Vector2.ZERO
	if g != null:
		_drag_offset = Vector2(g.x, g.z) - _subj_pos
	_drag_from = Vector3(_subj_pos.x, _subj_pos.y, _subj_rot)


func _drag_to(p: Vector2) -> void:
	var g = _ground_at(p)
	if g == null:
		return
	var raw := Vector2(g.x, g.z) - _drag_offset
	var res := _solve_pose(raw, _subj_rot)
	_subj_pos = _clamp_xz(res["pos"])
	_subj_rot = float(res["rot"])
	_snapped = bool(res["snapped"])
	if _snapped:
		_edge_a = res["a"]
		_edge_b = res["b"]
	if selected_uid >= 0:
		Game.update_object(selected_uid, _subj_pos.x, _subj_pos.y, _subj_rot, false)
	_refresh_visuals()


## ドラッグを終える。commit=true なら確定(選択中の物は Undo 1件)。false なら開始時の位置へ戻す。
func _end_drag(commit: bool) -> void:
	if not _drag_active:
		return
	_drag_active = false
	_drag_index = -1
	var fx := _drag_from.x
	var fz := _drag_from.y
	var fr := _drag_from.z
	if not commit:
		_subj_pos = Vector2(fx, fz)
		_subj_rot = fr
		_snapped = false
		if selected_uid >= 0:
			Game.update_object(selected_uid, fx, fz, fr, false)
	if selected_uid >= 0:
		Game.commit_move(selected_uid, fx, fz, fr)
		_load_subject()
	_refresh_visuals()


# ---------------------------------------------------------------- 当たり判定

func _hit_test(p: Vector2) -> Dictionary:
	var g = _ground_at(p)
	if _has_subject() and _hit_subject(p, g):
		return {"kind": "subject", "uid": -1}
	var uid := _pick_object(p, g)
	if uid >= 0:
		return {"kind": "object", "uid": uid}
	return {"kind": "none", "uid": -1}


func _hit_subject(p: Vector2, g: Variant) -> bool:
	var poly := Geom.to_world(Catalog.footprint_polygon(_subj_type), _subj_pos, _subj_rot)
	if g != null and Geom.point_in_polygon(Vector2(g.x, g.z), poly):
		return true
	var rig := _rig()
	if rig == null or rig.camera == null:
		return false
	var c3 := Vector3(_subj_pos.x, _ground_y(_subj_pos), _subj_pos.y)
	if rig.camera.is_position_behind(c3):
		return false
	return rig.camera.unproject_position(c3).distance_to(p) <= SELECT_PX


## 物の当たり。ObjectLayer.pick を優先し、無ければ(-1 が返れば)地面の点が占有領域に入るかで探す。
func _pick_object(p: Vector2, g: Variant) -> int:
	var m := _main()
	var ol = m.get("objects") if m != null else null
	var rig := _rig()
	if ol != null and rig != null and ol.has_method("pick"):
		var uid := int(ol.pick(rig.camera, p))
		if uid >= 0:
			return uid
	if g == null or Game.world == null:
		return -1
	var gp := Vector2(g.x, g.z)
	for i in range(Game.world.objects.size() - 1, -1, -1):
		var obj: Dictionary = Game.world.objects[i]
		var poly := Geom.to_world(Catalog.footprint_polygon(str(obj["type"])),
			Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))
		if Geom.point_in_polygon(gp, poly):
			return int(obj["uid"])
	return -1


# ---------------------------------------------------------------- スナップ・重なり

## 姿勢の解決: スナップ(設定 on・木以外)なら吸着先を使う。戻り値 {pos, rot, snapped, a, b}。
func _solve_pose(raw: Vector2, rot: float) -> Dictionary:
	var result := {"pos": raw, "rot": rot, "snapped": false, "a": Vector2.ZERO, "b": Vector2.ZERO}
	if not _snap_enabled():
		return result
	var r := Geom.compute_snap(Catalog.footprint_polygon(_subj_type), raw, rot, _others_all, _snap_threshold())
	if bool(r["snapped"]):
		result["pos"] = r["pos"]
		result["rot"] = float(r["rot"])
		result["snapped"] = true
		result["a"] = r["edge_from"]
		result["b"] = r["edge_to"]
	return result


func _snap_enabled() -> bool:
	return bool(Game.settings.get("snap", true)) and not _is_tree(_subj_type)


## 吸着距離: カメラが近いほど細かく(0.6〜2.5m)。
func _snap_threshold() -> float:
	var d := _camera_distance()
	return clampf(SNAP_MIN + (d - 10.0) * (SNAP_MAX - SNAP_MIN) / 140.0, SNAP_MIN, SNAP_MAX)


func _overlaps_solid(poly: PackedVector2Array) -> bool:
	for other in _others_solid:
		var o: PackedVector2Array = other
		if Geom.polygons_overlap(poly, o):
			return true
	return false


## 他の物の占有領域を取り直す(開始時・確定時・変更時。毎フレームは呼ばない)。
func _refresh_others() -> void:
	var exclude := selected_uid
	_others_all = []
	_others_solid = []
	if Game.world == null:
		return
	var m := _main()
	var ol = m.get("objects") if m != null else null
	var use_layer: bool = ol != null and ol.has_method("all_footprints")
	if use_layer:
		_others_all = ol.all_footprints(exclude)
	for obj in Game.world.objects:
		var uid := int(obj["uid"])
		if uid == exclude:
			continue
		var type := str(obj["type"])
		var poly := Geom.to_world(Catalog.footprint_polygon(type),
			Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))
		if not use_layer:
			_others_all.append(poly)
		if not _is_tree(type):
			_others_solid.append(poly)


# ---------------------------------------------------------------- 選択・仮置きの状態

func _set_selected(uid: int) -> void:
	if selected_uid == uid:
		return
	if selected_uid >= 0:
		_set_highlight(selected_uid, false)
	selected_uid = uid
	_snapped = false
	if uid >= 0:
		_set_highlight(uid, true)
		_load_subject()
		_refresh_others()
	selection_changed.emit()
	_refresh_visuals()


## 選択中の物の姿勢を Game から読み直す。
func _load_subject() -> void:
	var o := Game.get_object(selected_uid)
	if o.is_empty():
		selected_uid = -1
		return
	_subj_type = str(o["type"])
	_subj_pos = Vector2(float(o["x"]), float(o["z"]))
	_subj_rot = float(o["rot"])


func _has_subject() -> bool:
	return placing_type != "" or selected_uid >= 0


func _drop_ghost() -> void:
	if _ghost != null:
		_ghost.queue_free()
		_ghost = null
	placing_type = ""


func _make_ghost(type: String) -> Node3D:
	var m := _main()
	var ol = m.get("objects") if m != null else null
	var node: Node3D = null
	if ol != null and ol.has_method("make_ghost"):
		node = ol.make_ghost(type)
	if node == null:
		node = Catalog.instantiate(type)
		_set_transparency(node, GHOST_TRANSPARENCY)
	# 枠は EditMode が傾きに合わせて作る。ObjectLayer の平らな枠は二重になるので外す
	var flat := node.get_node_or_null("Frame")
	if flat != null:
		node.remove_child(flat)
		flat.free()
	return node


func _set_transparency(n: Node, a: float) -> void:
	if n is GeometryInstance3D:
		(n as GeometryInstance3D).transparency = a
	for c in n.get_children():
		_set_transparency(c, a)


## 枠・仮置き・吸着線の見た目を現在の姿勢に合わせる。
func _refresh_visuals() -> void:
	var has := _has_subject()
	_frame.visible = has
	if not has:
		_snap_line.visible = false
		return
	var gy := _ground_y(_subj_pos)
	var w := clampf(_camera_distance() * 0.0025, 0.12, 0.5)
	_frame.position = Vector3(_subj_pos.x, gy, _subj_pos.y)
	_frame.rotation.y = _subj_rot
	_frame.mesh = ObjectLayer.outline_mesh(Catalog.footprint_polygon(_subj_type), _frame_height_fn(gy), w)
	var poly := Geom.to_world(Catalog.footprint_polygon(_subj_type), _subj_pos, _subj_rot)
	var overlap := _overlaps_solid(poly)
	var mat := _mat_cream
	if overlap:
		mat = _mat_bad
	elif placing_type != "":
		mat = _mat_ghost
	_frame.material_override = mat
	if _ghost != null:
		_ghost.position = Vector3(_subj_pos.x, gy, _subj_pos.y)
		_ghost.rotation.y = _subj_rot
	_update_snap_line(gy, w)


## 枠の頂点の高さ: 頂点の地形の高さ+FLOOR_LIFT(_frame の原点の高さ gy からの差で返す)。
func _frame_height_fn(gy: float) -> Callable:
	return func(p: Vector2) -> float:
		var g := Geom.to_world(PackedVector2Array([p]), _subj_pos, _subj_rot)[0]
		return _ground_y(g) - gy + FLOOR_LIFT


func _update_snap_line(gy: float, w: float) -> void:
	if not _snapped:
		_snap_line.visible = false
		return
	var d := _edge_b - _edge_a
	var len := d.length()
	if len < 0.01:
		_snap_line.visible = false
		return
	var mid := (_edge_a + _edge_b) * 0.5
	_snap_line.visible = true
	_snap_line.position = Vector3(mid.x, gy + FLOOR_LIFT + 0.05, mid.y)
	_snap_line.rotation.y = atan2(-d.y, d.x)
	_snap_line.scale = Vector3(len, LINE_H, w * 1.2)


# ---------------------------------------------------------------- 補助

func _on_object_added(_uid: int) -> void:
	if _has_subject() and not _drag_active:
		_refresh_others()
		_refresh_visuals()


func _on_object_changed(uid: int) -> void:
	if _drag_active:
		return
	if uid == selected_uid:
		_load_subject()
	if _has_subject():
		_refresh_others()
		_refresh_visuals()


func _on_object_removed(uid: int) -> void:
	if uid == selected_uid:
		if _drag_active:
			_drag_active = false
			_drag_index = -1
		_set_selected(-1)
		return
	if _has_subject() and not _drag_active:
		_refresh_others()
		_refresh_visuals()


func _on_mode_changed(m: String) -> void:
	if m != "edit":
		cancel()
		_touches.clear()


func _set_highlight(uid: int, on: bool) -> void:
	var m := _main()
	var ol = m.get("objects") if m != null else null
	if ol != null and ol.has_method("set_highlight"):
		ol.set_highlight(uid, on)


func _center_xz() -> Vector2:
	var vp := get_viewport().get_visible_rect().size * 0.5
	var g = _ground_at(vp)
	if g != null:
		return _clamp_xz(Vector2(g.x, g.z))
	var rig := _rig()
	if rig != null:
		return _clamp_xz(Vector2(rig.target.x, rig.target.z))
	return Vector2.ZERO


func _clamp_xz(v: Vector2) -> Vector2:
	return Vector2(clampf(v.x, -WORLD_LIMIT, WORLD_LIMIT), clampf(v.y, -WORLD_LIMIT, WORLD_LIMIT))


func _footprint_size(type: String) -> Vector2:
	var poly := Catalog.footprint_polygon(type)
	return Vector2(poly[1].x - poly[0].x, poly[2].y - poly[1].y)


func _is_tree(type: String) -> bool:
	return bool(Catalog.get_item(type).get("tree", false))


func _make_material(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return m


func _main() -> Node:
	if not is_inside_tree():
		return null
	return get_tree().get_first_node_in_group("main")


func _rig() -> CameraRig:
	var m := _main()
	if m == null:
		return null
	return m.get("camera_rig") as CameraRig


func _terrain() -> Terrain:
	var m := _main()
	if m == null:
		return null
	return m.get("terrain") as Terrain


func _camera_distance() -> float:
	var rig := _rig()
	if rig == null:
		return DEFAULT_DISTANCE
	return rig.distance


func _ground_y(p: Vector2) -> float:
	var t := _terrain()
	if t != null and t.has_method("height_at"):
		return float(t.call("height_at", p.x, p.y))
	if Game.world != null:
		return Game.world.height_at(p.x, p.y)
	return 0.0


## 画面の点の地面の点(Vector3)。当たらなければ null。
func _ground_at(p: Vector2) -> Variant:
	var t := _terrain()
	var rig := _rig()
	if t == null or rig == null or rig.camera == null:
		return null
	if not t.has_method("screen_to_ground"):
		return null
	return t.call("screen_to_ground", rig.camera, p)
