## メニュー(☰)。全画面のオーバーレイ: 世界の一覧(開く・削除)・新しい世界・名前・画質・設定・操作説明・アプリ情報。
class_name MenuPanel
extends Control

signal message(text: String)

const NEW_KINDS := [["hills", "丘のある里"], ["flat", "平地"], ["sample", "見本の神社"]]
const QUALITY_NAMES := ["軽量", "標準", "高"]
const HELP_TEXT := (
	"・1本指のドラッグ: 地面を動かす(配置・地形)\n"
	+ "・ピンチ: 拡大・縮小\n"
	+ "・2本指でひねる: 回転\n"
	+ "・2本指で上下: 傾き\n"
	+ "・物をタップ: 選ぶ(動かす・回す・複製・削除)\n"
	+ "・歩く: 左下のスティックで歩き、ほかの場所をドラッグで見回す\n"
	+ "・撮影: 画面を隠して景色だけを撮る。「もどる」で戻る"
)

var _list: VBoxContainer
var _new_name: LineEdit
var _rename: LineEdit
var _quality_btns: Array[Button] = []
var _snap_btn: Button
var _now_name: Label
var _invert_btn: Button
var _pending_delete := ""


var _bg: PanelContainer


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false

	_bg = PanelContainer.new()
	_bg.add_theme_stylebox_override("panel", UiTheme.flat_box(UiTheme.PAPER))
	add_child(_bg)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	_bg.add_child(v)

	var head := HBoxContainer.new()
	v.add_child(head)
	var title := UiTheme.label("メニュー", UiTheme.FONT_TITLE)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	var close_btn := UiTheme.glyph_button("close")
	close_btn.pressed.connect(close_menu)
	head.add_child(close_btn)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	v.add_child(scroll)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 14)
	scroll.add_child(body)
	_build(body)


func _ready() -> void:
	UiTheme.fill(self)
	UiTheme.fill(_bg)


func open_menu() -> void:
	visible = true
	_pending_delete = ""
	_rebuild_list()
	_rename.text = Game.world.name if Game.world != null else ""
	_now_name.text = "名前: %s" % _rename.text
	_new_name.text = ""
	_refresh_toggles()


func close_menu() -> void:
	visible = false


func _build(body: VBoxContainer) -> void:
	body.add_child(_section("世界"))
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 8)
	body.add_child(_list)

	body.add_child(_section("新しい世界"))
	_new_name = _line("名前(空欄で自動)")
	body.add_child(_new_name)
	for k in NEW_KINDS:
		var b := UiTheme.button(k[1])
		b.pressed.connect(_on_new.bind(k[0]))
		body.add_child(b)

	body.add_child(_section("いまの世界"))
	_now_name = UiTheme.label("", UiTheme.FONT_BODY, UiTheme.INK_SOFT)
	body.add_child(_now_name)
	_rename = _line("")
	body.add_child(_rename)
	var rb := UiTheme.button("名前を変える")
	rb.pressed.connect(_on_rename)
	body.add_child(rb)

	body.add_child(_section("画質"))
	var qrow := HBoxContainer.new()
	qrow.add_theme_constant_override("separation", 8)
	body.add_child(qrow)
	for i in QUALITY_NAMES.size():
		var b := UiTheme.button(QUALITY_NAMES[i])
		b.pressed.connect(_on_quality.bind(i))
		qrow.add_child(b)
		_quality_btns.append(b)

	body.add_child(_section("設定"))
	_snap_btn = UiTheme.button("スナップ ON")
	_snap_btn.toggle_mode = true
	_snap_btn.toggled.connect(_on_snap)
	body.add_child(_snap_btn)
	_invert_btn = UiTheme.button("視点の上下を反転: 切")
	_invert_btn.toggle_mode = true
	_invert_btn.toggled.connect(_on_invert)
	body.add_child(_invert_btn)

	body.add_child(_section("操作"))
	var help := UiTheme.label(HELP_TEXT, UiTheme.FONT_SMALL)
	UiTheme.wrap_label(help)
	help.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(help)

	body.add_child(_section("アプリ"))
	var info := UiTheme.label("鎮守の里 v0.1", UiTheme.FONT_BODY)
	body.add_child(info)
	var engine := UiTheme.label("Godot 4.7.2", UiTheme.FONT_SMALL, UiTheme.INK_SOFT)
	body.add_child(engine)


