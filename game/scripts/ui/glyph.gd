## 図形アイコン(☰ ↶ ↷ カメラ × ＜ ＞ など)。記号フォントに頼らず _draw で描く。
## kind: "menu" "undo" "redo" "camera" "close" "chev_up" "chev_down" "chev_left" "chev_right"
class_name Glyph
extends Control

var kind := "menu":
	set(v):
		kind = v
		queue_redraw()

var tint := Color("#2B2B2B"):
	set(v):
		tint = v
		queue_redraw()


func _init(k: String = "menu") -> void:
	kind = k
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _draw() -> void:
	var s := minf(size.x, size.y)
	var c := size * 0.5
	var r := s * 0.26
	var w := maxf(3.0, s * 0.075)
	match kind:
		"menu":
			for k in [-1.0, 0.0, 1.0]:
				draw_line(c + Vector2(-r * 1.25, k * r * 0.9), c + Vector2(r * 1.25, k * r * 0.9), tint, w)
		"undo":
			_arc_arrow(c, r, w, false)
		"redo":
			_arc_arrow(c, r, w, true)
		"camera":
			draw_rect(Rect2(c + Vector2(-r * 1.5, -r * 0.9), Vector2(r * 3.0, r * 2.0)), tint, false, w)
			draw_rect(Rect2(c + Vector2(-r * 0.6, -r * 1.35), Vector2(r * 1.2, r * 0.45)), tint, true)
			draw_arc(c, r * 0.55, 0.0, TAU, 24, tint, w)
		"close":
			draw_line(c + Vector2(-r, -r), c + Vector2(r, r), tint, w)
			draw_line(c + Vector2(r, -r), c + Vector2(-r, r), tint, w)
		"chev_up":
			_chev(c, r, w, Vector2(0, -1))
		"chev_down":
			_chev(c, r, w, Vector2(0, 1))
		"chev_left":
			_chev(c, r, w, Vector2(-1, 0))
		"chev_right":
			_chev(c, r, w, Vector2(1, 0))


## 上から左へ戻る(undo)/上から右へ進む(redo)の弧と矢じり。
func _arc_arrow(c: Vector2, r: float, w: float, redo: bool) -> void:
	draw_arc(c, r, -PI, 0.0, 32, tint, w, true)
	var a := 0.0 if redo else -PI
	var p := c + Vector2(cos(a), sin(a)) * r
	var t := Vector2(-sin(a), cos(a))
	if not redo:
		t = -t
	var n := Vector2(-t.y, t.x)
	var tip := p + t * r * 0.6
	draw_colored_polygon(PackedVector2Array([tip, p + n * r * 0.6, p - n * r * 0.6]), tint)


func _chev(c: Vector2, r: float, w: float, d: Vector2) -> void:
	var p := Vector2(-d.y, d.x)
	var tip := c + d * r * 0.6
	var back := c - d * r * 0.6
	draw_polyline(PackedVector2Array([back + p * r * 0.9, tip, back - p * r * 0.9]), tint, w)
