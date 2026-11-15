## 歩行モードのテスト(architecture.md 11章・15.3・15.4)。
## 実行: godot --headless --path game --script res://tests/test_walk.gd   (失敗が1つでもあれば終了コード 1)
## Main シーンを読み込み、Main の mode 切替(Game.set_mode)経由で enter / exit を流す。
extends SceneTree

var _pass := 0
var _fail := 0
var _unverified: Array[String] = []
var _game: Node
var _main: Node
var _walk: WalkMode
var _created: Array[String] = []
var _extra: Array[Node] = []
var _saved_last := ""


var _started := false


## autoload(Game)は run_tests.gd と同じく、最初のフレーム以降に root から取る。
func _initialize() -> void:
	_game = root.get_node_or_null("Game")


func _process(_delta: float) -> bool:
	if not _started:
		_started = true
		_run()
	return false


func _run() -> void:
	if _game == null:
		print("FAIL: autoload Game が見つかりません")
		quit(1)
		return
	_saved_last = str(_game.get("last_world_id"))
	_main = (load("res://main.tscn") as PackedScene).instantiate()
	root.add_child(_main)
	_walk = _main.get("walk_mode") as WalkMode
	await _frames(3)

	await _test_flat()
	await _test_exit()
	await _test_bounds()
	await _test_water()
	await _test_steps()
	await _test_sample()
	await _test_spot()
	await _test_cam_spot()

	_cleanup()
	for s in _unverified:
		print("  未確認: %s" % s)
	print("---- PASS %d / FAIL %d" % [_pass, _fail])
	quit(1 if _fail > 0 else 0)


func _check(cond: bool, label: String) -> void:
	if cond:
		_pass += 1
	else:
		_fail += 1
		print("  FAIL: %s" % label)


func _section(name: String) -> void:
	print("[%s]" % name)


func _frames(n: int) -> void:
	for i in n:
		await physics_frame


## 新しい世界を作る(テスト終了時に消す)。歩行中なら先に終える。
func _new_world(kind: String) -> void:
	_clear_extra()
	_game.set_mode("edit")
	_game.new_world(kind)
	_created.append(str(_game.get("world").id))
	await _frames(2)


## 編集カメラの注視点と向きを置いてから歩行へ入る。
## 歩行HUDのスティックは表示中は毎フレーム set_move_vector(0) を送るため、テストは HUD を隠して API を直接動かす。
func _start_walk(x: float, z: float, yaw_rad: float) -> void:
	var rig = _main.get("camera_rig")
	rig.target = Vector3(x, 0.0, z)
	rig.yaw = yaw_rad
	_game.set_mode("walk")
	var hud = _main.get("hud")
	var walk_hud = hud.get("_walk") if hud != null else null
	if walk_hud != null:
		walk_hud.visible = false
	await _frames(40)


func _add_box(parent: Node, pos: Vector3, size: Vector3) -> void:
	var sb := StaticBody3D.new()
	sb.collision_layer = 1  # 地形と同じレイヤー(歩行は 1+2 を当たる)
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	sb.add_child(cs)
	parent.add_child(sb)
	sb.position = pos
	_extra.append(sb)


func _clear_extra() -> void:
	for n in _extra:
		if is_instance_valid(n):
			n.queue_free()
	_extra.clear()


func _has_object_colliders() -> bool:
	var objs: Node = _main.get("objects")
	return objs.find_children("*", "StaticBody3D", true, false).size() > 0


# ---------------------------------------------------------------- flat 世界(高さ 0.5)

