## 環境: 時刻・太陽と月・空・霧・四季・天気(architecture.md 10章・15.4)。
## 時刻は Game.world.env["time"] と同期する(毎フレーム直接書く。env_changed は出さない)。
## 季節・天気の変化は Game.env_changed で反映する。積雪・濡れはなめらかに補間する。
class_name EnvController
extends Node3D

const SKY_SHADER := preload("res://scripts/env/sky.gdshader")

# 季節 0春 1夏 2秋 3冬
const SEASON_ALT := [55.0, 78.0, 55.0, 32.0]        # 南中高度(度)
const SEASON_HALF_DAY := [6.0, 7.0, 6.0, 5.0]        # 12時から日の出・日の入りまでの時間(春秋 6-18 / 夏 5-19 / 冬 7-17)
const SEASON_GRASS := [Color(0.62, 0.8, 0.36), Color(0.27, 0.48, 0.22), Color(0.56, 0.5, 0.25), Color(0.52, 0.47, 0.33)]
const SEASON_SAKURA := [Color(0.96, 0.66, 0.74), Color(0.3, 0.52, 0.22), Color(0.62, 0.36, 0.18), Color(0.36, 0.26, 0.2)]
const SEASON_KAEDE := [Color(0.6, 0.78, 0.36), Color(0.28, 0.5, 0.2), Color(0.82, 0.22, 0.12), Color(0.42, 0.22, 0.12)]
const SEASON_DECIDUOUS := [1.0, 1.0, 1.0, 0.12]
const EVERGREEN_BASE := [Color(0.13, 0.3, 0.17), Color(0.16, 0.34, 0.2), Color(0.42, 0.58, 0.25)]  # 杉 松 竹
const EVERGREEN_TINT := [Color(1.05, 1.08, 1.0), Color(1.0, 1.0, 1.0), Color(1.05, 0.98, 0.9), Color(0.92, 0.98, 1.02)]
const SEASON_ZENITH := [Color(0.36, 0.58, 0.82), Color(0.26, 0.5, 0.84), Color(0.4, 0.56, 0.74), Color(0.44, 0.58, 0.74)]
const SEASON_HORIZON := [Color(0.84, 0.9, 0.92), Color(0.78, 0.88, 0.94), Color(0.88, 0.87, 0.82), Color(0.86, 0.9, 0.95)]
const SEASON_MOUNTAIN := [Color(0.42, 0.55, 0.5), Color(0.3, 0.44, 0.44), Color(0.47, 0.46, 0.4), Color(0.5, 0.54, 0.6)]
const SEASON_SNOW_IDLE := 0.35                       # 冬で雪でない時の積雪(地表・山の頂)

# 天気 0晴 1曇 2雨 3雪
const WEATHER_CLOUD := [0.22, 0.72, 0.95, 0.9]
const WEATHER_GREY := [0.0, 0.5, 0.8, 0.85]          # 空を灰色へ寄せる割合
const WEATHER_FOG := [0.0006, 0.0010, 0.0014, 0.0014]
const WEATHER_WIND := [0.3, 0.5, 0.8, 0.8]
const SNOW_RATE := 0.4                               # 1/秒(約2.5秒で追従)
const WET_RATE := 0.5

# 画質 0軽量 1標準 2高
const QUALITY_SCALE := [0.6, 0.8, 1.0]
const QUALITY_SHADOW_DIST := [80.0, 80.0, 120.0]
const QUALITY_GLOW := [0.0, 0.2, 0.4]
const QUALITY_PARTICLES := [300, 800, 1500]

# 空・光の色(空の色は sRGB で書き、シェーダの source_color が線形に変換する)
const ZENITH_NIGHT := Color(0.02, 0.035, 0.08)
const HORIZON_NIGHT := Color(0.07, 0.1, 0.17)
const ZENITH_WARM := Color(0.36, 0.42, 0.6)
const HORIZON_WARM := Color(0.97, 0.6, 0.4)
const OVERCAST_ZENITH := Color(0.58, 0.62, 0.67)
const OVERCAST_HORIZON := Color(0.8, 0.82, 0.85)
const CLOUD_DAY := Color(0.97, 0.97, 0.98)
const CLOUD_NIGHT := Color(0.14, 0.16, 0.24)
const CLOUD_WARM := Color(1.0, 0.74, 0.58)
const SUN_DISK := Color(1.0, 0.97, 0.9)
const SUN_DISK_WARM := Color(1.0, 0.62, 0.36)
const MOON_DISK := Color(0.78, 0.85, 1.0)
# 光・環境光(Light と Environment は線形の値をそのまま使う)
const SUN_LIGHT_WHITE := Color(1.0, 0.97, 0.92)
const SUN_LIGHT_WARM := Color(1.0, 0.66, 0.4)
const OVERCAST_LIGHT := Color(0.86, 0.88, 0.92)
const MOON_LIGHT := Color(0.6, 0.7, 1.0)
const AMBIENT_DAY := Color(0.2, 0.21, 0.23)
const AMBIENT_NIGHT := Color(0.12, 0.16, 0.26)
const AMBIENT_GREY := Color(0.9, 0.92, 0.96)