func _section(text: String) -> Label:
	var l := UiTheme.label(text, UiTheme.FONT_BODY, UiTheme.VERMILION)
	l.clip_text = false
	return l


func _line(placeholder: String) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.custom_minimum_size = Vector2(0, UiTheme.TOUCH)
	e.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	e.max_length = 20
	return e


## 保存された世界の一覧。削除は2段階(「削除」→「消す」)。
func _rebuild_list() -> void:
	for ch in _list.get_children():
		_list.remove_child(ch)
		ch.queue_free()
	var worlds := Game.list_worlds()
	if worlds.is_empty():
		_list.add_child(UiTheme.label("保存された世界はまだありません。", UiTheme.FONT_SMALL, UiTheme.INK_SOFT))
		return
	var current := Game.world.id if Game.world != null else ""
	for w in worlds:
		var id: String = w["id"]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		var col := VBoxContainer.new()
		col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		col.add_theme_constant_override("separation", 0)
		var title: String = str(w["name"])
		if id == current:
			title += "(開いています)"
		col.add_child(UiTheme.label(title, UiTheme.FONT_BODY))
		col.add_child(UiTheme.label(_date_text(float(w["modified"])), UiTheme.FONT_SMALL, UiTheme.INK_SOFT))
		row.add_child(col)
		if _pending_delete == id:
			var yes := UiTheme.button("消す", UiTheme.TOUCH, 120.0)
			yes.add_theme_color_override("font_color", UiTheme.VERMILION)
			yes.pressed.connect(_on_delete_confirmed.bind(id))
			row.add_child(yes)
			var no := UiTheme.button("やめる", UiTheme.TOUCH, 120.0)
			no.pressed.connect(_on_delete_cancel)
			row.add_child(no)
		else:
			var op := UiTheme.button("開く", UiTheme.TOUCH, 120.0)
			op.pressed.connect(_on_open.bind(id))
			row.add_child(op)
			var del := UiTheme.button("削除", UiTheme.TOUCH, 120.0)
			del.pressed.connect(_on_delete_request.bind(id))
			row.add_child(del)
		_list.add_child(row)


func _refresh_toggles() -> void:
	var q := int(Game.settings.get("quality", 1))
	for i in _quality_btns.size():
		UiTheme.set_active(_quality_btns[i], i == q)
	var snap := bool(Game.settings.get("snap", true))
	_snap_btn.set_pressed_no_signal(snap)
	_snap_btn.text = "スナップ ON" if snap else "スナップ OFF"
	UiTheme.set_active(_snap_btn, snap)
	var inv := bool(Game.settings.get("invert_look", false))
	_invert_btn.set_pressed_no_signal(inv)
	_invert_btn.text = "視点の上下を反転: %s" % ("入" if inv else "切")
	UiTheme.set_active(_invert_btn, inv)


func _on_new(kind: String) -> void:
	Game.new_world(kind, _new_name.text.strip_edges())
	close_menu()


func _on_rename() -> void:
	var t := _rename.text.strip_edges()
	if t.is_empty() or Game.world == null:
		message.emit("名前を入れてください")
		return
	Game.world.name = t
	Game.save_world()
	message.emit("名前を変えました")


func _on_open(id: String) -> void:
	if Game.load_world(id):
		close_menu()
	else:
		message.emit("開けませんでした")


func _on_delete_request(id: String) -> void:
	_pending_delete = id
	_rebuild_list()


func _on_delete_cancel() -> void:
	_pending_delete = ""
	_rebuild_list()


func _on_delete_confirmed(id: String) -> void:
	Game.delete_world(id)
	_pending_delete = ""
	_rebuild_list()
	message.emit("世界を削除しました")


func _on_quality(i: int) -> void:
	Game.set_setting("quality", i)
	_refresh_toggles()


func _on_snap(on: bool) -> void:
	Game.set_setting("snap", on)
	_refresh_toggles()


func _on_invert(on: bool) -> void:
	Game.set_setting("invert_look", on)
	_refresh_toggles()


## 「2026/11/14 21:40」の形(端末の時刻帯)。
func _date_text(unix: float) -> String:
	var bias := int(Time.get_time_zone_from_system()["bias"])
	var d := Time.get_datetime_dict_from_unix_time(int(unix) + bias * 60)
	return "%04d/%02d/%02d %02d:%02d" % [d["year"], d["month"], d["day"], d["hour"], d["minute"]]
