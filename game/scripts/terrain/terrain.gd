## 地形メッシュ・ブラシ・当たり(architecture.md 8章・15章)。
## 高さ・地表・森の実体は Game.world の配列にあり、ここはその見た目(32×32セルのチャンク・splat テクスチャ)と当たりを持つ。
## ブラシ系は配列を書き換え、自分の見た目だけを即更新して変更 Rect2i を返す。シグナルは出さない(Game.end_stroke が出す)。
class_name Terrain
extends Node3D

const N := 257                 # 頂点数(1m格子)
const LAST := 256              # N - 1
const ROW := 257               # 1行の要素数(idx = iz*ROW + ix)
const HALF := 128.0
const CHUNK := 32              # チャンク1辺のセル数
const CHUNK_VERTS := 33        # チャンク1辺の頂点数(境界を両側に含む)
const CHUNK_COUNT := 8         # 1辺のチャンク数(256 / 32)

const RAISE_RATE := 6.0        # 上げる・下げる: strength=1 で 6m/秒(中心)
const FLATTEN_RATE := 6.0      # 平らにする・なめらかに: 1/秒 の寄せ率(strength=1 中心)
const SURFACE_RATE := 1.5      # 地表: strength=1 中心で約0.7秒で塗り切る
const FOREST_RATE := 255.0     # 森: 中心で約1秒で満杯・空
const SEAM_NORMAL_MARGIN := 1  # 法線の依存範囲(隣の頂点)

const PATTERN_SIZE := 256

static var _pattern: ImageTexture = null

var _chunks: Array = []        # MeshInstance3D
var _meshes: Array = []        # ArrayMesh
var _cverts: Array = []        # PackedVector3Array(33*33) チャンクごとの頂点位置(保持して部分更新する)
var _cnorms: Array = []        # PackedVector3Array(33*33) チャンクごとの法線
var _indices := PackedInt32Array()
var _mat: ShaderMaterial
var _tex_a: ImageTexture
var _tex_b: ImageTexture
var _body: StaticBody3D
var _shape: HeightMapShape3D
var _water: MeshInstance3D
var _flatten_h := 0.0
var _has_flatten := false
var _ws := PackedFloat32Array()   # 地表ブラシ用の作業領域(種類1-7)


func _ready() -> void:
	add_to_group("terrain")
	_ws.resize(8)
	_build_nodes()
	game().world_loaded.connect(_on_world_loaded)
	game().terrain_changed.connect(_on_terrain_changed)
	game().surface_changed.connect(_on_surface_changed)
	if game().world != null:
		rebuild_all()


## autoload "Game" を取る。識別子で直接書くと --script のテストで解決できないため root から取得する。
static func game() -> Node:
	return (Engine.get_main_loop() as SceneTree).root.get_node("Game")


## 子ノード(チャンク・当たり・水)を作る。二回目以降は何もしない。
func _build_nodes() -> void:
	if not _chunks.is_empty():
		return
	_mat = ShaderMaterial.new()
	_mat.shader = preload("res://scripts/terrain/terrain.gdshader")
	_mat.set_shader_parameter("pattern_tex", _pattern_texture())
	_mat.set_shader_parameter("water_level", WorldData.WATER_LEVEL)
	_indices = _make_indices()
	for k in CHUNK_COUNT * CHUNK_COUNT:
		var mi := MeshInstance3D.new()
		mi.name = "Chunk_%d_%d" % [k % CHUNK_COUNT, k / CHUNK_COUNT]
		var m := ArrayMesh.new()
		mi.mesh = m
		mi.material_override = _mat
		add_child(mi)
		_chunks.append(mi)
		_meshes.append(m)
		_cverts.append(PackedVector3Array())
		_cnorms.append(PackedVector3Array())

	_body = StaticBody3D.new()
	_body.name = "Body"
	_body.collision_layer = 1
	_body.collision_mask = 0
	_shape = HeightMapShape3D.new()
	_shape.map_width = N
	_shape.map_depth = N
	var cs := CollisionShape3D.new()
	cs.name = "Shape"
	cs.shape = _shape
	_body.add_child(cs)
	add_child(_body)

	_water = MeshInstance3D.new()
	_water.name = "Water"
	var plane := PlaneMesh.new()
	plane.size = Vector2(600.0, 600.0)
	_water.mesh = plane
	var wm := ShaderMaterial.new()
	wm.shader = preload("res://scripts/terrain/water.gdshader")
	wm.set_shader_parameter("wave_tex", _pattern_texture())
	_water.material_override = wm
	_water.position = Vector3(0.0, WorldData.WATER_LEVEL, 0.0)
	_water.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_water)


