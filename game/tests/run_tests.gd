## 骨格のテスト。実行: godot --headless --path game --script res://tests/run_tests.gd
## autoload(Game / Catalog)はコンパイル時の名前では見えないため、root から取得する。
extends SceneTree

const PERF_ITERATIONS := 200
const PERF_BUDGET_MS := 1.0

var _pass := 0
var _fail := 0
var _game: Node
var _catalog: Node
var _saved_last_world := ""
var _created_ids: Array[String] = []


var _started := false


func _initialize() -> void:
	_game = root.get_node_or_null("Game")
	_catalog = root.get_node_or_null("Catalog")


## autoload の _ready は最初のフレームまでに済むので、テストは _process の初回で走らせる。
func _process(_delta: float) -> bool:
	if _started:
		return true
	_started = true
	if _game == null or _catalog == null:
		print("FAIL: autoload Game / Catalog が見つかりません")
		quit(1)
		return true
	_saved_last_world = str(_game.get("last_world_id"))
	_run_all()
	_cleanup()
	print("---- PASS %d / FAIL %d" % [_pass, _fail])
	quit(1 if _fail > 0 else 0)
	return true


func _check(cond: bool, label: String) -> void:
	if cond:
		_pass += 1
	else:
		_fail += 1
		print("  FAIL: %s" % label)


func _section(name: String) -> void:
	print("[%s]" % name)


func _run_all() -> void:
	_test_geom_to_world()
	_test_geom_polygons()
	_test_snap()
	_test_worlddata_roundtrip()
	_test_worlddata_robust()
	_test_game_objects_undo()
	_test_game_stroke_undo()
	_test_game_undo_limit()
	_test_game_save_load()
	_test_game_generation()
	_test_catalog()
	_test_snap_perf()


# ---------------------------------------------------------------- Geom

func _test_geom_to_world() -> void:
	_section("Geom.to_world と Node3D 回転の一致")
	var local := PackedVector2Array([Vector2(1.5, -0.7), Vector2(-2.0, 0.3)])
	for rot in [0.0, 0.3, 1.2, -2.0]:
		var pos := Vector2(4.0, -3.5)
		var node := Node3D.new()
		node.rotation.y = rot
		node.position = Vector3(pos.x, 0.0, pos.y)
		var world := Geom.to_world(local, pos, rot)
		for i in local.size():
			var w3 := node.transform * Vector3(local[i].x, 0.0, local[i].y)
			_check(absf(w3.x - world[i].x) < 1e-4 and absf(w3.z - world[i].y) < 1e-4,
				"to_world == Node3D (rot=%.2f, i=%d)" % [rot, i])
		node.free()


func _test_geom_polygons() -> void:
	_section("Geom 点・重なり")
	var sq := PackedVector2Array([Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)])
	_check(Geom.point_in_polygon(Vector2(0, 0), sq), "内側の点")
	_check(not Geom.point_in_polygon(Vector2(1.5, 0), sq), "外側の点")
	var far := sq.duplicate()
	for i in far.size():
		far[i] += Vector2(5, 0)
	_check(not Geom.polygons_overlap(sq, far), "離れた2つは重ならない")
	var near := sq.duplicate()
	for i in near.size():
		near[i] += Vector2(1.0, 0)
	_check(Geom.polygons_overlap(sq, near), "食い込む2つは重なる")
	var touch := sq.duplicate()
	for i in touch.size():
		touch[i] += Vector2(2.0, 0)
	_check(not Geom.polygons_overlap(sq, touch), "辺が接するだけは重ならない")


