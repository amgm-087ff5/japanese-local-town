## 地形パネル(architecture 11章・12章): 道具・地表の種類(道具が「地表」の時だけ)・ブラシの大きさと強さ。
class_name TerrainPanel
extends VBoxContainer

const TOOLS := [
	["raise", "上げる"], ["lower", "下げる"], ["flatten", "平ら"], ["smooth", "なめらか"],
	["surface", "地表"], ["forest_add", "森を植える"], ["forest_remove", "森を消す"],
]
const SURFACE_NAMES := ["草", "土", "砂利", "石畳", "苔", "白砂", "畑", "舗装"]
var SURFACE_COLORS: Array[Color] = [
	Color("#7C9A4E"), Color("#8A6A47"), Color("#A7A39B"), Color("#CFCABF"),
	Color("#5E7D3A"), Color("#EEE8D8"), Color("#B07D45"), Color("#55534E"),
]

var _main: Node
var _tool_grid: GridContainer
var _tool_btns := {}
var _surface_grid: GridContainer
var _chips: Array[Button] = []
var _slider_grid: GridContainer
var _radius_label: Label
var _radius_slider: HSlider
var _strength_label: Label
var _strength_slider: HSlider
var _key := ""


func _init(main: Node) -> void:
	_main = main
	add_theme_constant_override("separation", 8)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL

	_tool_grid = GridContainer.new()
	_tool_grid.add_theme_constant_override("h_separation", 8)
	_tool_grid.add_theme_constant_override("v_separation", 8)
	add_child(_tool_grid)
	for t in TOOLS:
		var b := UiTheme.button(t[1])
		b.pressed.connect(_on_tool.bind(t[0]))
		_tool_grid.add_child(b)
		_tool_btns[t[0]] = b

	_surface_grid = GridContainer.new()
	_surface_grid.add_theme_constant_override("h_separation", 8)
	_surface_grid.add_theme_constant_override("v_separation", 8)
	add_child(_surface_grid)
	for i in SURFACE_NAMES.size():
		var b := _make_chip(i)
		_surface_grid.add_child(b)
		_chips.append(b)

	_slider_grid = GridContainer.new()
	_slider_grid.add_theme_constant_override("h_separation", 16)
	_slider_grid.add_theme_constant_override("v_separation", 8)
	add_child(_slider_grid)
	var r := _slider_column()
	_radius_label = r[0]
	_radius_slider = r[1]
	_radius_slider.min_value = 2.0
	_radius_slider.max_value = 30.0
	_radius_slider.step = 1.0
	_radius_slider.value_changed.connect(_on_radius)
	var s := _slider_column()
	_strength_label = s[0]
	_strength_slider = s[1]
	_strength_slider.min_value = 0.0
	_strength_slider.max_value = 1.0
	_strength_slider.step = 0.05
	_strength_slider.value_changed.connect(_on_strength)
	set_landscape(false)


## 縦: 道具4列・地表4列(2段)。横: 2列で縦に流す。
func set_landscape(land: bool) -> void:
	_tool_grid.columns = 2 if land else 4
	_surface_grid.columns = 2 if land else 4
	_slider_grid.columns = 1 if land else 2
	_key = ""
	refresh()


func refresh() -> void:
	var tm: Variant = _main.get("terrain_mode") if _main != null else null
	if tm == null:
		return
	var tool := str(tm.get("tool"))
	var st := int(tm.get("surface_type"))
	var rad := float(tm.get("radius"))
	var stg := float(tm.get("strength"))
	var key := "%s|%d|%.2f|%.3f" % [tool, st, rad, stg]
	if key == _key:
		return
	_key = key
	for t in _tool_btns:
		UiTheme.set_active(_tool_btns[t], t == tool)
	var on_surface := tool == "surface"
	_surface_grid.visible = on_surface
	for i in _chips.size():
		_style_chip(_chips[i], i, on_surface and i == st)
	_radius_label.text = "ブラシ %dm" % int(rad)
	_radius_slider.set_value_no_signal(rad)
	_strength_label.text = "強さ %d%%" % int(roundf(stg * 100.0))
	_strength_slider.set_value_no_signal(stg)


func _make_chip(i: int) -> Button:
	var b := UiTheme.button(SURFACE_NAMES[i])
	b.pressed.connect(_on_surface.bind(i))
	var sw := Panel.new()
	sw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sw.position = Vector2(16, (UiTheme.TOUCH - 30.0) * 0.5)
	sw.size = Vector2(30, 30)
	sw.add_theme_stylebox_override("panel", UiTheme.box(SURFACE_COLORS[i], UiTheme.INK, 1, 6))
	b.add_child(sw)
	_style_chip(b, i, false)
	return b


## 色見本つきのチップ。文字は色見本の右に寄せる。
func _style_chip(b: Button, _i: int, on: bool) -> void:
	var bg: Color = UiTheme.VERMILION if on else UiTheme.PAPER_LIGHT
	var border: Color = UiTheme.VERMILION if on else UiTheme.LINE
	var s := UiTheme.box(bg, border, 2)
	s.content_margin_left = 56.0
	b.add_theme_stylebox_override("normal", s)
	b.add_theme_stylebox_override("hover", s)
	b.add_theme_stylebox_override("pressed", s)
	var fc: Color = UiTheme.PAPER_LIGHT if on else UiTheme.INK
	b.add_theme_color_override("font_color", fc)
	b.add_theme_color_override("font_hover_color", fc)
	b.add_theme_color_override("font_pressed_color", fc)


## [Label, HSlider] の組。
func _slider_column() -> Array:
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	var lb := UiTheme.label("", UiTheme.FONT_SMALL)
	col.add_child(lb)
	var sl := HSlider.new()
	sl.custom_minimum_size = Vector2(0, 64)
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sl.focus_mode = Control.FOCUS_NONE
	col.add_child(sl)
	_slider_grid.add_child(col)
	return [lb, sl]


func _on_tool(t: String) -> void:
	_set_tm("tool", t)


func _on_surface(i: int) -> void:
	_set_tm("surface_type", i)


func _on_radius(v: float) -> void:
	_set_tm("radius", v)


func _on_strength(v: float) -> void:
	_set_tm("strength", v)


func _set_tm(prop: String, value: Variant) -> void:
	var tm: Variant = _main.get("terrain_mode") if _main != null else null
	if tm != null:
		tm.set(prop, value)
	_key = ""
	refresh()
