## 配置物の表示・当たり・選択・灯り(architecture.md 9章・15.4)。
## 各物は Catalog.instantiate のノードを子にし、高さは地形に追従する。
## 材質は名前で判定し、種類ごとに共有の材質を1つだけ作って使い回す(static の shared_material)。
class_name ObjectLayer
extends Node3D

const LEAF_KINDS := ["sugi", "matsu", "take", "sakura", "kaede"]
const DECIDUOUS_KINDS := ["sakura", "kaede"]
const FOLIAGE_SHADER := preload("res://scripts/objects/foliage.gdshader")
const GLOW_SHADER := preload("res://scripts/objects/glow.gdshader")
const ROOF_SHADER := preload("res://scripts/objects/roof.gdshader")

const BODY_LAYER := 2
const HIGHLIGHT_COLOR := Color(0.784, 0.271, 0.173)   # 朱 #C8452C
const HIGHLIGHT_WIDTH := 0.12
const HIGHLIGHT_LIFT := 0.15   # 枠は各頂点の地形の高さ+この高さ(傾いた地面で潜らない)
const GHOST_ALPHA := 0.45
const TERRAIN_MARGIN := 0.5
const LIGHT_POOL := 4
const LIGHT_RANGE := 7.0
const LIGHT_INTERVAL := 0.5
const LANTERN_LIGHT_HEIGHT := 0.8   # 灯籠の高さのこの割合に光源を置く

## 材質名 -> 共有の Material(static: Forest も同じ材質を使う)
static var _shared: Dictionary = {}

var _nodes: Dictionary = {}        # uid -> Node3D
var _hl_on: Dictionary = {}        # uid -> 枠の色(表示中のもの)
var _hl_color: Dictionary = {}     # uid -> 既定以外の枠の色
var _hl_nodes: Dictionary = {}     # uid -> MeshInstance3D(枠)
var _half_diag_cache: Dictionary = {}
var _lights: Array = []            # OmniLight3D(灯籠ライト。親は灯籠のノード)
var _light_timer := 0.0


func _ready() -> void:
	Game.world_loaded.connect(rebuild_all)
	Game.object_added.connect(_on_added)
	Game.object_changed.connect(_on_changed)
	Game.object_removed.connect(_on_removed)
	Game.terrain_changed.connect(_on_terrain_changed)
	Game.settings_changed.connect(_on_settings_changed)


func _process(delta: float) -> void:
	_light_timer -= delta
	if _light_timer <= 0.0:
		_light_timer = LIGHT_INTERVAL
		_update_lights()


# ---------------------------------------------------------------- 共有の材質

## 材質名から共有の Material を返す。対象外の名前は null(元の材質をそのまま使う)。
static func shared_material(mat_name: String, orig: Material = null) -> Material:
	if _shared.has(mat_name):
		return _shared[mat_name]
	var m: Material = null
	if mat_name.begins_with("leaf_"):
		var k := LEAF_KINDS.find(mat_name.substr(5))
		if k >= 0:
			m = _leaf_material(k)
	elif mat_name.begins_with("roof_"):
		m = _roof_material(orig)
	elif mat_name == "glow_lantern":
		m = _glow_material(true)
	elif mat_name == "glow_window":
		m = _glow_material(false)
	elif mat_name == "water_basin":
		m = _water_material()
	if m != null:
		_shared[mat_name] = m
	return m


static func _leaf_material(kind_index: int) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = FOLIAGE_SHADER
	m.set_shader_parameter("kind", kind_index)
	m.set_shader_parameter("deciduous", DECIDUOUS_KINDS.has(LEAF_KINDS[kind_index]))
	return m


static func _glow_material(lantern: bool) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = GLOW_SHADER
	if lantern:
		m.set_shader_parameter("glow_color", Color(1.0, 0.55, 0.15, 1.0))
		m.set_shader_parameter("glow_strength", 2.2)
	else:
		m.set_shader_parameter("glow_color", Color(1.0, 0.9, 0.55, 1.0))
		m.set_shader_parameter("glow_strength", 1.6)
	return m


