## 画面UI(architecture.md 12章・15.3)。縦・横で配置を変える。パネルやボタンの上のタッチは 3D に通さない(STOP)。
## 3D の領域は mouse_filter=IGNORE にして、モード側の _unhandled_input に届かせる。
## 縦: 上=状態バー、下=モードタブ、その上に道具のシート(38%まで・畳める)。
## 横: 上=状態バー、左=モードタブ(縦)、右=道具のパネル(幅380・畳める)。
class_name Hud
extends Control

const MODE_TABS := [["配置", "edit"], ["地形", "terrain"], ["歩く", "walk"], ["撮影", "photo"]]
const CAM_PRESETS := [["top", "真上"], ["side", "真横"], ["oblique", "斜め"], ["north", "北"]]
const BAR_H := 96.0
const GAP := 8.0
const SHEET_HEAD_H := 84.0
const SHEET_GAP := 6.0
const SHEET_MAX_RATIO := 0.38
const SIDE_W := 380.0         # 横画面のシートの幅(道具ボタン2列で「森を植える」が切れない幅)
const SIDE_COLLAPSED_W := 84.0
const TOAST_SEC := 2.0
const QUIT_SEC := 2.0
const POLL_SEC := 0.2
const QUIT_TEXT := "もう一度押すと終了します"

var _main: Node
var _thumbs: Thumbnailer
var _view := Vector2.ZERO
var _ins := Vector4.ZERO
var _landscape := false
var _sheet_open := true
var _last_min_h := -1.0
var _poll := 0.0
var _quit_armed := false

var _bar: PanelContainer
var _btn_menu: Button
var _lbl_world: Label
var _btn_env: Button
var _btn_undo: Button
var _btn_redo: Button
var _btn_cam: Button
var _tabs: BoxContainer
var _tab_btns := {}
var _sheet: PanelContainer
var _sheet_head: Button
var _sheet_scroll: ScrollContainer
var _sheet_content: VBoxContainer
var _palette: PalettePanel
var _terrain: TerrainPanel
var _walk: WalkHud
var _photo_back: Button
var _cam_pop: Control
var _cam_card: PanelContainer
var _env: EnvPanel
var _menu: MenuPanel
var _toast: PanelContainer
var _toast_label: Label
var _toast_timer: Timer
var _quit_timer: Timer


func _ready() -> void:
	UiTheme.fill(self)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	theme = UiTheme.make_theme()
	_main = get_tree().get_first_node_in_group("main")
	_thumbs = Thumbnailer.new()
	add_child(_thumbs)
	_build_bar()
	_build_tabs()
	_build_sheet()
	_build_walk()
	_build_photo()
	_build_overlays()
	_build_toast()
	Game.mode_changed.connect(_on_mode_changed)
	Game.world_loaded.connect(_refresh_all)
	Game.undo_changed.connect(_refresh_undo)
	Game.env_changed.connect(_on_env_changed)
	Game.settings_changed.connect(_on_settings_changed)
	get_viewport().size_changed.connect(_on_size_changed)
	_relayout()
	_refresh_all()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_GO_BACK_REQUEST:
		handle_back()


func _process(delta: float) -> void:
	_poll -= delta
	if _poll > 0.0:
		return
	_poll = POLL_SEC
	_refresh_world_name()
	_refresh_env_chip()
	_refresh_undo()
	if _palette.visible:
		_palette.refresh()
	if _terrain.visible:
		_terrain.refresh()
	if _env.visible:
		_env.tick()
	if absf(_content_min_h() - _last_min_h) > 0.5:
		_relayout()


# ---------------------------------------------------------------- 公開(テスト・Main から)

func show_toast(text: String) -> void:
	_toast_label.text = text
	_toast.visible = true
	_toast_timer.start(TOAST_SEC)
	_place_toast()


func tab_button(mode: String) -> Button:
	return _tab_btns.get(mode) as Button


func palette_card_count() -> int:
	return _palette.card_count()


func menu_open() -> bool:
	return _menu.visible


func is_quit_armed() -> bool:
	return _quit_armed


