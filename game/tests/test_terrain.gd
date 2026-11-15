## 地形のテスト(architecture.md 8章・13章・15.4)。実行: godot --headless --path game --script res://tests/test_terrain.gd
## autoload(Game)は root から取得する。テストが作る世界はテスト終了時に消し、last_world_id は元に戻す。
extends SceneTree

const H_EPS := 1e-3
const BRUSH_BUDGET_MS := 8.0

var _pass := 0
var _fail := 0
var _game: Node
var _saved_last := ""
var _created := ""
var _terrain: Terrain
var _tmode: TerrainMode


func _initialize() -> void:
	_game = root.get_node_or_null("Game")
	if _game == null:
		print("FAIL: autoload Game が見つかりません")
		quit(1)
		return
	_saved_last = str(_game.get("last_world_id"))
	_run()


func _run() -> void:
	_terrain = Terrain.new()
	_terrain.name = "Terrain"
	root.add_child(_terrain)
	_tmode = TerrainMode.new()
	_tmode.name = "TerrainMode"
	root.add_child(_tmode)
	_game.new_world("hills")
	_created = _game.world.id
	_check_hills_world()
	# 自動保存でテストの世界が書かれないよう、タイマーを止める
	var timer := _game.get("_save_timer") as Timer
	if timer != null:
		timer.stop()
	_terrain.rebuild_all()
	# 物理(HeightMapShape3D)の反映に物理フレームを2回待つ
	await physics_frame
	await physics_frame

	_test_brush_height()
	_test_flatten_and_smooth()
	_test_surface()
	_test_flatten_polygon()
	_test_raycast()
	await _test_collision()
	_test_undo()
	_test_incremental_matches_full()
	_test_timing()
	_test_terrain_mode()

	_cleanup()
	print("---- PASS %d / FAIL %d" % [_pass, _fail])
	quit(1 if _fail > 0 else 0)


func _check(cond: bool, label: String) -> void:
	if cond:
		_pass += 1
	else:
		_fail += 1
		print("  FAIL: %s" % label)


## 丘の世界の仕上げ: 森の塊・川べりの砂利(地表 2 = splat_a の G)があり、配置物は置かない。
func _check_hills_world() -> void:
	_section("丘の世界の仕上げ(森・砂利・配置物なし)")
	var w: WorldData = _game.world
	var forest_n := 0
	for v in w.forest:
		if v > 0:
			forest_n += 1
	_check(forest_n > 0, "hills の forest>0 のセルがある (%d)" % forest_n)
	var gravel_n := 0
	for i in WorldData.N * WorldData.N:
		if w.splat_a[i * 4 + 1] > 0:
			gravel_n += 1
	_check(gravel_n > 0, "hills に川べりの砂利がある (%d)" % gravel_n)
	_check(w.objects.is_empty(), "hills は配置物を置かない")


func _section(name: String) -> void:
	print("[%s]" % name)


func _cleanup() -> void:
	if _created != "":
		DirAccess.remove_absolute("user://worlds/%s.json" % _created)
	_game.set("last_world_id", _saved_last)
	_game.call("_save_settings")


## 高さを一定にし、地表・森を初期化して見た目を作り直す。
func _reset(h: float) -> void:
	_game.world.reset_terrain(h)
	_terrain.rebuild_all()


func _h(x: float, z: float) -> float:
	return _terrain.height_at(x, z)


## 中心の頂点だけ高くした地形(見た目も作り直す)。
func _set_center_bump(h: float) -> void:
	var hs: PackedFloat32Array = _game.world.heights
	hs[WorldData.idx(_vx(0), _vx(0))] = h
	_game.world.heights = hs
	_terrain.rebuild_all()


func _vx(x: float) -> int:
	return int(round(x + 128.0))


func _splat_bytes(which: String) -> PackedByteArray:
	return _game.world.splat_a if which == "a" else _game.world.splat_b


# ---------------------------------------------------------------- 高さのブラシ

