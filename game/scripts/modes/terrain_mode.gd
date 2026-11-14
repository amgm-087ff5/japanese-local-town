## 地形モード(architecture.md 11章・15.3)。1本指(マウス左)のドラッグでブラシ、2本目の指でカメラへ切り替える。
## ストロークは Game.begin_stroke(layer) → 毎フレーム Terrain.brush_*() → Game.end_stroke(累積 rect)で包む。
class_name TerrainMode
extends Node

signal tool_changed

const TOOL_LAYER := {
	"raise": "height", "lower": "height", "flatten": "height", "smooth": "height",
	"surface": "surface", "forest_add": "forest", "forest_remove": "forest",
}
const RADIUS_MIN := 2.0
const RADIUS_MAX := 30.0
const RING_SEGMENTS := 96
const RING_HALF_WIDTH := 0.14
const RING_LIFT := 0.14
const NO_OWNER := -1
const MOUSE_OWNER := -2

var surface_type: int = 3      # 地表の種類 1-7(3=石畳)
var radius: float = 6.0        # ブラシ半径(m)。2-30 に収める
var strength: float = 0.5      # 0-1

var _tool := "raise"
var _ring: MeshInstance3D
var _ring_mat: StandardMaterial3D
var _ring_r := -1.0
var _ring_center := Vector3.INF
var _stroking := false
var _owner := NO_OWNER         # ストロークを持つ指の index / マウス(MOUSE_OWNER)
var _locked := false           # 2本指になったあと、指が全部離れるまでブラシを始めない
var _touches: Dictionary = {}  # index -> 画面座標
var _has_target := false
var _target := Vector3.ZERO
var _stroke_rect := Rect2i()


## 道具("raise" "lower" "flatten" "smooth" "surface" "forest_add" "forest_remove")。変えると tool_changed を出す。
var tool: String:
	get:
		return _tool
	set(v):
		_set_tool(v)


func _ready() -> void:
	_ring_mat = StandardMaterial3D.new()
	_ring_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_ring_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_ring_mat.albedo_color = Color(1.0, 0.97, 0.9, 0.8)
	_ring_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_ring = MeshInstance3D.new()
	_ring.name = "BrushRing"
	_ring.material_override = _ring_mat
	_ring.visible = false
	_ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_ring)
	Terrain.game().mode_changed.connect(_on_mode_changed)


func _notification(what: int) -> void:
	if what == NOTIFICATION_PAUSED:
		_cancel_input()


func _unhandled_input(event: InputEvent) -> void:
	if not _is_active():
		return
	if event is InputEventScreenTouch:
		_on_touch(event)
	elif event is InputEventScreenDrag:
		_on_drag(event)
	elif event is InputEventMouseButton:
		_on_mouse_button(event)
	elif event is InputEventMouseMotion:
		_on_mouse_motion(event)


func _process(delta: float) -> void:
	if not _is_active():
		return
	if _stroking and _has_target:
		var t := _terrain()
		if t != null:
			var rect := _apply_brush(t, delta)
			_stroke_rect = _merge(_stroke_rect, rect)
	_update_ring()


# ---------------------------------------------------------------- 入力

func _on_touch(e: InputEventScreenTouch) -> void:
	if e.pressed:
		_touches[e.index] = e.position
		if _touches.size() == 1 and not _locked and not _stroking:
			_begin_stroke(e.position, e.index)
		else:
			# 2本目の指: ブラシは終えてカメラ操作へ
			_locked = true
			_end_stroke()
			_has_target = false
			_camera_input(e)
		get_viewport().set_input_as_handled()
	else:
		_touches.erase(e.index)
		if e.index == _owner:
			_end_stroke()
			_has_target = false
		else:
			_camera_input(e)
		if _touches.is_empty():
			_locked = false
		get_viewport().set_input_as_handled()


func _on_drag(e: InputEventScreenDrag) -> void:
	_touches[e.index] = e.position
	if _stroking and e.index == _owner:
		_set_target_from_screen(e.position)
		get_viewport().set_input_as_handled()
	else:
		_camera_input(e)


func _on_mouse_button(e: InputEventMouseButton) -> void:
	if e.device == InputEvent.DEVICE_ID_EMULATION:
		return   # タッチからの擬似マウスは使わない
	if e.button_index == MOUSE_BUTTON_LEFT:
		if e.pressed:
			if _touches.is_empty() and not _locked and not _stroking:
				_begin_stroke(e.position, MOUSE_OWNER)
		elif _owner == MOUSE_OWNER:
			_end_stroke()
		get_viewport().set_input_as_handled()
	else:
		# 右ドラッグ・ホイールはカメラ
		_camera_input(e)


