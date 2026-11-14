## 森(architecture.md 9章・15.4)。Game.world.forest の濃さから決定的に木を生成する。
## 世界を 32m のチャンク(8×8)に分け、チャンクごと・樹種ごと(部品ごと)に MultiMeshInstance3D を作る。
## 歩行中は、プレイヤーの近くの木の幹に円柱の当たりを付ける(プールを使い回す)。
class_name Forest
extends Node3D

const CHUNK := 32.0
const CHUNK_COUNT := 8
const CELL := 2.5
const SPECIES := ["sugi", "kaede", "sakura", "matsu", "take"]
const SPECIES_WEIGHT := [0.45, 0.20, 0.15, 0.10, 0.10]
const RANGE_END := [70.0, 120.0, 180.0]      # 画質 0/1/2 の描画距離
const DENSITY_SCALE := [0.5, 1.0, 1.0]       # 画質 0/1/2 の密度
const EXCLUDE_MARGIN := 1.0                  # 建物の占有領域からの距離
const SLOPE_MIN_NY := 0.75
const SINK := 0.1                            # 根元を少し地面に沈める(浮き防止)
const SCALE_MIN := 0.8
const SCALE_MAX := 1.25
const WALK_RADIUS := 12.0
const TRUNK_POOL := 24
const TRUNK_RADIUS := 0.35
const TRUNK_HEIGHT := 3.0
const WALK_INTERVAL := 0.25
const DIRTY_MARGIN := 2.0

var _chunk_nodes: Dictionary = {}     # Vector2i -> Node3D
var _chunk_counts: Dictionary = {}    # Vector2i -> int(木の数)
var _chunk_trunks: Dictionary = {}    # Vector2i -> PackedVector3Array(木の根元)
var _dirty: Dictionary = {}           # Vector2i -> true(次フレームに作り直す)
var _known_rects: Dictionary = {}     # uid -> Rect2(非木の物の占有領域+余裕)
var _parts_cache: Dictionary = {}     # 樹種 -> Array[{mesh, xf, mats}]
var _seed_mix := 0
var _quality := -1
var _trunk_bodies: Array[StaticBody3D] = []
var _walk_timer := 0.0


func _ready() -> void:
	Game.world_loaded.connect(_on_world_loaded)
	Game.object_added.connect(_on_object_added)
	Game.object_changed.connect(_on_object_changed)
	Game.object_removed.connect(_on_object_removed)
	Game.terrain_changed.connect(_on_terrain_changed)
	Game.forest_changed.connect(_on_forest_changed)
	Game.settings_changed.connect(_on_settings_changed)
	_quality = _quality_level()


func _process(delta: float) -> void:
	# 同じフレームの要求はまとめて、次のフレームに1回だけ作り直す
	if not _dirty.is_empty():
		var keys := _dirty.keys()
		_dirty.clear()
		for k in keys:
			_build_chunk(k)
	_walk_timer -= delta
	if _walk_timer <= 0.0:
		_walk_timer = WALK_INTERVAL
		_update_trunk_colliders()


# ---------------------------------------------------------------- 公開API

## 全チャンクを同期的に作り直す。
func rebuild_all() -> void:
	_dirty.clear()
	_clear_chunks()
	_refresh_known()
	_quality = _quality_level()
	if Game.world == null:
		return
	for cz in CHUNK_COUNT:
		for cx in CHUNK_COUNT:
			_build_chunk(Vector2i(cx, cz))


## 生成した木の数(デバッグ・テスト用)。
func tree_count() -> int:
	var n := 0
	for c in _chunk_counts.values():
		n += int(c)
	return n