func _test_brush_height() -> void:
	_section("brush_height: raise / lower")
	_reset(10.0)
	var c := Vector2.ZERO
	var rect := _terrain.brush_height("raise", c, 6.0, 1.0, 0.5)
	_check(absf(_h(0, 0) - 13.0) < H_EPS, "raise: 中心が strength*6m/秒*0.5秒 上がる(%.4f)" % _h(0, 0))
	_check(rect.has_point(Vector2i(_vx(0), _vx(0))), "raise: 返す Rect2i が中心の頂点を含む")
	_check(rect.size.x >= 12 and rect.size.x <= 15, "raise: Rect2i の幅が半径 6m に見合う(%s)" % str(rect))
	_check(absf(_h(20, 20) - 10.0) < H_EPS, "raise: 半径の外は変わらない")
	_terrain.brush_height("lower", c, 6.0, 1.0, 0.5)
	_check(absf(_h(0, 0) - 10.0) < H_EPS, "lower: raise と同じ量だけ下がって元に戻る")

	# 上限: H_MAX で止まる
	for i in 20:
		_terrain.brush_height("raise", c, 6.0, 1.0, 1.0)
	_check(absf(_h(0, 0) - WorldData.H_MAX) < H_EPS, "raise: H_MAX で止まる(%.3f)" % _h(0, 0))
	# 端のセル(世界の端)も変更できる。範囲外の座標で落ちない
	var edge := _terrain.brush_height("lower", Vector2(-128, -128), 4.0, 1.0, 0.1)
	_check(edge.position.x >= 0 and edge.position.y >= 0 and edge.end.x <= 257 and edge.end.y <= 257, "端のブラシ: Rect2i が世界の範囲に収まる")
	_check(_terrain.brush_height("raise", c, 6.0, 1.0, 0.0) == Rect2i(), "dt=0 は何もしない")


func _test_flatten_and_smooth() -> void:
	_section("brush_height: flatten / smooth")
	_reset(10.0)
	_terrain.set_flatten_height(12.0)
	var c := Vector2.ZERO
	for i in 60:
		_terrain.brush_height("flatten", c, 6.0, 1.0, 1.0 / 60.0)
	_check(_h(0, 0) > 11.9 and _h(0, 0) <= 12.0 + H_EPS, "flatten: 開始高さ(12m)へ寄る(%.3f)" % _h(0, 0))
	_check(absf(_h(20, 20) - 10.0) < H_EPS, "flatten: 半径の外は変わらない")

	# 開始高さの記憶: 中心が 20m の山。設定した 12m へ向かう(reset しない)
	_reset(10.0)
	_set_center_bump(20.0)
	_terrain.set_flatten_height(12.0)
	_terrain.brush_height("flatten", c, 3.0, 1.0, 0.1)
	_check(_h(0, 0) < 19.0, "flatten: 設定した開始高さ(12m)へ中心が下がる(%.3f)" % _h(0, 0))
	# reset_stroke の後は、最初の呼び出しの中心(20m)を開始高さにする
	_reset(10.0)
	_set_center_bump(20.0)
	_terrain.set_flatten_height(12.0)
	_terrain.reset_stroke()
	_terrain.brush_height("flatten", c, 3.0, 1.0, 0.1)
	_check(absf(_h(0, 0) - 20.0) < H_EPS, "flatten: reset_stroke 後は中心の高さ(20m)を保つ(%.3f)" % _h(0, 0))

	# smooth: 中心の山が近傍平均へ
	_reset(10.0)
	_set_center_bump(20.0)
	_terrain.brush_height("smooth", c, 3.0, 1.0, 0.2)
	var avg := (8.0 * 10.0 + 20.0) / 9.0
	_check(absf(_h(0, 0) - avg) < 0.01, "smooth: 中心が 3x3 平均(%.4f)へ寄る" % _h(0, 0))


# ---------------------------------------------------------------- 地表・森

