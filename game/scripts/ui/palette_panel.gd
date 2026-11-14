## 配置パネル(architecture 11章・12章)。分類タブ・アイテムのグリッド(サムネイル+名前)・仮置き/選択中の操作・スナップ。
## 縦は横スクロールの1行、横は2列の縦スクロール(外側のシートがスクロールする)。
class_name PalettePanel
extends VBoxContainer

const CATEGORIES := [["shrine", "神社"], ["nature", "自然"], ["town", "街"]]
const CARD_W := 128.0
const CARD_H := 150.0
const THUMB := 100.0
const ROT_STEP := 15.0

var _thumbs: Thumbnailer
var _main: Node
var _landscape := false
var _cat := "shrine"
var _cat_btns := {}
var _grids := {}
var _cards := {}
var _card_images := {}
var _scroll: ScrollContainer
var _hint: Label
var _actions: GridContainer
var _snap_slot: VBoxContainer     # スナップの切り替えは全幅の1行(横では文字が切れないように)
var _state_key := ""


func _init(thumbs: Thumbnailer, main: Node) -> void:
	_thumbs = thumbs
	_main = main
	add_theme_constant_override("separation", 8)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var cat_grid := GridContainer.new()
	cat_grid.columns = 3
	cat_grid.add_theme_constant_override("h_separation", 8)
	add_child(cat_grid)
	for c in CATEGORIES:
		var b := UiTheme.button(c[1])
		b.pressed.connect(_on_cat.bind(c[0]))
		cat_grid.add_child(b)
		_cat_btns[c[0]] = b

	_hint = UiTheme.label("", UiTheme.FONT_SMALL, UiTheme.INK_SOFT)
	UiTheme.wrap_label(_hint)
	add_child(_hint)

	_actions = GridContainer.new()
	_actions.add_theme_constant_override("h_separation", 8)
	_actions.add_theme_constant_override("v_separation", 8)
	add_child(_actions)
	_snap_slot = VBoxContainer.new()
	_snap_slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(_snap_slot)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(_scroll)
	var stack := VBoxContainer.new()
	stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(stack)
	for c in CATEGORIES:
		var g := GridContainer.new()
		g.add_theme_constant_override("h_separation", 8)
		g.add_theme_constant_override("v_separation", 8)
		stack.add_child(g)
		_grids[c[0]] = g
		for it in Catalog.by_category(c[0]):
			g.add_child(_make_card(it))

	_thumbs.thumb_ready.connect(_on_thumb)
	var em: Variant = _main.get("edit_mode") if _main != null else null
	if em != null:
		if em.has_signal("placing_changed"):
			em.connect("placing_changed", _on_edit_changed)
		if em.has_signal("selection_changed"):
			em.connect("selection_changed", _on_edit_changed)
	set_landscape(false)


func card_count() -> int:
	return _cards.size()


## 縦横に合わせて並びを変える。縦: 分類ごとに1行の横スクロール。横: 2列で縦に流す。
func set_landscape(land: bool) -> void:
	_landscape = land
	for c in CATEGORIES:
		var g: GridContainer = _grids[c[0]]
		g.columns = 2 if land else maxi(1, Catalog.by_category(c[0]).size())
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED if land else ScrollContainer.SCROLL_MODE_AUTO
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_state_key = ""
	_apply_cat()
	refresh()


## 仮置き・選択・スナップが変わったら操作列を作り直す。変わっていなければ何もしない。
func refresh() -> void:
	var em: Variant = _em()
	var placing := str(_prop(em, "placing_type", ""))
	var sel := int(_prop(em, "selected_uid", -1))
	var snap := bool(Game.settings.get("snap", true))
	var key := "%s|%d|%s|%s" % [placing, sel, str(snap), str(_landscape)]
	if _hint.visible:
		UiTheme.refit(_hint)
	if key == _state_key:
		return
	_state_key = key
	_rebuild_actions(placing, sel, snap)
	for id in _cards:
		var card := _cards[id] as Button
		if id == placing:
			card.add_theme_stylebox_override("normal", UiTheme.box(UiTheme.PAPER_LIGHT, UiTheme.VERMILION, 3))
		else:
			card.remove_theme_stylebox_override("normal")


