## 世界の純データと直列化(architecture.md 4章・15.2章)。描画やノードを持たない。
class_name WorldData
extends RefCounted

const N := 257
const SIZE := 256.0
const HALF := 128.0
const WATER_LEVEL := -0.6
const H_MIN := -8.0
const H_MAX := 40.0
const CURRENT_VERSION := 1

## 地表の種類ID: 0=草(既定) 1=土 2=砂利 3=石畳 4=苔 5=白砂 6=畑 7=舗装
const SURFACE_COUNT := 8

var version := CURRENT_VERSION
var id := ""
var name := "あたらしい里"
var seed := 0
var heights := PackedFloat32Array()     # N*N
var splat_a := PackedByteArray()        # N*N*4  R=土 G=砂利 B=石畳 A=苔
var splat_b := PackedByteArray()        # N*N*4  R=白砂 G=畑 B=舗装 A=予備
var forest := PackedByteArray()         # N*N
var objects: Array[Dictionary] = []     # {uid:int, type:String, x:float, z:float, rot:float}
var next_uid := 1
var env := {"time": 9.0, "time_flow": true, "day_minutes": 12.0, "season": 0, "weather": 0}
var player := {"x": 0.0, "z": 20.0, "yaw": 0.0}


func _init() -> void:
	reset_terrain(0.5)


## 地形と地表を初期化する(高さは一定、地表は全部草、森なし)。
func reset_terrain(height: float) -> void:
	heights = PackedFloat32Array()
	heights.resize(N * N)
	heights.fill(height)
	splat_a = PackedByteArray()
	splat_a.resize(N * N * 4)
	splat_a.fill(0)
	splat_b = PackedByteArray()
	splat_b.resize(N * N * 4)
	splat_b.fill(0)
	forest = PackedByteArray()
	forest.resize(N * N)
	forest.fill(0)


static func idx(ix: int, iz: int) -> int:
	return iz * N + ix


## 世界座標 (x, z) の高さ(双線形)。範囲外は端の値。
func height_at(x: float, z: float) -> float:
	var fx := clampf(x + HALF, 0.0, SIZE)
	var fz := clampf(z + HALF, 0.0, SIZE)
	var ix := mini(int(floor(fx)), N - 2)
	var iz := mini(int(floor(fz)), N - 2)
	var tx := fx - ix
	var tz := fz - iz
	var h00 := heights[idx(ix, iz)]
	var h10 := heights[idx(ix + 1, iz)]
	var h01 := heights[idx(ix, iz + 1)]
	var h11 := heights[idx(ix + 1, iz + 1)]
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)


## 地表の重み(0-255)を取る。type_id は 1-7(0 の草は残り。戻り値は重みそのもの)。
func get_surface_weight(ix: int, iz: int, type_id: int) -> int:
	if type_id <= 0 or type_id >= SURFACE_COUNT:
		return 0
	var i := idx(ix, iz) * 4
	if type_id <= 4:
		return splat_a[i + type_id - 1]
	return splat_b[i + type_id - 5]


## 1 texel を単一の地表にする(指定種 255、他 0。草は残り)。ワールド生成用。
func set_surface_hard(ix: int, iz: int, type_id: int) -> void:
	var i := idx(ix, iz) * 4
	for c in 4:
		splat_a[i + c] = 0
		splat_b[i + c] = 0
	if type_id <= 0 or type_id >= SURFACE_COUNT:
		return
	if type_id <= 4:
		splat_a[i + type_id - 1] = 255
	else:
		splat_b[i + type_id - 5] = 255


## 座標範囲の正規化(頂点 index。position 以上、position+size 未満)。N の外は切る。
static func clamp_rect(r: Rect2i) -> Rect2i:
	var x0 := clampi(r.position.x, 0, N)
	var z0 := clampi(r.position.y, 0, N)
	var x1 := clampi(r.position.x + r.size.x, 0, N)
	var z1 := clampi(r.position.y + r.size.y, 0, N)
	if x1 <= x0 or z1 <= z0:
		return Rect2i()
	return Rect2i(x0, z0, x1 - x0, z1 - z0)


