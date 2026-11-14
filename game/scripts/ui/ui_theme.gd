## UI の配色・文字サイズ・Theme(architecture.md 12章・15.4)。UI はすべてコードで組み、.tscn を作らない。
## 寸法は base 720 の論理px。タッチ対象は TOUCH(84px)以上。
class_name UiTheme
extends RefCounted

const FONT_PATH := "res://assets/fonts/NotoSansJP-Regular.otf"

# 配色: 生成り・墨・朱・松葉
const PAPER := Color("#F4EFE4")
const PAPER_LIGHT := Color("#FBF8F1")
const PAPER_DEEP := Color("#E4DCCA")
const INK := Color("#2B2B2B")
const INK_SOFT := Color("#5C584F")
const VERMILION := Color("#C8452C")
const MATSU := Color("#3F6B4F")
const MUTED := Color("#9C968A")
const LINE := Color(0.17, 0.17, 0.17, 0.22)
const SHADOW := Color(0.0, 0.0, 0.0, 0.16)

# 寸法
const TOUCH := 84.0
const MARGIN := 12.0
const PANEL_PAD_H := 12.0
const PANEL_PAD_V := 6.0
const RADIUS := 12
const FONT_BODY := 26
const FONT_SMALL := 22
const FONT_TITLE := 30
const FONT_TAB := 28

const SEASONS := ["春", "夏", "秋", "冬"]
const WEATHERS := ["晴", "曇", "雨", "雪"]

static var _font: Font = null


## 日本語フォント。assets/fonts が無ければ端末の既定フォント(開発用)。
static func font() -> Font:
	if _font == null:
		if ResourceLoader.exists(FONT_PATH):
			_font = load(FONT_PATH)
		else:
			_font = ThemeDB.fallback_font
	return _font


## 角丸の箱。影は任意。余白は左右 12・上下 6。
static func box(bg: Color, border: Color = Color(0, 0, 0, 0), bw: int = 0, radius: int = RADIUS, shadow := false) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.set_corner_radius_all(radius)
	s.set_border_width_all(bw)
	s.border_color = border
	s.content_margin_left = PANEL_PAD_H
	s.content_margin_right = PANEL_PAD_H
	s.content_margin_top = PANEL_PAD_V
	s.content_margin_bottom = PANEL_PAD_V
	if shadow:
		s.shadow_color = SHADOW
		s.shadow_size = 6
		s.shadow_offset = Vector2(0, 2)
	return s


## 和紙風の半透明パネル。
static func paper_panel(alpha := 0.94) -> StyleBoxFlat:
	return box(Color(PAPER.r, PAPER.g, PAPER.b, alpha), LINE, 1, RADIUS, true)


## 角のない単色(全画面のメニューなど)。
static func flat_box(bg: Color) -> StyleBoxFlat:
	return box(bg, Color(0, 0, 0, 0), 0, 0, false)


## Theme を作って Hud に適用する。
static func make_theme() -> Theme:
	var t := Theme.new()
	t.default_font = font()
	t.default_font_size = FONT_BODY

	var btn := box(PAPER_LIGHT, LINE, 2)
	t.set_stylebox("normal", "Button", btn)
	t.set_stylebox("hover", "Button", btn)
	t.set_stylebox("pressed", "Button", box(PAPER_DEEP, LINE, 2))
	t.set_stylebox("disabled", "Button", box(Color(0.9, 0.88, 0.84, 0.7), LINE, 2))
	t.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	for k in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color", "font_hover_pressed_color"]:
		t.set_color(k, "Button", INK)
	t.set_color("font_disabled_color", "Button", MUTED)
	t.set_font_size("font_size", "Button", FONT_BODY)

	t.set_color("font_color", "Label", INK)
	t.set_font_size("font_size", "Label", FONT_BODY)

	t.set_stylebox("panel", "PanelContainer", paper_panel())

	t.set_stylebox("normal", "LineEdit", box(PAPER_LIGHT, LINE, 2))
	t.set_stylebox("focus", "LineEdit", box(PAPER_LIGHT, VERMILION, 2))
	t.set_stylebox("read_only", "LineEdit", box(PAPER_DEEP, LINE, 2))
	t.set_color("font_color", "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", MUTED)
	t.set_color("caret_color", "LineEdit", VERMILION)
	t.set_font_size("font_size", "LineEdit", FONT_BODY)

	t.set_stylebox("slider", "HSlider", box(PAPER_DEEP, Color(0, 0, 0, 0), 0, 6))
	var fill := box(VERMILION, Color(0, 0, 0, 0), 0, 6)
	t.set_stylebox("grabber_area", "HSlider", fill)
	t.set_stylebox("grabber_area_highlight", "HSlider", fill)
	t.set_icon("grabber", "HSlider", grabber_texture(false))
	t.set_icon("grabber_highlight", "HSlider", grabber_texture(true))
	t.set_icon("grabber_disabled", "HSlider", grabber_texture(false))

	t.set_stylebox("panel", "ScrollContainer", StyleBoxEmpty.new())
	return t