func _test_snap() -> void:
	_section("Geom.compute_snap")
	var box := PackedVector2Array([Vector2(-0.5, -0.5), Vector2(0.5, -0.5), Vector2(0.5, 0.5), Vector2(-0.5, 0.5)])
	# 相手は 4m 四方(-2..2)。動かす物は 1m 四方。角どうしは threshold/2(0.6m)より離す。
	var target := Geom.to_world(box, Vector2(0, 0), 0.0)
	target = target.duplicate()
	for i in target.size():
		target[i] *= 4.0
	var others := [target]
	var thr := 1.2

	# 平行・辺沿いの位置は保つ・接する(右辺 x=2 に、動かす物の左辺が接する → 中心 x=2.5)
	var r := Geom.compute_snap(box, Vector2(2.6, 0.4), 0.0, others, thr)
	_check(r["snapped"], "近い辺に吸着する")
	_check(absf(r["pos"].x - 2.5) < 1e-3, "垂直方向に辺へ接する (x=%.4f)" % r["pos"].x)
	_check(absf(r["pos"].y - 0.4) < 1e-3, "辺に沿った位置は保つ (z=%.4f)" % r["pos"].y)
	_check(absf(r["rot"]) < 1e-3, "回転は 0 のまま")

	# 回転ありでも基準辺と平行に、辺が接する
	var r2 := Geom.compute_snap(box, Vector2(2.7, 0.4), 0.3, others, thr)
	_check(r2["snapped"], "回転していても吸着する")
	var moved := Geom.to_world(box, r2["pos"], r2["rot"])
	var min_x := INF
	for p in moved:
		min_x = minf(min_x, p.x)
	_check(absf(min_x - 2.0) < 1e-3, "回転後も辺が接する (minx=%.4f)" % min_x)
	var q := fposmod(r2["rot"], PI * 0.5)
	_check(minf(q, PI * 0.5 - q) < 1e-3, "回転は基準辺と平行(90°の倍数)")

	# 角どうしが近ければ角も合わせる(動かす物の角 z=1.95 → 相手の角 z=2 へ)
	var r3 := Geom.compute_snap(box, Vector2(2.6, 2.45), 0.0, others, thr)
	_check(r3["snapped"], "角の近くで吸着する")
	_check(absf(r3["pos"].y - 2.5) < 1e-3, "角が threshold/2 以内なら角も合わせる (z=%.4f)" % r3["pos"].y)

	# threshold 外は吸着しない
	var r4 := Geom.compute_snap(box, Vector2(4.5, 0.0), 0.0, others, thr)
	_check(not r4["snapped"], "threshold 外は吸着しない")
	_check(r4["pos"] == Vector2(4.5, 0.0), "吸着しなければ位置は変えない")


# ---------------------------------------------------------------- WorldData

func _test_worlddata_roundtrip() -> void:
	_section("WorldData 直列化の往復")
	var w := WorldData.new()
	w.id = "rt_test"
	w.name = "往復"
	w.seed = 12345
	for i in 500:
		w.heights[i * 37 % w.heights.size()] = float(i) * 0.05 - 3.0
	w.set_surface_hard(10, 10, 3)
	w.set_surface_hard(11, 10, 6)
	w.forest[500] = 200
	w.objects.append({"uid": 7, "type": "haiden", "x": 1.5, "z": -2.25, "rot": 0.5})
	w.next_uid = 8
	w.env["season"] = 2
	var text := JSON.stringify(w.to_dict())
	var parsed = JSON.parse_string(text)
	_check(parsed is Dictionary, "JSON として読める")
	var back := WorldData.from_dict(parsed)
	_check(back.heights == w.heights, "heights が一致")
	_check(back.splat_a == w.splat_a, "splat_a が一致")
	_check(back.splat_b == w.splat_b, "splat_b が一致")
	_check(back.forest == w.forest, "forest が一致")
	_check(back.objects.size() == 1 and back.objects[0]["type"] == "haiden", "objects が一致")
	_check(int(back.objects[0]["uid"]) == 7 and back.next_uid == 8, "uid / next_uid が一致")
	_check(int(back.env["season"]) == 2, "env が一致")
	_check(back.seed == 12345 and back.id == "rt_test", "seed / id が一致")


