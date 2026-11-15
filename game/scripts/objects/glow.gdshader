// 夜に灯る材質(glow_lantern / glow_window)。architecture.md 10章・15.4。
// 昼は和紙色。夜は emission = 暖色 × g_night × 強さ(g_night は EnvController が global uniform で設定)。
// ObjectLayer が種類ごとに1個の ShaderMaterial を共有する(物ごとに複製しない)。
shader_type spatial;
render_mode cull_back, diffuse_lambert, specular_disabled;

global uniform float g_night;

uniform vec4 base_color : source_color = vec4(0.93, 0.9, 0.82, 1.0);
uniform vec4 glow_color : source_color = vec4(1.0, 0.55, 0.15, 1.0);
uniform float glow_strength = 3.0;

void fragment() {
	ALBEDO = base_color.rgb;
	ROUGHNESS = 0.9;
	EMISSION = glow_color.rgb * (clamp(g_night, 0.0, 1.0) * glow_strength);
}
