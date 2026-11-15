## アセット定義の読込(architecture.md 6章)。autoload 名 "Catalog"。
## data/catalog.json が無い・壊れている場合は内蔵の仮定義を使う。モデルが無い場合は箱を返す。
extends Node

const CATALOG_PATH := "res://data/catalog.json"

## 内蔵の仮定義。キーは catalog.json と同じ意味。
const BUILTIN := [
	{"id": "haiden", "name": "拝殿", "category": "shrine", "footprint": [9.0, 8.0], "height": 7.5, "order": 10},
	{"id": "honden", "name": "本殿", "category": "shrine", "footprint": [7.0, 6.0], "height": 6.0, "order": 11},
	{"id": "torii", "name": "鳥居", "category": "shrine", "footprint": [6.0, 2.0], "height": 4.5, "order": 1},
	{"id": "torii_ishi", "name": "鳥居の石", "category": "shrine", "footprint": [1.5, 1.5], "height": 0.6, "order": 2, "walkable": true},
	{"id": "toro", "name": "石灯籠", "category": "shrine", "footprint": [1.2, 1.2], "height": 2.2, "glow": "lantern", "order": 3},
	{"id": "komainu_a", "name": "狛犬(阿)", "category": "shrine", "footprint": [1.0, 1.0], "height": 0.8, "order": 4},
	{"id": "komainu_un", "name": "狛犬(吽)", "category": "shrine", "footprint": [1.0, 1.0], "height": 0.8, "order": 5},
	{"id": "chozuya", "name": "手水舎", "category": "shrine", "footprint": [3.0, 2.0], "height": 2.5, "order": 6},
	{"id": "shamusho", "name": "社務所", "category": "shrine", "footprint": [7.0, 5.0], "height": 4.5, "order": 7},
	{"id": "tamagaki", "name": "玉垣", "category": "shrine", "footprint": [4.0, 0.6], "height": 1.0, "order": 8},
	{"id": "ishidan", "name": "石段", "category": "shrine", "footprint": [4.0, 3.0], "height": 0.8, "order": 9, "walkable": true},
	{"id": "hashi", "name": "太鼓橋", "category": "town", "footprint": [10.0, 3.0], "height": 1.2, "order": 20, "walkable": true},
	{"id": "jizo", "name": "地蔵", "category": "town", "footprint": [1.0, 1.0], "height": 1.2, "order": 21},
	{"id": "ie_kawara", "name": "瓦屋根の家", "category": "town", "footprint": [8.0, 7.0], "height": 6.0, "glow": "window", "order": 22},
	{"id": "ie_kayabuki", "name": "茅葺きの家", "category": "town", "footprint": [9.0, 8.0], "height": 6.5, "glow": "window", "order": 23},
	{"id": "denchu", "name": "電柱", "category": "town", "footprint": [0.5, 0.5], "height": 9.0, "order": 24},
	{"id": "iwa_l", "name": "大きな岩", "category": "nature", "footprint": [3.0, 3.0], "height": 2.5, "order": 30},
	{"id": "iwa_s", "name": "小さな岩", "category": "nature", "footprint": [1.5, 1.5], "height": 1.0, "order": 31},
	{"id": "sugi", "name": "杉", "category": "nature", "footprint": [1.2, 1.2], "height": 18.0, "tree": true, "order": 40},
	{"id": "sakura", "name": "桜", "category": "nature", "footprint": [1.2, 1.2], "height": 8.0, "tree": true, "order": 41},
	{"id": "kaede", "name": "楓", "category": "nature", "footprint": [1.2, 1.2], "height": 8.0, "tree": true, "order": 42},
	{"id": "matsu", "name": "松", "category": "nature", "footprint": [1.2, 1.2], "height": 10.0, "tree": true, "order": 43},
	{"id": "take", "name": "竹", "category": "nature", "footprint": [1.2, 1.2], "height": 7.0, "tree": true, "order": 44},
]

const CATEGORIES := ["shrine", "town", "nature"]
const FALLBACK_FOOTPRINT := Vector2(1.0, 1.0)
const FALLBACK_HEIGHT := 1.0

var _items: Array[Dictionary] = []
var _by_id: Dictionary = {}
var _builtin_by_id: Dictionary = {}


func _ready() -> void:
	for b in BUILTIN:
		_builtin_by_id[b["id"]] = _normalize(b)
	_items = _load_json_items()
	if _items.is_empty():
		for b in BUILTIN:
			_items.append(_normalize(b))
	_items.sort_custom(func(a: Dictionary, c: Dictionary) -> bool: return int(a["order"]) < int(c["order"]))
	for it in _items:
		_by_id[it["id"]] = it


## 読込済みの全アイテム(order 昇順)。
func items() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for it in _items:
		out.append(it)
	return out