## 全チャンク・splat・当たりを作り直す。Main と world_loaded の両方から呼ばれても壊れない。
func rebuild_all() -> void:
	if game().world == null:
		return
	_build_nodes()
	var h: PackedFloat32Array = game().world.heights
	for k in CHUNK_COUNT * CHUNK_COUNT:
		_refresh_chunk(k, 0, 0, N, N, h)
	_update_splats()
	update_collision()


## 変更矩形(頂点 index。position 以上・end 未満)に重なるチャンクだけ作り直す。法線の依存(隣の1頂点)も含める。
func rebuild_rect(rect: Rect2i) -> void:
	if game().world == null:
		return
	if _cverts.is_empty() or (_cverts[0] as PackedVector3Array).is_empty():
		rebuild_all()
		return
	var r := WorldData.clamp_rect(rect)
	if r.size == Vector2i.ZERO:
		return
	var x0 := maxi(r.position.x - SEAM_NORMAL_MARGIN, 0)
	var z0 := maxi(r.position.y - SEAM_NORMAL_MARGIN, 0)
	var x1 := mini(r.end.x + SEAM_NORMAL_MARGIN, N)
	var z1 := mini(r.end.y + SEAM_NORMAL_MARGIN, N)
	var h: PackedFloat32Array = game().world.heights
	for k in CHUNK_COUNT * CHUNK_COUNT:
		var ox := (k % CHUNK_COUNT) * CHUNK
		var oz := (k / CHUNK_COUNT) * CHUNK
		if ox >= x1 or ox + CHUNK_VERTS <= x0 or oz >= z1 or oz + CHUNK_VERTS <= z0:
			continue
		_refresh_chunk(k, x0, z0, x1, z1, h)


## 世界の高さ(双線形)。実体は Game.world。
func height_at(x: float, z: float) -> float:
	if game().world == null:
		return 0.0
	return game().world.height_at(x, z)


## 法線(中央差分)。
func normal_at(x: float, z: float) -> Vector3:
	var e := 0.5
	var dx := height_at(x + e, z) - height_at(x - e, z)
	var dz := height_at(x, z + e) - height_at(x, z - e)
	return Vector3(-dx, 2.0 * e, -dz).normalized()


## レイと地形の交点(物理に依存しない)。世界の箱で区間を切ってから 0.5m 刻みで進み、2分法で詰める。無ければ null。
func raycast(from: Vector3, dir: Vector3, max_dist := 2000.0) -> Variant:
	if game().world == null:
		return null
	var t0 := 0.0
	var t1 := max_dist
	var lo := Vector3(-HALF, WorldData.H_MIN - 1.0, -HALF)
	var hi := Vector3(HALF, WorldData.H_MAX + 1.0, HALF)
	for a in 3:
		var d: float = dir[a]
		var o: float = from[a]
		if absf(d) < 1e-9:
			if o < lo[a] or o > hi[a]:
				return null
		else:
			var ta: float = (lo[a] - o) / d
			var tb: float = (hi[a] - o) / d
			if ta > tb:
				var tmp := ta
				ta = tb
				tb = tmp
			t0 = maxf(t0, ta)
			t1 = minf(t1, tb)
	if t0 > t1:
		return null
	var step := 0.5
	var prev := t0
	var t := t0
	while t <= t1 + step:
		var tt := minf(t, t1)
		var p := from + dir * tt
		if p.y <= height_at(p.x, p.z):
			var lo_t := prev
			var hi_t := tt
			for _i in 16:
				var mid := (lo_t + hi_t) * 0.5
				var q := from + dir * mid
				if q.y <= height_at(q.x, q.z):
					hi_t = mid
				else:
					lo_t = mid
			return from + dir * hi_t
		if tt >= t1:
			break
		prev = tt
		t += step
	return null


func screen_to_ground(camera: Camera3D, screen_pos: Vector2) -> Variant:
	if camera == null:
		return null
	return raycast(camera.project_ray_origin(screen_pos), camera.project_ray_normal(screen_pos))


