## 2D 幾何・スナップ計算の純関数群(architecture.md 7章)。
## 座標は (x, z) を Vector2(x, y) として扱う。回転は Node3D.rotation.y と同じ向き。
class_name Geom
extends RefCounted

const EPS := 1e-6


## 物のローカル多角形をワールド座標へ。Node3D(rotation.y = rot, position = pos) と一致する。
static func to_world(poly_local: PackedVector2Array, pos: Vector2, rot: float) -> PackedVector2Array:
	var c := cos(rot)
	var s := sin(rot)
	var out := PackedVector2Array()
	out.resize(poly_local.size())
	for i in poly_local.size():
		var p := poly_local[i]
		out[i] = Vector2(p.x * c + p.y * s, -p.x * s + p.y * c) + pos
	return out


## 点が多角形の内側か(crossing number 法。凹多角形も可)。
static func point_in_polygon(p: Vector2, poly: PackedVector2Array) -> bool:
	var n := poly.size()
	if n < 3:
		return false
	var inside := false
	var j := n - 1
	for i in n:
		var a := poly[i]
		var b := poly[j]
		if (a.y > p.y) != (b.y > p.y):
			var x_cross := a.x + (p.y - a.y) * (b.x - a.x) / (b.y - a.y)
			if p.x < x_cross:
				inside = not inside
		j = i
	return inside


## 凸多角形どうしの重なり(SAT)。辺が接するだけなら重なりなし。
## tol は許容の食い込み(m)。食い込みが tol 以下なら重なりとしない(例: 玉垣の並びは 0.01)。
static func polygons_overlap(a: PackedVector2Array, b: PackedVector2Array, tol := EPS) -> bool:
	if a.size() < 3 or b.size() < 3:
		return false
	for k in 2:
		var poly: PackedVector2Array = a if k == 0 else b
		var n := poly.size()
		for i in n:
			var e := poly[(i + 1) % n] - poly[i]
			if e.length() < EPS:
				continue
			var axis := Vector2(-e.y, e.x).normalized()
			var ra := _project(a, axis)
			var rb := _project(b, axis)
			if ra.y <= rb.x + tol or rb.y <= ra.x + tol:
				return false
	return true


## 動かす物(poly_local, pos, rot)を、他の物の辺に吸着させる。仕様は architecture.md 7章。
## others = [PackedVector2Array(ワールド座標), ...]
## 戻り値: {snapped: bool, pos: Vector2, rot: float, edge_from: Vector2, edge_to: Vector2}
##   edge_from / edge_to は吸着先の相手側の辺のワールド座標。吸着なしなら両方 Vector2.ZERO。
static func compute_snap(poly_local: PackedVector2Array, pos: Vector2, rot: float, others: Array, threshold: float) -> Dictionary:
	var result := {"snapped": false, "pos": pos, "rot": rot, "edge_from": Vector2.ZERO, "edge_to": Vector2.ZERO}
	if poly_local.size() < 3 or others.is_empty() or threshold <= 0.0:
		return result
	var mine := to_world(poly_local, pos, rot)
	var mine_sign := _outward_sign(mine)
	# 回転中心 pos から最も遠い頂点までの距離(回転しても変わらない)
	var radius := 0.0
	for p in poly_local:
		radius = maxf(radius, p.length())
	var best_dist := INF
	var best: Dictionary = {}

	for other_v in others:
		var other: PackedVector2Array = other_v
		if other.size() < 3:
			continue
		# 遠い相手は飛ばす(相手の AABB と pos の距離が 半径+2*threshold を超えたら候補にならない)
		if _aabb_distance(other, pos) > radius + 2.0 * threshold:
			continue
		var other_sign := _outward_sign(other)
		for j in other.size():
			var f0 := other[j]
			var f1 := other[(j + 1) % other.size()]
			var fd := f1 - f0
			if fd.length() < EPS:
				continue
			var fu := fd.normalized()
			# 相手の外向き法線
			var fn := Vector2(fu.y, -fu.x) * other_sign
			# 動かす物の辺の外向き法線が、相手の外向き法線と逆向き(外側どうしで向かい合う)になる角
			var target_angle := (-fn).angle()

			for i in mine.size():
				var e0 := mine[i]
				var e1 := mine[(i + 1) % mine.size()]
				var ed := e1 - e0
				if ed.length() < EPS:
					continue
				var en := Vector2(ed.y, -ed.x).normalized() * mine_sign
				# 回転量。to_world は rot を増やすと世界のベクトル角が減るため、en の角から target を引く
				var d_rot := wrapf(en.angle() - target_angle, -PI, PI)
				if absf(d_rot) > deg_to_rad(45.0):
					continue
				var new_rot := rot + d_rot
				# 吸着判定に必要な2頂点だけ回転する
				var m0 := _rot_vertex(poly_local[i], pos, new_rot)
				var m1 := _rot_vertex(poly_local[(i + 1) % poly_local.size()], pos, new_rot)
				# 辺どうしの垂直距離(符号つき。動かす量になる)
				var s := (m0 - f0).dot(fn)
				if absf(s) > threshold:
					continue
				# 辺に沿った射影が重なる(または端の差が threshold 以内)
				if not _along_ok(m0, m1, f0, f1, threshold):
					continue
				if absf(s) < best_dist:
					best_dist = absf(s)
					best = {"rot": new_rot, "shift": -s * fn, "f0": f0, "f1": f1, "u": fu,
						"pos": pos, "rot_in": rot, "local": poly_local, "edge": i}

	if best.is_empty():
		return result

	var shift: Vector2 = best["shift"]
	var u: Vector2 = best["u"]
	var f0v: Vector2 = best["f0"]
	var f1v: Vector2 = best["f1"]
	var local: PackedVector2Array = best["local"]
	var ei: int = best["edge"]
	var bpos: Vector2 = best["pos"]
	var brot: float = best["rot"]
	# 吸着した辺の両端(動かす物側)
	var m_ends := [_rot_vertex(local[ei], bpos, brot) + shift,
		_rot_vertex(local[(ei + 1) % local.size()], bpos, brot) + shift]
	var f_ends := [f0v, f1v]
	# 角どうしが threshold/2 以内なら、辺に沿ってだけ動かして角を合わせる
	var corner_best := INF
	var corner_shift := Vector2.ZERO
	for mc in m_ends:
		for q in f_ends:
			var dd: float = (q - mc).length()
			if dd <= threshold * 0.5 and dd < corner_best:
				corner_best = dd
				corner_shift = u * (q - mc).dot(u)

	result["snapped"] = true
	result["pos"] = pos + shift + corner_shift
	result["rot"] = best["rot"]
	result["edge_from"] = f0v
	result["edge_to"] = f1v
	return result