func _test_flat() -> void:
	_section("flat 世界: 立つ・歩く・走る・跳ぶ・見回す・視点")
	await _new_world("flat")
	await _start_walk(0.0, 20.0, 0.0)
	_check(_walk.camera.current, "歩行カメラが current になる")
	_check(absf(_walk.global_position.y - 0.5) < 0.02,
		"flat(高さ0.5)に立つ y=%.3f" % _walk.global_position.y)
	print("  info: is_on_floor=%s (地形の当たりが未実装の間は false。保険で立っている)" % str(_walk.is_on_floor()))

	# enter の二重呼び出しで位置が動かない
	var before := _walk.global_position
	_walk.enter()
	_check(before.distance_to(_walk.global_position) < 0.001, "enter を二重に呼んでも位置が変わらない")

	# 歩き: 3.2 m/s 前後
	var p0 := _walk.global_position
	_walk.set_move_vector(Vector2(0, 1))
	await _frames(60)
	var d := Vector2(_walk.global_position.x - p0.x, _walk.global_position.z - p0.z).length()
	var v := d / (60.0 / Engine.physics_ticks_per_second)
	_check(absf(v - 3.2) < 0.16, "歩き速度 %.2f m/s(3.2 前後)" % v)
	_check(_walk.global_position.z < p0.z, "前進(y=1)は yaw=0 の -Z へ進む")
	_check(absf(_walk.global_position.y - 0.5) < 0.02, "歩行中も高さ 0.5 を保つ y=%.3f" % _walk.global_position.y)
	_walk.set_move_vector(Vector2.ZERO)
	await _frames(5)

	# スティック半分: 1.6 m/s 前後
	p0 = _walk.global_position
	_walk.set_move_vector(Vector2(0, 0.5))
	await _frames(60)
	d = Vector2(_walk.global_position.x - p0.x, _walk.global_position.z - p0.z).length()
	v = d / (60.0 / Engine.physics_ticks_per_second)
	_check(absf(v - 1.6) < 0.1, "スティック半分の速さ %.2f m/s(1.6 前後)" % v)
	_walk.set_move_vector(Vector2.ZERO)
	await _frames(5)

	# 走り: 6.0 m/s 前後
	p0 = _walk.global_position
	_walk.set_run(true)
	_walk.set_move_vector(Vector2(0, 1))
	await _frames(60)
	_walk.set_run(false)
	_walk.set_move_vector(Vector2.ZERO)
	d = Vector2(_walk.global_position.x - p0.x, _walk.global_position.z - p0.z).length()
	v = d / (60.0 / Engine.physics_ticks_per_second)
	_check(absf(v - 6.0) < 0.3, "走り速度 %.2f m/s(6.0 前後)" % v)
	await _frames(5)

	# ジャンプ: 初速 4.5 m/s → 最高 約1.03m
	var y0 := _walk.global_position.y
	_walk.jump()
	var ymax := y0
	for i in 60:
		await physics_frame
		ymax = maxf(ymax, _walk.global_position.y)
	_check(ymax - y0 > 0.9 and ymax - y0 < 1.2, "ジャンプの高さ %.2f m(約1.03 m)" % (ymax - y0))
	_check(absf(_walk.global_position.y - y0) < 0.02, "着地して元の高さに戻る")

	# 見回し: 0.25°/px、drag 上で見上げる、pitch は -60〜+70 に収まる
	var yaw0 := _walk.yaw
	_walk.add_look(Vector2(100, 0))
	_check(absf(_walk.yaw - (yaw0 - deg_to_rad(25.0))) < 0.001, "右へ 100px で体の向きが 25° 右へ")
	var pitch0 := _walk.pitch
	_walk.add_look(Vector2(0, -40))
	_check(absf(_walk.pitch - (pitch0 + deg_to_rad(10.0))) < 0.001, "上へ 40px で 10° 見上げる")
	_walk.add_look(Vector2(0, -100000))
	_check(absf(_walk.pitch - deg_to_rad(70.0)) < 0.001, "見上げは +70° で止まる")
	_walk.add_look(Vector2(0, 100000))
	_check(absf(_walk.pitch - deg_to_rad(-60.0)) < 0.001, "見下ろしは -60° で止まる")
	_walk.pitch = 0.0

	# 視点: 既定は三人称、V で一人称へ
	_check(not _walk.first_person, "既定は三人称")
	_walk.toggle_view()
	_check(_walk.first_person, "toggle_view で一人称へ")
	await _frames(2)
	_check(absf(_walk.camera.position.y - 1.5) < 0.01, "一人称のカメラ高さ 1.5m(実測 %.2f)" % _walk.camera.position.y)
	_walk.toggle_view()
	await _frames(2)
	var cp := _walk.camera.position
	_check(not _walk.first_person and absf(cp.y - 1.9) < 0.05 and absf(cp.z - 3.2) < 0.05,
		"三人称のカメラ 後方3.2m・高さ1.9m(実測 z=%.2f y=%.2f)" % [cp.z, cp.y])


# ---------------------------------------------------------------- exit

func _test_exit() -> void:
	_section("exit: 編集カメラが歩行位置へ")
	var p := _walk.global_position
	_game.set_mode("edit")
	await _frames(1)
	var rig = _main.get("camera_rig")
	_check(absf(rig.target.x - p.x) < 0.01 and absf(rig.target.z - p.z) < 0.01,
		"camera_rig.target が歩行位置 (%.2f, %.2f)" % [rig.target.x, rig.target.z])
	_check(rig.camera.current, "編集カメラが current に戻る")
	var pl: Dictionary = _game.get("world").player
	_check(absf(float(pl["x"]) - p.x) < 0.01 and absf(float(pl["z"]) - p.z) < 0.01,
		"Game.world.player に歩行位置を保存")
	_check(bool(_game.get("_dirty")), "歩行を終えると世界が保存対象になる(次の保存に位置が入る)")
	_walk.exit()  # 二重に呼んでも落ちない(歩行中でなければ何もしない)
	_check(_walk.global_position.distance_to(p) < 0.001, "exit の二重呼び出しで位置が変わらない")