## 高さを変えるブラシ。kind は "raise" "lower" "flatten" "smooth"。
## raise/lower は中心からの smoothstep 減衰。flatten は開始高さへ寄せる(開始高さは set_flatten_height か最初の呼び出しの中心高さ)。
## smooth は 3x3 の近傍平均へ寄せる。戻り値は変更した頂点の Rect2i。
func brush_height(kind: String, center: Vector2, radius: float, strength: float, dt: float) -> Rect2i:
	if game().world == null or dt <= 0.0 or not (kind in ["raise", "lower", "flatten", "smooth"]):
		return Rect2i()
	var r := maxf(radius, 0.05)
	var s := clampf(strength, 0.0, 1.0)
	var rect := _circle_rect(center, r)
	if rect.size == Vector2i.ZERO:
		return rect
	if kind == "flatten" and not _has_flatten:
		_flatten_h = height_at(center.x, center.y)
		_has_flatten = true
	var world: WorldData = game().world
	var h := world.heights
	var x0 := rect.position.x
	var z0 := rect.position.y
	var x1 := rect.end.x
	var z1 := rect.end.y
	var cx := center.x
	var cz := center.y
	var r2 := r * r

	if kind == "smooth":
		# 近傍平均は変更前の値から取る(書き込みで順序の偏りが出ないよう、先に全部計算してから書く)
		var buf := PackedFloat32Array()
		buf.resize(rect.size.x * rect.size.y)
		var bi := 0
		for iz in range(z0, z1):
			var zw := float(iz) - HALF
			for ix in range(x0, x1):
				var xw := float(ix) - HALF
				var d2 := (xw - cx) * (xw - cx) + (zw - cz) * (zw - cz)
				var cur := h[iz * ROW + ix]
				var nv := cur
				if d2 < r2:
					var f := 1.0 - smoothstep(0.0, r, sqrt(d2))
					var avg := _local_avg(h, ix, iz)
					nv = lerpf(cur, avg, clampf(s * f * dt * FLATTEN_RATE, 0.0, 1.0))
				buf[bi] = nv
				bi += 1
		bi = 0
		for iz in range(z0, z1):
			for ix in range(x0, x1):
				h[iz * ROW + ix] = clampf(buf[bi], WorldData.H_MIN, WorldData.H_MAX)
				bi += 1
	else:
		# 種類は文字列のまま内側のループで比べない(ループの外で数値にする)
		var tgt := _flatten_h
		var sign_up := 1.0 if kind == "raise" else -1.0
		var is_flatten := kind == "flatten"
		var rate := s * RAISE_RATE * dt * sign_up
		var flat_rate := s * dt * FLATTEN_RATE
		for iz in range(z0, z1):
			var zw := float(iz) - HALF
			var dz2 := (zw - cz) * (zw - cz)
			for ix in range(x0, x1):
				var xw := float(ix) - HALF
				var dx := xw - cx
				var d2 := dx * dx + dz2
				if d2 >= r2:
					continue
				var k := iz * ROW + ix
				var f := 1.0 - smoothstep(0.0, r, sqrt(d2))
				var cur := h[k]
				var nv: float
				if is_flatten:
					nv = lerpf(cur, tgt, clampf(flat_rate * f, 0.0, 1.0))
				else:
					nv = cur + rate * f
				h[k] = clampf(nv, WorldData.H_MIN, WorldData.H_MAX)

	world.heights = h
	rebuild_rect(rect)
	return rect


## 開始高さ(flatten 用)を明示する。
func set_flatten_height(h: float) -> void:
	_flatten_h = h
	_has_flatten = true


## ストローク開始時に呼ぶ。flatten の開始高さを解除する(次の呼び出しで中心の高さを記憶し直す)。
func reset_stroke() -> void:
	_has_flatten = false


## 地表の重みを塗る。type_id=0 は草(他をすべて減らす)。対象を増やし他を比例で減らす。合計は 255 以下に保つ。
func brush_surface(type_id: int, center: Vector2, radius: float, strength: float, dt: float) -> Rect2i:
	if game().world == null or dt <= 0.0 or type_id < 0 or type_id >= WorldData.SURFACE_COUNT:
		return Rect2i()
	var r := maxf(radius, 0.05)
	var s := clampf(strength, 0.0, 1.0)
	var rect := _circle_rect(center, r)
	if rect.size == Vector2i.ZERO:
		return rect
	var world: WorldData = game().world
	var a := world.splat_a
	var b := world.splat_b
	var ws := _ws
	var r2 := r * r
	for iz in range(rect.position.y, rect.end.y):
		var zw := float(iz) - HALF
		for ix in range(rect.position.x, rect.end.x):
			var xw := float(ix) - HALF
			var dx := xw - center.x
			var d2 := dx * dx + (zw - center.y) * (zw - center.y)
			if d2 >= r2:
				continue
			var t := clampf(s * (1.0 - smoothstep(0.0, r, sqrt(d2))) * dt * SURFACE_RATE, 0.0, 1.0)
			if t <= 0.0:
				continue
			var base := (iz * ROW + ix) * 4
			for c in range(1, WorldData.SURFACE_COUNT):
				ws[c] = a[base + c - 1] if c <= 4 else b[base + c - 5]
			ws = _mix_weights(ws, type_id, t)
			for c in range(1, WorldData.SURFACE_COUNT):
				var v := int(ws[c])
				if c <= 4:
					a[base + c - 1] = v
				else:
					b[base + c - 5] = v
	world.splat_a = a
	world.splat_b = b
	_update_splats()
	return rect