## id のアイテム。無ければ内蔵定義、それも無ければ空の Dictionary。
func get_item(id: String) -> Dictionary:
	if _by_id.has(id):
		return _by_id[id]
	if _builtin_by_id.has(id):
		return _builtin_by_id[id]
	return {}


func by_category(cat: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for it in _items:
		if it["category"] == cat:
			out.append(it)
	return out


func tree_ids() -> Array[String]:
	var out: Array[String] = []
	for it in _items:
		if bool(it.get("tree", false)):
			out.append(it["id"])
	return out


## 占有領域(ローカル x,z の4頂点、反時計回り)。未知の id は既定の 1m 四方。
func footprint_polygon(id: String) -> PackedVector2Array:
	var fp := _footprint_of(id)
	var hw := fp.x * 0.5
	var hd := fp.y * 0.5
	return PackedVector2Array([Vector2(-hw, -hd), Vector2(hw, -hd), Vector2(hw, hd), Vector2(-hw, hd)])


## 配置用のノードを作る。モデルが無い・読めない場合は占有領域サイズの色付きの箱と正面の印。
## 戻り値の正面は +Z。
func instantiate(id: String) -> Node3D:
	var it := get_item(id)
	var model_path := str(it.get("model", ""))
	if not model_path.is_empty() and ResourceLoader.exists(model_path):
		var res := load(model_path)
		if res is PackedScene:
			var inst = (res as PackedScene).instantiate()
			if inst is Node3D:
				inst.name = id
				return inst
			if inst != null:
				inst.queue_free()
	return _make_box(id, it)


func _make_box(id: String, it: Dictionary) -> Node3D:
	var fp := _footprint_of(id)
	var h := float(it.get("height", FALLBACK_HEIGHT))
	var root := Node3D.new()
	root.name = id
	var body := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(fp.x, h, fp.y)
	body.mesh = mesh
	body.position = Vector3(0, h * 0.5, 0)
	body.material_override = _solid_material(_color_for(id))
	root.add_child(body)
	# 正面の印(+Z 側の小さな四角)
	var mark := MeshInstance3D.new()
	var mark_mesh := BoxMesh.new()
	mark_mesh.size = Vector3(0.3, 0.3, 0.3)
	mark.mesh = mark_mesh
	mark.position = Vector3(0, minf(h, 0.6), fp.y * 0.5 + 0.2)
	mark.material_override = _solid_material(Color(1.0, 1.0, 1.0))
	root.add_child(mark)
	return root


func _solid_material(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = 0.9
	return m


func _color_for(id: String) -> Color:
	var it := get_item(id)
	match str(it.get("category", "")):
		"shrine":
			return Color(0.78, 0.27, 0.17)
		"town":
			return Color(0.55, 0.52, 0.47)
		"nature":
			return Color(0.25, 0.45, 0.30) if bool(it.get("tree", false)) else Color(0.5, 0.5, 0.48)
	return Color(0.6, 0.6, 0.6)


func _footprint_of(id: String) -> Vector2:
	var it := get_item(id)
	var fp = it.get("footprint", [])
	if fp is Array and fp.size() == 2:
		return Vector2(float(fp[0]), float(fp[1]))
	return FALLBACK_FOOTPRINT


func _load_json_items() -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	if not FileAccess.file_exists(CATALOG_PATH):
		return out
	var text := FileAccess.get_file_as_string(CATALOG_PATH)
	var data = JSON.parse_string(text)
	if not (data is Dictionary) or not (data.get("items") is Array):
		push_warning("catalog.json の形式が不正。内蔵定義を使います。")
		return out
	for raw in data["items"]:
		if raw is Dictionary and raw.has("id"):
			out.append(_normalize(raw))
	return out


## 欠けた項目を既定値で埋める。
func _normalize(raw: Dictionary) -> Dictionary:
	var id := str(raw.get("id", ""))
	var it := {
		"id": id,
		"name": str(raw.get("name", id)),
		"category": str(raw.get("category", "town")),
		"model": str(raw.get("model", "res://assets/models/%s.glb" % id)),
		"footprint": raw.get("footprint", [1.0, 1.0]),
		"colliders": raw.get("colliders", []),
		"height": float(raw.get("height", FALLBACK_HEIGHT)),
		"walkable": bool(raw.get("walkable", false)),
		"glow": str(raw.get("glow", "")),
		"tree": bool(raw.get("tree", false)),
		"order": int(raw.get("order", 999)),
	}
	if it["colliders"] is Array and (it["colliders"] as Array).is_empty() and not bool(it["walkable"]):
		var fp := FALLBACK_FOOTPRINT
		var raw_fp = it["footprint"]
		if raw_fp is Array and raw_fp.size() == 2:
			fp = Vector2(float(raw_fp[0]), float(raw_fp[1]))
		var h := float(it["height"])
		it["colliders"] = [{"pos": [0.0, h * 0.5, 0.0], "size": [fp.x, h, fp.y]}]
	return it