func _test_worlddata_robust() -> void:
	_section("WorldData 壊れたデータでも落ちない")
	var empty := WorldData.from_dict({})
	_check(empty.heights.size() == WorldData.N * WorldData.N, "空の辞書 → heights は既定サイズ")
	_check(empty.splat_a.size() == WorldData.N * WorldData.N * 4, "空の辞書 → splat は既定サイズ")

	var good := WorldData.new().to_dict()
	var bad := good.duplicate(true)
	bad["heights"] = {"size": 264196, "data": "!!!not base64!!!"}
	_check(WorldData.from_dict(bad).heights.size() == WorldData.N * WorldData.N, "壊れた base64 → 既定値")
	var wrong := good.duplicate(true)
	wrong["splat_a"] = {"size": 10, "data": good["splat_a"]["data"]}
	_check(WorldData.from_dict(wrong).splat_a.size() == WorldData.N * WorldData.N * 4, "サイズ不一致 → 既定値")
	var future := good.duplicate(true)
	future["version"] = 99
	var fw := WorldData.from_dict(future)
	_check(fw.version == 99 and fw.heights.size() == WorldData.N * WorldData.N, "未知の version でも読める範囲で読む")
	var odd := good.duplicate(true)
	odd["objects"] = [{"uid": 3, "type": "torii", "x": 1.0, "z": 2.0, "rot": 0.0}, "not a dict", {"type": "x"}]
	odd["next_uid"] = 1
	var ow := WorldData.from_dict(odd)
	_check(ow.objects.size() == 1, "壊れた object 要素は無視する")
	_check(ow.next_uid >= 4, "next_uid は既存 uid より大きくする")


# ---------------------------------------------------------------- Game

func _new_test_world(kind: String) -> void:
	_game.call("new_world", kind, "テスト")
	_created_ids.append(str(_game.world.id))


func _test_game_objects_undo() -> void:
	_section("Game 物の追加・移動・削除と Undo/Redo")
	_new_test_world("flat")
	var base_count: int = _game.world.objects.size()
	var uid: int = _game.add_object("torii", 1.0, 2.0, 0.0)
	_check(_game.get_object(uid)["x"] == 1.0, "add_object で追加")
	_game.update_object(uid, 3.0, 4.0, 0.5)
	_check(_game.get_object(uid)["z"] == 4.0, "update_object(record_undo 既定) で移動")
	_game.update_object(uid, 5.0, 6.0, 1.0, false)
	_game.commit_move(uid, 3.0, 4.0, 0.5)
	_game.undo()
	var o: Dictionary = _game.get_object(uid)
	_check(absf(float(o["x"]) - 3.0) < 1e-6 and absf(float(o["rot"]) - 0.5) < 1e-6, "ドラッグの取り消しは開始位置へ")
	_game.redo()
	o = _game.get_object(uid)
	_check(absf(float(o["x"]) - 5.0) < 1e-6 and absf(float(o["rot"]) - 1.0) < 1e-6, "ドラッグのやり直し")
	_game.remove_object(uid)
	_check(_game.get_object(uid).is_empty(), "remove_object で削除")
	_game.undo()
	_check(not _game.get_object(uid).is_empty(), "削除の取り消しで復元")
	_game.redo()
	_check(_game.get_object(uid).is_empty(), "削除のやり直し")
	# 追加の取り消しを全部戻すと元の数になる
	_game.undo()
	_game.undo()
	_game.undo()
	_game.undo()
	_check(_game.world.objects.size() == base_count, "全部取り消すと元の物の数に戻る")
	_check(_game.can_redo(), "取り消した操作はやり直せる")


