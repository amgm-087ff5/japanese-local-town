## 編集用カメラ(architecture.md 11章・15.3・15.4)。class_name CameraRig。
##
## 符号と範囲(tools/shot.gd などが直接書く値。単位はすべて rad / m):
##   pitch:    下向きを負とする。-89°(ほぼ真上)〜 -8°(ほぼ真横)。範囲外は丸める。
##   yaw:      0 で北(-Z)が画面の上、東(+X)が右。増やすと地図は画面上で時計回りに回る。
##   distance: 4〜220 m。
##   target:   注視点。xz は ±128 に制限、y は地形の高さに追従する。
## 直接値を書いても、_process で見た目(_v_*)が滑らかに追いつく。指・マウスの操作中は即時に反映する。
## settle() は見た目を即座に合わせる(テスト用)。
##
## 入力: handle_input(event) が処理して true を返す。モード側(EditMode など)が呼ぶ。
## マウス左ボタンは emulate_touch_from_mouse によりタッチとしても届くので無視する(二重に動かないため)。
## 右ドラッグ=yaw/pitch、ホイール=ズーム。_unhandled_input は Game.mode == "photo" の時だけ handle_input を呼ぶ。
class_name CameraRig
extends Node3D

const FOV := 50.0
const NEAR := 0.2
const FAR := 4000.0
const DIST_MIN := 4.0
const DIST_MAX := 220.0
const PITCH_STEEP := -89.0 * PI / 180.0    # 真上に近い(最も下向き)
const PITCH_SHALLOW := -8.0 * PI / 180.0   # 真横に近い
const LIMIT := 128.0                       # 注視点の xz 範囲
const CLEARANCE := 1.0                     # カメラは地形より 1m 以上上
const SMOOTH := 12.0                       # 見た目の追従の速さ(1/s)
const INERTIA_DECAY := 4.0                 # 慣性の減衰(1/s)
const STALE_MS := 120                      # この時間動かさずに指を離したら慣性を持たない
const TOUCH_PITCH_SENS := 0.004            # 2本指の上下 1px あたりの pitch(rad)
const MOUSE_YAW_SENS := 0.006
const MOUSE_PITCH_SENS := 0.004
const WHEEL_STEP := 0.9

var target := Vector3.ZERO
var yaw := 0.0
var pitch := -PI * 0.25
var distance := 120.0
var camera: Camera3D

# 見た目(滑らかに追う値)
var _v_target := Vector3.ZERO
var _v_yaw := 0.0
var _v_pitch := -PI * 0.25
var _v_distance := 120.0

# 指の状態: index -> 現在位置
var _touches: Dictionary = {}
var _grab: Variant = null          # 1本指: 指を置いた瞬間の地面の点(Vector3)。空からなら null
var _pan_last := Vector2.ZERO
var _prev_span := 0.0
var _prev_angle := 0.0
var _prev_mid := Vector2.ZERO
var _right_drag := false
var _vel := Vector2.ZERO           # 慣性(xz, m/s)
var _vel_yaw := 0.0                # 慣性(rad/s)
var _last_ms := 0


func _ready() -> void:
	camera = Camera3D.new()
	camera.name = "Camera"
	camera.fov = FOV
	camera.near = NEAR
	camera.far = FAR
	add_child(camera)
	if Game.has_signal("mode_changed"):
		Game.mode_changed.connect(_on_mode_changed)
	settle()


## 定位置へ向ける。"top"(真上・北が上) "side"(真横に近い) "oblique"(斜め45°) "north"(北を上へ・傾きは保つ)。
## 距離は変えない。値は滑らかに変わる(settle() で即座に)。
func set_preset(preset: String) -> void:
	match preset:
		"top":
			yaw = 0.0
			pitch = PITCH_STEEP
		"side":
			yaw = 0.0
			pitch = PITCH_SHALLOW
		"oblique":
			yaw = 0.0
			pitch = -45.0 * PI / 180.0
		"north":
			yaw = 0.0
		_:
			push_warning("未知のプリセット: %s" % preset)
			return
	_vel = Vector2.ZERO
	_vel_yaw = 0.0


## 注視点を移す(滑らかに)。y は地形に合わせて自動で決まる。
func focus(pos: Vector3) -> void:
	target = pos


## 見た目を即座に状態へ合わせる(テスト・初期化用)。
func settle() -> void:
	_clamp_state()
	_v_target = target
	_v_yaw = yaw
	_v_pitch = pitch
	_v_distance = distance
	_update_camera()


## 指・マウスの途中状態を捨てる(モードが変わった時など)。
func reset_input() -> void:
	_touches.clear()
	_right_drag = false
	_grab = null
	_vel = Vector2.ZERO
	_vel_yaw = 0.0