var time := 9.0
var _sun: DirectionalLight3D
var _moon: DirectionalLight3D
var _env: Environment
var _sky_mat: ShaderMaterial
var _backdrop: Backdrop
var _fx: WeatherFx
var _season := 0
var _weather := 0
var _night := 0.0
var _snow_target := 0.0
var _snow_cur := 0.0
var _wet_target := 0.0
var _wet_cur := 0.0
var _cloud_time := 0.0
var _last_written := -1.0
var _globals := {}   # 設定したグローバル uniform の値(get_global で読む)


## autoload Game は --script 実行時にはコンパイル時の名前として見えないため、実行時に /root から取得する。
func _game() -> Node:
	return get_node_or_null("/root/Game")


func _world() -> WorldData:
	var g := _game()
	if g == null:
		return null
	return g.get("world") as WorldData


func _ready() -> void:
	_build()
	var g := _game()
	if g != null:
		g.connect("world_loaded", apply_all)
		g.connect("env_changed", _on_env_changed)
		g.connect("settings_changed", _apply_quality)
	apply_all()


func _exit_tree() -> void:
	var g := _game()
	if g == null:
		return
	if g.is_connected("world_loaded", apply_all):
		g.disconnect("world_loaded", apply_all)
	if g.is_connected("env_changed", _on_env_changed):
		g.disconnect("env_changed", _on_env_changed)
	if g.is_connected("settings_changed", _apply_quality):
		g.disconnect("settings_changed", _apply_quality)


func _process(delta: float) -> void:
	_step(delta)


## 世界の時刻・季節・天気を全部反映する。積雪・濡れは即時に目標値へ揃える。
func apply_all() -> void:
	if _sun == null:
		return   # _ready の前(ツリーに入る前)は何もしない。_ready の中で改めて呼ばれる
	var w := _world()
	if w != null:
		time = fposmod(float(w.env.get("time", time)), 24.0)
		_last_written = time
	_apply_quality()
	_sync_season_weather(true)
	_refresh()


## 太陽へ向かう単位ベクトル。北=-Z、東=+X、南=+Z。6時に東、12時に南中、18時に西。
func sun_direction() -> Vector3:
	var s := _world_int("season", 0, 0, 3)
	var alt := deg_to_rad(float(SEASON_ALT[s]))
	var half := float(SEASON_HALF_DAY[s])
	var h := (time - 12.0) / half * (PI * 0.5)
	return Vector3(-sin(h), cos(h) * sin(alt), cos(h) * cos(alt)).normalized()


## 太陽が地平線の下か。
func is_night() -> bool:
	return sun_direction().y < 0.0


## 時刻を設定する(0-24 に丸める)。env_changed は出さない。
func set_time(t: float) -> void:
	time = fposmod(t, 24.0)
	if _sun == null:
		return   # ツリーに入る前は表示を更新しない(_ready の apply_all で反映される)
	_last_written = time
	var w := _world()
	if w != null:
		w.env["time"] = time
	_refresh()


## グローバル uniform を設定する。RenderingServer.global_shader_parameter_get は実行時には使えない(エディタ専用)ため、値はここでも保持する。
func _set_global(uniform_name: String, value: Variant) -> void:
	_globals[uniform_name] = value
	RenderingServer.global_shader_parameter_set(uniform_name, value)


## 最後に設定したグローバル uniform の値(テスト・デバッグ用)。
func get_global(uniform_name: String) -> Variant:
	return _globals.get(uniform_name)


func _on_env_changed() -> void:
	_sync_season_weather(false)
	_refresh()