# ---------------------------------------------------------------- 開始位置

## 編集カメラの注視点が拝殿の真ん中でも、歩行は占有領域(+0.5m)の外から始まる。
func _test_spot() -> void:
	_section("歩行の開始位置: 物の中・物のすぐ際には立たない")
	await _new_world("sample")
	await _start_walk(0.0, -30.0, 0.0)
	var p2 := Vector2(_walk.global_position.x, _walk.global_position.z)
	var worst := INF
	var inside := false
	for obj in _game.get("world").objects:
		var item: Dictionary = _catalog().get_item(str(obj["type"]))
		if bool(item.get("tree", false)):
			continue
		var poly := Geom.to_world(_catalog().footprint_polygon(str(obj["type"])),
			Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))
		if Geom.point_in_polygon(p2, poly):
			inside = true
		worst = minf(worst, _dist_outline(p2, poly))
	_check(not inside, "物の占有領域の中に立たない (%.2f, %.2f)" % [p2.x, p2.y])
	_check(worst >= 0.49, "どの物の占有領域からも 0.5m 以上離れる (最も近い %.2f m)" % worst)
	_check(p2.distance_to(Vector2(0.0, -30.0)) < 12.0, "中心から遠くへ飛ばされない")
	_walk.set_move_vector(Vector2.ZERO)


## 見本の世界で歩行を始めた直後、三人称カメラの位置(横・縦の後方距離と実際のカメラ)が
## 木以外の占有領域(+1m)のどれにも入っていないこと。注視点・向きを変えて何通りか試す。
func _test_cam_spot() -> void:
	_section("歩行の開始位置(見本の世界): 三人称カメラの位置が物の際(+1m)に入らない")
	await _new_world("sample")
	# 鳥居(0, 22)の手前(南)から北へ向けると、アバターは物から3m以上離れるがカメラが鳥居の直下に入る
	var starts := [Vector2(0.0, 0.0), Vector2(0.0, 40.0), Vector2(0.0, -30.0), Vector2(0.0, 17.0), Vector2(0.0, 15.0)]
	var yaws := [0.0, PI * 0.5, -PI * 0.5, PI]
	for s in starts:
		for y in yaws:
			_game.set_mode("edit")   # 歩行中だと enter が早期 return するため、毎回編集へ戻してから歩行を始める
			await _frames(2)
			await _start_walk(s.x, s.y, y)
			if _walk.first_person:
				_walk.toggle_view()
				await _frames(2)
			var cams: Array[Vector3] = [
				_walk.global_transform * Vector3(0.0, WalkMode.TP_HEIGHT, WalkMode.TP_BACK),
				_walk.global_transform * Vector3(0.0, WalkMode.TP_HEIGHT, WalkMode.TP_BACK_PORTRAIT),
				_walk.camera.global_position,
			]
			var worst := INF
			for c in cams:
				worst = minf(worst, _cam_clearance(Vector2(c.x, c.z)))
			_check(worst >= 1.0,
				"(%.0f, %.0f) yaw %.0f°: 三人称カメラが占有領域(+1m)の外 (最も近い %.2f m)" % [s.x, s.y, rad_to_deg(y), worst])
			_walk.set_move_vector(Vector2.ZERO)


## 木以外の占有領域から q までの距離(q が中に入るなら 0)。
func _cam_clearance(q: Vector2) -> float:
	var best := INF
	for obj in _game.get("world").objects:
		var item: Dictionary = _catalog().get_item(str(obj["type"]))
		if bool(item.get("tree", false)):
			continue
		var poly := Geom.to_world(_catalog().footprint_polygon(str(obj["type"])),
			Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))
		if Geom.point_in_polygon(q, poly):
			return 0.0
		best = minf(best, _dist_outline(q, poly))
	return best


func _dist_outline(q: Vector2, poly: PackedVector2Array) -> float:
	var best := INF
	for i in poly.size():
		var a := poly[i]
		var b := poly[(i + 1) % poly.size()]
		var ab := b - a
		var t := clampf((q - a).dot(ab) / maxf(ab.dot(ab), 1e-9), 0.0, 1.0)
		best = minf(best, q.distance_to(a + ab * t))
	return best


func _catalog() -> Node:
	return root.get_node("Catalog")


# ---------------------------------------------------------------- 範囲

