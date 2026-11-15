## 環境(EnvController)のテスト。実行: godot --headless --path game --script res://tests/test_env.gd
## autoload(Game)は root から取得する。テストが作る世界は終了時に消し、world / last_world_id / 画質を元に戻す。
extends SceneTree

var _pass := 0
var _fail := 0
var _game  # Game(autoload)。型を付けると world などへのアクセスがコンパイルで落ちるため無し
var _started := false
var _env: EnvController
var _test_id := ""


func _initialize() -> void:
	_game = root.get_node_or_null("Game")


## autoload の _ready は最初のフレームまでに済むので、テストは _process の初回で走らせる。
func _process(_delta: float) -> bool:
	if _started:
		return true
	_started = true
	if _game == null:
		print("FAIL: autoload Game が見つかりません")
		quit(1)
		return true
	var prev_world = _game.get("world")
	var prev_last := str(_game.get("last_world_id"))
	var prev_quality := int(_game.get("settings")["quality"])
	_run()
	_cleanup(prev_world, prev_last, prev_quality)
	print("---- PASS %d / FAIL %d" % [_pass, _fail])
	quit(1 if _fail > 0 else 0)
	return true


func _check(cond: bool, label: String) -> void:
	if cond:
		_pass += 1
	else:
		_fail += 1
		print("  FAIL: %s" % label)


func _section(name: String) -> void:
	print("[%s]" % name)


func _run() -> void:
	_game.new_world("flat", "試験の環境")
	_test_id = _game.world.id
	_game.world.env["time_flow"] = false
	_env = EnvController.new()
	root.add_child(_env)
	_env.set_process(false)   # 進行は _step() で直接呼ぶ(テスト中に時刻が勝手に動かないように)
	_test_nodes()
	_test_sun()
	_test_clock()
	_test_flow()
	_test_season_weather_globals()
	_test_snow_wet()
	_test_quality()


func _set_world_env(key: String, value) -> void:
	_game.world.env[key] = value
	_env.apply_all()


func _set_time(t: float) -> void:
	_env.set_time(t)


## グローバル uniform の値。RenderingServer.global_shader_parameter_get は実行時に使えないため EnvController の保持値を読む。
func _g(name: String) -> float:
	return float(_env.get_global(name))


func _test_nodes() -> void:
	_section("構成")
	for n in ["WorldEnvironment", "Sun", "Moon", "Backdrop", "WeatherFx"]:
		_check(_env.get_node_or_null(n) != null, "子ノード %s がある" % n)


func _test_sun() -> void:
	_section("太陽の向き")
	var expect_alt := [55.0, 78.0, 55.0, 32.0]
	for s in 4:
		_set_world_env("season", s)
		_set_time(12.0)
		var d := _env.sun_direction()
		var alt := rad_to_deg(asin(clampf(d.y, -1.0, 1.0)))
		_check(d.z > 0.0, "12時は南(+Z) 季節 %d" % s)
		_check(absf(alt - expect_alt[s]) < 0.5, "12時の南中高度 季節 %d = %.2f 度" % [s, alt])
		_check(absf(d.x) < 0.01, "12時は真南(x=0) 季節 %d" % s)
	_set_world_env("season", 0)
	_set_time(6.0)
	var d6 := _env.sun_direction()
	_check(d6.x > 0.99 and absf(d6.y) < 0.01, "春の6時は真東(+X) %s" % str(d6))
	_set_time(18.0)
	var d18 := _env.sun_direction()
	_check(d18.x < -0.99 and absf(d18.y) < 0.01, "春の18時は真西(-X) %s" % str(d18))
	_set_world_env("season", 1)
	_set_time(5.0)
	_check(absf(_env.sun_direction().y) < 0.01, "夏は5時に日の出")
	_set_world_env("season", 3)
	_set_time(7.0)
	_check(absf(_env.sun_direction().y) < 0.01, "冬は7時に日の出")


func _test_clock() -> void:
	_section("時刻と昼夜")
	_set_world_env("season", 0)
	_set_time(0.0)
	_check(_env.is_night(), "0時は夜")
	_set_time(12.0)
	_check(not _env.is_night(), "12時は昼")
	_set_time(21.5)
	_check(_env.is_night(), "21時半は夜")
	_env.set_time(25.5)
	_check(absf(_env.time - 1.5) < 0.0001, "set_time は24時を超えたら0へ回る")
	_check(absf(float(_game.world.env["time"]) - 1.5) < 0.0001, "world.env[time] に反映される")

	var sun := _env.get_node("Sun") as DirectionalLight3D
	var moon := _env.get_node("Moon") as DirectionalLight3D
	_set_time(0.0)
	_check(sun.light_energy == 0.0, "夜は太陽の光が0")
	_check(moon.light_energy > 0.1 and not moon.shadow_enabled, "夜は月の光があり、影は落とさない")
	_check(_g("g_night") > 0.99, "夜の g_night は1: %.3f" % _g("g_night"))
	_set_time(12.0)
	_check(sun.light_energy > 0.5, "昼は太陽の光がある")
	_check(_g("g_night") < 0.01, "昼の g_night は0: %.3f" % _g("g_night"))


func _test_flow() -> void:
	_section("時刻の進行")
	_game.world.env["day_minutes"] = 12.0
	_game.world.env["time_flow"] = true
	_set_time(10.0)
	_env._step(30.0)   # 12分で24時間 → 30秒で1時間
	var t1 := float(_game.world.env["time"])
	_check(absf(t1 - 11.0) < 0.001, "30秒で1時間進む: %.3f" % t1)
	_set_time(23.5)
	_env._step(60.0)   # 2時間進んで 25.5 → 1.5
	var t2 := float(_game.world.env["time"])
	_check(absf(t2 - 1.5) < 0.001, "24時を超えたら0へ回る: %.3f" % t2)
	_game.world.env["time_flow"] = false
	_env._step(60.0)
	_check(absf(float(_game.world.env["time"]) - 1.5) < 0.001, "time_flow が false なら進まない")
	_game.world.env["time"] = 15.0
	_env._step(0.0)
	_check(absf(_env.time - 15.0) < 0.001, "外から書かれた時刻(HUD など)を採用する")


