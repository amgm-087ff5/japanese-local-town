extends Node
# 画面確認用: メインシーンを起動してスクリーンショットを保存する。
# 例: xvfb-run -a -s "-screen 0 1600x1600x24" godot --path game --rendering-method mobile --resolution 720x1560 \
#       res://tools/shot.tscn -- out=/tmp/a.png world=sample mode=edit time=9 season=0 weather=0 cam=oblique dist=60 wait=2.5
# 引数(すべて省略可): out, world(sample|hills|flat|keep), mode(edit|terrain|walk|photo), time, season, weather,
#   cam(top|side|oblique|north), dist, tx, tz(注視点), yaw, pitch(度), wait(秒), call=<Mainのメソッド名>(撮影前に呼ぶ)
func _ready() -> void:
	var root := get_tree().root
	var a := {}
	for s in OS.get_cmdline_user_args():
		var kv := s.split("=", true, 1)
		if kv.size() == 2:
			a[kv[0]] = kv[1]
	var game := root.get_node("Game")
	var main: Node = load("res://main.tscn").instantiate()
	root.add_child.call_deferred(main)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	var w: String = a.get("world", "sample")
	if w != "keep":
		game.new_world(w)
	await get_tree().process_frame
	if a.has("time"):
		game.world.env["time"] = float(a["time"])
	game.world.env["time_flow"] = false
	if a.has("season"):
		game.set_env("season", int(a["season"]))
	if a.has("weather"):
		game.set_env("weather", int(a["weather"]))
	game.set_env("time_flow", false)
	var rig = main.get("camera_rig")
	if rig != null:
		if a.has("cam") and rig.has_method("set_preset"):
			rig.set_preset(a["cam"])
		if a.has("tx") or a.has("tz"):
			rig.target = Vector3(float(a.get("tx", "0")), 0.0, float(a.get("tz", "0")))
		if a.has("dist"):
			rig.distance = float(a["dist"])
		if a.has("yaw"):
			rig.yaw = deg_to_rad(float(a["yaw"]))
		if a.has("pitch"):
			rig.pitch = deg_to_rad(float(a["pitch"]))
	if a.has("mode"):
		game.set_mode(a["mode"])
	if a.has("call") and main.has_method(a["call"]):
		main.call(a["call"])
	await get_tree().create_timer(float(a.get("wait", "2.5"))).timeout
	var img := root.get_viewport().get_texture().get_image()
	var out: String = a.get("out", "/tmp/shot.png")
	img.save_png(out)
	print("saved ", out, " ", img.get_size())
	get_tree().quit()
