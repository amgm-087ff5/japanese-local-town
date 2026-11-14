## 部品のサムネイル(architecture 15.4)。SubViewport(独自の3Dワールド・透明背景)で Catalog.instantiate(id) を斜めから1回描き、
## user://thumbs/<id>_v1.png に保存して以後は読む。1フレームに1個ずつ生成し、起動を止めない。
class_name Thumbnailer
extends Node

signal thumb_ready(id: String, texture: Texture2D)

const SIZE := 128
const DIR := "user://thumbs"
const VERSION := "v1"
const FOV := 30.0

var _vp: SubViewport
var _holder: Node3D
var _cam: Camera3D
var _queue: Array[String] = []
var _queued := {}
var _cache := {}


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(DIR)
	_build_viewport()
	_work()


func path_for(id: String) -> String:
	return "%s/%s_%s.png" % [DIR, id, VERSION]


## 既にあればテクスチャを返す。無ければ生成キューに入れて null を返す(完成時に thumb_ready)。
func request(id: String) -> Texture2D:
	if _cache.has(id):
		return _cache[id]
	var path := path_for(id)
	if FileAccess.file_exists(path):
		var img := Image.load_from_file(path)
		if img != null and not img.is_empty():
			var tex := ImageTexture.create_from_image(img)
			_cache[id] = tex
			return tex
	if not _queued.has(id):
		_queued[id] = true
		_queue.append(id)
	return null


func _build_viewport() -> void:
	_vp = SubViewport.new()
	_vp.size = Vector2i(SIZE, SIZE)
	_vp.own_world_3d = true
	_vp.transparent_bg = true
	_vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_vp)
	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.9, 0.9, 0.88)
	env.ambient_light_energy = 0.6
	var we := WorldEnvironment.new()
	we.environment = env
	_vp.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 35.0, 0.0)
	sun.light_energy = 1.1
	_vp.add_child(sun)
	_cam = Camera3D.new()
	_cam.fov = FOV
	_cam.near = 0.05
	_cam.far = 1000.0
	_cam.current = true
	_vp.add_child(_cam)
	_holder = Node3D.new()
	_vp.add_child(_holder)


## キューを1つずつ処理する。キューが空の間は1フレームずつ待つ。
func _work() -> void:
	while is_inside_tree():
		if _queue.is_empty():
			await get_tree().process_frame
			continue
		var id: String = _queue.pop_front()
		var img: Image = await _render(id)
		_queued.erase(id)
		if img == null or img.is_empty():
			continue
		img.save_png(path_for(id))
		var tex := ImageTexture.create_from_image(img)
		_cache[id] = tex
		thumb_ready.emit(id, tex)


func _render(id: String) -> Image:
	var model := Catalog.instantiate(id)
	if model == null:
		return null
	_holder.add_child(model)
	await get_tree().process_frame
	var box := _local_aabb(model)
	var center := box.get_center()
	var r := maxf(box.size.length() * 0.5, 0.2)
	var dir := Vector3(1.0, 0.8, 1.0).normalized()
	_cam.position = center + dir * (r * 3.4 + 0.6)
	_cam.look_at(center, Vector3.UP)
	_vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	var img := _vp.get_texture().get_image()
	_holder.remove_child(model)
	model.queue_free()
	return img


## root の座標系での、子孫の見た目の箱(AABB)。
func _local_aabb(root: Node3D) -> AABB:
	var out := AABB()
	var has := false
	var inv := root.global_transform.affine_inverse()
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if n is GeometryInstance3D:
			var gi := n as GeometryInstance3D
			var t: Transform3D = inv * gi.global_transform
			var a: AABB = t * gi.get_aabb()
			if has:
				out = out.merge(a)
			else:
				out = a
				has = true
	if not has:
		out = AABB(Vector3(-0.5, 0.0, -0.5), Vector3(1.0, 1.0, 1.0))
	return out