## 毎フレーム: 時刻の進行(time_flow)、季節・天気の変化の検出、補間、表示の更新。
func _step(delta: float) -> void:
	var w := _world()
	if w == null:
		return
	var e: Dictionary = w.env
	var wt := float(e.get("time", time))
	if absf(wt - _last_written) > 0.0001:
		time = fposmod(wt, 24.0)            # 外から書き換えられた(HUD のスライダなど)
	if bool(e.get("time_flow", false)):
		var dm := maxf(float(e.get("day_minutes", 12.0)), 0.1)
		time = fposmod(time + delta * 24.0 / (dm * 60.0), 24.0)
	e["time"] = time
	_last_written = time
	_sync_season_weather(false)
	_cloud_time = fposmod(_cloud_time + delta * (0.4 + WEATHER_WIND[_weather]), 1000.0)
	_snow_cur = move_toward(_snow_cur, _snow_target, SNOW_RATE * delta)
	_wet_cur = move_toward(_wet_cur, _wet_target, WET_RATE * delta)
	_refresh()


func _world_int(key: String, def: int, lo: int, hi: int) -> int:
	var w := _world()
	if w == null:
		return def
	return clampi(int(w.env.get(key, def)), lo, hi)


## 季節・天気が変わったら、季節の色・風・積雪と濡れの目標を設定する。snap なら補間せず即時。
func _sync_season_weather(snap: bool) -> void:
	var s := _world_int("season", 0, 0, 3)
	var w := _world_int("weather", 0, 0, 3)
	if s == _season and w == _weather and not snap:
		return
	_season = s
	_weather = w
	_set_season_globals(s)
	_set_global("g_wind", WEATHER_WIND[w])
	_snow_target = 1.0 if w == 3 else (SEASON_SNOW_IDLE if s == 3 else 0.0)
	_wet_target = 1.0 if w == 2 else 0.0
	if snap:
		_snow_cur = _snow_target
		_wet_cur = _wet_target
	if _fx != null:
		_fx.set_weather(w)


## 季節の色は sRGB で書いてあり、グローバル uniform は変換されずに届くので、ここで線形へ直してから渡す(シェーダは線形として使う)。
func _set_season_globals(s: int) -> void:
	_set_global("g_season_grass", SEASON_GRASS[s].srgb_to_linear())
	_set_global("g_leaf_sakura", SEASON_SAKURA[s].srgb_to_linear())
	_set_global("g_leaf_kaede", SEASON_KAEDE[s].srgb_to_linear())
	_set_global("g_leaf_density_deciduous", SEASON_DECIDUOUS[s])
	var tint: Color = EVERGREEN_TINT[s]
	_set_global("g_leaf_sugi", (EVERGREEN_BASE[0] * tint).clamp().srgb_to_linear())
	_set_global("g_leaf_matsu", (EVERGREEN_BASE[1] * tint).clamp().srgb_to_linear())
	_set_global("g_leaf_take", (EVERGREEN_BASE[2] * tint).clamp().srgb_to_linear())


func _apply_quality() -> void:
	var q := 1
	var g := _game()
	if g != null:
		q = clampi(int((g.get("settings") as Dictionary).get("quality", 1)), 0, 2)
	var vp := get_viewport()
	if vp != null:
		vp.scaling_3d_scale = QUALITY_SCALE[q]
	_sun.shadow_enabled = q >= 1
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS if q == 2 else DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	_sun.directional_shadow_max_distance = QUALITY_SHADOW_DIST[q]
	_env.glow_enabled = q >= 1
	_env.glow_intensity = QUALITY_GLOW[q]
	_fx.set_amount(QUALITY_PARTICLES[q])