static func _water_material() -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.42, 0.66, 0.78)
	m.roughness = 0.12
	m.metallic_specular = 0.6
	return m


## ノードの材質を差し替える(名前で判定。対象外はそのまま)。
static func apply_materials(root: Node) -> void:
	if root is MeshInstance3D:
		var mi := root as MeshInstance3D
		if mi.mesh != null:
			for s in mi.mesh.get_surface_count():
				var orig := mi.mesh.surface_get_material(s)
				if orig == null:
					continue
				var shared := shared_material(orig.resource_name, orig)
				if shared != null:
					mi.set_surface_override_material(s, shared)
	for c in root.get_children():
		apply_materials(c)


# ---------------------------------------------------------------- 公開API

func rebuild_all() -> void:
	for n in _nodes.values():
		var node := n as Node3D
		if node != null and node.get_parent() == self:
			remove_child(node)
			node.queue_free()
	_nodes.clear()
	_hl_nodes.clear()
	_lights.clear()
	if Game.world == null:
		return
	for obj in Game.world.objects:
		_spawn(obj)


func node_of(uid: int) -> Node3D:
	return _nodes.get(uid) as Node3D


## 画面座標の位置にある物の uid(最も手前)。物理に頼らず、各物の向き付きの箱(footprint×height)とレイを交差させる。無ければ -1。
func pick(camera: Camera3D, screen_pos: Vector2) -> int:
	if camera == null or Game.world == null:
		return -1
	var origin := camera.project_ray_origin(screen_pos)
	var dir := camera.project_ray_normal(screen_pos)
	var best_t := INF
	var best := -1
	for obj in Game.world.objects:
		var uid := int(obj["uid"])
		var node := _nodes.get(uid) as Node3D
		if node == null or not node.is_inside_tree():
			continue
		var item := Catalog.get_item(str(obj["type"]))
		var fp := _footprint_vec(item)
		var h := float(item.get("height", 1.0))
		var inv := node.global_transform.affine_inverse()
		var lo := inv * origin
		var ld := inv.basis * dir
		var t := _ray_box(lo, ld, Vector3(-fp.x * 0.5, 0.0, -fp.y * 0.5), Vector3(fp.x * 0.5, h, fp.y * 0.5))
		if t >= 0.0 and t < best_t:
			best_t = t
			best = uid
	return best


## 選択の枠(占有領域の輪郭・地面より少し上・朱色)を表示/非表示にする。
func set_highlight(uid: int, on: bool) -> void:
	if on:
		if not _hl_on.has(uid):
			_hl_on[uid] = _hl_color.get(uid, HIGHLIGHT_COLOR)
			_rebuild_highlight(uid)
	else:
		_hl_on.erase(uid)
		_remove_highlight(uid)


## 枠の色(重なり警告などに使う)。表示中なら即座に変える。
func set_highlight_color(uid: int, color: Color) -> void:
	_hl_color[uid] = color
	if _hl_on.has(uid):
		_hl_on[uid] = color
		var mi := _hl_nodes.get(uid) as MeshInstance3D
		if mi != null:
			(mi.material_override as StandardMaterial3D).albedo_color = color
		else:
			_rebuild_highlight(uid)


## 物の占有領域(ワールド座標の4頂点)。
func world_footprint(uid: int) -> PackedVector2Array:
	var obj := Game.get_object(uid)
	if obj.is_empty():
		return PackedVector2Array()
	return _footprint_world(obj)


## 木(tree=true)を除く、他の物の占有領域。木にはスナップしない。
func all_footprints(except_uid: int) -> Array:
	var out: Array = []
	if Game.world == null:
		return out
	for obj in Game.world.objects:
		if int(obj["uid"]) == except_uid or _is_tree(str(obj["type"])):
			continue
		out.append(_footprint_world(obj))
	return out


