## 雨・雪の粒(architecture.md 10章)。GPUParticles3D をカメラの真上に置いて追従させる。
## 雨 = 細長い筋が速く落ちる(align_y で速度方向に向ける)。雪 = 柔らかい粒がゆっくり舞う。
## 粒数は画質で決まる(set_amount: 300 / 800 / 1500)。
class_name WeatherFx
extends Node3D

const RAIN_HEIGHT := 9.0
const SNOW_HEIGHT := 12.0
const BOX_HALF := Vector3(34.0, 1.0, 34.0)
const VIS_AABB := AABB(Vector3(-60.0, -40.0, -60.0), Vector3(120.0, 80.0, 120.0))

var _rain: GPUParticles3D
var _snow: GPUParticles3D
var _weather := 0
var _amount := 800


func _ready() -> void:
	_rain = _make_rain()
	add_child(_rain)
	_snow = _make_snow()
	add_child(_snow)
	_rain.emitting = false
	_snow.emitting = false


func _process(_delta: float) -> void:
	if _weather != 2 and _weather != 3:
		return
	var vp := get_viewport()
	if vp == null:
		return
	var cam := vp.get_camera_3d()
	if cam == null:
		return
	var p := cam.global_position
	_rain.global_position = Vector3(p.x, p.y + RAIN_HEIGHT, p.z)
	_snow.global_position = Vector3(p.x, p.y + SNOW_HEIGHT, p.z)


## 0晴 1曇 2雨 3雪。雨と雪以外は粒を止める。
func set_weather(w: int) -> void:
	if w == _weather:
		return
	_weather = w
	_rain.emitting = w == 2
	_snow.emitting = w == 3
	if w == 2:
		_rain.restart()
	elif w == 3:
		_snow.restart()


## 粒数(画質の値)。雨と雪の両方に使う。
func set_amount(n: int) -> void:
	if n == _amount:
		return
	_amount = n
	_rain.amount = n
	_snow.amount = n


func _make_rain() -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.name = "Rain"
	p.amount = _amount
	p.lifetime = 1.2
	p.preprocess = 1.2
	p.visibility_aabb = VIS_AABB

	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = BOX_HALF
	pm.direction = Vector3(0.12, -1.0, 0.05)
	pm.spread = 3.0
	pm.initial_velocity_min = 9.0
	pm.initial_velocity_max = 11.0
	pm.gravity = Vector3(0.0, -2.0, 0.0)
	pm.scale_min = 0.8
	pm.scale_max = 1.2
	pm.particle_flag_align_y = true
	p.process_material = pm

	var quad := QuadMesh.new()
	quad.size = Vector2(0.035, 0.9)
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.billboard_keep_scale = true
	mat.vertex_color_use_as_albedo = true
	mat.albedo_color = Color(0.8, 0.86, 0.95, 0.42)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.disable_receive_shadows = true
	quad.material = mat
	p.draw_pass_1 = quad
	return p


func _make_snow() -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.name = "Snow"
	p.amount = _amount
	p.lifetime = 9.0
	p.preprocess = 9.0
	p.visibility_aabb = VIS_AABB

	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = BOX_HALF
	pm.direction = Vector3(0.0, -1.0, 0.0)
	pm.spread = 25.0
	pm.initial_velocity_min = 0.6
	pm.initial_velocity_max = 1.2
	pm.gravity = Vector3(0.0, -0.1, 0.0)
	pm.scale_min = 0.7
	pm.scale_max = 1.3
	pm.turbulence_enabled = true
	pm.turbulence_noise_strength = 0.6
	pm.turbulence_noise_scale = 3.0
	pm.turbulence_noise_speed = Vector3(0.4, 0.1, 0.4)
	p.process_material = pm

	var grad := Gradient.new()
	grad.colors = PackedColorArray([Color(1.0, 1.0, 1.0, 1.0), Color(1.0, 1.0, 1.0, 0.0)])
	grad.offsets = PackedFloat32Array([0.0, 1.0])
	var tex := GradientTexture2D.new()
	tex.gradient = grad
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	tex.width = 32
	tex.height = 32

	var quad := QuadMesh.new()
	quad.size = Vector2(0.13, 0.13)
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.billboard_keep_scale = true
	mat.vertex_color_use_as_albedo = true
	mat.albedo_texture = tex
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.disable_receive_shadows = true
	quad.material = mat
	p.draw_pass_1 = quad
	return p