## Android の戻るボタン(15.3)。メニュー/環境/カメラの覆い → 仮置き・選択の解除 → 地形モードは配置へ → 歩行/撮影を終了 → 「もう一度」で保存して終了。
## 戻り値: 処理したら true。
func handle_back() -> bool:
	if _menu.visible:
		_menu.close_menu()
		return true
	if _env.visible:
		_env.close_panel()
		return true
	if _cam_pop.visible:
		_cam_pop.visible = false
		return true
	var em: Variant = _main.get("edit_mode") if _main != null else null
	if Game.mode == "edit" and em != null:
		var placing := str(_prop(em, "placing_type", ""))
		var sel := int(_prop(em, "selected_uid", -1))
		if placing != "" and em.has_method("cancel"):
			em.cancel()
			return true
		if sel >= 0:
			if em.has_method("clear_selection"):
				em.clear_selection()
			elif em.has_method("cancel"):
				em.cancel()
			return true
	if Game.mode == "terrain":
		Game.set_mode("edit")
		return true
	if Game.mode == "walk" or Game.mode == "photo":
		Game.set_mode("edit")
		return true
	if _quit_armed:
		Game.save_world()
		get_tree().quit()
		return true
	_quit_armed = true
	_quit_timer.start(QUIT_SEC)
	show_toast(QUIT_TEXT)
	return true


# ---------------------------------------------------------------- 構築

func _build_bar() -> void:
	_bar = PanelContainer.new()
	_bar.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_bar)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	_bar.add_child(row)

	_btn_menu = UiTheme.glyph_button("menu")
	_btn_menu.tooltip_text = "メニュー"
	_btn_menu.pressed.connect(_open_menu)
	row.add_child(_btn_menu)

	_lbl_world = UiTheme.label("", UiTheme.FONT_BODY)
	_lbl_world.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_lbl_world.custom_minimum_size = Vector2(0, UiTheme.TOUCH)
	_lbl_world.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(_lbl_world)

	_btn_env = UiTheme.button("", UiTheme.TOUCH, 172.0)
	_btn_env.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	_btn_env.pressed.connect(_open_env)
	row.add_child(_btn_env)

	_btn_undo = UiTheme.glyph_button("undo")
	_btn_undo.tooltip_text = "元に戻す"
	_btn_undo.pressed.connect(Game.undo)
	row.add_child(_btn_undo)

	_btn_redo = UiTheme.glyph_button("redo")
	_btn_redo.tooltip_text = "やり直す"
	_btn_redo.pressed.connect(Game.redo)
	row.add_child(_btn_redo)

	_btn_cam = UiTheme.glyph_button("camera")
	_btn_cam.tooltip_text = "カメラの定位置"
	_btn_cam.pressed.connect(_toggle_cam)
	row.add_child(_btn_cam)


func _build_tabs() -> void:
	_tabs = BoxContainer.new()
	_tabs.add_theme_constant_override("separation", 8)
	_tabs.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_tabs)
	for t in MODE_TABS:
		var b := UiTheme.button(t[0], UiTheme.TOUCH)
		b.add_theme_font_size_override("font_size", UiTheme.FONT_TAB)
		b.pressed.connect(Game.set_mode.bind(t[1]))
		_tabs.add_child(b)
		_tab_btns[t[1]] = b


func _build_sheet() -> void:
	_sheet = PanelContainer.new()
	_sheet.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_sheet)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(SHEET_GAP))
	_sheet.add_child(v)

	_sheet_head = UiTheme.button("配置", UiTheme.TOUCH)
	var g := Glyph.new("chev_down")
	g.name = "Glyph"
	_sheet_head.add_child(g)
	_sheet_head.pressed.connect(_toggle_sheet)
	v.add_child(_sheet_head)

	_sheet_scroll = ScrollContainer.new()
	_sheet_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_sheet_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(_sheet_scroll)
	_sheet_content = VBoxContainer.new()
	_sheet_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sheet_content.add_theme_constant_override("separation", 10)
	_sheet_scroll.add_child(_sheet_content)

	_palette = PalettePanel.new(_thumbs, _main)
	_sheet_content.add_child(_palette)
	_terrain = TerrainPanel.new(_main)
	_sheet_content.add_child(_terrain)