func _test_surface() -> void:
	_section("brush_surface")
	_reset(5.0)
	var c := Vector2.ZERO
	var rect := _terrain.brush_surface(3, c, 6.0, 1.0, 1.0)
	var idx := WorldData.idx(_vx(0), _vx(0)) * 4
	var a := _splat_bytes("a")
	_check(rect.has_point(Vector2i(_vx(0), _vx(0))), "surface: 返す Rect2i が中心を含む")
	_check(a[idx + 2] == 255, "surface: 石畳(3)が中心で 255 まで塗れる(%d)" % a[idx + 2])
	_terrain.brush_surface(1, c, 6.0, 1.0, 1.0)
	a = _splat_bytes("a")
	_check(a[idx] == 255 and a[idx + 2] == 0, "surface: 土を塗ると石畳は比例で 0 になる")
	_terrain.brush_surface(0, c, 6.0, 1.0, 1.0)
	a = _splat_bytes("a")
	_check(a[idx] == 0 and a[idx + 2] == 0, "surface: 草(0)は他を全部減らす")

	# 乱暴な塗り重ね: 重みの合計が 255 を超えない
	var rng := RandomNumberGenerator.new()
	rng.seed = 42
	for i in 200:
		var p := Vector2(rng.randf_range(-40, 40), rng.randf_range(-40, 40))
		_terrain.brush_surface(rng.randi_range(0, 7), p, rng.randf_range(2, 20), rng.randf(), rng.randf() * 0.3)
	_check(_splat_sums_ok(), "surface: 全セルで重みの合計 <= 255")

	# splat テクスチャは 257x257 で作られている(中身の更新はヘッドレスのダミー描画では確認できない。画面で見る)
	var tex := _terrain.get("_tex_a") as ImageTexture
	_check(tex != null and tex.get_width() == WorldData.N and tex.get_height() == WorldData.N, "surface: splat テクスチャは 257x257")
	_reset(5.0)


func _splat_sums_ok() -> bool:
	var a := _splat_bytes("a")
	var b := _splat_bytes("b")
	for i in WorldData.N * WorldData.N:
		var o := i * 4
		var s := int(a[o]) + int(a[o + 1]) + int(a[o + 2]) + int(a[o + 3]) + int(b[o]) + int(b[o + 1]) + int(b[o + 2])
		if s > 255:
			return false
	return true


func _test_flatten_polygon() -> void:
	_section("flatten_polygon")
	var world: WorldData = _game.world
	# 起伏を入れてから整地する
	world.reset_terrain(0.0)
	var hs: PackedFloat32Array = world.heights
	for iz in WorldData.N:
		for ix in WorldData.N:
			hs[WorldData.idx(ix, iz)] = 3.0 * sin(float(ix) * 0.4) + 2.0 * cos(float(iz) * 0.3)
	world.heights = hs
	_terrain.rebuild_all()

	var poly := PackedVector2Array([Vector2(-24, 11), Vector2(-16, 11), Vector2(-16, 19), Vector2(-24, 19)])
	var target := _h(-20, 15)
	var far_before := _h(-60, 0)
	_terrain.flatten_polygon(poly, 1.5)
	var ok := true
	for iz in range(13, 18):
		for ix in range(-23, -16):
			if absf(_h(ix, iz) - target) > H_EPS:
				ok = false
	_check(ok, "flatten_polygon: 多角形の内側は中心の高さ(%.3f)に揃う" % target)
	_check(absf(_h(-60, 0) - far_before) < H_EPS, "flatten_polygon: 余白(margin)の外は変わらない")


# ---------------------------------------------------------------- 当たり・レイ

