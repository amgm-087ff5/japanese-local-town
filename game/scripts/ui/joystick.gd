## 仮想スティック(浮動式)。触れた位置を中心にし、指を離すと 0 に戻る。
## vector: x=右(+)・y=前(+)、長さは 0..1。自分の指(index)だけを扱い、マルチタッチに対応する。
## 領域の外のタッチは扱わない(WalkMode の見回しに回す)。
class_name Joystick
extends Control

const BASE_R := 96.0
const KNOB_R := 44.0
const DEADZONE := 0.12

var vector := Vector2.ZERO
var _touch := -1
var _center := Vector2.ZERO
var _knob := Vector2.ZERO
var _active := false


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func reset() -> void:
	_touch = -1
	_active = false
	vector = Vector2.ZERO
	_knob = Vector2.ZERO
	queue_redraw()


func _input(event: InputEvent) -> void:
	if not is_visible_in_tree():
		return
	if event is InputEventScreenTouch:
		var t := event as InputEventScreenTouch
		if t.pressed:
			if _touch == -1 and get_global_rect().has_point(t.position):
				_touch = t.index
				_active = true
				_center = t.position - global_position
				_update(t.position)
				get_viewport().set_input_as_handled()
		elif t.index == _touch:
			reset()
			get_viewport().set_input_as_handled()
	elif event is InputEventScreenDrag:
		var d := event as InputEventScreenDrag
		if d.index == _touch:
			_update(d.position)
			get_viewport().set_input_as_handled()


func _update(p: Vector2) -> void:
	var d := p - global_position - _center
	if d.length() > BASE_R:
		d = d.normalized() * BASE_R
	_knob = d
	var v := Vector2(d.x, -d.y) / BASE_R
	if v.length() < DEADZONE:
		v = Vector2.ZERO
	vector = v.limit_length(1.0)
	queue_redraw()


func _draw() -> void:
	var home := Vector2(BASE_R + 24.0, size.y - BASE_R - 24.0)
	var base := _center if _active else home
	var alpha := 0.45 if _active else 0.2
	draw_circle(base, BASE_R, Color(UiTheme.PAPER, 0.35 + alpha * 0.5))
	draw_arc(base, BASE_R, 0.0, TAU, 48, Color(UiTheme.INK, alpha + 0.2), 3.0)
	var knob := base + _knob
	draw_circle(knob, KNOB_R, Color(UiTheme.VERMILION, 0.85 if _active else 0.4))
