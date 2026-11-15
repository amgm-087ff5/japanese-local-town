## 配置モード・編集カメラの確認(architecture.md 11章・15.3)。
## 実行: godot --headless --path game --script res://tests/test_edit.gd
## Main を読み込み、flat の世界で確認する。タッチは EditMode._unhandled_input に直接流す。
## テストが作った世界は終了時に消し、last_world_id は元の値に戻す(run_tests.gd と同じ方針)。
extends SceneTree

var _pass := 0
var _fail := 0
var _game = null
var _catalog = null
var _main: Node = null
var _edit = null   # EditMode(型注釈は付けない: --script 実行時に autoload 前にコンパイルされるため)
var _rig = null    # CameraRig
var _saved_last := ""
var _created_ids: Array[String] = []
var _uid_a := -1


func _initialize() -> void:
	_run()


func _run() -> void:
	_game = root.get_node_or_null("Game")
	_catalog = root.get_node_or_null("Catalog")
	if _game == null or _catalog == null:
		print("FAIL: autoload Game / Catalog が見つかりません")
		quit(1)
		return
	_saved_last = str(_game.get("last_world_id"))
	var scene: PackedScene = load("res://main.tscn")
	_main = scene.instantiate()
	root.add_child(_main)
	await process_frame
	await process_frame
	_edit = _main.get("edit_mode")
	_rig = _main.get("camera_rig")
	_game.new_world("flat")
	_created_ids.append(str(_game.world.id))
	_game.set_mode("edit")
	_game.settings["snap"] = true
	_rig.distance = 60.0
	_rig.focus(Vector3.ZERO)
	_rig.settle()
	await process_frame

	_test_placing()
	_test_selection_edit()
	_test_snap_drag()
	_test_camera_and_tap()
	_test_two_fingers()
	await _test_presets()
	await _test_clamp()
	_test_mode_change()

	_cleanup()
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


# ---------------------------------------------------------------- 入力の補助

func _touch(idx: int, p: Vector2, pressed: bool) -> void:
	var ev := InputEventScreenTouch.new()
	ev.index = idx
	ev.position = p
	ev.pressed = pressed
	_edit._unhandled_input(ev)


func _drag(idx: int, p: Vector2) -> void:
	var ev := InputEventScreenDrag.new()
	ev.index = idx
	ev.position = p
	ev.relative = Vector2.ZERO
	_edit._unhandled_input(ev)


## 世界の点 (x, z) を画面の点へ(現在のカメラ)。
func _screen_of(x: float, z: float) -> Vector2:
	var y: float = _game.world.height_at(x, z)
	return _rig.camera.unproject_position(Vector3(x, y, z))


func _min_x(poly: PackedVector2Array) -> float:
	var m := INF
	for p in poly:
		m = minf(m, p.x)
	return m


func _max_x(poly: PackedVector2Array) -> float:
	var m := -INF
	for p in poly:
		m = maxf(m, p.x)
	return m


# ---------------------------------------------------------------- 仮置き・選択

func _test_placing() -> void:
	_section("仮置き・確定・連続配置")
	var n0: int = _game.world.objects.size()
	_edit.start_placing("toro")
	_check(_edit.placing_type == "toro", "start_placing で仮置きになる")
	_edit.confirm()
	_check(_game.world.objects.size() == n0 + 1, "confirm で物が1増える")
	_check(_edit.placing_type == "toro", "連続配置: 同じ種類の仮置きが続く")
	_edit.cancel()
	_check(_edit.placing_type == "", "cancel で仮置きが消える")
	_check(_game.world.objects.size() == n0 + 1, "cancel は物を増やさない")
	_edit.continuous = false
	_edit.start_placing("toro")
	_edit.confirm()
	_check(_game.world.objects.size() == n0 + 2, "非連続の confirm も物が1増える")
	_check(_edit.placing_type == "" and _edit.selected_uid >= 0, "非連続: 確定後は選択状態")
	_edit.continuous = true
	_edit.select_object(-1)


func _test_selection_edit() -> void:
	_section("選択・回転・複製・削除・Undo")
	_edit.start_placing("toro")
	_edit.confirm()
	_edit.cancel()
	_edit.continuous = false
	_edit.start_placing("toro")
	_edit.confirm()
	_edit.continuous = true
	var uid: int = _edit.selected_uid
	_check(uid >= 0, "確定した物が選ばれている")
	var n: int = _game.world.objects.size()
	var rot0 := float(_game.get_object(uid)["rot"])
	_edit.rotate_selected(15.0)
	var rot1 := float(_game.get_object(uid)["rot"])
	_check(absf(rot1 - rot0 - deg_to_rad(15.0)) < 1e-4, "rotate_selected(15) で回転が 15° 変わる")

	var o: Dictionary = _game.get_object(uid)
	var old_p := Vector2(float(o["x"]), float(o["z"]))
	_edit.duplicate_selected()
	_check(_game.world.objects.size() == n + 1, "duplicate で物が1増える")
	var nuid: int = _edit.selected_uid
	_check(nuid >= 0 and nuid != uid, "複製が選択される")
	var o2: Dictionary = _game.get_object(nuid)
	var new_p := Vector2(float(o2["x"]), float(o2["z"]))
	var poly: PackedVector2Array = _catalog.footprint_polygon("toro")
	var width: float = poly[1].x - poly[0].x
	_check(absf(old_p.distance_to(new_p) - width) < 1e-3, "複製は占有領域の幅ぶん右へずれる (%.3f m)" % old_p.distance_to(new_p))

	_edit.delete_selected()
	_check(_game.world.objects.size() == n, "delete で複製が消える")
	_check(_edit.selected_uid == -1, "削除すると選択が解除される")
	_game.undo()
	_check(_game.world.objects.size() == n + 1, "Undo で削除が取り消される")
	_edit.select_object(-1)

	_edit.start_placing("toro")
	_edit.rotate_selected(90.0)
	var pose: Dictionary = _edit.get_subject_pose()
	_check(absf(float(pose["rot"]) - PI * 0.5) < 1e-4, "仮置き中の rotate は仮置きに効く")
	_edit.cancel()
	_check(_edit.placing_type == "", "仮置きを取り消せる")


