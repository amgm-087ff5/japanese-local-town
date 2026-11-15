## 遠景(architecture.md 10章・15.4)。
## 山並み3層: 半径約2000m のリング状の壁(稜線は手続き生成、高さ 150〜450m)。手前ほど濃く、奥ほど霞む。
## 裾野: 世界(256m四方)の外側の地表色の面。y は世界端の標準高さ付近から緩く下がる。
## 山は常にカメラの xz に追従する(視差で近く見えないように)。裾野は世界に固定。
## 色は EnvController が set_look() で時刻・天気・季節に合わせて更新する。
class_name Backdrop
extends Node3D

const RING_SEGMENTS := 144
const BOTTOM_Y := -30.0
const APRON_INNER := 127.8        # 世界の端(128)の少し内側。地形の下に潜らせて継ぎ目を隠す
const APRON_OUTER := 2500.0
const APRON_Y_IN := 0.4
const APRON_DROP := 18.4
const PEAK_MAX := 450.0
const SHADER_RANGE := preload("res://scripts/env/backdrop.gdshader")
const SHADER_APRON := preload("res://scripts/env/apron.gdshader")

# 層: [半径, 基部の高さ, 高さの振れ, 乱数 seed, 霞の割合(0 くっきり 〜 1 空の色)]。手前から奥へ。
const LAYERS := [
	[1800.0, 90.0, 130.0, 37, 0.25],
	[2000.0, 130.0, 170.0, 23, 0.5],
	[2200.0, 170.0, 190.0, 11, 0.75],
]

var _range_mats: Array[ShaderMaterial] = []
var _apron: MeshInstance3D
var _apron_mat: ShaderMaterial


func _ready() -> void:
	for i in LAYERS.size():
		var mi := MeshInstance3D.new()
		mi.name = "Range%d" % i
		mi.mesh = _build_ring(LAYERS[i])
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var m := ShaderMaterial.new()
		m.shader = SHADER_RANGE
		mi.material_override = m
		_range_mats.append(m)
		add_child(mi)

	_apron = MeshInstance3D.new()
	_apron.name = "Apron"
	_apron.top_level = true
	_apron.mesh = _build_apron()
	_apron.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_apron_mat = ShaderMaterial.new()
	_apron_mat.shader = SHADER_APRON
	_apron.material_override = _apron_mat
	add_child(_apron)


func _process(_delta: float) -> void:
	var vp := get_viewport()
	if vp == null:
		return
	var cam := vp.get_camera_3d()
	if cam != null:
		var p := cam.global_position
		global_position = Vector3(p.x, 0.0, p.z)


## 色の更新。mountain: 季節の基本色、haze: 空の地平色(霞の色)、night 0-1、snow 0-1(頂の雪)、cloud 0-1(曇りほど霞む)。
func set_look(mountain: Color, haze: Color, night: float, snow: float, cloud: float) -> void:
	var night_dark := Color(0.05, 0.07, 0.12, 1.0)
	var snow_day := Color(0.92, 0.94, 0.97, 1.0)
	var snow_night := Color(0.22, 0.26, 0.36, 1.0)
	for i in _range_mats.size():
		var layer_haze: float = clampf(float(LAYERS[i][4]) + cloud * 0.1, 0.0, 0.95)
		var c := mountain.lerp(haze, layer_haze)
		c = c.lerp(night_dark, night * 0.75)
		_range_mats[i].set_shader_parameter("base_color", c)
		_range_mats[i].set_shader_parameter("snow_color", snow_day.lerp(snow_night, night))
		_range_mats[i].set_shader_parameter("snow_amount", snow)


## 山の層のリング。頂点色 R=稜線の位置(1=頂 0=下端)、G=山の高さ(雪用)。
func _build_ring(layer: Array) -> ArrayMesh:
	var radius: float = layer[0]
	var base: float = layer[1]
	var amp: float = layer[2]
	var rng := RandomNumberGenerator.new()
	rng.seed = int(layer[3])
	var ph := PackedFloat32Array()
	for k in 4:
		ph.append(rng.randf() * TAU)

	var verts := PackedVector3Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	var n := RING_SEGMENTS
	for k in range(n + 1):
		var a := TAU * float(k) / float(n)
		var ridge := 0.55 * absf(sin(3.0 * a + ph[0])) + 0.3 * absf(sin(7.0 * a + ph[1])) \
			+ 0.2 * absf(sin(13.0 * a + ph[2])) + 0.12 * sin(29.0 * a + ph[3])
		var h := base + amp * maxf(ridge, 0.0) + amp * 0.08 * rng.randf()
		var peak := clampf(h / PEAK_MAX, 0.0, 1.0)
		var cx := cos(a) * radius
		var cz := sin(a) * radius
		verts.append(Vector3(cx, h, cz))
		cols.append(Color(1.0, peak, 0.0, 1.0))
		verts.append(Vector3(cx, BOTTOM_Y, cz))
		cols.append(Color(0.0, peak, 0.0, 1.0))
	for k in n:
		var t0 := 2 * k
		var b0 := t0 + 1
		var t1 := t0 + 2
		var b1 := t0 + 3
		idx.append_array(PackedInt32Array([t0, b0, t1, t1, b0, b1]))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_COLOR] = cols
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


## 裾野: 世界の外(±APRON_INNER より外)だけの格子。内側は地形が覆うので穴にする。
func _build_apron() -> ArrayMesh:
	var xs := PackedFloat32Array([-APRON_OUTER, -1200.0, -500.0, -APRON_INNER, APRON_INNER, 500.0, 1200.0, APRON_OUTER])
	var m := xs.size()
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	for j in m:
		for i in m:
			var x := xs[i]
			var z := xs[j]
			verts.append(Vector3(x, _apron_y(x, z), z))
			norms.append(Vector3.UP)
	var idx := PackedInt32Array()
	for j in m - 1:
		for i in m - 1:
			var cx := (xs[i] + xs[i + 1]) * 0.5
			var cz := (xs[j] + xs[j + 1]) * 0.5
			if absf(cx) < APRON_INNER and absf(cz) < APRON_INNER:
				continue
			var v00 := j * m + i
			var v10 := v00 + 1
			var v01 := v00 + m
			var v11 := v01 + 1
			idx.append_array(PackedInt32Array([v00, v01, v11, v00, v11, v10]))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _apron_y(x: float, z: float) -> float:
	var d := maxf(absf(x), absf(z))
	var t := clampf((d - APRON_INNER) / (APRON_OUTER - APRON_INNER), 0.0, 1.0)
	return APRON_Y_IN - t * APRON_DROP