func _on_mouse_motion(e: InputEventMouseMotion) -> void:
	if e.device == InputEvent.DEVICE_ID_EMULATION:
		return
	if (e.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0 and _owner == MOUSE_OWNER:
		_set_target_from_screen(e.position)
		get_viewport().set_input_as_handled()
	elif (e.button_mask & MOUSE_BUTTON_MASK_RIGHT) != 0:
		_camera_input(e)
	elif not _stroking and _touches.is_empty():
		# 何も押していない時は、ブラシの輪を指す位置に出す
		_set_target_from_screen(e.position)


# ---------------------------------------------------------------- ストローク

func _begin_stroke(pos: Vector2, owner: int) -> void:
	_owner = owner
	_stroking = true
	_stroke_rect = Rect2i()
	Terrain.game().begin_stroke(TOOL_LAYER.get(_tool, "height"))
	var t := _terrain()
	if t != null:
		t.reset_stroke()
	_set_target_from_screen(pos)


func _end_stroke() -> void:
	if not _stroking:
		return
	_stroking = false
	_owner = NO_OWNER
	Terrain.game().end_stroke(_stroke_rect)
	_stroke_rect = Rect2i()


## 進行中の入力を全部止める(ポーズ・モード切替時)。
func _cancel_input() -> void:
	_end_stroke()
	_touches.clear()
	_locked = false
	_has_target = false
	_ring.visible = false


func _apply_brush(t: Terrain, dt: float) -> Rect2i:
	var r := clampf(radius, RADIUS_MIN, RADIUS_MAX)
	var s := clampf(strength, 0.0, 1.0)
	var c := Vector2(_target.x, _target.z)
	match _tool:
		"raise", "lower", "smooth":
			return t.brush_height(_tool, c, r, s, dt)
		"flatten":
			return t.brush_height("flatten", c, r, s, dt)
		"surface":
			return t.brush_surface(surface_type, c, r, s, dt)
		"forest_add":
			return t.brush_forest(c, r, true, dt)
		"forest_remove":
			return t.brush_forest(c, r, false, dt)
	return Rect2i()


func _set_target_from_screen(pos: Vector2) -> void:
	var t := _terrain()
	var cam := _camera()
	_has_target = false
	if t == null or cam == null:
		return
	var g: Variant = t.screen_to_ground(cam, pos)
	if g is Vector3:
		_target = g
		_has_target = true


func _set_tool(v: String) -> void:
	if v == _tool:
		return
	if not TOOL_LAYER.has(v):
		push_warning("未知の道具: %s" % v)
		return
	_end_stroke()
	_tool = v
	tool_changed.emit()


func _on_mode_changed(m: String) -> void:
	if m != "terrain":
		_cancel_input()


# ---------------------------------------------------------------- ブラシの輪

func _update_ring() -> void:
	var t := _terrain()
	if not _has_target or t == null:
		_ring.visible = false
		return
	var r := clampf(radius, RADIUS_MIN, RADIUS_MAX)
	if not _ring.visible or _target != _ring_center or not is_equal_approx(r, _ring_r):
		_ring.mesh = _make_ring(t, _target, r)
		_ring_center = _target
		_ring_r = r
	_ring.visible = true


## 地形に沿う細い帯(三角形)。内側と外側の頂点の高さは地形から取る。
func _make_ring(t: Terrain, c: Vector3, r: float) -> ArrayMesh:
	var verts := PackedVector3Array()
	verts.resize(RING_SEGMENTS * 6)
	var n := 0
	var rin := maxf(r - RING_HALF_WIDTH, 0.05)
	var rout := r + RING_HALF_WIDTH
	for i in RING_SEGMENTS:
		var a0 := TAU * float(i) / float(RING_SEGMENTS)
		var a1 := TAU * float(i + 1) / float(RING_SEGMENTS)
		var pin0 := _ring_point(t, c, rin, a0)
		var pout0 := _ring_point(t, c, rout, a0)
		var pin1 := _ring_point(t, c, rin, a1)
		var pout1 := _ring_point(t, c, rout, a1)
		verts[n] = pin0
		verts[n + 1] = pout0
		verts[n + 2] = pin1
		verts[n + 3] = pout0
		verts[n + 4] = pout1
		verts[n + 5] = pin1
		n += 6
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, [verts])
	return m


func _ring_point(t: Terrain, c: Vector3, rad: float, a: float) -> Vector3:
	var x: float = c.x + cos(a) * rad
	var z: float = c.z + sin(a) * rad
	return Vector3(x, t.height_at(x, z) + RING_LIFT, z)


# ---------------------------------------------------------------- 補助

func _is_active() -> bool:
	return can_process() and Terrain.game().mode == "terrain"


func _main() -> Node:
	return get_tree().get_first_node_in_group("main")


func _terrain() -> Terrain:
	var m := _main()
	if m == null:
		return null
	return m.get("terrain") as Terrain


func _camera() -> Camera3D:
	var m := _main()
	if m == null:
		return null
	var rig = m.get("camera_rig")
	if rig == null:
		return null
	return rig.camera as Camera3D


func _camera_input(e: InputEvent) -> void:
	var m := _main()
	if m == null:
		return
	var rig = m.get("camera_rig")
	if rig != null:
		rig.handle_input(e)


static func _merge(a: Rect2i, b: Rect2i) -> Rect2i:
	if b.size == Vector2i.ZERO:
		return a
	if a.size == Vector2i.ZERO:
		return b
	return a.merge(b)