func _test_game_stroke_undo() -> void:
	_section("Game ストローク(地形・地表・森)の Undo/Redo")
	_new_test_world("flat")
	var counter := {"n": 0}
	var on_terrain := func(_r: Rect2i) -> void:
		counter["n"] += 1
	_game.terrain_changed.connect(on_terrain)
	var w = _game.world
	var before_h: float = w.heights[WorldData.idx(105, 105)]
	_game.begin_stroke("height")
	for iz in range(100, 111):
		for ix in range(100, 111):
			w.heights[WorldData.idx(ix, iz)] = 3.0
	_game.end_stroke(Rect2i(100, 100, 11, 11))
	_check(counter["n"] == 1, "end_stroke で terrain_changed が1回")
	_check(absf(w.heights[WorldData.idx(105, 105)] - 3.0) < 1e-6, "ストローク後の高さ")
	_game.undo()
	_check(absf(w.heights[WorldData.idx(105, 105)] - before_h) < 1e-6, "高さの Undo")
	_game.redo()
	_check(absf(w.heights[WorldData.idx(105, 105)] - 3.0) < 1e-6, "高さの Redo")
	_game.terrain_changed.disconnect(on_terrain)

	_game.begin_stroke("surface")
	for ix in range(20, 26):
		w.set_surface_hard(ix, 20, 5)
	_game.end_stroke(Rect2i(20, 20, 6, 1))
	_check(w.get_surface_weight(22, 20, 5) == 255, "地表を塗れる")
	_game.undo()
	_check(w.get_surface_weight(22, 20, 5) == 0, "地表の Undo")

	_game.begin_stroke("forest")
	w.forest[WorldData.idx(50, 50)] = 255
	_game.end_stroke(Rect2i(50, 50, 1, 1))
	_game.undo()
	_check(w.forest[WorldData.idx(50, 50)] == 0, "森の Undo")
	_game.redo()
	_check(w.forest[WorldData.idx(50, 50)] == 255, "森の Redo")

	# 変化がない・空の矩形は Undo に積まない
	_new_test_world("flat")
	_game.begin_stroke("height")
	_game.end_stroke(Rect2i(10, 10, 4, 4))
	_check(not _game.can_undo(), "変化なしのストロークは Undo に積まない")
	_game.begin_stroke("height")
	_game.end_stroke(Rect2i())
	_check(not _game.can_undo(), "空の矩形のストロークは無視")


func _test_game_undo_limit() -> void:
	_section("Game Undo の上限(30件)")
	_new_test_world("flat")
	for i in 40:
		_game.add_object("torii", float(i), 0.0, 0.0)
	var steps := 0
	while _game.can_undo():
		_game.undo()
		steps += 1
	_check(steps == 30, "Undo は最大30件 (実際 %d)" % steps)


func _test_game_save_load() -> void:
	_section("Game 保存・読込(異常系を含む)")
	_new_test_world("hills")
	var id: String = _game.world.id
	var path := "user://worlds/%s.json" % id
	_game.add_object("sugi", 2.0, 3.0, 0.1)
	_check(_game.save_world(), "save_world が成功")
	_check(FileAccess.file_exists(path), "保存ファイルができる")
	_check(not FileAccess.file_exists(path + ".tmp"), "一時ファイルが残らない")
	var h_saved: float = _game.world.heights[WorldData.idx(128, 128)]
	_check(_game.load_world(id), "load_world が成功")
	_check(absf(_game.world.heights[WorldData.idx(128, 128)] - h_saved) < 1e-6, "読込後の高さが一致")
	_check(_game.world.objects.size() >= 1, "読込後に物が残る")

	# 壊れた JSON
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string("{\"version\": 1, \"heights\": {broken")
	f = null
	_check(not _game.load_world(id), "壊れた JSON は false")
	_check(_game.world != null and _game.world.id == id, "失敗時も現在の世界は変わらない")

	# 未知の version
	var good := WorldData.new()
	good.id = id
	var d := good.to_dict()
	d["version"] = 99
	f = FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(d))
	f = null
	_check(_game.load_world(id), "未知の version でも読める")
	_check(int(_game.world.version) == 99, "version は読んだ値を保持")

	_check(not _game.load_world("no_such_world_xyz"), "存在しない id は false")
	var listed: Array = _game.list_worlds()
	_check(listed.size() >= 1, "list_worlds に保存済みの世界が出る")