## つまみの丸(44px)。通常は生成り、強調は朱。
static func grabber_texture(hot: bool) -> ImageTexture:
	var n := 44
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var c := Vector2(n, n) * 0.5
	var fill: Color = VERMILION if hot else PAPER_LIGHT
	var edge: Color = INK if not hot else VERMILION
	for y in n:
		for x in n:
			var d := Vector2(x + 0.5, y + 0.5).distance_to(c)
			if d <= n * 0.5 - 1.0:
				img.set_pixel(x, y, fill if d <= n * 0.5 - 6.0 else edge)
	return ImageTexture.create_from_image(img)


## 押せる部品(Button)。高さ・幅の既定は 84px(タッチ対象の最小)。
static func button(text: String, h: float = TOUCH, w: float = 0.0) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(w, h)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.focus_mode = Control.FOCUS_NONE
	b.clip_text = true
	return b


## 図形アイコンだけの正方形ボタン(☰ ↶ ↷ カメラ × など)。子の Glyph で描く。
static func glyph_button(kind: String, size: float = TOUCH) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(size, size)
	b.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	b.focus_mode = Control.FOCUS_NONE
	var g := Glyph.new(kind)
	g.name = "Glyph"
	fill(g)
	b.add_child(g)
	return b


static func set_glyph(b: Button, kind: String) -> void:
	var g := b.get_node_or_null("Glyph") as Glyph
	if g != null:
		g.kind = kind


static func label(text: String, size: int = FONT_BODY, color: Color = INK) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	l.clip_text = true
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	return l


## 全面に広げる(親に入った後で呼ぶ。追加前の set_anchors_preset は矩形に反映されないことがあるため)。
static func fill(c: Control) -> void:
	# プリセットは既定で最小サイズに縮むため、アンカーとオフセットを直接指定する
	c.anchor_left = 0.0
	c.anchor_top = 0.0
	c.anchor_right = 1.0
	c.anchor_bottom = 1.0
	c.offset_left = 0.0
	c.offset_top = 0.0
	c.offset_right = 0.0
	c.offset_bottom = 0.0


## 折り返す文字(Label の autowrap)。Godot は折り返し後の高さを最小サイズに入れないため、幅に合わせて高さを自分で決める。
static func wrap_label(l: Label) -> void:
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.clip_text = false
	l.text_overrun_behavior = TextServer.OVERRUN_NO_TRIMMING
	l.resized.connect(refit.bind(l))
	refit(l)


static func refit(l: Label) -> void:
	var w := l.size.x
	if w < 40.0:
		return
	var fs := l.get_theme_font_size("font_size")
	var h := font().get_multiline_string_size(l.text, HORIZONTAL_ALIGNMENT_LEFT, w, fs).y
	var nh := ceilf(h) + 12.0
	if absf(l.custom_minimum_size.y - nh) > 0.5:
		l.custom_minimum_size.y = nh


## 選択中(朱)/未選択の切り替え。Glyph の子がいれば色も合わせる。
static func set_active(b: Button, on: bool) -> void:
	if on:
		var acc := box(VERMILION, Color(0, 0, 0, 0), 0)
		b.add_theme_stylebox_override("normal", acc)
		b.add_theme_stylebox_override("hover", acc)
		b.add_theme_stylebox_override("pressed", acc)
		b.add_theme_color_override("font_color", PAPER_LIGHT)
		b.add_theme_color_override("font_hover_color", PAPER_LIGHT)
		b.add_theme_color_override("font_pressed_color", PAPER_LIGHT)
	else:
		for k in ["normal", "hover", "pressed"]:
			b.remove_theme_stylebox_override(k)
		for k in ["font_color", "font_hover_color", "font_pressed_color"]:
			b.remove_theme_color_override(k)
	var g := b.get_node_or_null("Glyph") as Glyph
	if g != null:
		g.tint = PAPER_LIGHT if on else INK


## 主要な操作(決定など)の色。松葉。
static func set_primary(b: Button) -> void:
	var m := box(MATSU, Color(0, 0, 0, 0), 0)
	b.add_theme_stylebox_override("normal", m)
	b.add_theme_stylebox_override("hover", m)
	b.add_theme_stylebox_override("pressed", m)
	b.add_theme_color_override("font_color", PAPER_LIGHT)
	b.add_theme_color_override("font_hover_color", PAPER_LIGHT)
	b.add_theme_color_override("font_pressed_color", PAPER_LIGHT)


## 時刻 0-24 を「9:30」の形に。
static func time_text(t: float) -> String:
	var minutes := int(roundf(fposmod(t, 24.0) * 60.0)) % 1440
	return "%d:%02d" % [minutes / 60, minutes % 60]
