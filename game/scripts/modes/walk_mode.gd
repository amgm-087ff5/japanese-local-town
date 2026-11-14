## 歩行モード(architecture.md 11章・15.3・15.4)。class_name WalkMode。
## CharacterBody3D(カプセル 高さ1.6m・半径0.3m)。原点は足元。Main が Game.mode_changed に合わせて
## enter() / exit() を呼ぶ(二重に呼ばれても壊れない)。UI(Hud)は set_move_vector / set_run / jump を呼ぶ。
## 地形の当たり(Terrain の StaticBody3D)が無くても、毎フレーム terrain.height_at より下に落ちない。
class_name WalkMode
extends CharacterBody3D

signal view_changed

const WALK_SPEED := 3.2
const RUN_SPEED := 6.0
const JUMP_SPEED := 4.5
const GRAVITY := 9.8

const BODY_HEIGHT := 1.6
const BODY_RADIUS := 0.3
const FLOOR_MAX_ANGLE_DEG := 46.0
const FLOOR_SNAP := 0.35
const STEP_UP := 0.35        # 段差の乗り越え量(0.3m の段を越える余裕を持たせる)
const STEP_EXTRA_DOWN := 0.05

const WORLD_LIMIT := 127.0
const WATER_DEPTH_MAX := 1.0  # 足元が WATER_LEVEL - 1.0 より深い所へは進めない

const SPOT_CLEARANCE := 0.5   # 開始位置は木以外の占有領域からこの距離(m)より外に置く
const SPOT_STEP := 0.25       # 開始位置を探すときの半径の刻み(m)
const SPOT_MAX_RADIUS := 15.0
const SPOT_DIRS := 32

const EYE_HEIGHT := 1.5
const TP_HEIGHT := 1.9        # 三人称のカメラ高さ
const TP_BACK := 3.2          # 三人称のカメラ距離(後方)
const CAM_TERRAIN_CLEAR := 0.3
const CAM_HIT_MARGIN := 0.2
const CAM_MIN_DIST := 0.6

const LOOK_DEG_PER_PX := 0.25
const PITCH_MIN_DEG := -60.0
const PITCH_MAX_DEG := 70.0

const AVATAR_PATH := "res://assets/models/avatar.glb"
const AVATAR_HEIGHT := 1.6
const PHYS_LAYER := 4         # 3番目のレイヤー "player"
const PHYS_MASK := 3          # レイヤー1(地形)+2(配置物)

var first_person := false     # true: 一人称 / false: 地面に近い三人称
var camera: Camera3D
var yaw := 0.0                # 体の向き(rad)。Godot の rotation.y と同じ符号
var pitch := 0.0              # カメラの上下(rad)。正=上を見る

var _active := false
var _grounded := false
var _stick := Vector2.ZERO
var _run_req := false
var _jump_req := false
var _facing := 0.0            # アバターが向いている世界の向き(rad)
var _bob := 0.0
var _moving := false
var _main: Node
var _avatar_root: Node3D
var _shadow: MeshInstance3D


func _ready() -> void:
	add_to_group("player")
	collision_layer = PHYS_LAYER
	collision_mask = PHYS_MASK
	floor_max_angle = deg_to_rad(FLOOR_MAX_ANGLE_DEG)
	floor_snap_length = FLOOR_SNAP

	var col := CollisionShape3D.new()
	col.name = "Collision"
	var cap := CapsuleShape3D.new()
	cap.height = BODY_HEIGHT
	cap.radius = BODY_RADIUS
	col.shape = cap
	col.position = Vector3(0.0, BODY_HEIGHT * 0.5, 0.0)  # 原点=足元
	add_child(col)

	camera = Camera3D.new()
	camera.name = "WalkCamera"
	camera.near = 0.1
	camera.far = 4000.0
	add_child(camera)

	_build_avatar()
	_build_shadow()
	_game().mode_changed.connect(_on_mode_changed)
	_update_camera()


func _on_mode_changed(m: String) -> void:
	if m == "walk":
		enter()
	else:
		exit()