func _test_game_generation() -> void:
	_section("Game 世界の生成(flat / hills / sample)")
	var sizes_ok := true
	for kind in ["flat", "hills", "sample"]:
		_new_test_world(kind)
		var w = _game.world
		var n := WorldData.N * WorldData.N
		if w.heights.size() != n or w.splat_a.size() != n * 4 or w.splat_b.size() != n * 4 or w.forest.size() != n:
			sizes_ok = false
		print("  %s: objects=%d forest>0=%d" % [kind, w.objects.size(), _count_nonzero(w.forest)])
	_check(sizes_ok, "3種とも配列サイズが正しい")

	_new_test_world("flat")
	var flat_ok := true
	for h in _game.world.heights:
		if absf(h - 0.5) > 1e-6:
			flat_ok = false
	_check(flat_ok, "flat は高さ 0.5 の平地")

	_new_test_world("hills")
	var w = _game.world
	var lo := INF
	var hi := -INF
	for h in w.heights:
		lo = minf(lo, h)
		hi = maxf(hi, h)
	_check(lo >= WorldData.H_MIN - 1e-4 and hi <= WorldData.H_MAX + 1e-4, "hills の高さは範囲内 (%.2f..%.2f)" % [lo, hi])
	_check(w.height_at(-40.0, 0.0) < WorldData.WATER_LEVEL, "川は水位より下")
	_check(absf(w.height_at(0.0, 0.0) - w.height_at(2.0, 2.0)) < 0.5, "中央付近は平ら")

	_new_test_world("sample")
	w = _game.world
	var types := {}
	for o in w.objects:
		types[o["type"]] = true
	_check(types.has("haiden") and types.has("honden") and types.has("torii"), "見本に神社の主要な物がある")
	_check(w.objects.size() >= 30, "見本の物の数 (%d)" % w.objects.size())
	_check(_count_nonzero(w.forest) > 1000, "見本の周囲は森")
	_check(w.get_surface_weight(128, 140, 3) == 255, "参道(x=0, z=12)は石畳")
	_check(_game.world.next_uid > w.objects.size(), "next_uid は既存より大きい")


func _count_nonzero(a: PackedByteArray) -> int:
	var c := 0
	for v in a:
		if v != 0:
			c += 1
	return c


# ---------------------------------------------------------------- Catalog

func _test_catalog() -> void:
	_section("Catalog")
	var ids := ["haiden", "honden", "torii", "torii_ishi", "toro", "komainu_a", "komainu_un", "chozuya",
		"shamusho", "tamagaki", "ishidan", "hashi", "jizo", "ie_kawara", "ie_kayabuki", "denchu",
		"iwa_l", "iwa_s", "sugi", "sakura", "kaede", "matsu", "take"]
	var ok := true
	for id in ids:
		var node: Node3D = _catalog.instantiate(id)
		if node == null:
			ok = false
		else:
			node.free()
	_check(ok, "全ての既定 id を instantiate できる(箱でもよい)")
	var poly: PackedVector2Array = _catalog.footprint_polygon("haiden")
	_check(poly.size() == 4, "占有領域は4頂点")
	var item: Dictionary = _catalog.get_item("haiden")
	_check(item.get("category", "") == "shrine", "拝殿は shrine")
	_check(_catalog.get_item("no_such_item").is_empty(), "未知の id は空")
	_check(_catalog.footprint_polygon("no_such_item").size() == 4, "未知の id の占有領域は既定値")
	_check(_catalog.tree_ids().has("sugi"), "tree_ids に杉")


# ---------------------------------------------------------------- 性能(表示のみ・超過は警告)

func _test_snap_perf() -> void:
	_section("compute_snap の時間(物100個)")
	var box := PackedVector2Array([Vector2(-2, -2), Vector2(2, -2), Vector2(2, 2), Vector2(-2, 2)])
	var others: Array = []
	for i in 100:
		var c := Vector2(float(i % 10) * 6.0 - 30.0, float(i / 10) * 6.0 - 30.0)
		others.append(Geom.to_world(box, c, 0.0))
	var t0 := Time.get_ticks_usec()
	for _k in PERF_ITERATIONS:
		Geom.compute_snap(box, Vector2(0.5, 0.5), 0.0, others, 1.2)
	var per_ms := float(Time.get_ticks_usec() - t0) / 1000.0 / PERF_ITERATIONS
	print("  compute_snap 1回: %.4f ms" % per_ms)
	if per_ms > PERF_BUDGET_MS:
		print("  WARNING: 目標 %.1f ms を超えています(表示のみ・失敗にはしない)" % PERF_BUDGET_MS)


# ---------------------------------------------------------------- 後始末

func _cleanup() -> void:
	# delete_world は使わない(開いている世界を消すと見本が新しく作られるため)
	for id in _created_ids:
		DirAccess.remove_absolute("user://worlds/%s.json" % id)
	_game.set("last_world_id", _saved_last_world)
	_game.call("_save_settings")