## 入力を処理する。処理したら true。タッチは指の index で追跡する。
func handle_input(event: InputEvent) -> bool:
	if event is InputEventScreenTouch:
		return _on_touch(event as InputEventScreenTouch)
	if event is InputEventScreenDrag:
		return _on_drag(event as InputEventScreenDrag)
	if event is InputEventMouseButton:
		return _on_mouse_button(event as InputEventMouseButton)
	if event is InputEventMouseMotion:
		return _on_mouse_motion(event as InputEventMouseMotion)
	return false


func _unhandled_input(event: InputEvent) -> void:
	if Game.mode != "photo":
		return
	if handle_input(event):
		get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if _touches.is_empty() and not _right_drag and _has_inertia():
		target.x += _vel.x * delta
		target.z += _vel.y * delta
		yaw += _vel_yaw * delta
		var f := exp(-INERTIA_DECAY * delta)
		_vel *= f
		_vel_yaw *= f
		if _vel.length() < 0.01:
			_vel = Vector2.ZERO
		if absf(_vel_yaw) < 0.001:
			_vel_yaw = 0.0
	_clamp_state()
	var k := 1.0 - exp(-SMOOTH * delta)
	_v_target = _v_target.lerp(target, k)
	_v_yaw += angle_difference(_v_yaw, yaw) * k
	_v_pitch = lerpf(_v_pitch, pitch, k)
	_v_distance = lerpf(_v_distance, distance, k)
	_update_camera()


# ---------------------------------------------------------------- タッチ

func _on_touch(ev: InputEventScreenTouch) -> bool:
	if ev.pressed:
		_touches[ev.index] = ev.position
		_vel = Vector2.ZERO
		_vel_yaw = 0.0
		if _touches.size() == 1:
			_begin_pan(ev.position)
		elif _touches.size() == 2:
			_begin_pinch()
		return true
	if not _touches.has(ev.index):
		return false
	_touches.erase(ev.index)
	if Time.get_ticks_msec() - _last_ms > STALE_MS:
		_vel = Vector2.ZERO
		_vel_yaw = 0.0
	if _touches.size() == 1:
		var rest: Vector2 = _touches.values()[0]
		_begin_pan(rest)
	elif _touches.size() == 2:
		_begin_pinch()
	return true


func _on_drag(ev: InputEventScreenDrag) -> bool:
	if not _touches.has(ev.index):
		return false
	_touches[ev.index] = ev.position
	if _touches.size() == 1:
		_pan_to(ev.position)
	elif _touches.size() == 2:
		_pinch_to()
	return true


## 1本指: 指の下の地面をつかむ。空の上で始まった場合は、地面に当たった時点でつかむ。
func _begin_pan(p: Vector2) -> void:
	_grab = _ground_at(p)
	_pan_last = p
	_last_ms = Time.get_ticks_msec()


func _pan_to(p: Vector2) -> void:
	var dt := _tick_dt()
	var g = _ground_at(p)
	var delta := Vector3.ZERO
	if g != null:
		if _grab == null:
			_grab = g
		else:
			var grab: Vector3 = _grab
			var gp: Vector3 = g
			delta = grab - gp
	elif _grab == null:
		# 地面が無い所(空)から始まった場合は画面上の移動量で動かす
		delta = _screen_pan_delta(p - _pan_last)
	_pan_last = p
	delta.y = 0.0
	if delta.length_squared() > 0.0:
		target.x += delta.x
		target.z += delta.z
		_vel = _vel.lerp(Vector2(delta.x, delta.z) / dt, 0.5)
		_set_direct()


## 画面上の移動量(px)を、地面上の移動量(m)へ。距離と画角から決める。
func _screen_pan_delta(rel: Vector2) -> Vector3:
	if camera == null or not camera.is_inside_tree():
		return Vector3.ZERO
	var vp := camera.get_viewport().get_visible_rect().size
	# KEEP_WIDTH では画角は横方向。KEEP_HEIGHT では縦方向で決まる
	var span := maxf(vp.x if camera.keep_aspect == Camera3D.KEEP_WIDTH else vp.y, 1.0)
	var s := 2.0 * _v_distance * tan(deg_to_rad(FOV) * 0.5) / span
	var b := camera.global_transform.basis
	var right := Vector3(b.x.x, 0.0, b.x.z)
	var up_flat := Vector3(b.y.x, 0.0, b.y.z)
	if right.length() > 0.0001:
		right = right.normalized()
	if up_flat.length() > 0.0001:
		up_flat = up_flat.normalized()
	return (-right * rel.x + up_flat * rel.y) * s


## 2本指: 開きでズーム、ひねりで yaw、同方向の上下で pitch。
func _begin_pinch() -> void:
	var keys := _touches.keys()
	keys.sort()
	var a: Vector2 = _touches[keys[0]]
	var b: Vector2 = _touches[keys[1]]
	_prev_span = a.distance_to(b)
	_prev_angle = (b - a).angle()
	_prev_mid = (a + b) * 0.5
	_last_ms = Time.get_ticks_msec()