func _test_season_weather_globals() -> void:
	_section("季節・天気のグローバル uniform")
	_set_time(12.0)
	_set_world_env("weather", 0)
	var grass := []
	for s in 4:
		_set_world_env("season", s)
		grass.append(_env.get_global("g_season_grass"))
	_check(grass[0] != grass[1] and grass[1] != grass[2] and grass[2] != grass[3], "季節で草色が変わる")
	_check(grass[0].g > grass[1].g, "春の若草は夏の濃い緑より明るい")

	_set_world_env("season", 0)
	var sak: Color = _env.get_global("g_leaf_sakura")
	_check(sak.r > sak.g and sak.b > sak.g, "春の桜は桃色")
	_set_world_env("season", 2)
	var kae: Color = _env.get_global("g_leaf_kaede")
	_check(kae.r > kae.g * 1.5 and kae.r > kae.b, "秋のカエデは紅")
	_check(absf(_g("g_leaf_density_deciduous") - 1.0) < 0.001, "秋は落葉樹が葉を持つ(density 1)")
	_set_world_env("season", 3)
	_check(absf(_g("g_leaf_density_deciduous") - 0.12) < 0.001, "冬は落葉樹が疎ら(density 0.12)")
	var sugi_before: Color = _env.get_global("g_leaf_sugi")
	_set_world_env("season", 1)
	_check(sugi_before != _env.get_global("g_leaf_sugi"), "常緑も季節でわずかに変わる")

	for w in [0, 1, 2]:
		_set_world_env("weather", w)
		var want: float = [0.3, 0.5, 0.8][w]
		_check(absf(_g("g_wind") - want) < 0.001, "天気 %d の風 = %.1f" % [w, want])


func _test_snow_wet() -> void:
	_section("積雪・濡れ")
	_set_world_env("season", 0)
	_set_world_env("weather", 3)
	_check(absf(_g("g_snow") - 1.0) < 0.001, "雪の天気は apply_all で即時に積雪1")
	_set_world_env("weather", 0)
	_check(absf(_g("g_snow")) < 0.001, "春の晴れは積雪0")
	_set_world_env("season", 3)
	_check(absf(_g("g_snow") - 0.35) < 0.001, "冬の雪でない日は積雪0.35")
	_set_world_env("weather", 2)
	_check(absf(_g("g_wet") - 1.0) < 0.001, "雨で濡れ1")
	_set_world_env("weather", 0)
	_check(absf(_g("g_wet")) < 0.001, "晴れで濡れ0")

	# 変化は数秒かけて補間する(env_changed 相当: 世界の値だけ書き換えて毎フレームの処理を呼ぶ)
	_set_world_env("season", 0)
	_set_world_env("weather", 0)
	_game.world.env["weather"] = 3
	_env._step(0.5)
	var mid := _g("g_snow")
	_check(mid > 0.05 and mid < 0.95, "雪は補間される: 0.5秒後 %.2f" % mid)
	_env._step(10.0)
	_check(absf(_g("g_snow") - 1.0) < 0.001, "10秒後に積雪1")
	_game.world.env["weather"] = 0
	_env._step(10.0)
	_check(absf(_g("g_snow")) < 0.001, "10秒後に積雪0")


func _test_quality() -> void:
	_section("画質")
	var vp := root
	var sun := _env.get_node("Sun") as DirectionalLight3D
	var we := _env.get_node("WorldEnvironment") as WorldEnvironment
	var fx := _env.get_node("WeatherFx") as WeatherFx
	_game.world.env["weather"] = 2
	_env.apply_all()
	var rain := fx.get_node("Rain") as GPUParticles3D

	_game.set_setting("quality", 0)
	_check(absf(vp.scaling_3d_scale - 0.6) < 0.001 and not sun.shadow_enabled and not we.environment.glow_enabled, "軽量: 描画0.6・影なし・Glowなし")
	_check(rain.amount == 300, "軽量の粒数 300")

	_game.set_setting("quality", 1)
	_check(absf(vp.scaling_3d_scale - 0.8) < 0.001 and sun.shadow_enabled and we.environment.glow_enabled, "標準: 描画0.8・影あり・弱いGlow")
	_check(sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS and absf(sun.directional_shadow_max_distance - 80.0) < 0.001, "標準: 2分割・80m")
	_check(rain.amount == 800, "標準の粒数 800")

	_game.set_setting("quality", 2)
	_check(absf(vp.scaling_3d_scale - 1.0) < 0.001 and sun.shadow_enabled, "高: 描画1.0・影あり")
	_check(sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS and absf(sun.directional_shadow_max_distance - 120.0) < 0.001, "高: 4分割・120m")
	_check(we.environment.glow_intensity > 0.2, "高: Glow が標準より強い")
	_check(rain.amount == 1500, "高の粒数 1500")


func _cleanup(prev_world, prev_last: String, prev_quality: int) -> void:
	if _env != null:
		root.remove_child(_env)
		_env.free()
		_env = null
	# 世界を外してから消す(delete_world は開いている世界を消すと見本を作るため)
	_game.set("world", null)
	_game.delete_world(_test_id)
	_game.set("world", prev_world)
	_game.set("last_world_id", prev_last)
	_game.set_setting("quality", prev_quality)
	_game.call("_save_settings")