# ---------------------------------------------------------------- スナップ・ドラッグ

func _test_snap_drag() -> void:
	_section("拝殿どうしのスナップ・物のドラッグ・Undo 1件")
	var fp: PackedVector2Array = _catalog.footprint_polygon("haiden")
	var hw: float = (fp[1].x - fp[0].x) * 0.5
	# A は (-30, 0)。B は右側に離して置き、A の右の辺から 0.5m 空けて離す(吸着距離の内側)
	var ax := -30.0
	var a: int = _game.add_object("haiden", ax, 0.0, 0.0)
	var b: int = _game.add_object("haiden", -18.0, 0.0, 0.0)
	_uid_a = a
	var expect_x := ax + 2.0 * hw
	var drop_x := expect_x + 0.5
	_edit.select_object(b)
	var press := _screen_of(-18.0, 0.0)
	# z=2.0 は角どうしが離れている(角合わせの範囲外)ので、辺に沿った位置は指のまま残る
	var mid := _screen_of(drop_x + 0.6, 1.8)
	var target := _screen_of(drop_x, 2.0)
	_touch(0, press, true)
	_drag(0, mid)
	_drag(0, target)
	_touch(0, target, false)

	var ob: Dictionary = _game.get_object(b)
	var pa := Geom.to_world(fp, Vector2(ax, 0.0), 0.0)
	var pb := Geom.to_world(fp, Vector2(float(ob["x"]), float(ob["z"])), float(ob["rot"]))
	_check(absf(float(ob["x"]) - expect_x) < 0.02, "辺に吸着して辺どうしが接する位置 (x=%.3f / 期待 %.3f)" % [float(ob["x"]), expect_x])
	_check(absf(float(ob["z"]) - 2.0) < 0.02, "辺に沿った位置は指のまま (z=%.3f)" % float(ob["z"]))
	_check(absf(float(ob["rot"])) < 1e-4, "回転は基準辺と平行 (rot=0)")
	_check(not Geom.polygons_overlap(pa, pb), "吸着後は重ならない")
	_check(absf(_max_x(pa) - _min_x(pb)) < 0.02, "辺どうしが接する (gap=%.3f)" % absf(_max_x(pa) - _min_x(pb)))

	_game.undo()
	var ob2: Dictionary = _game.get_object(b)
	_check(absf(float(ob2["x"]) + 18.0) < 1e-3 and absf(float(ob2["z"])) < 1e-3,
		"指を離した1回のドラッグは Undo 1件で元の位置に戻る")


# ---------------------------------------------------------------- カメラ・タップ

func _test_camera_and_tap() -> void:
	_section("空き地ドラッグ=カメラ・タップで選択")
	_edit.select_object(-1)
	var t0: Vector3 = _rig.target
	var p0 := _screen_of(50.0, -20.0)
	_touch(0, p0, true)
	_drag(0, p0 + Vector2(60.0, 0.0))
	_drag(0, p0 + Vector2(120.0, 0.0))
	_touch(0, p0 + Vector2(120.0, 0.0), false)
	var moved := Vector2(_rig.target.x - t0.x, _rig.target.z - t0.z).length()
	_check(moved > 1.0, "空き地ドラッグでカメラの target が動く (%.2f m)" % moved)

	var hp := _screen_of(-30.0, 0.0)
	_touch(0, hp, true)
	_touch(0, hp, false)
	_check(_edit.selected_uid == _uid_a, "物を短くタップすると選択される")

	var ep := _screen_of(60.0, -60.0)
	_touch(0, ep, true)
	_touch(0, ep, false)
	_check(_edit.selected_uid == -1, "空き地をタップすると選択が解除される")