## 歩行を始める。開始位置は編集カメラの注視点(xz)、向きは編集カメラの yaw。
func enter() -> void:
	if _active:
		camera.make_current()
		return
	var rig: Variant = _rig()
	var tgt := Vector3.ZERO
	if rig != null:
		tgt = rig.target
		yaw = rig.yaw
	var start := Vector2(clampf(tgt.x, -WORLD_LIMIT, WORLD_LIMIT), clampf(tgt.z, -WORLD_LIMIT, WORLD_LIMIT))
	start = _free_spot(start)
	var x := start.x
	var z := start.y
	var t = _terrain()
	if t != null and t.has_method("update_collision"):
		t.update_collision()
	global_position = Vector3(x, _ground_y(x, z) + 0.2, z)
	rotation.y = yaw
	velocity = Vector3.ZERO
	_facing = yaw
	_grounded = false
	_jump_req = false
	_stick = Vector2.ZERO
	_active = true
	camera.make_current()
	_update_camera()


## 歩行を終える。編集カメラを歩行位置へ向け、位置と向きを世界に保存対象にする(次の保存時に含まれる)。
func exit() -> void:
	if not _active:
		return
	_active = false
	_stick = Vector2.ZERO
	_run_req = false
	_jump_req = false
	_moving = false
	velocity = Vector3.ZERO
	_shadow.visible = false
	var rig: Variant = _rig()
	if rig != null:
		rig.focus(global_position)
	var g := _game()
	if g.world != null:
		g.world.player = {"x": global_position.x, "z": global_position.z, "yaw": yaw}
		g.mark_dirty()   # 次の保存に含める(位置は世界データ)


## 開始位置 p が木以外の占有領域(+SPOT_CLEARANCE)の外か。外なら p、内なら最も近い外側の点を返す。
## 中心から半径を広げながら方向を変えて探す(最初に見つかった点が最も近い)。
func _free_spot(p: Vector2) -> Vector2:
	var polys := _solid_footprints()
	if not _spot_blocked(p, polys):
		return p
	var r := SPOT_STEP
	while r <= SPOT_MAX_RADIUS:
		for k in SPOT_DIRS:
			var a := TAU * float(k) / float(SPOT_DIRS)
			var q := p + Vector2(cos(a), sin(a)) * r
			if absf(q.x) <= WORLD_LIMIT and absf(q.y) <= WORLD_LIMIT and not _spot_blocked(q, polys):
				return q
		r += SPOT_STEP
	return p