## 直列化。Packed 配列は zstd 圧縮 → Base64。展開サイズも保存する。
func to_dict() -> Dictionary:
	return {
		"version": version,
		"id": id,
		"name": name,
		"seed": seed,
		"modified": Time.get_unix_time_from_system(),
		"heights": _pack_bytes(heights.to_byte_array()),
		"splat_a": _pack_bytes(splat_a),
		"splat_b": _pack_bytes(splat_b),
		"forest": _pack_bytes(forest),
		"objects": objects.duplicate(true),
		"next_uid": next_uid,
		"env": env.duplicate(true),
		"player": player.duplicate(true),
	}


## 読み込み。欠けたキー・壊れた配列・未知の version でも落ちず、既定値で埋める。
static func from_dict(d: Dictionary) -> WorldData:
	var w := WorldData.new()
	w.version = int(_get_num(d, "version", CURRENT_VERSION))
	w.id = str(d.get("id", ""))
	w.name = str(d.get("name", w.name))
	w.seed = int(_get_num(d, "seed", 0))
	w.next_uid = maxi(1, int(_get_num(d, "next_uid", 1)))

	var h_bytes := _unpack_bytes(d.get("heights", null), N * N * 4)
	if h_bytes.size() == N * N * 4:
		w.heights = h_bytes.to_float32_array()
	var a := _unpack_bytes(d.get("splat_a", null), N * N * 4)
	if a.size() == N * N * 4:
		w.splat_a = a
	var b := _unpack_bytes(d.get("splat_b", null), N * N * 4)
	if b.size() == N * N * 4:
		w.splat_b = b
	var f := _unpack_bytes(d.get("forest", null), N * N)
	if f.size() == N * N:
		w.forest = f

	var objs = d.get("objects", [])
	if objs is Array:
		for o in objs:
			if o is Dictionary and o.has("uid") and o.has("type"):
				w.objects.append({
					"uid": int(o["uid"]),
					"type": str(o["type"]),
					"x": float(_get_num(o, "x", 0.0)),
					"z": float(_get_num(o, "z", 0.0)),
					"rot": float(_get_num(o, "rot", 0.0)),
				})
	# uid の重複と next_uid の整合を取る
	var max_uid := 0
	for o in w.objects:
		max_uid = maxi(max_uid, o["uid"])
	w.next_uid = maxi(w.next_uid, max_uid + 1)

	var e = d.get("env", null)
	if e is Dictionary:
		for k in w.env.keys():
			if e.has(k):
				w.env[k] = e[k]
	var p = d.get("player", null)
	if p is Dictionary:
		for k in w.player.keys():
			if p.has(k):
				w.player[k] = float(p[k])
	return w


static func _pack_bytes(bytes: PackedByteArray) -> Dictionary:
	var comp := bytes.compress(FileAccess.COMPRESSION_ZSTD)
	return {"size": bytes.size(), "data": Marshalls.raw_to_base64(comp)}


## 圧縮データを展開する。失敗時は空配列。expected_size と違えば空配列にする。
static func _unpack_bytes(v, expected_size: int) -> PackedByteArray:
	if not (v is Dictionary) or not v.has("data"):
		return PackedByteArray()
	var raw := Marshalls.base64_to_raw(str(v["data"]))
	if raw.is_empty():
		return PackedByteArray()
	var size := int(_get_num(v, "size", expected_size))
	if size != expected_size:
		return PackedByteArray()
	var out := raw.decompress(size, FileAccess.COMPRESSION_ZSTD)
	if out.size() != expected_size:
		return PackedByteArray()
	return out


static func _get_num(d: Dictionary, key: String, default: float) -> float:
	var v = d.get(key, default)
	if v is int or v is float:
		return float(v)
	return default