func _pinch_to() -> void:
	var keys := _touches.keys()
	keys.sort()
	var a: Vector2 = _touches[keys[0]]
	var b: Vector2 = _touches[keys[1]]
	var span := a.distance_to(b)
	var ang := (b - a).angle()
	var mid := (a + b) * 0.5
	var dt := _tick_dt()
	if _prev_span > 1.0 and span > 1.0:
		distance *= _prev_span / span
	var dang := wrapf(ang - _prev_angle, -PI, PI)
	yaw += dang
	pitch -= (mid.y - _prev_mid.y) * TOUCH_PITCH_SENS
	_vel = Vector2.ZERO
	_vel_yaw = lerpf(_vel_yaw, dang / dt, 0.5)
	_prev_span = span
	_prev_angle = ang
	_prev_mid = mid
	_set_direct()


## 前回からの経過秒(下限あり)。同時に記録を更新する。
func _tick_dt() -> float:
	var now := Time.get_ticks_msec()
	var dt := maxf(float(now - _last_ms) / 1000.0, 1.0 / 120.0)
	_last_ms = now
	return dt


# ---------------------------------------------------------------- マウス(右ドラッグ・ホイール)

func _on_mouse_button(ev: InputEventMouseButton) -> bool:
	match ev.button_index:
		MOUSE_BUTTON_RIGHT:
			_right_drag = ev.pressed
			_vel = Vector2.ZERO
			_vel_yaw = 0.0
			return true
		MOUSE_BUTTON_WHEEL_UP:
			if ev.pressed:
				distance *= WHEEL_STEP
			return true
		MOUSE_BUTTON_WHEEL_DOWN:
			if ev.pressed:
				distance /= WHEEL_STEP
			return true
	return false


func _on_mouse_motion(ev: InputEventMouseMotion) -> bool:
	if not _right_drag:
		return false
	yaw += ev.relative.x * MOUSE_YAW_SENS
	pitch -= ev.relative.y * MOUSE_PITCH_SENS
	_set_direct()
	return true


# ---------------------------------------------------------------- 内部

func _on_mode_changed(_m: String) -> void:
	reset_input()


func _has_inertia() -> bool:
	return _vel.length_squared() > 0.0001 or absf(_vel_yaw) > 0.001


## 操作中は状態と見た目を一致させる(遅れを出さない)。
func _set_direct() -> void:
	_clamp_state()
	_v_target = target
	_v_yaw = yaw
	_v_pitch = pitch
	_v_distance = distance
	_update_camera()


func _clamp_state() -> void:
	target.x = clampf(target.x, -LIMIT, LIMIT)
	target.z = clampf(target.z, -LIMIT, LIMIT)
	target.y = _ground_y(target.x, target.z)
	yaw = wrapf(yaw, -PI, PI)
	pitch = clampf(pitch, PITCH_STEEP, PITCH_SHALLOW)
	distance = clampf(distance, DIST_MIN, DIST_MAX)


func _update_camera() -> void:
	if camera == null or not is_inside_tree():
		return
	# 縦長は KEEP_WIDTH(横の画角を保つ)。横画面と同じ横方向の見え方(同じ距離で同じ縮尺)になる。
	var sz := camera.get_viewport().get_visible_rect().size
	var keep := Camera3D.KEEP_WIDTH if sz.y > sz.x else Camera3D.KEEP_HEIGHT
	if camera.keep_aspect != keep:
		camera.keep_aspect = keep
	var offset := Vector3(sin(_v_yaw) * cos(_v_pitch), -sin(_v_pitch), cos(_v_yaw) * cos(_v_pitch)) * _v_distance
	var pos := _v_target + offset
	var ground := _ground_y(pos.x, pos.z)
	if pos.y < ground + CLEARANCE:
		pos.y = ground + CLEARANCE
	camera.global_transform = Transform3D(Basis.looking_at(_v_target - pos, Vector3.UP), pos)


func _main() -> Node:
	if not is_inside_tree():
		return null
	return get_tree().get_first_node_in_group("main")


func _ground_y(x: float, z: float) -> float:
	var m := _main()
	if m != null:
		var t = m.get("terrain")
		if t != null and t.has_method("height_at"):
			return float(t.height_at(x, z))
	if Game.world != null:
		return Game.world.height_at(x, z)
	return 0.0


## 画面の点の地面の点(Vector3)。当たらなければ null。
func _ground_at(p: Vector2) -> Variant:
	var m := _main()
	if m == null or camera == null:
		return null
	var t = m.get("terrain")
	if t == null or not t.has_method("screen_to_ground"):
		return null
	return t.screen_to_ground(camera, p)