## 森の濃さ(0-255)を足す・減らす。add=false で減らす。戻り値は変更した頂点の Rect2i。
func brush_forest(center: Vector2, radius: float, add: bool, dt: float) -> Rect2i:
	if game().world == null or dt <= 0.0:
		return Rect2i()
	var r := maxf(radius, 0.05)
	var rect := _circle_rect(center, r)
	if rect.size == Vector2i.ZERO:
		return rect
	var world: WorldData = game().world
	var f_arr := world.forest
	var r2 := r * r
	for iz in range(rect.position.y, rect.end.y):
		var zw := float(iz) - HALF
		for ix in range(rect.position.x, rect.end.x):
			var xw := float(ix) - HALF
			var dx := xw - center.x
			var d2 := dx * dx + (zw - center.y) * (zw - center.y)
			if d2 >= r2:
				continue
			var fall := 1.0 - smoothstep(0.0, r, sqrt(d2))
			var amt := maxi(1, roundi(FOREST_RATE * fall * dt))
			var k := iz * ROW + ix
			if add:
				f_arr[k] = mini(int(f_arr[k]) + amt, 255)
			else:
				f_arr[k] = maxi(int(f_arr[k]) - amt, 0)
	world.forest = f_arr
	return rect


## 多角形(ワールド座標)の内側を中心の高さに揃え、縁から margin m でなだらかにつなぐ(占有領域の整地)。
func flatten_polygon(poly_world: PackedVector2Array, margin := 1.5) -> Rect2i:
	if game().world == null or poly_world.size() < 3:
		return Rect2i()
	var m := maxf(margin, 0.01)
	var lo := poly_world[0]
	var hi := lo
	var c := Vector2.ZERO
	for p in poly_world:
		lo = lo.min(p)
		hi = hi.max(p)
		c += p
	c /= float(poly_world.size())
	var target := height_at(c.x, c.y)
	var rect := _bounds_rect(lo - Vector2(m, m), hi + Vector2(m, m))
	if rect.size == Vector2i.ZERO:
		return rect
	var world: WorldData = game().world
	var h := world.heights
	for iz in range(rect.position.y, rect.end.y):
		for ix in range(rect.position.x, rect.end.x):
			var p := Vector2(float(ix) - HALF, float(iz) - HALF)
			var d := 0.0
			if not Geom.point_in_polygon(p, poly_world):
				d = _dist_to_poly(p, poly_world)
			if d > m:
				continue
			var w := 1.0 - smoothstep(0.0, m, d)
			var k := iz * ROW + ix
			h[k] = clampf(lerpf(h[k], target, w), WorldData.H_MIN, WorldData.H_MAX)
	world.heights = h
	rebuild_rect(rect)
	return rect


## 当たり(HeightMapShape3D)を世界の高さで更新する。map_data は行優先(z→x)で heights と同じ並び。
func update_collision() -> void:
	if game().world == null or _shape == null:
		return
	_shape.map_width = N
	_shape.map_depth = N
	_shape.map_data = game().world.heights


## 見た目の高さ(テスト用)。頂点 (ix, iz) を覆うチャンクの頂点位置の y を返す。
func mesh_vertex_height(ix: int, iz: int) -> float:
	var cx := mini(ix / CHUNK, CHUNK_COUNT - 1)
	var cz := mini(iz / CHUNK, CHUNK_COUNT - 1)
	var k := cz * CHUNK_COUNT + cx
	var li := (iz - cz * CHUNK) * CHUNK_VERTS + (ix - cx * CHUNK)
	var v: PackedVector3Array = _cverts[k]
	return v[li].y if li < v.size() else 0.0


func _on_world_loaded() -> void:
	rebuild_all()


func _on_terrain_changed(rect: Rect2i) -> void:
	rebuild_rect(rect)
	update_collision()