## pos から radius 以内の木の根元位置。
func get_trunks_near(pos: Vector3, radius: float) -> Array[Vector3]:
	var out: Array[Vector3] = []
	var r2 := radius * radius
	var c0 := _chunk_of(pos.x - radius, pos.z - radius)
	var c1 := _chunk_of(pos.x + radius, pos.z + radius)
	for cz in range(c0.y, c1.y + 1):
		for cx in range(c0.x, c1.x + 1):
			var key := Vector2i(cx, cz)
			if not _chunk_trunks.has(key):
				continue
			var trunks: PackedVector3Array = _chunk_trunks[key]
			for p in trunks:
				var dx := p.x - pos.x
				var dz := p.z - pos.z
				if dx * dx + dz * dz <= r2:
					out.append(p)
	return out


# ---------------------------------------------------------------- 更新の購読

## 世界の読込は Forest 自身が作る(Main は呼ばない。二重に作らない)。
func _on_world_loaded() -> void:
	rebuild_all()


func _on_object_added(uid: int) -> void:
	_set_known(uid)


## ドラッグ中(Game.is_dragging)は作り直さず、_known_rects も開始時の値のまま残す。
## ドラッグが終わって commit_move が object_changed を出した時に、開始時の範囲と終了時の範囲を1回だけ作り直す。
func _on_object_changed(uid: int) -> void:
	if Game.is_dragging():
		return
	var old: Rect2 = _known_rects.get(uid, Rect2())
	if old.has_area():
		_mark_rect(old)
	_set_known(uid)


func _on_object_removed(uid: int) -> void:
	if _known_rects.has(uid):
		_mark_rect(_known_rects[uid])
		_known_rects.erase(uid)


func _on_terrain_changed(rect: Rect2i) -> void:
	_mark_rect(_rect_world(rect).grow(DIRTY_MARGIN))


func _on_forest_changed(rect: Rect2i) -> void:
	_mark_rect(_rect_world(rect))


func _on_settings_changed() -> void:
	var q := _quality_level()
	if q != _quality:
		_quality = q
		_mark_all()


func _set_known(uid: int) -> void:
	var r := _object_rect(uid)
	if r.has_area():
		_known_rects[uid] = r
		_mark_rect(r)
	else:
		_known_rects.erase(uid)


func _refresh_known() -> void:
	_known_rects.clear()
	if Game.world == null:
		return
	for obj in Game.world.objects:
		if _is_tree(str(obj["type"])):
			continue
		_known_rects[int(obj["uid"])] = _aabb(_expanded_world(obj, EXCLUDE_MARGIN))


func _mark_rect(r: Rect2) -> void:
	var c0 := _chunk_of(r.position.x, r.position.y)
	var c1 := _chunk_of(r.end.x, r.end.y)
	for cz in range(c0.y, c1.y + 1):
		for cx in range(c0.x, c1.x + 1):
			_dirty[Vector2i(cx, cz)] = true


func _mark_all() -> void:
	for cz in CHUNK_COUNT:
		for cx in CHUNK_COUNT:
			_dirty[Vector2i(cx, cz)] = true


# ---------------------------------------------------------------- チャンク生成