## 物を動かしている途中で2本目の指が来たら、物を元の位置へ戻し、以後はカメラになる。
func _test_two_fingers() -> void:
	_section("2本目の指で物の移動を取り消す")
	var c: int = _game.add_object("toro", 40.0, -40.0, 0.0)
	_edit.select_object(c)
	var p0 := _screen_of(40.0, -40.0)
	var q := _screen_of(46.0, -40.0)
	_touch(0, p0, true)
	_drag(0, q)
	var mid: Dictionary = _game.get_object(c)
	_check(absf(float(mid["x"]) - 46.0) < 0.05, "物の上からのドラッグで物が動く (x=%.2f)" % float(mid["x"]))
	var p1 := _screen_of(0.0, -70.0)
	_touch(1, p1, true)
	var back: Dictionary = _game.get_object(c)
	_check(absf(float(back["x"]) - 40.0) < 1e-3 and absf(float(back["z"]) + 40.0) < 1e-3,
		"2本目の指で物の移動が元の位置へ戻る")
	# 2本指はカメラ(ピンチ・ひねり・上下)。ピンチで距離が変わる
	var d0: float = _rig.distance
	_drag(0, q + Vector2(-80.0, 0.0))
	_drag(1, p1 + Vector2(0.0, 40.0))
	_check(absf(_rig.distance - d0) > 0.01, "以後の指はカメラ操作になる (ピンチで距離が変わる)")
	var after: Dictionary = _game.get_object(c)
	_check(absf(float(after["x"]) - 40.0) < 1e-3, "取り消し後は物が動かない")
	_touch(1, p1 + Vector2(0.0, 40.0), false)
	_touch(0, q + Vector2(-80.0, 0.0), false)
	_edit.select_object(-1)


# ---------------------------------------------------------------- カメラの定位置・範囲

func _test_presets() -> void:
	_section("カメラの定位置")
	_rig.focus(Vector3.ZERO)
	var cam: Camera3D = _rig.camera
	_check(absf(cam.fov - 50.0) < 1e-3 and absf(cam.near - 0.2) < 1e-4 and absf(cam.far - 4000.0) < 1e-3,
		"カメラの画角と範囲 (fov 50 / near 0.2 / far 4000)")
	for preset in ["top", "side", "oblique", "north"]:
		_rig.set_preset(preset)
		_rig.settle()
		var fwd := -cam.global_transform.basis.z
		var origin := cam.global_transform.origin
		var ground: float = _game.world.height_at(origin.x, origin.z)
		var above := origin.y >= ground + 0.99
		var north_up := cam.unproject_position(Vector3(0.0, 0.0, -30.0)).y < cam.unproject_position(Vector3(0.0, 0.0, 30.0)).y
		var dir_ok := false
		match preset:
			"top":
				dir_ok = fwd.y < -0.99
			"side":
				dir_ok = absf(fwd.y - sin(-8.0 * PI / 180.0)) < 0.01
			"oblique":
				dir_ok = absf(fwd.y - sin(-45.0 * PI / 180.0)) < 0.01
			"north":
				dir_ok = absf(fwd.x) < 0.01 and fwd.z < 0.0
		_check(dir_ok and north_up and above, "preset %s: 所定の向き・北が画面の上・地面より上" % preset)


## 値の範囲: 距離 4〜220、pitch -89°〜-8°、注視点 ±128。直接書いた値も次のフレームで丸まる。
func _test_clamp() -> void:
	_section("範囲の制限")
	_rig.distance = 1000.0
	_rig.target = Vector3(500.0, 0.0, -500.0)
	_rig.pitch = deg_to_rad(-120.0)
	await process_frame
	await process_frame
	_check(_rig.distance <= 220.0 + 1e-3, "距離は 220m まで (%.1f)" % _rig.distance)
	_check(absf(_rig.target.x - 128.0) < 1e-3 and absf(_rig.target.z + 128.0) < 1e-3, "注視点は ±128 に制限")
	_check(absf(_rig.pitch - deg_to_rad(-89.0)) < 1e-3, "pitch は -89° まで")
	var gy: float = _game.world.height_at(_rig.target.x, _rig.target.z)
	_check(absf(_rig.target.y - gy) < 1e-3, "注視点の y は地形に追従")

	_rig.distance = 0.5
	_rig.pitch = deg_to_rad(-2.0)
	await process_frame
	await process_frame
	_check(_rig.distance >= 4.0 - 1e-3, "距離は 4m 以上")
	_check(absf(_rig.pitch - deg_to_rad(-8.0)) < 1e-3, "pitch は -8° まで")

	_rig.distance = 60.0
	_rig.pitch = deg_to_rad(-45.0)
	_rig.focus(Vector3.ZERO)
	await process_frame
	await process_frame


# ---------------------------------------------------------------- モード

func _test_mode_change() -> void:
	_section("モード切替で仮置き・選択が解除される")
	_edit.start_placing("toro")
	_game.set_mode("terrain")
	_check(_edit.placing_type == "" and _edit.selected_uid == -1, "terrain へ切り替えると仮置き・選択が解除")
	_game.set_mode("edit")
	_check(_game.mode == "edit", "edit へ戻せる")


func _cleanup() -> void:
	# 開いている世界を消すと見本が新しく作られるため、Game.delete_world は使わない
	_game.set("world", null)
	for id in _created_ids:
		DirAccess.remove_absolute("user://worlds/%s.json" % id)
	_game.set("last_world_id", _saved_last)
	_game.call("_save_settings")