func _test_raycast() -> void:
	_section("raycast")
	_reset(3.0)
	var p: Variant = _terrain.raycast(Vector3(5, 50, 7), Vector3.DOWN)
	_check(p is Vector3 and (p as Vector3).distance_to(Vector3(5, 3, 7)) < 0.01, "raycast: 平地へ真下に落とすと (5,3,7)(%s)" % str(p))
	var d := Vector3(1, -1, 0).normalized()
	var q: Variant = _terrain.raycast(Vector3(0, 30, 0), d)
	_check(q is Vector3 and (q as Vector3).distance_to(Vector3(27, 3, 0)) < 0.02, "raycast: 斜めのレイが (27,3,0) で当たる(%s)" % str(q))
	_check(_terrain.raycast(Vector3(0, 10, 0), Vector3.UP) == null, "raycast: 上向きは当たらない")
	_check(_terrain.raycast(Vector3(0, 10, 0), Vector3.RIGHT) == null, "raycast: 水平(地面より上)は当たらない")
	var g: Variant = _terrain.screen_to_ground(null, Vector2.ZERO)
	_check(g == null, "screen_to_ground: カメラ無しは null")


func _test_collision() -> void:
	_section("collision (HeightMapShape3D)")
	# 方向で値が変わる線形の地形(行と列の取り違えを検出する)
	var world: WorldData = _game.world
	var hs: PackedFloat32Array = world.heights
	for iz in WorldData.N:
		for ix in WorldData.N:
			var x := float(ix) - 128.0
			var z := float(iz) - 128.0
			hs[WorldData.idx(ix, iz)] = 10.0 + 0.08 * x - 0.04 * z
	world.heights = hs
	_terrain.rebuild_all()
	await physics_frame
	await physics_frame
	var space := _terrain.get_world_3d().direct_space_state
	var pts := [Vector2(0, 0), Vector2(37.3, -21.2), Vector2(-100.5, 50.25), Vector2(127, -127), Vector2(-127.5, 127.5), Vector2(-3.7, 90.1)]
	var ok := true
	var worst := 0.0
	for pt in pts:
		var query := PhysicsRayQueryParameters3D.create(Vector3(pt.x, 100, pt.y), Vector3(pt.x, -100, pt.y))
		var res := space.intersect_ray(query)
		if not res.has("position"):
			ok = false
			print("    ray miss at %s" % str(pt))
			continue
		var dy := absf((res["position"] as Vector3).y - _h(pt.x, pt.y))
		worst = maxf(worst, dy)
		if dy > 0.02:
			ok = false
	_check(ok, "当たり: 物理の高さが height_at と一致(最大誤差 %.4f m)" % worst)
	# 元に戻す
	_reset(10.0)
	await physics_frame


# ---------------------------------------------------------------- Undo・増分更新

func _test_undo() -> void:
	_section("Undo / Redo(Game 経由)")
	_reset(10.0)
	var c := Vector2(10, 10)
	var h0 := _h(10, 10)
	var m0 := _terrain.mesh_vertex_height(_vx(10), _vx(10))
	_check(absf(m0 - h0) < H_EPS, "見た目の高さが最初から一致")
	_game.begin_stroke("height")
	var rect := _terrain.brush_height("raise", c, 6.0, 1.0, 0.5)
	_game.end_stroke(rect)
	_check(absf(_h(10, 10) - (h0 + 3.0)) < H_EPS, "ストロークで高さが上がる")
	_check(absf(_terrain.mesh_vertex_height(_vx(10), _vx(10)) - (h0 + 3.0)) < H_EPS, "ストロークで見た目も上がる")
	_game.undo()
	_check(absf(_h(10, 10) - h0) < H_EPS, "undo で元の高さに戻る")
	_check(absf(_terrain.mesh_vertex_height(_vx(10), _vx(10)) - h0) < H_EPS, "undo で見た目(チャンク)も戻る")
	_game.redo()
	_check(absf(_h(10, 10) - (h0 + 3.0)) < H_EPS, "redo でやり直せる")
	_game.undo()

	# 地表も Undo できる
	var idx := WorldData.idx(_vx(10), _vx(10)) * 4
	var before := _splat_bytes("a")[idx + 2]
	_game.begin_stroke("surface")
	var r2 := _terrain.brush_surface(3, c, 6.0, 1.0, 1.0)
	_game.end_stroke(r2)
	_check(_splat_bytes("a")[idx + 2] == 255, "地表のストロークで石畳が塗れる")
	_game.undo()
	_check(_splat_bytes("a")[idx + 2] == before, "地表の undo で元に戻る")