func _build_walk() -> void:
	_walk = WalkHud.new(_main)
	add_child(_walk)


func _build_photo() -> void:
	_photo_back = UiTheme.button("もどる", UiTheme.TOUCH, 190.0)
	_photo_back.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var fade := UiTheme.box(Color(UiTheme.PAPER, 0.55), Color(0, 0, 0, 0), 0)
	for k in ["normal", "hover", "pressed"]:
		_photo_back.add_theme_stylebox_override(k, fade)
	for k in ["font_color", "font_hover_color", "font_pressed_color"]:
		_photo_back.add_theme_color_override(k, Color(UiTheme.INK, 0.85))
	var g := Glyph.new("chev_left")
	g.name = "Glyph"
	g.anchor_bottom = 1.0
	g.offset_left = 14.0
	g.offset_right = 54.0
	_photo_back.add_child(g)
	_photo_back.pressed.connect(Game.set_mode.bind("edit"))
	add_child(_photo_back)


func _build_overlays() -> void:
	_env = EnvPanel.new(_main)
	add_child(_env)
	_menu = MenuPanel.new()
	_menu.message.connect(show_toast)
	add_child(_menu)

	_cam_pop = Control.new()
	_cam_pop.mouse_filter = Control.MOUSE_FILTER_STOP
	_cam_pop.visible = false
	_cam_pop.gui_input.connect(_on_cam_catcher)
	add_child(_cam_pop)
	UiTheme.fill(_cam_pop)
	_cam_card = PanelContainer.new()
	_cam_card.custom_minimum_size = Vector2(220, 0)
	_cam_pop.add_child(_cam_card)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	_cam_card.add_child(v)
	for p in CAM_PRESETS:
		var b := UiTheme.button(p[1])
		b.pressed.connect(_on_cam_preset.bind(p[0]))
		v.add_child(b)


func _build_toast() -> void:
	_toast = PanelContainer.new()
	_toast.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast.add_theme_stylebox_override("panel", UiTheme.box(Color(UiTheme.INK, 0.86), Color(0, 0, 0, 0), 0, 12, true))
	_toast_label = UiTheme.label("", UiTheme.FONT_BODY, UiTheme.PAPER_LIGHT)
	_toast_label.clip_text = false
	_toast.add_child(_toast_label)
	_toast.visible = false
	add_child(_toast)
	_toast_timer = Timer.new()
	_toast_timer.one_shot = true
	_toast_timer.wait_time = TOAST_SEC
	_toast_timer.timeout.connect(_on_toast_timeout)
	add_child(_toast_timer)
	_quit_timer = Timer.new()
	_quit_timer.one_shot = true
	_quit_timer.wait_time = QUIT_SEC
	_quit_timer.timeout.connect(_on_quit_timeout)
	add_child(_quit_timer)


# ---------------------------------------------------------------- 配置(縦横・表示)

func _on_size_changed() -> void:
	_relayout()