func _test_bounds() -> void:
	_section("範囲: ±127 から出ない")
	await _new_world("flat")
	await _start_walk(126.0, 0.0, -PI * 0.5)  # yaw=-90° で +X へ
	_walk.set_move_vector(Vector2(0, 1))
	await _frames(180)
	_walk.set_move_vector(Vector2.ZERO)
	var x := _walk.global_position.x
	_check(x <= 127.001 and x > 126.9, "+X へ歩いても x=%.3f で止まる(127 以内)" % x)


# ---------------------------------------------------------------- 水

func _test_water() -> void:
	_section("水: 深さ1mより深い所へ進めない")
	await _new_world("flat")
	var w: WorldData = _game.get("world")
	var hs: PackedFloat32Array = w.heights
	for iz in range(126, 131):
		for ix in range(138, 149):  # x 10..20, z -2..2 を池(床 -3.0)にする
			hs[WorldData.idx(ix, iz)] = -3.0
	w.heights = hs
	await _start_walk(3.0, 0.0, -PI * 0.5)
	_walk.set_move_vector(Vector2(0, 1))
	var xmax := -INF
	for i in 240:
		await physics_frame
		xmax = maxf(xmax, _walk.global_position.x)
	_walk.set_move_vector(Vector2.ZERO)
	await _frames(60)  # 岸で止まった後、地表へ落ち着くまで待つ
	_check(xmax > 8.5 and xmax < 9.8, "池の手前で止まる xmax=%.2f(深さ1mの縁 約9.6)" % xmax)
	var gp := _walk.global_position
	var gh := w.height_at(gp.x, gp.z)
	_check(absf(gp.y - gh) < 0.02 and gh > WorldData.WATER_LEVEL - 1.0,
		"沈まず岸(地形高さ %.2f)で立つ y=%.3f" % [gh, gp.y])


# ---------------------------------------------------------------- 段差

func _test_steps() -> void:
	_section("段差: 0.3m は乗り越え、0.6m は止まる(地形の当たりが無い平地に箱を置いて確認)")
	await _new_world("flat")
	var world_node := _walk.get_parent()
	_add_box(world_node, Vector3(22.0, 0.65, 0.0), Vector3(4.0, 0.3, 4.0))  # 上面 0.8 (段差 0.3)
	_add_box(world_node, Vector3(40.0, 0.8, 0.0), Vector3(4.0, 0.6, 4.0))   # 上面 1.1 (段差 0.6)
	await _frames(2)
	await _start_walk(16.0, 0.0, -PI * 0.5)
	_walk.set_move_vector(Vector2(0, 1))
	var on_step := false
	for i in 480:
		await physics_frame
		var p := _walk.global_position
		if p.x > 20.3 and p.x < 23.7 and p.y > 0.75:
			on_step = true
	_walk.set_move_vector(Vector2.ZERO)
	var x := _walk.global_position.x
	_check(on_step, "0.3m の段に乗る(上面 y=0.8)")
	_check(x > 36.0 and x < 37.9, "0.6m の壁の手前で止まる x=%.2f" % x)
	_check(absf(_walk.global_position.y - 0.5) < 0.02, "壁の手前で地面(0.5)に立つ y=%.3f" % _walk.global_position.y)
	_clear_extra()


# ---------------------------------------------------------------- 見本の里

func _test_sample() -> void:
	_section("見本の里: 鳥居をくぐる・拝殿の手前で止まる")
	await _new_world("sample")
	var colliders := _has_object_colliders()
	await _start_walk(0.0, 40.0, 0.0)  # 参道の手前(南)から北(-Z)へ
	_walk.set_move_vector(Vector2(0, 1))
	var torii_passed := false
	var zmin := INF
	for i in 1200:
		await physics_frame
		var z := _walk.global_position.z
		zmin = minf(zmin, z)
		if z < 17.0:
			torii_passed = true
	_walk.set_move_vector(Vector2.ZERO)
	if colliders:
		_check(torii_passed, "鳥居(z=22)をくぐって先へ進める")
		_check(zmin > -27.0, "拝殿(z=-34〜-26)の手前で止まる zmin=%.2f" % zmin)
	else:
		_unverified.append("鳥居のくぐり・拝殿の手前での停止: ObjectLayer の当たりが未実装のため確認できず(最深 z=%.2f)" % zmin)


func _cleanup() -> void:
	_clear_extra()
	_game.set_mode("edit")
	if is_instance_valid(_main):
		_main.queue_free()
	for id in _created:
		DirAccess.remove_absolute("user://worlds/%s.json" % id)
	_game.set("last_world_id", _saved_last)
	_game.call("_save_settings")
