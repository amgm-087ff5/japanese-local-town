## 画面UI(Hud)のテスト。実行: godot --headless --path game --scene res://tests/test_ui.tscn
## (--script では autoload の Game / Catalog が見えないため、シーンとして起動する。architecture 15.5)
## Main を読み込み、縦 720x1560・横 1560x720 で配置・モード切替・パレット・歩行HUD・戻るボタンを確かめる。
extends Node

const PORTRAIT := Vector2(720, 1560)
const LANDSCAPE := Vector2(1560, 720)
const TOUCH_MIN := 84.0

var _pass := 0
var _fail := 0
var _main: Node
var _hud: Hud


func _ready() -> void:
	_run()


func _check(cond: bool, label: String) -> void:
	if cond:
		_pass += 1
	else:
		_fail += 1
		print("  FAIL: %s" % label)


func _section(name: String) -> void:
	print("[%s]" % name)


func _run() -> void:
	await get_tree().process_frame
	_check(ResourceLoader.exists(UiTheme.FONT_PATH), "日本語フォント assets/fonts/NotoSansJP-Regular.otf がある")

	_main = load("res://main.tscn").instantiate()
	get_tree().root.add_child(_main)
	await get_tree().process_frame
	await get_tree().process_frame
	_hud = _main.get("hud") as Hud
	_check(_hud != null, "Main に Hud がある")
	if _hud == null:
		_finish()
		return
	Game.set_mode("edit")
	await get_tree().process_frame

	_section("縦 720x1560: 配置・重なり・画面内")
	_hud._relayout(PORTRAIT)
	await get_tree().process_frame
	_check_layout("縦 edit", PORTRAIT)
	_check_touch_sizes("縦 edit")

	_section("横 1560x720: 配置・重なり・画面内")
	_hud._relayout(LANDSCAPE)
	await get_tree().process_frame
	_check_layout("横 edit", LANDSCAPE)
	_check_touch_sizes("横 edit")

	_section("状態バー・スナップ表示(縦は世界名を出さず時刻チップを広げる。スナップは全幅の行で ON/OFF を表示)")
	_hud._relayout(PORTRAIT)
	await get_tree().process_frame
	_check(not _hud._lbl_world.visible, "縦: 状態バーに世界名を出さない(メニューに出す)")
	var chip_portrait: float = _hud._btn_env.size.x
	_hud._relayout(LANDSCAPE)
	await get_tree().process_frame
	_check(_hud._lbl_world.visible, "横: 状態バーに世界名を出す")
	var chip_land: float = _hud._btn_env.size.x
	_check(chip_portrait > chip_land + 100.0, "縦の時刻チップは横より広い (縦 %.0f / 横 %.0f)" % [chip_portrait, chip_land])
	for on in [true, false]:
		Game.set_setting("snap", on)
		_hud._palette.refresh()
		await get_tree().process_frame
		var sb := _hud._palette._snap_slot.get_child(0) as Button
		var want := "スナップ ON" if on else "スナップ OFF"
		_check(sb != null and sb.text == want, "横のスナップの表示: %s" % want)
		var need := UiTheme.font().get_string_size(want, HORIZONTAL_ALIGNMENT_LEFT, -1, UiTheme.FONT_BODY).x + 2.0 * UiTheme.PANEL_PAD_H
		_check(sb != null and need <= sb.size.x, "横でも「%s」が切れない (文字 %.0f / 幅 %.0f)" % [want, need, sb.size.x if sb != null else 0.0])
	Game.set_setting("snap", true)
	_hud._palette.refresh()

	_section("地形モードへの切替")
	_hud.tab_button("terrain").pressed.emit()
	await get_tree().process_frame
	_check(Game.mode == "terrain", "地形タブで Game.mode が terrain")
	_check(_hud._terrain.visible and not _hud._palette.visible, "地形モードは地形パネルだけ出る")
	_hud._relayout(PORTRAIT)
	_check_layout("縦 terrain", PORTRAIT)
	_hud._relayout(LANDSCAPE)
	_check_layout("横 terrain", LANDSCAPE)
	_check_touch_sizes("横 terrain")

	_section("パレット")
	_check(_hud.palette_card_count() == Catalog.items().size(), "パレットのアイテム数 = Catalog.items().size()")

	_section("歩行HUDだけ表示")
	_hud.tab_button("walk").pressed.emit()
	await get_tree().process_frame
	_check(Game.mode == "walk", "歩くタブで Game.mode が walk")
	_check(not _hud._bar.visible and not _hud._tabs.visible and not _hud._sheet.visible, "歩行中は状態バー・タブ・パネルを隠す")
	_check(_hud._walk.visible, "歩行中は歩行HUDを出す")
	_hud._relayout(PORTRAIT)
	_check(_walk_inside("縦 walk", PORTRAIT), "縦 歩行HUD が画面内で重ならない")
	_hud._relayout(LANDSCAPE)
	_check(_walk_inside("横 walk", LANDSCAPE), "横 歩行HUD が画面内で重ならない")

	_section("撮影モード")
	Game.set_mode("photo")
	await get_tree().process_frame
	_check(_hud._photo_back.visible and not _hud._walk.visible and not _hud._bar.visible, "撮影中は「もどる」だけ出す")
	_check(_hud._photo_back.get_global_rect().size.y >= TOUCH_MIN, "もどるボタンが 84px 以上")

	_section("戻るボタン(段階的に閉じる)")
	Game.set_mode("terrain")
	await get_tree().process_frame
	_hud.handle_back()
	await get_tree().process_frame
	_check(Game.mode == "edit", "地形モードの戻るで配置モードへ戻る")
	_check(not _hud.is_quit_armed(), "配置へ戻るだけでは終了を待機しない")
	Game.set_mode("walk")
	await get_tree().process_frame
	_hud.notification(Node.NOTIFICATION_WM_GO_BACK_REQUEST)
	await get_tree().process_frame
	_check(Game.mode == "edit", "歩行中の戻るで edit に戻る")
	_hud._open_menu()
	await get_tree().process_frame
	_check(_hud.menu_open(), "メニューを開く")
	_hud.notification(Node.NOTIFICATION_WM_GO_BACK_REQUEST)
	await get_tree().process_frame
	_check(not _hud.menu_open(), "戻るでメニューが閉じる")
	_hud._open_env()
	await get_tree().process_frame
	_check(_hud._env.visible, "環境パネルを開く")
	_hud.notification(Node.NOTIFICATION_WM_GO_BACK_REQUEST)
	await get_tree().process_frame
	_check(not _hud._env.visible, "戻るで環境パネルが閉じる")
	_check(not _hud.is_quit_armed(), "まだ終了は待機していない")
	_hud.notification(Node.NOTIFICATION_WM_GO_BACK_REQUEST)
	await get_tree().process_frame
	_check(_hud.is_quit_armed(), "何も開いていない編集で戻る → 「もう一度で終了」を待機")
	_check(_hud._toast.visible, "終了の確認トーストを出す")

	_section("環境パネル・時刻チップ")
	Game.set_mode("edit")
	await get_tree().process_frame
	_hud._open_env()
	await get_tree().process_frame
	var env_text := _hud._btn_env.text
	_check(env_text.length() >= 6, "時刻チップに「季 天気 時刻」が出ている: %s" % env_text)
	_hud._env.close_panel()

	_finish()