## 画面の大きさに合わせて全部配置し直す。size_override はテスト用(省略時はビューポート)。
func _relayout(size_override := Vector2.ZERO) -> void:
	var vs := size_override
	if vs == Vector2.ZERO:
		vs = get_viewport_rect().size
	_view = vs
	_ins = _safe_insets(vs)
	_landscape = vs.x > vs.y
	var l := _ins.x
	var t := _ins.y
	var r := _ins.z
	var b := _ins.w
	var m := UiTheme.MARGIN
	var mode := Game.mode
	var chrome := mode == "edit" or mode == "terrain"
	var inner_w := vs.x - l - r

	_bar.visible = chrome
	_tabs.visible = chrome
	_sheet.visible = chrome
	_tabs.vertical = _landscape
	# 縦では世界名を状態バーから外し(メニューに出す)、その分だけ時刻チップを広げる
	_lbl_world.visible = _landscape
	_btn_env.size_flags_horizontal = Control.SIZE_SHRINK_CENTER if _landscape else Control.SIZE_EXPAND_FILL
	_btn_env.custom_minimum_size.x = 172.0 if _landscape else 0.0
	_palette.set_landscape(_landscape)
	_terrain.set_landscape(_landscape)
	_update_head()

	var bar_rect := Rect2(l + m, t + GAP, inner_w - 2.0 * m, BAR_H)
	_place(_bar, bar_rect)
	_sheet_scroll.visible = chrome and _sheet_open
	var content_h := _content_min_h()
	_last_min_h = content_h
	var sheet_pad := 2.0 * UiTheme.PANEL_PAD_V
	if _landscape:
		var top := bar_rect.end.y + GAP
		var bottom := vs.y - b - 16.0
		_place(_tabs, Rect2(l + m, top, UiTheme.TOUCH, 4.0 * UiTheme.TOUCH + 3.0 * 8.0))
		var w := SIDE_W if _sheet_open else SIDE_COLLAPSED_W
		var h := (bottom - top) if _sheet_open else (SHEET_HEAD_H + sheet_pad)
		_place(_sheet, Rect2(vs.x - r - m - w, top, w, h))
	else:
		var tab_top := vs.y - b - 16.0 - UiTheme.TOUCH
		_place(_tabs, Rect2(l + m, tab_top, inner_w - 2.0 * m, UiTheme.TOUCH))
		var tail := SHEET_HEAD_H + sheet_pad
		var h2 := tail
		if _sheet_open:
			var body := minf(content_h, vs.y * SHEET_MAX_RATIO - tail - SHEET_GAP)
			h2 = tail + SHEET_GAP + maxf(body, 0.0)
		_place(_sheet, Rect2(l + m, tab_top - GAP - h2, inner_w - 2.0 * m, h2))

	_walk.visible = mode == "walk"
	if _walk.visible:
		_walk.layout(vs, _ins)
	_photo_back.visible = mode == "photo"
	_place(_photo_back, Rect2(l + m, t + GAP, 190.0, UiTheme.TOUCH))

	_env.layout(vs, _landscape)

	_cam_card.size = _cam_card.get_combined_minimum_size()
	_cam_card.position = Vector2(vs.x - r - m - _cam_card.size.x, bar_rect.end.y + 6.0)
	_place_toast()


func _place_toast() -> void:
	var w := minf(560.0, _view.x - 2.0 * UiTheme.MARGIN)
	_toast.size = Vector2(w, 0.0)
	_toast.size = Vector2(w, _toast.get_combined_minimum_size().y)
	_toast.position = Vector2((_view.x - w) * 0.5, _ins.y + GAP + BAR_H + 12.0)


## セーフエリア(端末の切り欠き・ナビゲーションバー)を論理pxに換算する。デスクトップでは 0。
func _safe_insets(vs: Vector2) -> Vector4:
	if not OS.has_feature("mobile"):
		return Vector4.ZERO
	var win := Vector2(DisplayServer.window_get_size())
	var safe := DisplayServer.get_display_safe_area()
	if win.x <= 0.0 or win.y <= 0.0 or safe.size.x <= 0 or safe.size.y <= 0:
		return Vector4.ZERO
	var kx := vs.x / win.x
	var ky := vs.y / win.y
	var l := clampf(float(safe.position.x) * kx, 0.0, vs.x * 0.2)
	var t := clampf(float(safe.position.y) * ky, 0.0, vs.y * 0.2)
	var r := clampf((win.x - float(safe.end.x)) * kx, 0.0, vs.x * 0.2)
	var b := clampf((win.y - float(safe.end.y)) * ky, 0.0, vs.y * 0.2)
	return Vector4(l, t, r, b)


func _content_min_h() -> float:
	return _sheet_content.get_combined_minimum_size().y