func _rebuild_actions(placing: String, sel: int, snap: bool) -> void:
	for ch in _actions.get_children():
		_actions.remove_child(ch)
		ch.queue_free()
	var list: Array[Button] = []
	if placing != "":
		_set_hint("ドラッグで場所を決め、「決定」を押します。")
		list.append(_act("決定", _on_confirm, true))
		list.append(_act("やめる", _on_cancel))
		list.append(_act("左15°", _on_rot.bind(-ROT_STEP)))
		list.append(_act("右15°", _on_rot.bind(ROT_STEP)))
	elif sel >= 0:
		_hint.visible = false
		list.append(_act("左15°", _on_rot.bind(-ROT_STEP)))
		list.append(_act("右15°", _on_rot.bind(ROT_STEP)))
		list.append(_act("複製", _call_em.bind("duplicate_selected")))
		list.append(_act("整地", _call_em.bind("flatten_selected")))
		list.append(_act("削除", _call_em.bind("delete_selected")))
		list.append(_act("解除", _on_clear))
	else:
		_set_hint("下の分類から置くものを選びます。置いた物をタップすると、動かす・回す・削除できます。")
	for b in list:
		_actions.add_child(b)
	_actions.columns = maxi(1, 2 if _landscape else list.size())
	for ch in _snap_slot.get_children():
		_snap_slot.remove_child(ch)
		ch.queue_free()
	var snap_b := UiTheme.button("スナップ ON" if snap else "スナップ OFF")
	snap_b.toggle_mode = true
	snap_b.set_pressed_no_signal(snap)
	UiTheme.set_active(snap_b, snap)
	snap_b.toggled.connect(_on_snap)
	_snap_slot.add_child(snap_b)


func _set_hint(text: String) -> void:
	_hint.text = text
	_hint.visible = true
	UiTheme.refit(_hint)


func _act(text: String, cb: Callable, primary := false) -> Button:
	var b := UiTheme.button(text)
	b.pressed.connect(cb)
	if primary:
		UiTheme.set_primary(b)
	return b


func _make_card(it: Dictionary) -> Button:
	var id: String = it["id"]
	var b := Button.new()
	b.custom_minimum_size = Vector2(CARD_W, CARD_H)
	b.focus_mode = Control.FOCUS_NONE
	b.clip_text = true
	b.pressed.connect(_on_card.bind(id))
	var v := VBoxContainer.new()
	UiTheme.fill(v)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 4)
	b.add_child(v)
	var tr := TextureRect.new()
	tr.custom_minimum_size = Vector2(THUMB, THUMB)
	tr.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tr.texture = _thumbs.request(id)
	v.add_child(tr)
	var lb := UiTheme.label(str(it["name"]), UiTheme.FONT_SMALL)
	lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(lb)
	_cards[id] = b
	_card_images[id] = tr
	return b


func _apply_cat() -> void:
	for c in CATEGORIES:
		var on: bool = c[0] == _cat
		(_grids[c[0]] as GridContainer).visible = on
		UiTheme.set_active(_cat_btns[c[0]], on)
	_scroll.scroll_horizontal = 0


func _on_cat(c: String) -> void:
	_cat = c
	_apply_cat()


func _on_card(id: String) -> void:
	_call_em("start_placing", [id])


func _on_thumb(id: String, tex: Texture2D) -> void:
	if _card_images.has(id):
		(_card_images[id] as TextureRect).texture = tex


func _on_confirm() -> void:
	_call_em("confirm")


func _on_cancel() -> void:
	_call_em("cancel")


func _on_rot(step: float) -> void:
	_call_em("rotate_selected", [step])


func _on_clear() -> void:
	var em: Variant = _em()
	if em != null and em.has_method("clear_selection"):
		em.clear_selection()
	else:
		_call_em("cancel")
		return
	_state_key = ""
	refresh()


func _on_snap(on: bool) -> void:
	Game.set_setting("snap", on)
	_state_key = ""
	refresh()


func _on_edit_changed() -> void:
	_state_key = ""
	refresh()


func _call_em(method: String, args: Array = []) -> void:
	var em: Variant = _em()
	if em != null and em.has_method(method):
		em.callv(method, args)
	_state_key = ""
	refresh()


func _em() -> Variant:
	return _main.get("edit_mode") if _main != null else null


static func _prop(obj: Variant, prop: String, default: Variant) -> Variant:
	if obj == null:
		return default
	var v: Variant = obj.get(prop)
	return default if v == null else v
