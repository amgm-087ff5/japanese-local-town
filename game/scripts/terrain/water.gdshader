shader_type spatial;
render_mode blend_mix, specular_schlick_ggx;

// 水面: 深い青緑。フレネルで空色寄り。時間で動く波の法線(ノイズテクスチャ由来)。やや透明。
// hint_depth_texture は使わない(Mobile / Compatibility 両対応のため)。
uniform sampler2D wave_tex : filter_linear_mipmap, repeat_enable;
uniform vec3 deep_color : source_color = vec3(0.06, 0.22, 0.24);
uniform vec3 sky_color : source_color = vec3(0.50, 0.63, 0.70);
uniform float alpha = 0.85;

varying vec3 w_pos;

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float wave(vec2 p, float t) {
	float a = texture(wave_tex, p / 13.0 + vec2(t * 0.012, t * 0.008)).r;
	float b = texture(wave_tex, p / 5.5 + vec2(-t * 0.020, t * 0.017)).g;
	return a * 0.65 + b * 0.35;
}

void fragment() {
	float t = TIME;
	vec2 p = w_pos.xz;
	float e = 0.3;
	float h0 = wave(p, t);
	float hx = wave(p + vec2(e, 0.0), t);
	float hz = wave(p + vec2(0.0, e), t);
	vec3 n_w = normalize(vec3(-(hx - h0) / e * 0.8, 1.0, -(hz - h0) / e * 0.8));
	NORMAL = normalize((VIEW_MATRIX * vec4(n_w, 0.0)).xyz);

	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	ALBEDO = mix(deep_color, sky_color, clamp(0.12 + fres * 0.7, 0.0, 1.0));
	ROUGHNESS = 0.18;
	SPECULAR = 0.35;
	METALLIC = 0.0;
	ALPHA = clamp(alpha + fres * 0.1, 0.0, 1.0);
}
