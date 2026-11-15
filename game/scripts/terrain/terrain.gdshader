shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

// 地表の重み(splat)。a: R=土 G=砂利 B=石畳 A=苔 / b: R=白砂 G=畑 B=舗装。草は残り(1 - 合計)。
// texel i の中心が頂点 i(x = i - 128)に一致するよう、UV は (x + 128.5) / 257。
uniform sampler2D splat_a : filter_linear, repeat_disable;
uniform sampler2D splat_b : filter_linear, repeat_disable;
// 起動時に作るタイリングのノイズ(R,G,B,A は別周波数)。
uniform sampler2D pattern_tex : filter_linear_mipmap, repeat_enable;
uniform float water_level = -0.6;

global uniform vec4 g_season_grass : source_color;
global uniform float g_snow;
global uniform float g_wet;
global uniform float g_night;

uniform vec3 c_soil : source_color = vec3(0.56, 0.48, 0.37);
uniform vec3 c_wet_soil : source_color = vec3(0.30, 0.25, 0.20);
uniform vec3 c_gravel : source_color = vec3(0.60, 0.59, 0.55);
uniform vec3 c_stone : source_color = vec3(0.52, 0.52, 0.50);
uniform vec3 c_mortar : source_color = vec3(0.30, 0.30, 0.28);
uniform vec3 c_moss : source_color = vec3(0.37, 0.47, 0.30);
uniform vec3 c_sand : source_color = vec3(0.97, 0.95, 0.88);
uniform vec3 c_field : source_color = vec3(0.42, 0.33, 0.24);
uniform vec3 c_pave : source_color = vec3(0.27, 0.27, 0.28);
uniform vec3 c_rock : source_color = vec3(0.45, 0.43, 0.40);
uniform vec3 c_snow : source_color = vec3(0.98, 0.99, 1.0);

varying vec3 w_pos;
varying vec3 w_nrm;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	w_nrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float hash12(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

// 夜の色味(g_night 0 昼 〜 1 夜): 彩度を落として青みの灰色へ寄せ、明度も下げる。昼は素通し。
vec3 night_grade(vec3 c, float n) {
	float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
	vec3 cool = vec3(l) * vec3(1.02, 1.16, 0.64);
	c = mix(c, cool, n * 0.75);
	return c * mix(1.0, 0.55, n);
}

void fragment() {
	vec2 p = w_pos.xz;
	vec2 suv = (p + 128.5) / 257.0;
	vec4 a = texture(splat_a, suv);
	vec4 b = texture(splat_b, suv);
	float wsum = a.r + a.g + a.b + a.a + b.r + b.g + b.b;
	float wg = clamp(1.0 - wsum, 0.0, 1.0);

	// 模様は遠くで弱める(モアレ防止)。detail=0 で平均色に寄る
	float dist = distance(w_pos, CAMERA_POSITION_WORLD);
	float detail = 1.0 - smoothstep(40.0, 150.0, dist);

	vec4 n1 = texture(pattern_tex, p / 16.0);
	vec2 q = vec2(p.x * 0.8 + p.y * 0.6, p.y * 0.8 - p.x * 0.6);
	vec4 n2 = texture(pattern_tex, q / 23.0 + vec2(0.37, 0.61));
	float big = mix(0.5, mix(n1.r, n2.r, 0.5), detail);
	float mid = mix(0.5, n1.g, detail);
	float fine = mix(0.5, n1.b, detail);
	float grain = mix(0.5, n1.a, detail);

	// 草: 季節色に濃淡。露出で白っぽくなるため彩度は落とさず、明るさだけを抑える
	vec3 grass_base = g_season_grass.rgb * 0.82;
	vec3 c_grass = grass_base * mix(0.78, 1.14, big) * mix(0.90, 1.08, mid);
	c_grass *= mix(0.9, 1.05, w_nrm.y);

	// 土・砂利・苔・白砂・舗装
	vec3 c_soil_v = c_soil * mix(0.82, 1.12, mid) * mix(0.92, 1.06, fine);
	vec3 c_gravel_v = c_gravel * mix(0.72, 1.18, grain) * mix(0.92, 1.05, fine);
	vec3 c_moss_v = c_moss * mix(0.80, 1.16, mid) * mix(0.90, 1.10, fine);
	vec3 c_sand_v = c_sand * mix(0.94, 1.03, grain) * mix(0.96, 1.02, mid);
	vec3 c_pave_v = c_pave * mix(0.90, 1.10, grain) * mix(0.94, 1.05, mid);

	// 石畳: 0.6m 角の千鳥の格子。目地は細く暗く、遠くでは平均色へ
	vec2 g = p / 0.6;
	g.x += 0.5 * mod(floor(g.y), 2.0);
	vec2 cell = floor(g);
	vec2 f = fract(g);
	float edge = min(min(f.x, 1.0 - f.x), min(f.y, 1.0 - f.y));
	float joint = (1.0 - smoothstep(0.03, 0.075, edge)) * detail;
	float sh = hash12(cell);
	vec3 c_stone_v = c_stone * mix(1.0, mix(0.84, 1.14, sh), detail) * mix(0.92, 1.06, mid);
	c_stone_v = mix(c_stone_v, c_mortar, joint);

	// 畑: 畝の縞(間隔 1.1m、南北方向の縞)
	float ridge = mix(0.5, 0.5 + 0.5 * sin(p.x * 6.2831853 / 1.1), detail);
	vec3 c_field_v = c_field * mix(0.74, 1.12, ridge) * mix(0.90, 1.08, mid);

	vec3 col = c_grass * wg
		+ c_soil_v * a.r
		+ c_gravel_v * a.g
		+ c_stone_v * a.b
		+ c_moss_v * a.a
		+ c_sand_v * b.r
		+ c_field_v * b.g
		+ c_pave_v * b.b;
	col /= max(wg + wsum, 0.001);

	// 水際(水位付近)は濡れた土色
	float shore = 1.0 - smoothstep(0.0, 0.8, abs(w_pos.y - water_level));
	col = mix(col, c_wet_soil, shore * 0.7);

	// 急斜面は岩肌へ(法線.y < 0.70 付近で滑らかに)
	float ny = w_nrm.y;
	float cliff = 1.0 - smoothstep(0.64, 0.76, ny);
	vec3 c_rock_v = c_rock * mix(0.80, 1.18, big) * mix(0.90, 1.08, fine);
	c_rock_v *= mix(0.92, 1.05, mid);
	col = mix(col, c_rock_v, cliff);
	col = night_grade(col, g_night);

	// 雪: 上向きの面に。縁は模様で揺らす(雪は夜の色味を掛けず、青白いまま)
	float snow_edge = 0.62 - 0.15 * (big - 0.5);
	float snow = g_snow * smoothstep(snow_edge, snow_edge + 0.18, ny) * (1.0 - cliff);
	col = mix(col, c_snow * mix(0.94, 1.0, grain), snow);

	// 雨: 暗く、平らな面は濡れて光る
	float wet = g_wet * (1.0 - snow);
	col *= mix(1.0, 0.72, wet);

	ALBEDO = col;
	SPECULAR = 0.25;
	float rough = mix(0.93, 0.62, wet * smoothstep(0.7, 0.95, ny));
	rough = mix(rough, 0.80, snow);
	ROUGHNESS = mix(rough, 0.95, cliff);
}