## ローカル頂点 v を、pos を中心に rot で回した世界座標(to_world の1頂点分)。
static func _rot_vertex(v: Vector2, pos: Vector2, rot: float) -> Vector2:
	var c := cos(rot)
	var s := sin(rot)
	return Vector2(v.x * c + v.y * s, -v.x * s + v.y * c) + pos


## 多角形の AABB と点 p の距離(中にあれば 0)。
static func _aabb_distance(poly: PackedVector2Array, p: Vector2) -> float:
	var lo := poly[0]
	var hi := poly[0]
	for q in poly:
		lo = lo.min(q)
		hi = hi.max(q)
	var dx := maxf(maxf(lo.x - p.x, 0.0), p.x - hi.x)
	var dy := maxf(maxf(lo.y - p.y, 0.0), p.y - hi.y)
	return Vector2(dx, dy).length()


static func _project(poly: PackedVector2Array, axis: Vector2) -> Vector2:
	var lo := INF
	var hi := -INF
	for p in poly:
		var d := p.dot(axis)
		lo = minf(lo, d)
		hi = maxf(hi, d)
	return Vector2(lo, hi)


## 多角形の符号(向き): +1 なら外向き法線は (dy, -dx)、-1 なら (-dy, dx)。
static func _outward_sign(poly: PackedVector2Array) -> float:
	var area := 0.0
	var n := poly.size()
	for i in n:
		var a := poly[i]
		var b := poly[(i + 1) % n]
		area += a.x * b.y - b.x * a.y
	return 1.0 if area >= 0.0 else -1.0


## 辺 m0-m1 と f0-f1 の、辺方向 u への射影が重なるか、端の差が threshold 以内か。
static func _along_ok(m0: Vector2, m1: Vector2, f0: Vector2, f1: Vector2, threshold: float) -> bool:
	var u := (f1 - f0).normalized()
	var a0 := (m0 - f0).dot(u)
	var a1 := (m1 - f0).dot(u)
	var b0 := 0.0
	var b1 := (f1 - f0).dot(u)
	var lo_a := minf(a0, a1)
	var hi_a := maxf(a0, a1)
	if hi_a >= b0 - EPS and lo_a <= b1 + EPS:
		return true
	# 端どうしの差
	var end_gap := minf(minf(absf(a0 - b0), absf(a0 - b1)), minf(absf(a1 - b0), absf(a1 - b1)))
	return end_gap <= threshold