## 太陽・月・空・霧・環境光・遠景の色と強さを、現在の時刻・季節・天気から計算して反映する。
func _refresh() -> void:
	var sun := sun_direction()
	var moon := -sun
	var cloud: float = WEATHER_CLOUD[_weather]
	var grey: float = WEATHER_GREY[_weather]
	var day_t := smoothstep(-0.08, 0.15, sun.y)
	var warm := 1.0 - smoothstep(0.0, 0.25, absf(sun.y))
	_night = 1.0 - smoothstep(-0.10, 0.04, sun.y)
	var sun_k := smoothstep(-0.03, 0.10, sun.y)
	var moon_k := smoothstep(-0.02, 0.10, moon.y)

	# 太陽(影あり)と月(影なし)。DirectionalLight は -Z 方向へ光を出すので、太陽の反対へ向ける。
	_sun.basis = Basis.looking_at(-sun, Vector3.UP)
	var light := SUN_LIGHT_WHITE.lerp(SUN_LIGHT_WARM, warm).lerp(OVERCAST_LIGHT, grey * 0.5)
	_sun.light_color = light
	# 積雪時は雲越しの拡散光が増えるので、太陽と環境光を雪の量に応じて持ち上げる(白い雪面を白く見せる)
	var snow_lift := 1.0 + 0.35 * _snow_cur
	_sun.light_energy = 0.55 * sun_k * (1.0 - 0.4 * cloud) * (1.0 + 0.4 * _snow_cur)
	_moon.basis = Basis.looking_at(sun, Vector3.UP)
	_moon.light_energy = 0.65 * _night * moon_k * (1.0 - 0.6 * cloud)

	# 空: 天頂・地平(時刻 → 朝夕の茜 → 天気の灰色)
	var zen := ZENITH_NIGHT.lerp(SEASON_ZENITH[_season], day_t).lerp(ZENITH_WARM, warm * 0.4)
	var hor := HORIZON_NIGHT.lerp(SEASON_HORIZON[_season], day_t).lerp(HORIZON_WARM, warm * 0.85)
	zen = zen.lerp(OVERCAST_ZENITH.lerp(ZENITH_NIGHT, 1.0 - day_t), grey)
	hor = hor.lerp(OVERCAST_HORIZON.lerp(HORIZON_NIGHT, 1.0 - day_t), grey)
	var cc := CLOUD_NIGHT.lerp(CLOUD_DAY, day_t).lerp(CLOUD_WARM, warm * 0.4 * (1.0 - grey))
	_sky_mat.set_shader_parameter("sun_dir", sun)
	_sky_mat.set_shader_parameter("moon_dir", moon)
	_sky_mat.set_shader_parameter("zenith_color", zen)
	_sky_mat.set_shader_parameter("horizon_color", hor)
	_sky_mat.set_shader_parameter("sun_color", SUN_DISK.lerp(SUN_DISK_WARM, warm))
	_sky_mat.set_shader_parameter("moon_color", MOON_DISK)
	_sky_mat.set_shader_parameter("glow_color", HORIZON_WARM)
	_sky_mat.set_shader_parameter("glow_amount", warm * 0.7)
	_sky_mat.set_shader_parameter("cloud_cover", cloud)
	_sky_mat.set_shader_parameter("cloud_color", cc)
	_sky_mat.set_shader_parameter("night", _night)
	_sky_mat.set_shader_parameter("time_sec", _cloud_time)

	# 霧と環境光(Environment の色は線形。霧は空の地平色に合わせる)
	_env.fog_light_color = hor.srgb_to_linear()
	_env.fog_density = WEATHER_FOG[_weather]
	_env.fog_sun_scatter = 0.08 + 0.3 * warm
	_env.ambient_light_color = AMBIENT_NIGHT.lerp(AMBIENT_DAY, day_t).lerp(AMBIENT_GREY, grey * 0.5) * snow_lift
	_env.adjustment_saturation = lerpf(1.0, 0.82, grey)

	_backdrop.set_look(SEASON_MOUNTAIN[_season], hor, _night, _snow_cur, cloud)

	_set_global("g_night", _night)
	_set_global("g_snow", _snow_cur)
	_set_global("g_wet", _wet_cur)


func _build() -> void:
	_sun = DirectionalLight3D.new()
	_sun.name = "Sun"
	_sun.shadow_enabled = true
	add_child(_sun)
	_moon = DirectionalLight3D.new()
	_moon.name = "Moon"
	_moon.shadow_enabled = false
	_moon.light_color = MOON_LIGHT
	add_child(_moon)

	_sky_mat = ShaderMaterial.new()
	_sky_mat.shader = SKY_SHADER
	var sky := Sky.new()
	sky.sky_material = _sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL

	_env = Environment.new()
	_env.background_mode = Environment.BG_SKY
	_env.sky = sky
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	_env.glow_hdr_threshold = 1.0
	_env.fog_enabled = true
	_env.fog_sky_affect = 0.25
	_env.adjustment_enabled = true
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = _env
	add_child(we)

	_backdrop = Backdrop.new()
	_backdrop.name = "Backdrop"
	add_child(_backdrop)
	_fx = WeatherFx.new()
	_fx.name = "WeatherFx"
	add_child(_fx)