## 主要部品(状態バー・タブ・シート・歩行HUD)が画面内に収まり、互いに重ならない。
func _check_layout(label: String, vs: Vector2) -> void:
	var rects := {}
	if _hud._bar.visible:
		rects["状態バー"] = _hud._bar.get_global_rect()
	if _hud._tabs.visible:
		rects["モードタブ"] = _hud._tabs.get_global_rect()
	if _hud._sheet.visible:
		rects["道具パネル"] = _hud._sheet.get_global_rect()
	var screen := Rect2(Vector2.ZERO, vs)
	for k in rects:
		_check(screen.encloses(rects[k]), "%s: %s が画面内に収まる %s" % [label, k, rects[k]])
	var keys := rects.keys()
	for i in keys.size():
		for j in range(i + 1, keys.size()):
			var a: Rect2 = rects[keys[i]]
			var bb: Rect2 = rects[keys[j]]
			_check(not a.intersects(bb), "%s: %s と %s が重ならない" % [label, keys[i], keys[j]])


## 歩行HUD: スティック・走る・ジャンプ・上部のボタン列が画面内で重ならない。
func _walk_inside(label: String, vs: Vector2) -> bool:
	var ok := true
	var screen := Rect2(Vector2.ZERO, vs)
	var rects: Dictionary = _hud._walk.visible_rects()
	for k in rects:
		var r: Rect2 = rects[k]
		if not screen.encloses(r):
			print("  FAIL: %s: %s が画面外 %s" % [label, k, r])
			ok = false
	var keys := rects.keys()
	for i in keys.size():
		for j in range(i + 1, keys.size()):
			var a: Rect2 = rects[keys[i]]
			var bb: Rect2 = rects[keys[j]]
			if a.intersects(bb):
				print("  FAIL: %s: %s と %s が重なる" % [label, keys[i], keys[j]])
				ok = false
	return ok


## 見えているボタンは 84px 以上(縦横どちらの辺も)。
func _check_touch_sizes(label: String) -> void:
	var buttons: Array[BaseButton] = []
	_collect_buttons(_hud, buttons)
	var bad := 0
	for b in buttons:
		var r := b.get_global_rect()
		if r.size.y < TOUCH_MIN - 0.5:
			bad += 1
			print("  小さいボタン: %s %s" % [b.text, r.size])
	_check(bad == 0, "%s: 見えているボタンが 84px 以上 (%d 件)" % [label, bad])


func _collect_buttons(node: Node, out: Array[BaseButton]) -> void:
	if node is Control and not (node as Control).is_visible_in_tree():
		return
	if node is BaseButton:
		out.append(node as BaseButton)
	for c in node.get_children():
		_collect_buttons(c, out)


func _finish() -> void:
	# 後片付け: 状態を戻す
	Game.set_mode("edit")
	print("---- PASS %d / FAIL %d" % [_pass, _fail])
	get_tree().quit(1 if _fail > 0 else 0)