func _on_surface_changed(_rect: Rect2i) -> void:
	_update_splats()


# ---------------------------------------------------------------- 内部: チャンク

## チャンク k の頂点範囲 [vx0, vx1) x [vz0, vz1)(全体座標)のうち、チャンクに含まれる部分の位置・法線を計算し直して描き直す。
func _refresh_chunk(k: int, vx0: int, vz0: int, vx1: int, vz1: int, h: PackedFloat32Array) -> void:
	var ox := (k % CHUNK_COUNT) * CHUNK
	var oz := (k / CHUNK_COUNT) * CHUNK
	var full := CHUNK_VERTS * CHUNK_VERTS
	var V: PackedVector3Array = _cverts[k]
	var Nr: PackedVector3Array = _cnorms[k]
	_cverts[k] = PackedVector3Array()
	_cnorms[k] = PackedVector3Array()
	if V.size() != full or Nr.size() != full:
		# 初回・未構築: チャンク全体を計算する
		V.resize(full)
		Nr.resize(full)
		vx0 = 0
		vz0 = 0
		vx1 = N
		vz1 = N
	var x0 := maxi(vx0, ox)
	var x1 := mini(vx1, ox + CHUNK_VERTS)
	var z0 := maxi(vz0, oz)
	var z1 := mini(vz1, oz + CHUNK_VERTS)
	for iz in range(z0, z1):
		var j := (iz - oz) * CHUNK_VERTS
		var zw := float(iz) - HALF
		for ix in range(x0, x1):
			var li := j + ix - ox
			V[li] = Vector3(float(ix) - HALF, h[iz * ROW + ix], zw)
			Nr[li] = _normal_of(h, ix, iz)
	_cverts[k] = V
	_cnorms[k] = Nr
	_upload(k)


func _upload(k: int) -> void:
	var m: ArrayMesh = _meshes[k]
	m.clear_surfaces()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = _cverts[k]
	arr[Mesh.ARRAY_NORMAL] = _cnorms[k]
	arr[Mesh.ARRAY_INDEX] = _indices
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)


## 頂点 (ix, iz) の法線。高さ配列の中央差分(端は片側差分)。世界全体の配列から計算するのでチャンクの継ぎ目は出ない。
static func _normal_of(h: PackedFloat32Array, ix: int, iz: int) -> Vector3:
	var xa := maxi(ix - 1, 0)
	var xb := mini(ix + 1, LAST)
	var za := maxi(iz - 1, 0)
	var zb := mini(iz + 1, LAST)
	var dx := (h[iz * ROW + xb] - h[iz * ROW + xa]) / float(xb - xa)
	var dz := (h[zb * ROW + ix] - h[za * ROW + ix]) / float(zb - za)
	return Vector3(-dx, 1.0, -dz).normalized()


## チャンク1つ分の三角形。左上→右上→右下、左上→右下→左下(Godot の表面は時計回り)。
static func _make_indices() -> PackedInt32Array:
	var out := PackedInt32Array()
	out.resize(CHUNK * CHUNK * 6)
	var n := 0
	for j in CHUNK:
		for i in CHUNK:
			var a := j * CHUNK_VERTS + i
			var b := a + 1
			var c := (j + 1) * CHUNK_VERTS + i + 1
			var d := (j + 1) * CHUNK_VERTS + i
			out[n] = a
			out[n + 1] = b
			out[n + 2] = c
			out[n + 3] = a
			out[n + 4] = c
			out[n + 5] = d
			n += 6
	return out


# ---------------------------------------------------------------- 内部: 地表テクスチャ

func _update_splats() -> void:
	if game().world == null or _mat == null:
		return
	var ia := Image.create_from_data(N, N, false, Image.FORMAT_RGBA8, game().world.splat_a)
	var ib := Image.create_from_data(N, N, false, Image.FORMAT_RGBA8, game().world.splat_b)
	if _tex_a == null:
		_tex_a = ImageTexture.create_from_image(ia)
		_tex_b = ImageTexture.create_from_image(ib)
		_mat.set_shader_parameter("splat_a", _tex_a)
		_mat.set_shader_parameter("splat_b", _tex_b)
	else:
		_tex_a.update(ia)
		_tex_b.update(ib)


## 模様用のタイリングノイズ(256px・RGBA に別周波数)。起動時に1回だけ作る。
static func _pattern_texture() -> ImageTexture:
	if _pattern == null:
		_pattern = ImageTexture.create_from_image(_make_pattern_image())
	return _pattern