## 仮置き用の見た目(半透明)+占有領域の枠。ツリーには追加せず返す(EditMode が追加する)。
func make_ghost(type: String) -> Node3D:
	var node := Catalog.instantiate(type)
	_ghostify(node)
	var frame := MeshInstance3D.new()
	frame.name = "Frame"
	frame.mesh = outline_mesh(Catalog.footprint_polygon(type), func(_p: Vector2) -> float: return HIGHLIGHT_LIFT)  # 平地用。傾きに合わせる枠は EditMode が持つ
	frame.material_override = _frame_material(HIGHLIGHT_COLOR)
	frame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(frame)
	return node


# ---------------------------------------------------------------- 生成・配置

func _spawn(obj: Dictionary) -> void:
	var uid := int(obj["uid"])
	var type := str(obj["type"])
	var node := Catalog.instantiate(type)
	node.set_meta("uid", uid)
	apply_materials(node)
	_add_colliders(node, type)
	add_child(node)
	_nodes[uid] = node
	_place(node, obj)


func _place(node: Node3D, obj: Dictionary) -> void:
	var uid := int(obj["uid"])
	var x := float(obj["x"])
	var z := float(obj["z"])
	node.position = Vector3(x, Game.world.height_at(x, z), z)
	node.rotation.y = float(obj["rot"])
	if _hl_on.has(uid):
		_rebuild_highlight(uid)


func _add_colliders(node: Node3D, type: String) -> void:
	var boxes = Catalog.get_item(type).get("colliders", [])
	if not (boxes is Array) or (boxes as Array).is_empty():
		return
	var body := StaticBody3D.new()
	body.name = "Body"
	body.collision_layer = BODY_LAYER
	body.collision_mask = 0
	for b in boxes:
		if not (b is Dictionary):
			continue
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = _vec3(b.get("size", [1.0, 1.0, 1.0]), Vector3.ONE)
		cs.shape = box
		cs.position = _vec3(b.get("pos", [0.0, 0.0, 0.0]), Vector3.ZERO)
		body.add_child(cs)
	node.add_child(body)


func _on_added(uid: int) -> void:
	var obj := Game.get_object(uid)
	if not obj.is_empty() and not _nodes.has(uid):
		_spawn(obj)


func _on_changed(uid: int) -> void:
	var obj := Game.get_object(uid)
	if obj.is_empty() or not _nodes.has(uid):
		return
	_place(_nodes[uid] as Node3D, obj)


func _on_removed(uid: int) -> void:
	if _nodes.has(uid):
		var node := _nodes[uid] as Node3D
		_nodes.erase(uid)
		_hl_on.erase(uid)
		_hl_nodes.erase(uid)
		if node != null:
			remove_child(node)
			node.queue_free()


## 矩形(頂点 index)に掛かる物の高さを追従させる。
func _on_terrain_changed(rect: Rect2i) -> void:
	if Game.world == null:
		return
	var r := _rect_world(rect)
	for obj in Game.world.objects:
		var uid := int(obj["uid"])
		var node := _nodes.get(uid) as Node3D
		if node == null:
			continue
		var c := Vector2(float(obj["x"]), float(obj["z"]))
		var reach := _half_diag(str(obj["type"])) + TERRAIN_MARGIN
		if c.x + reach < r.position.x or c.x - reach > r.end.x or c.y + reach < r.position.y or c.y - reach > r.end.y:
			continue
		_place(node, obj)


func _on_settings_changed() -> void:
	_update_lights()


# ---------------------------------------------------------------- 枠(選択・ゴースト)

func _rebuild_highlight(uid: int) -> void:
	var node := _nodes.get(uid) as Node3D
	if node == null or not node.is_inside_tree():
		return
	_remove_highlight(uid)
	var color: Color = _hl_on.get(uid, HIGHLIGHT_COLOR)
	var mi := MeshInstance3D.new()
	mi.name = "Highlight"
	mi.mesh = outline_mesh(Catalog.footprint_polygon(str(Game.get_object(uid).get("type", ""))), func(p: Vector2) -> float:
		var g := node.to_global(Vector3(p.x, 0.0, p.y))
		return Game.world.height_at(g.x, g.z) - node.global_position.y + HIGHLIGHT_LIFT)
	mi.material_override = _frame_material(color)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(mi)
	_hl_nodes[uid] = mi