## 増分更新の結果が、全体を作り直した結果と一致する(継ぎ目・取り残しが無い)。
func _test_incremental_matches_full() -> void:
	_section("増分更新 = 全体再構築")
	_reset(10.0)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for i in 40:
		var p := Vector2(rng.randf_range(-120, 120), rng.randf_range(-120, 120))
		_terrain.brush_height(["raise", "lower", "smooth", "flatten"][rng.randi_range(0, 3)], p, rng.randf_range(2, 20), rng.randf(), 0.2)
	var before_v: Array = _terrain.get("_cverts").duplicate(true)
	var before_n: Array = _terrain.get("_cnorms").duplicate(true)
	_terrain.rebuild_all()
	var after_v: Array = _terrain.get("_cverts")
	var after_n: Array = _terrain.get("_cnorms")
	var worst_v := 0.0
	var worst_n := 0.0
	for k in before_v.size():
		var bv: PackedVector3Array = before_v[k]
		var av: PackedVector3Array = after_v[k]
		var bn: PackedVector3Array = before_n[k]
		var an: PackedVector3Array = after_n[k]
		for i in bv.size():
			worst_v = maxf(worst_v, bv[i].distance_to(av[i]))
			worst_n = maxf(worst_n, bn[i].distance_to(an[i]))
	_check(worst_v < 1e-4, "増分更新の頂点位置が全体再構築と一致(最大差 %.6f)" % worst_v)
	_check(worst_n < 1e-4, "増分更新の法線が全体再構築と一致(最大差 %.6f)" % worst_n)


# ---------------------------------------------------------------- 性能

func _test_timing() -> void:
	_section("性能(表示のみ。目標 %.0fms 以下)" % BRUSH_BUDGET_MS)
	_reset(10.0)
	var runs := 20
	var t0 := Time.get_ticks_usec()
	for i in runs:
		_terrain.brush_height("raise", Vector2(float(i) * 3.0 - 30.0, 0.0), 30.0, 0.5, 1.0 / 60.0)
	var ms := float(Time.get_ticks_usec() - t0) / 1000.0 / runs
	print("  brush_height(半径30m, 見た目の更新込み) 平均 %.2f ms" % ms)
	if ms > BRUSH_BUDGET_MS:
		print("  WARNING: 目標 %.0fms を超過" % BRUSH_BUDGET_MS)
	t0 = Time.get_ticks_usec()
	for i in runs:
		_terrain.brush_surface(3, Vector2(float(i) * 3.0 - 30.0, 10.0), 30.0, 0.5, 1.0 / 60.0)
	print("  brush_surface(半径30m) 平均 %.2f ms" % (float(Time.get_ticks_usec() - t0) / 1000.0 / runs))
	t0 = Time.get_ticks_usec()
	for i in runs:
		_terrain.brush_forest(Vector2(float(i) * 3.0 - 30.0, -20.0), 30.0, true, 1.0 / 60.0)
	print("  brush_forest(半径30m) 平均 %.2f ms" % (float(Time.get_ticks_usec() - t0) / 1000.0 / runs))


# ---------------------------------------------------------------- 地形モード

func _test_terrain_mode() -> void:
	_section("TerrainMode(設定値と道具)")
	_check(_tmode.tool == "raise", "既定の道具は raise")
	_check(_tmode.surface_type == 3 and absf(_tmode.radius - 6.0) < 1e-6 and absf(_tmode.strength - 0.5) < 1e-6, "既定の surface_type=3 radius=6 strength=0.5")
	var count := [0]
	_tmode.tool_changed.connect(func() -> void: count[0] += 1)
	_tmode.tool = "surface"
	_check(_tmode.tool == "surface" and count[0] == 1, "tool を変えると tool_changed が出る")
	_tmode.tool = "surface"
	_check(count[0] == 1, "同じ道具では出ない")
	_tmode.tool = "no_such_tool"
	_check(_tmode.tool == "surface", "未知の道具は受け付けない")