func _update_head() -> void:
	var title := "配置" if Game.mode == "edit" else "地形"
	var collapsed_side := _landscape and not _sheet_open
	_sheet_head.text = "" if collapsed_side else title
	var g := _sheet_head.get_node("Glyph") as Glyph
	if _landscape:
		g.kind = "chev_right" if _sheet_open else "chev_left"
	else:
		g.kind = "chev_down" if _sheet_open else "chev_up"
	# 直接指定する(set_anchors_preset は今の親の大きさで計算し、高さが 0 になることがあったため使わない)
	g.anchor_top = 0.0
	g.anchor_bottom = 1.0
	g.offset_top = 0.0
	g.offset_bottom = 0.0
	if collapsed_side:
		# 狭い時(横の畳んだ状態)は全体の中央に描く
		g.anchor_left = 0.0
		g.anchor_right = 1.0
		g.offset_left = 0.0
		g.offset_right = 0.0
	else:
		# 見出しの右端に寄せる
		g.anchor_left = 1.0
		g.anchor_right = 1.0
		g.offset_left = -72.0
		g.offset_right = -20.0


func _place(c: Control, rect: Rect2) -> void:
	c.position = rect.position
	c.size = rect.size


func _toggle_sheet() -> void:
	_sheet_open = not _sheet_open
	_relayout()


# ---------------------------------------------------------------- 状態の反映

func _refresh_all() -> void:
	var m := Game.mode
	for k in _tab_btns:
		UiTheme.set_active(_tab_btns[k], k == m)
	_palette.visible = m == "edit"
	_terrain.visible = m == "terrain"
	_refresh_world_name()
	_refresh_env_chip()
	_refresh_undo()
	_palette.refresh()
	_terrain.refresh()
	_relayout()


func _refresh_world_name() -> void:
	_lbl_world.text = Game.world.name if Game.world != null else ""


func _refresh_env_chip() -> void:
	if Game.world == null:
		_btn_env.text = ""
		return
	var s := clampi(int(Game.world.env.get("season", 0)), 0, 3)
	var w := clampi(int(Game.world.env.get("weather", 0)), 0, 3)
	_btn_env.text = "%s %s %s" % [UiTheme.SEASONS[s], UiTheme.WEATHERS[w], UiTheme.time_text(_current_time())]


func _refresh_undo() -> void:
	_btn_undo.disabled = not Game.can_undo()
	_btn_redo.disabled = not Game.can_redo()


func _current_time() -> float:
	var e: Variant = _main.get("env") if _main != null else null
	if e != null:
		return float(e.get("time"))
	return float(Game.world.env.get("time", 9.0)) if Game.world != null else 9.0


func _on_mode_changed(_m: String) -> void:
	_menu.close_menu()
	_env.close_panel()
	_cam_pop.visible = false
	_walk.reset()
	_refresh_all()


func _on_env_changed() -> void:
	_refresh_env_chip()
	_env.refresh()


func _on_settings_changed() -> void:
	_palette.refresh()


# ---------------------------------------------------------------- 操作

func _open_menu() -> void:
	_env.close_panel()
	_cam_pop.visible = false
	_menu.open_menu()
	_relayout()


func _open_env() -> void:
	_menu.close_menu()
	_cam_pop.visible = false
	_env.open_panel()
	_relayout()


func _toggle_cam() -> void:
	_cam_pop.visible = not _cam_pop.visible
	_relayout()


func _on_cam_catcher(ev: InputEvent) -> void:
	var touch_down := ev is InputEventScreenTouch and (ev as InputEventScreenTouch).pressed
	var mouse_down := ev is InputEventMouseButton and (ev as InputEventMouseButton).pressed
	if touch_down or mouse_down:
		_cam_pop.visible = false


func _on_cam_preset(preset: String) -> void:
	var rig: Variant = _main.get("camera_rig") if _main != null else null
	if rig != null and rig.has_method("set_preset"):
		rig.set_preset(preset)
	_cam_pop.visible = false


func _on_toast_timeout() -> void:
	_toast.visible = false


func _on_quit_timeout() -> void:
	_quit_armed = false


static func _prop(obj: Variant, prop: String, default: Variant) -> Variant:
	if obj == null:
		return default
	var v: Variant = obj.get(prop)
	return default if v == null else v
