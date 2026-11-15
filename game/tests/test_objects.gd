## 配置物(ObjectLayer)と森(Forest)のテスト(architecture.md 9章・15.4)。
## 実行: godot --headless --path game --script res://tests/test_objects.gd
## Main シーンを読み込み、見本の世界(sample)で確かめる。テストが作った世界は終了時に消す。
extends SceneTree

var _pass := 0
var _fail := 0

## 見本の世界の seed(固定)。旧版の木の手前の試験は、この seed のような「開始点が別の木に重なる」場合に落ちた。
const TEST_SEED := 6
## 歩行体(半径0.3m)と幹(半径0.35m)が触れる距離は 0.65m。これを下回ったら木の中へ入っている。
const TRUNK_CONTACT_MIN := 0.6


func _init() -> void:
	# autoload(Game / Catalog)の _ready を待つ
	await process_frame
	var game := root.get_node_or_null("Game")
	var catalog := root.get_node_or_null("Catalog")
	if game == null or catalog == null:
		print("FAIL: autoload Game / Catalog が見つかりません")
		quit(1)
		return
	var saved_last := str(game.get("last_world_id"))
	var saved_quality := int(game.settings.get("quality", 1))

	var main: Node = load("res://main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	await process_frame
	game.new_world("sample", "", TEST_SEED)
	await process_frame
	var world_id: String = game.world.id

	await _run(game, main)

	main.queue_free()
	await process_frame
	game.delete_world(world_id)
	game.set("last_world_id", saved_last)
	if int(game.settings.get("quality", 1)) != saved_quality:
		game.set_setting("quality", saved_quality)
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


func _run(game: Node, main: Node) -> void:
	var catalog: Node = root.get_node("Catalog")
	# ObjectLayer / Forest は autoload を参照するため、型名では読まず実行時に load する
	var OL: GDScript = load("res://scripts/objects/object_layer.gd")
	var layer = main.objects
	var forest = main.forest
	var world: WorldData = game.world

	# ------------------------------------------------ ObjectLayer: 生成と差分更新
	_section("ObjectLayer: 生成と差分更新")
	_check(layer.get_child_count() == world.objects.size(),
		"子の数 = world.objects の数 (%d / %d)" % [layer.get_child_count(), world.objects.size()])
	var all_placed := true
	for obj in world.objects:
		var n: Variant = layer.node_of(int(obj["uid"]))
		if n == null or absf(n.position.y - world.height_at(float(obj["x"]), float(obj["z"]))) > 1e-4:
			all_placed = false
	_check(all_placed, "全ての物の高さは地形に一致")

	var toro_uid: int = game.add_object("toro", 3.0, 4.0, 0.3)
	_check(layer.get_child_count() == world.objects.size(), "追加で子が1つ増える")
	var node: Variant = layer.node_of(toro_uid)
	_check(node != null and absf(node.rotation.y - 0.3) < 1e-5, "追加した物の向き")
	_check(node != null and node.has_meta("uid") and int(node.get_meta("uid")) == toro_uid, "uid メタ")

	game.update_object(toro_uid, -20.0, 9.0, 1.0)
	node = layer.node_of(toro_uid)
	_check(node != null and absf(node.position.x + 20.0) < 1e-4 and absf(node.position.z - 9.0) < 1e-4,
		"移動で位置が追従")
	_check(node != null and absf(node.position.y - world.height_at(-20.0, 9.0)) < 1e-4, "移動後も地形の高さ")
	_check(node != null and absf(node.rotation.y - 1.0) < 1e-5, "回転が追従")

	# 地形の変化: 物の下の頂点を持ち上げて terrain_changed を流す
	var ix := roundi(-20.0 + WorldData.HALF)
	var iz := roundi(9.0 + WorldData.HALF)
	for dz in [-1, 0, 1]:
		for dx in [-1, 0, 1]:
			var k := WorldData.idx(ix + dx, iz + dz)
			world.heights[k] = world.heights[k] + 2.0
	game.terrain_changed.emit(Rect2i(ix - 1, iz - 1, 3, 3))
	node = layer.node_of(toro_uid)
	_check(node != null and absf(node.position.y - world.height_at(-20.0, 9.0)) < 1e-4,
		"地形変更で高さが追従 (y=%.3f)" % (node.position.y if node != null else -1.0))

	# 当たり: 灯籠は colliders が無いので箱(占有領域×高さ)が1つ付く
	var body: StaticBody3D = null
	if node != null:
		body = node.get_node_or_null("Body") as StaticBody3D
	_check(body != null and body.collision_layer == 2, "当たりは StaticBody3D(レイヤー2)")

	game.remove_object(toro_uid)
	_check(layer.node_of(toro_uid) == null, "削除で node_of が null")
	_check(layer.get_child_count() == world.objects.size(), "削除で子が1つ減る")

	# ------------------------------------------------ 選択・ピック・占有領域
	_section("ObjectLayer: pick・占有領域・枠")
	var haiden_uid := -1
	for obj in world.objects:
		if str(obj["type"]) == "haiden":
			haiden_uid = int(obj["uid"])
	var hn: Variant = layer.node_of(haiden_uid)
	var item: Dictionary = catalog.get_item("haiden")
	var h := float(item["height"])
	var cam := Camera3D.new()
	root.add_child(cam)
	cam.global_position = Vector3(0.0, 60.0, -20.0)
	cam.look_at(Vector3(0.0, 4.0, -30.0), Vector3.UP)
	cam.make_current()
	await process_frame
	var center := Vector3(0.0, hn.position.y + h * 0.5, -30.0)
	var sp := cam.unproject_position(center)
	_check(layer.pick(cam, sp) == haiden_uid, "物の中心のスクリーン座標で uid を返す (got %d)" % layer.pick(cam, sp))
	var sky: Vector3 = cam.global_position + (-cam.global_transform.basis.z) * 50.0 + Vector3(0.0, 100.0, 0.0)
	_check(layer.pick(cam, cam.unproject_position(sky)) == -1, "何も無い方向(空)は -1")
	_check(layer.pick(null, sp) == -1, "カメラ null は -1")

	var fp: Variant = layer.world_footprint(haiden_uid)
	var local: PackedVector2Array = catalog.footprint_polygon("haiden")
	var obj_h: Dictionary = game.get_object(haiden_uid)
	var expect := Geom.to_world(local, Vector2(float(obj_h["x"]), float(obj_h["z"])), float(obj_h["rot"]))
	var same: Variant = fp.size() == expect.size()
	for i in fp.size():
		if same and not fp[i].is_equal_approx(expect[i]):
			same = false
	_check(same, "world_footprint は Geom.to_world と一致")

	# 回転付きの物で、Node3D の変換と占有領域が一致する(符号の確認)
	var tilted_uid: int = game.add_object("toro", 5.0, -6.0, 0.7)
	var tn: Variant = layer.node_of(tilted_uid)
	var tfp: Variant = layer.world_footprint(tilted_uid)
	var tloc: PackedVector2Array = catalog.footprint_polygon("toro")
	var rot_ok := true
	for i in tloc.size():
		var w3: Variant = tn.transform * Vector3(tloc[i].x, 0.0, tloc[i].y)
		if absf(w3.x - tfp[i].x) > 1e-4 or absf(w3.z - tfp[i].y) > 1e-4:
			rot_ok = false
	_check(rot_ok, "占有領域(ワールド)と Node3D の変換が一致(回転 0.7)")
	game.remove_object(tilted_uid)

	var others: Variant = layer.all_footprints(haiden_uid)
	var non_tree := 0
	for obj in world.objects:
		if not bool(catalog.get_item(str(obj["type"])).get("tree", false)):
			non_tree += 1
	_check(others.size() == non_tree - 1, "all_footprints は木を除き、自分を除く (%d / %d)" % [others.size(), non_tree - 1])

	layer.set_highlight(haiden_uid, true)
	_check(hn.get_node_or_null("Highlight") != null, "選択の枠が付く")
	layer.set_highlight_color(haiden_uid, Color(1.0, 0.0, 0.0))
	layer.set_highlight(haiden_uid, false)
	_check(hn.get_node_or_null("Highlight") == null, "選択の枠が消える")

	var ghost: Variant = layer.make_ghost("toro")
	_check(ghost != null and not ghost.is_inside_tree() and ghost.get_node_or_null("Frame") != null,
		"make_ghost はツリー外で、枠つき")
	if ghost != null:
		ghost.free()

	# 材質: 種ごとに共有の1個。葉は ShaderMaterial、灯りも ShaderMaterial
	var leaf_a: Variant = OL.shared_material("leaf_sakura")
	var leaf_b: Variant = OL.shared_material("leaf_sakura")
	_check(leaf_a is ShaderMaterial and leaf_a == leaf_b, "leaf_sakura は共有の ShaderMaterial")
	_check(bool((leaf_a as ShaderMaterial).get_shader_parameter("deciduous")), "桜は落葉樹")
	_check(OL.shared_material("glow_lantern") is ShaderMaterial, "glow_lantern は ShaderMaterial")
	_check(OL.shared_material("water_basin") is StandardMaterial3D, "water_basin は StandardMaterial3D")
	_check(OL.shared_material("trunk") == null, "対象外の材質は null(そのまま)")
	var sugi_uid: int = game.add_object("sugi", 40.0, 40.0, 0.0)
	var sugi_mat := _override_of(layer.node_of(sugi_uid), "leaf_sugi")
	_check(sugi_mat is ShaderMaterial and not bool((sugi_mat as ShaderMaterial).get_shader_parameter("deciduous")),
		"杉の葉に常緑の葉材質が付く")
	game.remove_object(sugi_uid)

	# ------------------------------------------------ Forest
	_section("Forest")
	var t0 := Time.get_ticks_usec()
	forest.rebuild_all()
	var ms := float(Time.get_ticks_usec() - t0) / 1000.0
	var c1: Variant = forest.tree_count()
	_check(c1 > 0, "木が生成される (%d 本)" % c1)
	forest.rebuild_all()
	_check(forest.tree_count() == c1, "2回生成して同数(決定的) (%d / %d)" % [c1, forest.tree_count()])
	print("  info: 森の全再生成 %.1f ms (%d 本, 画質 %d)" % [ms, c1, int(game.settings.get("quality", 1))])

	var trunks: Variant = forest.get_trunks_near(Vector3.ZERO, 400.0)
	_check(trunks.size() == c1, "get_trunks_near で全ての木の根元が取れる (%d)" % trunks.size())
	var inside := 0
	var wet := 0
	for t in trunks:
		if t.y < WorldData.WATER_LEVEL + 0.2:
			wet += 1
		for obj in world.objects:
			if bool(catalog.get_item(str(obj["type"])).get("tree", false)):
				continue
			if Geom.point_in_polygon(Vector2(t.x, t.z), layer.world_footprint(int(obj["uid"]))):
				inside += 1
				break
	_check(inside == 0, "建物の占有領域の中に木が無い (%d)" % inside)
	_check(wet == 0, "水面の下に木が無い (%d)" % wet)

	# 歩行時の幹の当たり: 統合のままの歩行体(main.walk_mode。group "player" の CharacterBody3D)を使う
	# 試験の木は、周りに他の幹や物が無いものを選ぶ。他の木の当たりに開始点が重なると押し出されて横へ滑り、
	# 木の手前で止まらなくなる(滑って回り込むのは正しい動き。その場合は止まる試験の前提から外す)。
	var walk = main.walk_mode
	var tp := _pick_clear_tree(game.world, trunks)
	_check(tp != Vector3.ZERO, "歩行の試験に使える木(周りに他の幹や物が無い)がある")
	if tp != Vector3.ZERO:
		game.set_mode("walk")
		await process_frame
		_hide_walk_hud(main)
		var pool: Array = forest.get("_trunk_bodies")
		# 正面から歩く: 木の手前で止まる
		var r: Dictionary = await _walk_trial(main, game, forest, Vector3(tp.x - 2.0, 0.0, tp.z), -PI * 0.5, 90, false)
		var stop_x: float = (r["pos"] as Vector3).x
		var active := 0
		for b in pool:
			if (b as StaticBody3D).collision_layer == 2:
				active += 1
		_check(pool.size() == 24 and active >= 1 and active <= 24, "歩行中は近くの木に当たり(最大24) (%d)" % active)
		_check(stop_x > tp.x - 0.75 and stop_x < tp.x - 0.55,
			"木に当たって止まる (止まった x=%.2f / 木の x=%.2f)" % [stop_x, tp.x])
		_check(float(r["min_d"]) >= TRUNK_CONTACT_MIN, "歩きで木の中へ入らない (最短 %.3f m)" % float(r["min_d"]))
		# 走り(6m/s)でも木の手前で止まる
		r = await _walk_trial(main, game, forest, Vector3(tp.x - 2.0, 0.0, tp.z), -PI * 0.5, 60, true)
		stop_x = (r["pos"] as Vector3).x
		_check(stop_x > tp.x - 0.75 and stop_x < tp.x - 0.55, "走っても木の手前で止まる (止まった x=%.2f)" % stop_x)
		_check(float(r["min_d"]) >= TRUNK_CONTACT_MIN, "走りで木の中へ入らない (最短 %.3f m)" % float(r["min_d"]))
		# 正面から少しずれて歩く: 横へ滑っても木の中へは入らない
		r = await _walk_trial(main, game, forest, Vector3(tp.x - 2.0, 0.0, tp.z + 0.2), -PI * 0.5, 90, false)
		_check(float(r["min_d"]) >= TRUNK_CONTACT_MIN, "少しずれて当たっても木の中へ入らない (最短 %.3f m)" % float(r["min_d"]))
		# 木の無い道は通れる
		var path := _find_clear_path(forest, game.world)
		_check(path != Vector3.ZERO, "木も物も無い平らな 6m の道がある")
		if path != Vector3.ZERO:
			r = await _walk_trial(main, game, forest, path, -PI * 0.5, 90, false)
			var walked: float = (r["pos"] as Vector3).x - path.x
			_check(walked >= 4.0 and float(r["min_d"]) >= TRUNK_CONTACT_MIN,
				"木の無い道は歩いて通れる (進んだ %.2f m)" % walked)
		game.set_mode("edit")
		await process_frame
		await create_timer(0.35).timeout
		var off := 0
		for b in pool:
			if (b as StaticBody3D).collision_layer == 0:
				off += 1
		_check(off == pool.size(), "歩行を止めると当たりは無効")

	# ------------------------------------------------ Forest: 生成は1回・ドラッグ中は作り直さない
	_section("Forest: 生成と二重化")
	var nchunks := 0
	for c in forest.get_children():
		if str(c.name).begins_with("Chunk_"):
			nchunks += 1
	_check(nchunks == 8 * 8, "チャンクは 64 個だけ (%d)" % nchunks)

	_section("Forest: ドラッグ中は作り直さない")
	var dt_uid: int = game.add_object("toro", -100.0, -100.0, 0.0)
	await process_frame
	await process_frame
	var key := Vector2i(0, 0)   # (-100, -100) を含むチャンク(32m のチャンク、原点 -128)
	var chunk_nodes: Dictionary = forest.get("_chunk_nodes")
	var id_before: int = (chunk_nodes[key] as Node3D).get_instance_id()
	game.update_object(dt_uid, -101.0, -100.0, 0.0, false)
	game.update_object(dt_uid, -102.0, -100.0, 0.2, false)
	game.update_object(dt_uid, -103.0, -100.0, 0.3, false)
	await process_frame
	await process_frame
	chunk_nodes = forest.get("_chunk_nodes")
	_check(game.is_dragging(), "ドラッグ中は is_dragging() が true")
	_check((chunk_nodes[key] as Node3D).get_instance_id() == id_before, "ドラッグ中は森のチャンクを作り直さない")
	_check(layer.node_of(dt_uid).position.x < -102.5, "ドラッグ中も ObjectLayer は位置を追従する")
	game.commit_move(dt_uid, -100.0, -100.0, 0.0)
	_check(not game.is_dragging(), "commit_move でドラッグ終了")
	await process_frame
	await process_frame
	chunk_nodes = forest.get("_chunk_nodes")
	_check((chunk_nodes[key] as Node3D).get_instance_id() != id_before, "commit_move 後に該当チャンクを作り直す")
	game.remove_object(dt_uid)

	# ------------------------------------------------ 見本の配置
	_section("見本の配置: 木以外の占有領域どうしは重ならない")
	var solid: Array = []
	for obj in world.objects:
		if bool(catalog.get_item(str(obj["type"])).get("tree", false)):
			continue
		solid.append([str(obj["type"]), layer.world_footprint(int(obj["uid"]))])
	var clash: Array = []
	for i in solid.size():
		for j in range(i + 1, solid.size()):
			if Geom.polygons_overlap(solid[i][1], solid[j][1], 0.01):
				clash.append("%s/%s" % [solid[i][0], solid[j][0]])
	_check(clash.is_empty(), "重なり(1cm 超)が無い: %s" % str(clash))

	# ------------------------------------------------ 編集の枠(傾いた地面で潜らない)
	_section("編集の枠: 傾いた地面でも地面に潜らない")
	var em = main.edit_mode
	em.start_placing("haiden")
	var fpoly: PackedVector2Array = catalog.footprint_polygon("haiden")
	var best := Vector2.ZERO
	var best_range := -1.0
	for gz in range(-100, 101, 4):
		for gx in range(-100, 101, 4):
			var c := Vector2(gx, gz)
			var lo := INF
			var hi := -INF
			for q in Geom.to_world(fpoly, c, 0.4):
				var hq := world.height_at(q.x, q.y)
				lo = minf(lo, hq)
				hi = maxf(hi, hq)
			if hi - lo > best_range:
				best_range = hi - lo
				best = c
	em.set("_subj_pos", best)
	em.set("_subj_rot", 0.4)
	em.call("_refresh_visuals")
	var frame := em.get("_frame") as MeshInstance3D
	var verts: PackedVector3Array = frame.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var low := INF
	var high := -INF
	for v in verts:
		var g := frame.global_transform * v
		var above := g.y - world.height_at(g.x, g.z)
		low = minf(low, above)
		high = maxf(high, above)
	_check(best_range > 0.5, "傾きのある場所で確かめる (高低差 %.2f m)" % best_range)
	_check(low >= 0.1 and high <= 0.2, "枠の頂点は地形の上 0.15m (%.3f〜%.3f)" % [low, high])
	em.cancel()

	# ------------------------------------------------ 地形: 川べりと地表の境目
	_section("地形: 川べりはなだらか・地表の境目はグラデーション")
	var kink := 0.0
	var kink_mountain := 0.0
	for zz in [-80, -40, 0, 40, 80]:
		var rz: int = int(zz) + 128
		var cx: float = -40.0 + 8.0 * sin(float(zz) * 0.02)
		var row_kink := 0.0
		for kx in range(int(cx) - 7 + 128, int(cx) + 8 + 128):
			var a := world.heights[WorldData.idx(kx - 1, rz)]
			var b := world.heights[WorldData.idx(kx, rz)]
			var c2 := world.heights[WorldData.idx(kx + 1, rz)]
			row_kink = maxf(row_kink, absf(a - 2.0 * b + c2))
		print("    z=%d の川べり 折れ %.3f" % [zz, row_kink])
		if absf(float(zz)) <= 40.0:
			kink = maxf(kink, row_kink)   # 平地の川べり
		else:
			kink_mountain = maxf(kink_mountain, row_kink)
	print("  info: 川べりの最大の折れ(二階差分) %.3f m" % kink)
	# 生の地形(岸が急)は平地の川べりで折れ 1.5 m 前後。岸を広げてぼかした後は平地 0.6 以下。
	# 山の谷(|z|=80 付近)は元の地形が急なため、生の 3.3 m から 1.4 前後までしか下がらない(既知の残り)
	_check(kink <= 0.6, "平地の川べりは段差のないなだらかな斜面 (折れ %.3f m)" % kink)
	_check(kink_mountain <= 2.0, "山の谷の川べりは生の地形より折れが小さい (%.3f m、生は約3.3)" % kink_mountain)

	var soft := 0
	for rz in range(128 - 52, 128 - 18):
		for rx in range(128 - 16, 128 + 17):
			var wv := int(world.splat_b[WorldData.idx(rx, rz) * 4])   # 白砂 R
			if wv > 0 and wv < 255:
				soft += 1
	_check(soft >= 20, "境内の白砂の縁は中間の重み (%d 点)" % soft)

	cam.queue_free()


## 歩行HUDは表示中は毎フレーム stick を送るため、テストでは隠して API を直接動かす。
func _hide_walk_hud(main: Node) -> void:
	var hud = main.get("hud")
	var walk_hud = hud.get("_walk") if hud != null else null
	if walk_hud != null:
		walk_hud.visible = false


## 周りに他の幹や物が無い木を選ぶ(配列の順に最初に見つかったもの)。無ければ Vector3.ZERO。
func _pick_clear_tree(world: WorldData, trunks: Array) -> Vector3:
	for t in trunks:
		var tp: Vector3 = t
		if absf(tp.x) > 60.0 or absf(tp.z) > 60.0 or tp.y < WorldData.WATER_LEVEL + 0.5:
			continue
		if _lane_count(trunks, tp.x - 3.0, tp.x + 1.0, tp.z) == 1 and _no_objects_near(world, tp.x, tp.z, 7.0):
			return tp
	return Vector3.ZERO


## 平らで、幹も物も無い 6m の道の始点を探す(歩いて通れることの確認用)。無ければ Vector3.ZERO。
func _find_clear_path(forest: Node, world: WorldData) -> Vector3:
	var x := -90.0
	while x <= 90.0:
		var z := -90.0
		while z <= 90.0:
			var near: Array = forest.get_trunks_near(Vector3(x + 3.0, 0.0, z), 4.5)
			if _flat_run(world, x, z) and _lane_count(near, x - 0.5, x + 6.0, z) == 0 \
					and _no_objects_near(world, x + 3.0, z, 7.0):
				return Vector3(x, 0.0, z)
			z += 3.0
		x += 3.0
	return Vector3.ZERO


## x0〜x1 の帯(z の ±1.2m)にある幹の数。
func _lane_count(trunks: Array, x0: float, x1: float, z: float) -> int:
	var n := 0
	for t in trunks:
		var p: Vector3 = t
		if p.x >= x0 and p.x <= x1 and absf(p.z - z) < 1.2:
			n += 1
	return n


## (x, z) から r(m)以内に、配置物(木を含む)が無いか。
func _no_objects_near(world: WorldData, x: float, z: float, r: float) -> bool:
	for obj in world.objects:
		if absf(float(obj["x"]) - x) < r and absf(float(obj["z"]) - z) < r:
			return false
	return true


## x から 6m 先まで、水に近くなく、0.5m 進むごとの高さの差が 0.1m 以下か。
func _flat_run(world: WorldData, x: float, z: float) -> bool:
	var prev := world.height_at(x, z)
	if prev < WorldData.WATER_LEVEL + 0.5:
		return false
	for k in range(1, 13):
		var h := world.height_at(x + 0.5 * float(k), z)
		if absf(h - prev) > 0.1:
			return false
		prev = h
	return true


## 歩行体を start に置き、yaw の向きへ n 物理フレーム歩く(run で走る)。
## 戻り値: "pos" は止まった位置、"min_d" は途中で幹の中心へ最も近づいた距離(触れ始めは 0.65m)。
func _walk_trial(main: Node, game: Node, forest: Node, start: Vector3, yaw: float, n: int, run: bool) -> Dictionary:
	var walk = main.walk_mode
	walk.yaw = yaw
	walk.rotation.y = yaw
	walk.global_position = Vector3(start.x, game.world.height_at(start.x, start.z) + 0.2, start.z)
	walk.velocity = Vector3.ZERO
	await create_timer(0.35).timeout   # 幹の当たりは 0.25 秒ごとに更新される
	walk.set_run(run)
	var min_d := INF
	for i in n:
		walk.set_move_vector(Vector2(0.0, 1.0))
		await physics_frame
		var p: Vector3 = walk.global_position
		for t in forest.get_trunks_near(p, 1.5):
			var d: float = Vector2(t.x - p.x, t.z - p.z).length()
			min_d = minf(min_d, d)
	walk.set_move_vector(Vector2.ZERO)
	walk.set_run(false)
	return {"pos": walk.global_position, "min_d": min_d}


## 物のノードの中で、材質名に対応する表面の上書き材質を返す。
func _override_of(node: Node3D, mat_name: String) -> Material:
	if node == null:
		return null
	for c in _all_meshes(node):
		var mi := c as MeshInstance3D
		for s in mi.mesh.get_surface_count():
			var orig := mi.mesh.surface_get_material(s)
			if orig != null and orig.resource_name == mat_name:
				return mi.get_surface_override_material(s)
	return null


func _all_meshes(n: Node) -> Array:
	var out: Array = []
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		out.append_array(_all_meshes(c))
	return out