func _build_chunk(key: Vector2i) -> void:
	_drop_chunk(key)
	var w := Game.world
	if w == null:
		return
	_seed_mix = int(w.seed) & 0x7fffffff
	var q := _quality_level()
	var dens_scale: float = DENSITY_SCALE[q]
	var x0 := -WorldData.HALF + key.x * CHUNK
	var z0 := -WorldData.HALF + key.y * CHUNK
	var chunk_rect := Rect2(x0, z0, CHUNK, CHUNK)
	var blockers := _blockers_in(w, chunk_rect)

	var per_species: Array = []
	for k in SPECIES.size():
		per_species.append([])
	var trunks := PackedVector3Array()
	var i0 := floori((x0 + WorldData.HALF) / CELL) - 1
	var i1 := ceili((x0 + CHUNK + WorldData.HALF) / CELL) + 1
	var j0 := floori((z0 + WorldData.HALF) / CELL) - 1
	var j1 := ceili((z0 + CHUNK + WorldData.HALF) / CELL) + 1
	for j in range(j0, j1):
		for i in range(i0, i1):
			var px := -WorldData.HALF + (i + _hash01(i, j, 1)) * CELL
			var pz := -WorldData.HALF + (j + _hash01(i, j, 2)) * CELL
			if px < x0 or px >= x0 + CHUNK or pz < z0 or pz >= z0 + CHUNK:
				continue
			if px < -WorldData.HALF or px >= WorldData.HALF or pz < -WorldData.HALF or pz >= WorldData.HALF:
				continue
			var dens := _forest_at(w, px, pz) / 255.0
			if dens <= 0.0 or _hash01(i, j, 3) >= dens * dens_scale:
				continue
			var y := w.height_at(px, pz)
			if y < WorldData.WATER_LEVEL + 0.2:
				continue
			if _slope_ny(w, px, pz) < SLOPE_MIN_NY:
				continue
			if _inside_any(Vector2(px, pz), blockers):
				continue
			var sp := _pick_species(px, pz, _hash01(i, j, 4))
			var s := lerpf(SCALE_MIN, SCALE_MAX, _hash01(i, j, 5))
			var rot := _hash01(i, j, 6) * TAU
			var xf := Transform3D(Basis(Vector3.UP, rot).scaled(Vector3(s, s, s)), Vector3(px, y - SINK, pz))
			(per_species[sp] as Array).append(xf)
			trunks.append(Vector3(px, y, pz))

	var node := Node3D.new()
	node.name = "Chunk_%d_%d" % [key.x, key.y]
	add_child(node)
	var count := 0
	for k in SPECIES.size():
		var xfs: Array = per_species[k]
		if xfs.is_empty():
			continue
		count += xfs.size()
		for part in _parts_of(SPECIES[k]):
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = part["mesh"]
			mm.instance_count = xfs.size()
			var pxf: Transform3D = part["xf"]
			for t in xfs.size():
				mm.set_instance_transform(t, (xfs[t] as Transform3D) * pxf)
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm
			mmi.visibility_range_end = RANGE_END[q]
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if q > 0 else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			node.add_child(mmi)
	_chunk_nodes[key] = node
	_chunk_counts[key] = count
	_chunk_trunks[key] = trunks


func _drop_chunk(key: Vector2i) -> void:
	if _chunk_nodes.has(key):
		var old := _chunk_nodes[key] as Node3D
		if old != null and old.get_parent() == self:
			remove_child(old)
			old.queue_free()
	_chunk_nodes.erase(key)
	_chunk_counts.erase(key)
	_chunk_trunks.erase(key)


func _clear_chunks() -> void:
	for k in _chunk_nodes.keys():
		_drop_chunk(k)


## 配置物の部品(メッシュ・ローカル変換・材質)を樹種ごとに一度だけ作る。箱の場合は先頭の MeshInstance3D だけ。
func _parts_of(tree_id: String) -> Array:
	if _parts_cache.has(tree_id):
		return _parts_cache[tree_id]
	var parts: Array = []
	var template := Catalog.instantiate(tree_id)
	var model := str(Catalog.get_item(tree_id).get("model", ""))
	var list: Array = []
	_find_meshes(template, list)
	if not ResourceLoader.exists(model) and list.size() > 1:
		list = [list[0]]
	for mi in list:
		var mesh := (mi as MeshInstance3D).mesh
		if mesh == null:
			continue
		# MultiMeshInstance3D には表面の上書きが無いので、材質を差し替えた複製メッシュを使う
		var mats: Array = []
		var changed := false
		for s in mesh.get_surface_count():
			var m: Material = null
			if (mi as MeshInstance3D).material_override != null:
				m = (mi as MeshInstance3D).material_override
			else:
				var orig := mesh.surface_get_material(s)
				if orig != null:
					m = ObjectLayer.shared_material(orig.resource_name)
			if m != null:
				changed = true
			mats.append(m)
		var out_mesh: Mesh = mesh
		if changed:
			out_mesh = mesh.duplicate()
			for s in mats.size():
				if mats[s] != null:
					out_mesh.surface_set_material(s, mats[s])
		parts.append({"mesh": out_mesh, "xf": _relative_transform(mi, template)})
	template.free()
	_parts_cache[tree_id] = parts
	return parts


