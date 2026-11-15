## 環境パネル(状態バーの時刻チップから開く): 時刻スライダ・時間を流す・季節・天気。
## 全画面の薄暗い覆いで、カードの外を押すと閉じる。
class_name EnvPanel
extends Control

const CARD_MAX_W := 640.0

var _main: Node
var _card: PanelContainer
var _content: VBoxContainer
var _groups: GridContainer
var _time_slider: HSlider
var _time_label: Label
var _flow_btn: Button
var _season_btns: Array[Button] = []
var _weather_btns: Array[Button] = []
var _dragging := false


var _dim: ColorRect
var _center: CenterContainer


func _init(main: Node) -> void:
	_main = main
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false

	_dim = ColorRect.new()
	_dim.color = Color(0.0, 0.0, 0.0, 0.28)
	_dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_dim)

	_center = CenterContainer.new()
	_center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_center)

	_card = PanelContainer.new()
	_card.custom_minimum_size = Vector2(CARD_MAX_W, 0)
	_center.add_child(_card)

	_content = VBoxContainer.new()
	_content.add_theme_constant_override("separation", 14)
	_card.add_child(_content)

	var head := HBoxContainer.new()
	_content.add_child(head)
	var title := UiTheme.label("環境", UiTheme.FONT_TITLE)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	var close_btn := UiTheme.glyph_button("close")
	close_btn.pressed.connect(close_panel)
	head.add_child(close_btn)

	var time_row := HBoxContainer.new()
	time_row.add_theme_constant_override("separation", 12)
	_content.add_child(time_row)
	time_row.add_child(UiTheme.label("時刻", UiTheme.FONT_SMALL, UiTheme.INK_SOFT))
	_time_slider = HSlider.new()
	_time_slider.min_value = 0.0
	_time_slider.max_value = 24.0
	_time_slider.step = 0.05
	_time_slider.custom_minimum_size = Vector2(0, 64)
	_time_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_time_slider.focus_mode = Control.FOCUS_NONE
	_time_slider.value_changed.connect(_on_time)
	_time_slider.drag_started.connect(func() -> void: _dragging = true)
	_time_slider.drag_ended.connect(func(_changed: bool) -> void: _dragging = false)
	time_row.add_child(_time_slider)
	_time_label = UiTheme.label("", UiTheme.FONT_BODY)
	_time_label.custom_minimum_size = Vector2(120, 0)
	_time_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	time_row.add_child(_time_label)

	_flow_btn = UiTheme.button("時間を流す")
	_flow_btn.toggle_mode = true
	_flow_btn.toggled.connect(_on_flow)
	_content.add_child(_flow_btn)

	_groups = GridContainer.new()
	_groups.add_theme_constant_override("h_separation", 16)
	_groups.add_theme_constant_override("v_separation", 14)
	_content.add_child(_groups)
	_groups.add_child(_group("季節", UiTheme.SEASONS, _season_btns, _on_season))
	_groups.add_child(_group("天気", UiTheme.WEATHERS, _weather_btns, _on_weather))

	var done := UiTheme.button("閉じる")
	done.pressed.connect(close_panel)
	_content.add_child(done)


func _ready() -> void:
	UiTheme.fill(self)
	UiTheme.fill(_dim)
	UiTheme.fill(_center)


## 画面の大きさに合わせる。横は季節と天気を並べる。
func layout(vs: Vector2, landscape: bool) -> void:
	_card.custom_minimum_size = Vector2(minf(CARD_MAX_W, vs.x - 2.0 * UiTheme.MARGIN), 0)
	_groups.columns = 2 if landscape else 1
	refresh()


func open_panel() -> void:
	visible = true
	refresh()


func close_panel() -> void:
	visible = false


func is_open() -> bool:
	return visible


## 時刻は毎フレーム進むので、表示だけ追いかける(ドラッグ中は触らない)。
func tick() -> void:
	refresh()


func refresh() -> void:
	if Game.world == null:
		return
	var env: Dictionary = Game.world.env
	var t := _current_time()
	if not _dragging:
		_time_slider.set_value_no_signal(t)
	_time_label.text = UiTheme.time_text(t)
	_flow_btn.set_pressed_no_signal(bool(env.get("time_flow", true)))
	UiTheme.set_active(_flow_btn, bool(env.get("time_flow", true)))
	var s := int(env.get("season", 0))
	for i in _season_btns.size():
		UiTheme.set_active(_season_btns[i], i == s)
	var w := int(env.get("weather", 0))
	for i in _weather_btns.size():
		UiTheme.set_active(_weather_btns[i], i == w)


func _current_time() -> float:
	var e: Variant = _main.get("env") if _main != null else null
	if e != null:
		return float(e.get("time"))
	return float(Game.world.env.get("time", 9.0)) if Game.world != null else 9.0


## 季節・天気のどちらか一方のグループ(見出し+4つのボタン)。
func _group(title: String, names: Array, btns: Array[Button], cb: Callable) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 6)
	v.add_child(UiTheme.label(title, UiTheme.FONT_SMALL, UiTheme.INK_SOFT))
	var row := GridContainer.new()
	row.columns = 4
	row.add_theme_constant_override("h_separation", 8)
	v.add_child(row)
	for i in names.size():
		var b := UiTheme.button(names[i], UiTheme.TOUCH)
		b.add_theme_font_size_override("font_size", UiTheme.FONT_TAB)
		b.pressed.connect(cb.bind(i))
		row.add_child(b)
		btns.append(b)
	return v


func _on_time(v: float) -> void:
	var e: Variant = _main.get("env") if _main != null else null
	if e != null and e.has_method("set_time"):
		e.set_time(v)
	elif Game.world != null:
		Game.world.env["time"] = v
	_time_label.text = UiTheme.time_text(v)


func _on_flow(on: bool) -> void:
	Game.set_env("time_flow", on)
	refresh()


func _on_season(i: int) -> void:
	Game.set_env("season", i)
	refresh()


func _on_weather(i: int) -> void:
	Game.set_env("weather", i)
	refresh()


## 覆いを押したら閉じる(カードの中の操作は覆いに届かない)。
func _gui_input(ev: InputEvent) -> void:
	var touch_down := ev is InputEventScreenTouch and (ev as InputEventScreenTouch).pressed
	var mouse_down := ev is InputEventMouseButton and (ev as InputEventMouseButton).pressed
	if touch_down or mouse_down:
		close_panel()