func _remove_highlight(uid: int) -> void:
	var mi := _hl_nodes.get(uid) as MeshInstance3D
	if mi != null:
		if mi.get_parent() != null:
			mi.get_parent().remove_child(mi)
		mi.queue_free()
	_hl_nodes.erase(uid)


static func _frame_material(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


## 占有領域の輪郭を細い帯にする(三角形)。height_fn(局所の点) が帯の高さ(局所 y)を返す。width は帯の太さ(m)。
static func outline_mesh(poly: PackedVector2Array, height_fn: Callable, width := HIGHLIGHT_WIDTH) -> ArrayMesh:
	var verts := PackedVector3Array()
	var n := poly.size()
	for i in n:
		var a := poly[i]
		var b := poly[(i + 1) % n]
		var d := b - a
		var len := d.length()
		if len < 1e-4:
			continue
		var side := Vector2(-d.y, d.x) / len * (width * 0.5)
		var steps := maxi(1, ceili(len))
		for s in steps:
			var p0 := a.lerp(b, float(s) / steps)
			var p1 := a.lerp(b, float(s + 1) / steps)
			var l0 := p0 + side
			var r0 := p0 - side
			var l1 := p1 + side
			var r1 := p1 - side
			var v_l0 := Vector3(l0.x, height_fn.call(l0), l0.y)
			var v_r0 := Vector3(r0.x, height_fn.call(r0), r0.y)
			var v_l1 := Vector3(l1.x, height_fn.call(l1), l1.y)
			var v_r1 := Vector3(r1.x, height_fn.call(r1), r1.y)
			verts.append(v_l0)
			verts.append(v_r0)
			verts.append(v_l1)
			verts.append(v_r0)
			verts.append(v_r1)
			verts.append(v_l1)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	var mesh := ArrayMesh.new()
	if not verts.is_empty():
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


## ゴースト化: 材質を半透明にし、影を落とさない。
static func _ghostify(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh != null:
			for s in mi.mesh.get_surface_count():
				mi.set_surface_override_material(s, _ghost_material(mi.get_active_material(s)))
		if mi.material_override != null:
			mi.material_override = _ghost_material(mi.material_override)
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	for c in n.get_children():
		_ghostify(c)


## 屋根の材質(roof.gdshader)。元の色と粗さを引き継ぎ、雪は g_snow で決まる。
static func _roof_material(orig: Material) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = ROOF_SHADER
	var c := Color(0.5, 0.5, 0.5)
	var r := 0.8
	if orig is BaseMaterial3D:
		c = (orig as BaseMaterial3D).albedo_color
		r = (orig as BaseMaterial3D).roughness
	m.set_shader_parameter("albedo_color", c)
	m.set_shader_parameter("roughness_base", r)
	return m


static func _ghost_material(src: Material) -> StandardMaterial3D:
	var g := StandardMaterial3D.new()
	if src is StandardMaterial3D:
		g.albedo_color = (src as StandardMaterial3D).albedo_color
	elif src is ShaderMaterial and (src as ShaderMaterial).get_shader_parameter("albedo_color") is Color:
		g.albedo_color = (src as ShaderMaterial).get_shader_parameter("albedo_color")
	else:
		g.albedo_color = Color(0.92, 0.92, 0.88)
	g.albedo_color.a = GHOST_ALPHA
	g.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	g.roughness = 0.9
	return g


# ---------------------------------------------------------------- 灯籠ライト

func _update_lights() -> void:
	if not _want_lights():
		for l in _lights:
			if is_instance_valid(l):
				(l as Light3D).visible = false
		return
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	if cam == null or Game.world == null:
		return
	var cands: Array = []   # [距離², 灯籠ノード, 高さ]
	for obj in Game.world.objects:
		var item := Catalog.get_item(str(obj["type"]))
		if str(item.get("glow", "")) != "lantern":
			continue
		var node := _nodes.get(int(obj["uid"])) as Node3D
		if node == null:
			continue
		cands.append([node.global_position.distance_squared_to(cam.global_position), node,
			float(item.get("height", 1.0))])
	cands.sort_custom(func(a: Array, b: Array) -> bool: return float(a[0]) < float(b[0]))
	for i in LIGHT_POOL:
		var light := _light(i)
		if i < cands.size():
			var holder := cands[i][1] as Node3D
			if light.get_parent() != holder:
				if light.get_parent() != null:
					light.get_parent().remove_child(light)
				holder.add_child(light)
			light.position = Vector3(0.0, float(cands[i][2]) * LANTERN_LIGHT_HEIGHT, 0.0)
			light.visible = true
		else:
			light.visible = false


## 灯籠ライトを出すか: 画質2 かつ夜。夜の判定は main.env.is_night()(あれば)。無ければ世界の時刻で同じ基準を使う。
func _want_lights() -> bool:
	if int(Game.settings.get("quality", 1)) != 2:
		return false
	var main: Node = get_tree().get_first_node_in_group("main") if is_inside_tree() else null
	var env = main.get("env") if main != null else null
	if env != null and env.has_method("is_night"):
		return bool(env.call("is_night"))
	if Game.world == null:
		return false
	var t := float(Game.world.env.get("time", 9.0))
	return t < 5.5 or t > 18.5


func _light(i: int) -> OmniLight3D:
	while _lights.size() <= i:
		_lights.append(null)
	var l = _lights[i]
	if l == null or not is_instance_valid(l):
		var light := OmniLight3D.new()
		light.name = "LanternLight"
		light.omni_range = LIGHT_RANGE
		light.light_color = Color(1.0, 0.6, 0.25)
		light.light_energy = 1.8
		light.shadow_enabled = false
		light.visible = false
		_lights[i] = light
		return light
	return l as OmniLight3D


# ---------------------------------------------------------------- 幾何ヘルパ

func _footprint_vec(item: Dictionary) -> Vector2:
	var fp = item.get("footprint", [])
	if fp is Array and (fp as Array).size() == 2:
		return Vector2(float(fp[0]), float(fp[1]))
	return Vector2(1.0, 1.0)


func _footprint_world(obj: Dictionary) -> PackedVector2Array:
	return Geom.to_world(Catalog.footprint_polygon(str(obj["type"])),
		Vector2(float(obj["x"]), float(obj["z"])), float(obj["rot"]))


func _is_tree(type: String) -> bool:
	return bool(Catalog.get_item(type).get("tree", false))


func _half_diag(type: String) -> float:
	if not _half_diag_cache.has(type):
		_half_diag_cache[type] = _footprint_vec(Catalog.get_item(type)).length() * 0.5
	return float(_half_diag_cache[type])


## Rect2i(頂点 index・個数) を 世界座標の Rect2 にする。
static func _rect_world(rect: Rect2i) -> Rect2:
	var h := WorldData.HALF
	return Rect2(rect.position.x - h, rect.position.y - h, maxf(float(rect.size.x) - 1.0, 0.0), maxf(float(rect.size.y) - 1.0, 0.0))


static func _vec3(v, fallback: Vector3) -> Vector3:
	if v is Array and (v as Array).size() == 3:
		return Vector3(float(v[0]), float(v[1]), float(v[2]))
	return fallback


## 局所の箱 [bmin, bmax] へのレイ交差。手前の交点の t(>=0)、外れは -1。
static func _ray_box(o: Vector3, d: Vector3, bmin: Vector3, bmax: Vector3) -> float:
	var tmin := -INF
	var tmax := INF
	for axis in 3:
		var oa := o[axis]
		var da := d[axis]
		if absf(da) < 1e-9:
			if oa < bmin[axis] or oa > bmax[axis]:
				return -1.0
		else:
			var t1 := (bmin[axis] - oa) / da
			var t2 := (bmax[axis] - oa) / da
			tmin = maxf(tmin, minf(t1, t2))
			tmax = minf(tmax, maxf(t1, t2))
	if tmin > tmax or tmax < 0.0:
		return -1.0
	return maxf(tmin, 0.0)