static func _find_meshes(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_find_meshes(c, out)


## root からの相対変換(root 自身の変換は含めない。ObjectLayer も root に位置と向きを与える)。
static func _relative_transform(n: Node, root: Node) -> Transform3D:
	var t := Transform3D.IDENTITY
	var p: Node = n
	while p != null and p != root:
		if p is Node3D:
			t = (p as Node3D).transform * t
		p = p.get_parent()
	return t


# ---------------------------------------------------------------- 候補の判定

func _hash01(i: int, j: int, k: int) -> float:
	var h := ((i * 73856093) ^ (j * 19349663) ^ (k * 83492791) ^ (_seed_mix * 40503)) & 0x7fffffff
	h = ((h ^ (h >> 13)) * 1274126177) & 0x7fffffff
	h = (h ^ (h >> 16)) & 0x7fffffff
	return float(h) / 2147483648.0


func _forest_at(w: WorldData, x: float, z: float) -> int:
	var ix := clampi(roundi(x + WorldData.HALF), 0, WorldData.N - 1)
	var iz := clampi(roundi(z + WorldData.HALF), 0, WorldData.N - 1)
	return int(w.forest[WorldData.idx(ix, iz)])


func _slope_ny(w: WorldData, x: float, z: float) -> float:
	var gx := (w.height_at(x + 1.0, z) - w.height_at(x - 1.0, z)) * 0.5
	var gz := (w.height_at(x, z + 1.0) - w.height_at(x, z - 1.0)) * 0.5
	return 1.0 / sqrt(1.0 + gx * gx + gz * gz)


## 低周波ノイズで樹種の割合を偏らせ、同じ種がまとまる林相にする。u は [0,1) の乱数。
func _pick_species(x: float, z: float, u: float) -> int:
	var ph1 := float(_seed_mix % 997) * 0.01
	var ph2 := float(floori(float(_seed_mix) / 997.0) % 991) * 0.013
	var ws := PackedFloat32Array()
	var total := 0.0
	for k in SPECIES.size():
		var nk := 0.5 + 0.5 * sin(x * 0.045 + k * 1.7 + ph1) * cos(z * 0.038 - k * 2.3 + ph2)
		var wk := float(SPECIES_WEIGHT[k]) * (0.35 + 1.3 * nk)
		ws.append(wk)
		total += wk
	var r := u * total
	for k in SPECIES.size():
		r -= ws[k]
		if r <= 0.0:
			return k
	return SPECIES.size() - 1


## チャンクに掛かる、木以外の物の占有領域(余裕つき)。
func _blockers_in(w: WorldData, chunk_rect: Rect2) -> Array:
	var out: Array = []
	for obj in w.objects:
		if _is_tree(str(obj["type"])):
			continue
		var poly := _expanded_world(obj, EXCLUDE_MARGIN)
		if _aabb(poly).intersects(chunk_rect):
			out.append(poly)
	return out


func _inside_any(p: Vector2, polys: Array) -> bool:
	for poly in polys:
		if Geom.point_in_polygon(p, poly):
			return true
	return false


# ---------------------------------------------------------------- 歩行用の幹の当たり

func _update_trunk_colliders() -> void:
	var player := _find_walker()
	if Game.mode != "walk" or player == null:
		for b in _trunk_bodies:
			b.collision_layer = 0
		return
	_ensure_trunk_pool()
	var pp := player.global_position
	var near := get_trunks_near(pp, WALK_RADIUS)
	near.sort_custom(func(a: Vector3, b: Vector3) -> bool:
		return _dist2_xz(a, pp) < _dist2_xz(b, pp))
	for i in TRUNK_POOL:
		var body := _trunk_bodies[i]
		if i < near.size():
			body.position = near[i] + Vector3(0.0, TRUNK_HEIGHT * 0.5, 0.0)
			body.collision_layer = 2
		else:
			body.collision_layer = 0


## 歩いているプレイヤー(group "player" のうち、処理が有効なもの)。歩行モードが止まっている間は null。
## group の先頭だけを見ると、同じ group の別のノード(テスト用の仮の体など)を拾うため、有効なものを選ぶ。
func _find_walker() -> Node3D:
	if not is_inside_tree():
		return null
	for n in get_tree().get_nodes_in_group("player"):
		var body := n as Node3D
		if body != null and body.is_inside_tree() and body.can_process():
			return body
	return null


func _ensure_trunk_pool() -> void:
	if not _trunk_bodies.is_empty():
		return
	for i in TRUNK_POOL:
		var body := StaticBody3D.new()
		body.name = "TrunkBody%d" % i
		body.collision_layer = 0
		body.collision_mask = 0
		var cs := CollisionShape3D.new()
		var cyl := CylinderShape3D.new()
		cyl.radius = TRUNK_RADIUS
		cyl.height = TRUNK_HEIGHT
		cs.shape = cyl
		body.add_child(cs)
		add_child(body)
		_trunk_bodies.append(body)


static func _dist2_xz(a: Vector3, b: Vector3) -> float:
	var dx := a.x - b.x
	var dz := a.z - b.z
	return dx * dx + dz * dz


# ---------------------------------------------------------------- 幾何ヘルパ

func _quality_level() -> int:
	return clampi(int(Game.settings.get("quality", 1)), 0, 2)


func _is_tree(type: String) -> bool:
	return bool(Catalog.get_item(type).get("tree", false))


func _footprint_of(type: String) -> Vector2:
	var fp = Catalog.get_item(type).get("footprint", [])
	if fp is Array and (fp as Array).size() == 2:
		return Vector2(float(fp[0]), float(fp[1]))
	return Vector2(1.0, 1.0)


## 物の占有領域を margin だけ広げたワールド座標の多角形。
func _expanded_world(obj: Dictionary, margin: float) -> PackedVector2Array:
	var fp := _footprint_of(str(obj["type"]))
	var hw := fp.x * 0.5 + margin
	var hd := fp.y * 0.5 + margin
	var local := PackedVector2Array([Vector2(-hw, -hd), Vector2(hw, -hd), Vector2(hw, hd), Vector2(-hw, hd)])
	return Geom.to_world(local, Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))


func _object_rect(uid: int) -> Rect2:
	var obj := Game.get_object(uid)
	if obj.is_empty() or _is_tree(str(obj["type"])):
		return Rect2()
	return _aabb(_expanded_world(obj, EXCLUDE_MARGIN))


static func _aabb(poly: PackedVector2Array) -> Rect2:
	if poly.is_empty():
		return Rect2()
	var lo := poly[0]
	var hi := poly[0]
	for p in poly:
		lo = lo.min(p)
		hi = hi.max(p)
	return Rect2(lo, hi - lo)


## 頂点 index の矩形を世界座標の Rect2 にする(size は頂点の個数なので end は 1 引く)。
static func _rect_world(rect: Rect2i) -> Rect2:
	var h := WorldData.HALF
	return Rect2(rect.position.x - h, rect.position.y - h, maxf(float(rect.size.x) - 1.0, 0.0), maxf(float(rect.size.y) - 1.0, 0.0))


static func _chunk_of(x: float, z: float) -> Vector2i:
	return Vector2i(
		clampi(floori((x + WorldData.HALF) / CHUNK), 0, CHUNK_COUNT - 1),
		clampi(floori((z + WorldData.HALF) / CHUNK), 0, CHUNK_COUNT - 1))