static func _make_pattern_image() -> Image:
	var freqs := [0.02, 0.06, 0.16, 0.42]
	var planes: Array = []
	for k in 4:
		var fn := FastNoiseLite.new()
		fn.seed = 7 + k * 101
		fn.noise_type = FastNoiseLite.TYPE_SIMPLEX
		fn.frequency = freqs[k]
		var img := fn.get_seamless_image(PATTERN_SIZE, PATTERN_SIZE)
		img.convert(Image.FORMAT_L8)
		planes.append(img.get_data())
	var p0: PackedByteArray = planes[0]
	var p1: PackedByteArray = planes[1]
	var p2: PackedByteArray = planes[2]
	var p3: PackedByteArray = planes[3]
	var out := PackedByteArray()
	var count := PATTERN_SIZE * PATTERN_SIZE
	out.resize(count * 4)
	for i in count:
		var o := i * 4
		out[o] = p0[i]
		out[o + 1] = p1[i]
		out[o + 2] = p2[i]
		out[o + 3] = p3[i]
	var result := Image.create_from_data(PATTERN_SIZE, PATTERN_SIZE, false, Image.FORMAT_RGBA8, out)
	result.generate_mipmaps()
	return result


## 種類 1-7 の重み ws[1..7] を、type_id の重みを t だけ 255 へ寄せ、他を比例で減らす。合計は 255 以下。
## type_id=0(草)は他をすべて減らす(草は残りとして決まる)。
## PackedArray は値渡しなので、更新後の配列を返す。
static func _mix_weights(ws_in: PackedFloat32Array, type_id: int, t: float) -> PackedFloat32Array:
	var ws := ws_in
	var others := 0.0
	for c in range(1, WorldData.SURFACE_COUNT):
		if c == type_id:
			continue
		var v := roundf(ws[c] * (1.0 - t))
		ws[c] = v
		others += v
	if others > 255.0:
		# 丸めで超えた分は、他の種類の最大から引く
		var big := -1
		for c in range(1, WorldData.SURFACE_COUNT):
			if c == type_id:
				continue
			if big < 0 or ws[c] > ws[big]:
				big = c
		ws[big] -= others - 255.0
		others = 255.0
	if type_id > 0:
		var old := ws[type_id]
		ws[type_id] = minf(roundf(old + (255.0 - old) * t), 255.0 - others)
	return ws


# ---------------------------------------------------------------- 内部: 範囲・幾何

## 中心 c(ワールド座標)・半径 r の円を囲む頂点 Rect2i(世界の範囲に切る)。
static func _circle_rect(c: Vector2, r: float) -> Rect2i:
	return _bounds_rect(c - Vector2(r, r), c + Vector2(r, r))


## 範囲 [lo, hi](ワールド座標)を頂点 index の Rect2i にする(両端を含み、世界の範囲に切る)。
static func _bounds_rect(lo_w: Vector2, hi_w: Vector2) -> Rect2i:
	var x0 := clampi(floori(lo_w.x + HALF), 0, N)
	var z0 := clampi(floori(lo_w.y + HALF), 0, N)
	var x1 := clampi(ceili(hi_w.x + HALF) + 1, 0, N)
	var z1 := clampi(ceili(hi_w.y + HALF) + 1, 0, N)
	if x1 <= x0 or z1 <= z0:
		return Rect2i()
	return WorldData.clamp_rect(Rect2i(x0, z0, x1 - x0, z1 - z0))


## 4近傍+自分の 3x3 平均(端は範囲内だけ)。
static func _local_avg(h: PackedFloat32Array, ix: int, iz: int) -> float:
	var sum := 0.0
	var cnt := 0
	for dz in range(-1, 2):
		var z: int = iz + dz
		if z < 0 or z > LAST:
			continue
		for dx in range(-1, 2):
			var x: int = ix + dx
			if x < 0 or x > LAST:
				continue
			sum += h[z * ROW + x]
			cnt += 1
	return sum / float(cnt)


static func _dist_to_poly(p: Vector2, poly: PackedVector2Array) -> float:
	var best := INF
	var n := poly.size()
	for i in n:
		best = minf(best, _dist_to_segment(p, poly[i], poly[(i + 1) % n]))
	return best


static func _dist_to_segment(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var len2 := ab.dot(ab)
	if len2 < 1e-9:
		return p.distance_to(a)
	var t := clampf((p - a).dot(ab) / len2, 0.0, 1.0)
	return p.distance_to(a + ab * t)
