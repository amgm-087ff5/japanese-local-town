## 歩行HUD(architecture 11章・15.3)。左下の仮想スティック・走る(押している間)・ジャンプ、右上の視点切替・おわる。
## 走る/ジャンプは自分の指(index)で扱うので、スティックと同時に押せる。それ以外の領域は WalkMode の見回しに届く。
class_name WalkHud
extends Control

const PAD := 146.0

var _main: Node
var _stick: Joystick
var _top: BoxContainer
var _view_btn: Button
var _end_btn: Button
var _run_rect := Rect2()
var _jump_rect := Rect2()
var _run_touch := -1
var _jump_touch := -1


func _init(main: Node) -> void:
	_main = main
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = false

	_stick = Joystick.new()
	add_child(_stick)

	_top = BoxContainer.new()
	_top.add_theme_constant_override("separation", 8)
	_top.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(_top)
	_view_btn = UiTheme.button("視点切替", UiTheme.TOUCH, 190.0)
	_view_btn.size_flags_horizontal = Control.SIZE_SHRINK_END
	_view_btn.pressed.connect(_call_wm.bind("toggle_view"))
	_top.add_child(_view_btn)
	_end_btn = UiTheme.button("おわる", UiTheme.TOUCH, 150.0)
	_end_btn.size_flags_horizontal = Control.SIZE_SHRINK_END
	_end_btn.pressed.connect(Game.set_mode.bind("edit"))
	_top.add_child(_end_btn)


func _ready() -> void:
	UiTheme.fill(self)


## 画面の大きさに合わせて配置する。stick は左下の半分、走る/ジャンプは右下、ボタン列は右上。
func layout(vs: Vector2, ins: Vector4) -> void:
	var l := ins.x
	var t := ins.y
	var r := ins.z
	var b := ins.w
	var zone_top := vs.y * 0.34
	_stick.position = Vector2(l, zone_top)
	_stick.size = Vector2(vs.x * 0.5 - l, vs.y - zone_top - b)
	var bottom := vs.y - b - 20.0
	var right := vs.x - r - 16.0
	_jump_rect = Rect2(right - PAD, bottom - PAD, PAD, PAD)
	_run_rect = Rect2(right - PAD * 2.0 - 16.0, bottom - PAD, PAD, PAD)
	_top.size = _top.get_combined_minimum_size()
	_top.position = Vector2(vs.x - r - 16.0 - _top.size.x, t + 8.0)
	queue_redraw()


## 歩行を抜ける時に、押している指・スティックを止める。
func reset() -> void:
	_run_touch = -1
	_jump_touch = -1
	_stick.reset()
	_call_wm("set_run", [false])
	queue_redraw()


func visible_rects() -> Dictionary:
	return {
		"stick": _stick.get_global_rect(),
		"run": _run_rect,
		"jump": _jump_rect,
		"top": _top.get_global_rect(),
	}


func _process(_delta: float) -> void:
	if is_visible_in_tree():
		_call_wm("set_move_vector", [_stick.vector])


func _input(event: InputEvent) -> void:
	if not is_visible_in_tree():
		return
	if not (event is InputEventScreenTouch):
		return
	var t := event as InputEventScreenTouch
	if t.pressed:
		if _run_touch == -1 and _run_rect.has_point(t.position):
			_run_touch = t.index
			_call_wm("set_run", [true])
			queue_redraw()
			get_viewport().set_input_as_handled()
		elif _jump_touch == -1 and _jump_rect.has_point(t.position):
			_jump_touch = t.index
			_call_wm("jump")
			queue_redraw()
			get_viewport().set_input_as_handled()
	else:
		if t.index == _run_touch:
			_run_touch = -1
			_call_wm("set_run", [false])
			queue_redraw()
			get_viewport().set_input_as_handled()
		elif t.index == _jump_touch:
			_jump_touch = -1
			queue_redraw()
			get_viewport().set_input_as_handled()


func _draw() -> void:
	if not is_visible_in_tree():
		return
	_draw_pad(_run_rect, "走る", _run_touch != -1)
	_draw_pad(_jump_rect, "ジャンプ", _jump_touch != -1)


func _draw_pad(r: Rect2, text: String, pressed: bool) -> void:
	var c := r.get_center()
	var rad := r.size.x * 0.5
	var fill := Color(UiTheme.VERMILION, 0.9) if pressed else Color(UiTheme.PAPER, 0.8)
	draw_circle(c, rad, fill)
	draw_arc(c, rad, 0.0, TAU, 48, Color(UiTheme.INK, 0.5), 3.0)
	var fs := UiTheme.FONT_BODY
	var col: Color = UiTheme.PAPER_LIGHT if pressed else UiTheme.INK
	draw_string(UiTheme.font(), Vector2(r.position.x, c.y + fs * 0.35), text,
		HORIZONTAL_ALIGNMENT_CENTER, r.size.x, fs, col)


func _call_wm(method: String, args: Array = []) -> void:
	var wm: Variant = _main.get("walk_mode") if _main != null else null
	if wm != null and wm.has_method(method):
		wm.callv(method, args)