## 木以外の物の占有領域(ワールド座標)。Game.world から直接作る(ObjectLayer の生成に依らない)。
func _solid_footprints() -> Array:
	var out: Array = []
	var w := _game().world as WorldData
	if w == null:
		return out
	for obj in w.objects:
		var item: Dictionary = _catalog().get_item(str(obj["type"]))
		if bool(item.get("tree", false)):
			continue
		out.append(Geom.to_world(_catalog().footprint_polygon(str(obj["type"])),
			Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"])))
	return out


func _spot_blocked(q: Vector2, polys: Array) -> bool:
	for poly in polys:
		var pp: PackedVector2Array = poly
		if Geom.point_in_polygon(q, pp) or _dist_to_outline(q, pp) < SPOT_CLEARANCE:
			return true
	return false


static func _dist_to_outline(q: Vector2, poly: PackedVector2Array) -> float:
	var best := INF
	var n := poly.size()
	for i in n:
		var a := poly[i]
		var ab := poly[(i + 1) % n] - a
		var len2 := ab.dot(ab)
		var t := 0.0 if len2 < 1e-9 else clampf((q - a).dot(ab) / len2, 0.0, 1.0)
		best = minf(best, q.distance_to(a + ab * t))
	return best


func toggle_view() -> void:
	first_person = not first_person
	view_changed.emit()
	_update_camera()


## UI の仮想スティック。x=右、y=前、長さ 0-1。毎フレーム呼ぶ(離したら Vector2.ZERO)。
func set_move_vector(v: Vector2) -> void:
	_stick = v.limit_length(1.0)


## 画面ドラッグ量(px)で見回す。yaw は体、pitch はカメラ。
func add_look(delta: Vector2) -> void:
	var sens := deg_to_rad(LOOK_DEG_PER_PX)
	var inv := -1.0 if _game().settings.get("invert_look", false) else 1.0
	yaw = wrapf(yaw - delta.x * sens, -PI, PI)
	pitch = clampf(pitch - delta.y * sens * inv, deg_to_rad(PITCH_MIN_DEG), deg_to_rad(PITCH_MAX_DEG))
	rotation.y = yaw
	_update_camera()


func jump() -> void:
	if _active:
		_jump_req = true


func set_run(on: bool) -> void:
	_run_req = on


# ---------------------------------------------------------------- 入力

func _unhandled_input(event: InputEvent) -> void:
	if not _active:
		return
	if event is InputEventScreenDrag:
		add_look((event as InputEventScreenDrag).relative)
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion and (event as InputEventMouseMotion).button_mask & MOUSE_BUTTON_MASK_RIGHT:
		add_look((event as InputEventMouseMotion).relative)
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo:
		var k := event as InputEventKey
		if k.keycode == KEY_V:
			toggle_view()
			get_viewport().set_input_as_handled()
		elif k.keycode == KEY_SPACE:
			jump()
			get_viewport().set_input_as_handled()


## スティックとキーボード(WASD / 矢印)を合わせた移動入力。
func _input_vector() -> Vector2:
	var v := _stick
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		v.y += 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		v.y -= 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		v.x += 1.0
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		v.x -= 1.0
	return v.limit_length(1.0)


# ---------------------------------------------------------------- 物理

func _physics_process(delta: float) -> void:
	if not _active or delta <= 0.0:
		return
	var mv := _input_vector()
	var max_speed := RUN_SPEED if (_run_req or Input.is_key_pressed(KEY_SHIFT)) else WALK_SPEED
	var fwd := _forward()
	var right := _right()
	var want := (right * mv.x + fwd * mv.y) * max_speed * delta
	_moving = mv.length() > 0.01

	var was_grounded := _grounded
	if was_grounded:
		if _jump_req:
			velocity.y = JUMP_SPEED
			_grounded = false
		else:
			velocity.y = 0.0
	else:
		velocity.y -= GRAVITY * delta
	_jump_req = false

	want.y = 0.0
	want = _limit_horizontal(want)
	velocity.x = want.x / delta
	velocity.z = want.z / delta

	var before := global_transform
	move_and_slide()
	# 段差の手前では下端の丸い部分が床扱いの法線になるため is_on_wall() に頼らず、水平の進みが足りないかで判定する
	var want_len := Vector2(want.x, want.z).length()
	var got := Vector2(global_position.x - before.origin.x, global_position.z - before.origin.z).length()
	var stepped := false
	if was_grounded and want_len > 0.0005 and got < want_len * 0.5:
		var after := global_transform
		if _try_step(before, want):
			stepped = true
		else:
			global_transform = after

	# 水・範囲外へ入ったら xz を戻す
	var p := global_position
	if not _ok_at(p.x, p.z):
		p.x = before.origin.x
		p.z = before.origin.z
	p.x = clampf(p.x, -WORLD_LIMIT, WORLD_LIMIT)
	p.z = clampf(p.z, -WORLD_LIMIT, WORLD_LIMIT)

	# 保険: 地形の高さより下に落ちたら地表へ戻す(地形の当たりが無い間も立てるように)
	var gy := _ground_y(p.x, p.z)
	var fell := false
	if p.y < gy:
		p.y = gy
		if velocity.y < 0.0:
			velocity.y = 0.0
		fell = true
	# 床が検出できない間は、地表が段差の高さ以内なら地表へ吸着(地形の当たりが無いときの歩行の見た目)。
	# 下に当たり(地形・物)があるときは物理に任せる。吸着で箱の縁にめり込むのを避けるため。
	if was_grounded and not fell and not stepped and velocity.y <= 0.0 and not is_on_floor() \
			and p.y - gy < STEP_UP + STEP_EXTRA_DOWN \
			and not test_move(Transform3D(global_transform.basis, p), Vector3(0.0, -(STEP_UP + STEP_EXTRA_DOWN), 0.0)):
		p.y = gy
		fell = true
	global_position = p
	_grounded = is_on_floor() or fell

	_update_camera()
	_update_avatar(delta)
	_update_shadow()


## 段差の乗り越え: 少し持ち上げて進み、また下ろす。成功で true(global_transform を更新)。
func _try_step(from: Transform3D, want: Vector3) -> bool:
	var up := Vector3(0.0, STEP_UP, 0.0)
	if test_move(from, up):
		return false  # 頭上が詰まっている
	var lifted := Transform3D(from.basis, from.origin + up)
	if test_move(lifted, want):
		return false  # 持ち上げても壁
	var top := Transform3D(from.basis, from.origin + up + want)
	var down := Vector3(0.0, -(STEP_UP + STEP_EXTRA_DOWN), 0.0)
	var dest := top.origin
	var col := KinematicCollision3D.new()
	if test_move(top, down, col):
		dest += col.get_travel()
	else:
		dest += down
	if dest.y - from.origin.y > STEP_UP + 0.02:
		return false
	if not _ok_at(dest.x, dest.z):
		return false
	global_position = dest
	velocity.y = 0.0
	return true


## 進もうとする水平移動を、水・範囲外に入らない分だけに縮める(全体→x だけ→z だけ の順)。
func _limit_horizontal(d: Vector3) -> Vector3:
	var p := global_position
	if _ok_at(p.x + d.x, p.z + d.z):
		return d
	if _ok_at(p.x + d.x, p.z):
		return Vector3(d.x, 0.0, 0.0)
	if _ok_at(p.x, p.z + d.z):
		return Vector3(0.0, 0.0, d.z)
	return Vector3.ZERO


func _ok_at(x: float, z: float) -> bool:
	if absf(x) > WORLD_LIMIT or absf(z) > WORLD_LIMIT:
		return false
	return _ground_y(x, z) >= WorldData.WATER_LEVEL - WATER_DEPTH_MAX


# ---------------------------------------------------------------- カメラ・見た目

func _update_camera() -> void:
	if camera == null:
		return
	camera.rotation = Vector3(pitch, 0.0, 0.0)
	var eye := Vector3(0.0, EYE_HEIGHT, 0.0)
	if first_person:
		camera.position = eye
	else:
		var ideal := Vector3(0.0, TP_HEIGHT, TP_BACK)
		camera.position = eye.lerp(ideal, _third_person_t(eye, ideal))


## 三人称のカメラを 0〜1 の位置へ詰める(物の当たりを物理レイ、地形は高さ見本で判定)。
func _third_person_t(eye: Vector3, ideal: Vector3) -> float:
	var pivot := global_transform * eye
	var target := global_transform * ideal
	var t := 1.0
	var q := PhysicsRayQueryParameters3D.create(pivot, target, PHYS_MASK, [get_rid()])
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty():
		var total := pivot.distance_to(target)
		if total > 0.0001:
			t = clampf((pivot.distance_to(hit["position"]) - CAM_HIT_MARGIN) / total, 0.0, 1.0)
	for k in range(1, 9):
		var f := float(k) / 8.0
		var local := eye.lerp(ideal, f)
		var w := global_transform * local
		if w.y < _ground_y(w.x, w.z) + CAM_TERRAIN_CLEAR:
			t = minf(t, float(k - 1) / 8.0)
			break
	var min_t := CAM_MIN_DIST / (ideal - eye).length()
	return maxf(t, min_t)


func _update_avatar(delta: float) -> void:
	_avatar_root.visible = not first_person
	var v := Vector2(velocity.x, velocity.z)
	if v.length() > 0.2:
		var target := atan2(v.x, v.y)
		_facing = lerp_angle(_facing, target, clampf(delta * 10.0, 0.0, 1.0))
	_avatar_root.rotation.y = _facing - yaw
	if _moving:
		_bob += delta * 9.0
		_avatar_root.position.y = absf(sin(_bob)) * 0.03
	else:
		_avatar_root.position.y = lerpf(_avatar_root.position.y, 0.0, clampf(delta * 10.0, 0.0, 1.0))


func _update_shadow() -> void:
	_shadow.visible = _active and not first_person
	if not _shadow.visible:
		return
	var p := global_position
	_shadow.global_position = Vector3(p.x, _ground_y(p.x, p.z) + 0.03, p.z)


func _build_avatar() -> void:
	_avatar_root = Node3D.new()
	_avatar_root.name = "Avatar"
	add_child(_avatar_root)
	if ResourceLoader.exists(AVATAR_PATH):
		var ps = load(AVATAR_PATH)
		if ps is PackedScene:
			var inst := (ps as PackedScene).instantiate() as Node3D
			if inst != null:
				_avatar_root.add_child(inst)
				_fit_model(inst)
				return
	# 簡易人形(カプセルと球)
	var body := MeshInstance3D.new()
	body.name = "Body"
	var cap := CapsuleMesh.new()
	cap.radius = 0.22
	cap.height = 1.25
	body.mesh = cap
	body.position = Vector3(0.0, 0.7, 0.0)
	body.material_override = _solid(Color(0.16, 0.2, 0.3))
	_avatar_root.add_child(body)
	var head := MeshInstance3D.new()
	head.name = "Head"
	var sph := SphereMesh.new()
	sph.radius = 0.13
	sph.height = 0.26
	head.mesh = sph
	head.position = Vector3(0.0, 1.45, 0.0)
	head.material_override = _solid(Color(0.93, 0.84, 0.74))
	_avatar_root.add_child(head)


## 読み込んだモデルを高さ AVATAR_HEIGHT・足元が原点・中心 xz=0 に合わせる。
func _fit_model(inst: Node3D) -> void:
	var box := AABB()
	var has := false
	for n in inst.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		var local := inst.global_transform.affine_inverse() * mi.global_transform * mi.get_aabb()
		if not has:
			box = local
			has = true
		else:
			box = box.merge(local)
	if not has or box.size.y < 0.05:
		return
	var s := AVATAR_HEIGHT / box.size.y
	var c := box.position + box.size * 0.5
	inst.scale = Vector3.ONE * s
	inst.position = Vector3(-c.x * s, -box.position.y * s, -c.z * s)


func _build_shadow() -> void:
	_shadow = MeshInstance3D.new()
	_shadow.name = "Shadow"
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.42
	cyl.bottom_radius = 0.42
	cyl.height = 0.01
	_shadow.mesh = cyl
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.0, 0.0, 0.0, 0.35)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_shadow.material_override = m
	_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_shadow.top_level = true
	_shadow.visible = false
	add_child(_shadow)


static func _solid(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	return m


# ---------------------------------------------------------------- 補助

func _forward() -> Vector3:
	return Vector3(-sin(yaw), 0.0, -cos(yaw))


func _right() -> Vector3:
	return Vector3(cos(yaw), 0.0, -sin(yaw))


## autoload Game は class_name スクリプトから識別子で参照せず、実行時に root から取る(--script 実行でも解決できるように)。
func _game() -> Node:
	return get_node("/root/Game")


func _catalog() -> Node:
	return get_node("/root/Catalog")


func _main_node() -> Node:
	if _main == null or not is_instance_valid(_main):
		_main = get_tree().get_first_node_in_group("main")
	return _main


func _rig() -> Variant:
	var m := _main_node()
	return m.get("camera_rig") if m != null else null


func _terrain() -> Variant:
	var m := _main_node()
	return m.get("terrain") if m != null else null


## 地表の高さ。Main の terrain を優先し、無ければ世界データを直接読む。
func _ground_y(x: float, z: float) -> float:
	var t = _terrain()
	if t != null and t.has_method("height_at"):
		return float(t.height_at(x, z))
	var g := _game()
	if g.world != null:
		return g.world.height_at(x, z)
	return 0.0
