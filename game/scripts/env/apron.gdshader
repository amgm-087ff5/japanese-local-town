// 世界の外の裾野: 地表の草色(g_season_grass)。雨で濡れ、冬は雪が乗る。lit(太陽の影を受ける)。
shader_type spatial;
render_mode cull_disabled;

global uniform vec4 g_season_grass : source_color;
global uniform float g_snow;
global uniform float g_wet;

varying vec3 w_pos;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	// グローバル uniform の色は EnvController が線形へ直して渡すので、そのまま線形として使う
	vec3 c = g_season_grass.rgb;
	// 遠目に単調にならないよう、大きめの緩い濃淡
	float patch = sin(w_pos.x * 0.07) * sin(w_pos.z * 0.05) * 0.05 + sin((w_pos.x + w_pos.z) * 0.19) * 0.025;
	c *= 1.0 + patch;
	c *= mix(1.0, 0.8, g_wet);
	c = mix(c, vec3(0.85, 0.9, 0.93), g_snow * 0.85);
	ALBEDO = c;
	ROUGHNESS = 0.95;
}
