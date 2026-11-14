// 空(sky): 天頂の青→地平の霞、朝夕の茜、太陽・月・星、雲(値ノイズ3オクターブ)。
// Mobile / Compatibility 両対応: テクスチャ不使用、ループは固定回数。色は EnvController が時刻・天気から設定する。
shader_type sky;

uniform vec3 sun_dir = vec3(0.0, 0.7, 0.7);
uniform vec3 moon_dir = vec3(0.0, -0.7, -0.7);
uniform vec4 zenith_color : source_color = vec4(0.36, 0.58, 0.82, 1.0);
uniform vec4 horizon_color : source_color = vec4(0.84, 0.9, 0.92, 1.0);
uniform vec4 sun_color : source_color = vec4(1.0, 0.97, 0.9, 1.0);
uniform vec4 moon_color : source_color = vec4(0.78, 0.85, 1.0, 1.0);
uniform vec4 glow_color : source_color = vec4(1.0, 0.6, 0.4, 1.0);
uniform float glow_amount = 0.0;
uniform float cloud_cover = 0.2;
uniform vec4 cloud_color : source_color = vec4(0.97, 0.97, 0.98, 1.0);
uniform float night = 0.0;
uniform float time_sec = 0.0;

float hash21(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	float a = hash21(i);
	float b = hash21(i + vec2(1.0, 0.0));
	float c = hash21(i + vec2(0.0, 1.0));
	float d = hash21(i + vec2(1.0, 1.0));
	return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// 3オクターブの値ノイズ(0〜約1)
float cloud_fbm(vec2 p) {
	float v = 0.0;
	float amp = 0.55;
	for (int k = 0; k < 3; k++) {
		v += amp * vnoise(p);
		p = p * 2.03 + vec2(17.1, 9.2);
		amp *= 0.5;
	}
	return v / 0.96;
}

void sky() {
	vec3 dir = normalize(EYEDIR);
	float up = dir.y;
	vec3 sd = normalize(sun_dir);
	vec3 md = normalize(moon_dir);

	// 地平の霞 → 天頂の青
	float g = pow(smoothstep(-0.02, 0.6, up), 0.7);
	vec3 col = mix(horizon_color.rgb, zenith_color.rgb, g);

	// 朝夕の茜: 太陽のある方角の低い空を赤く
	float sunward = dot(normalize(dir.xz + vec2(1e-4)), normalize(sd.xz + vec2(1e-4)));
	float band = exp(-abs(up) * 7.0);
	float sw = 0.35 + 0.65 * pow(max(sunward, 0.0), 3.0);
	col = mix(col, glow_color.rgb, glow_amount * band * sw);

	// 地平線より下はやや暗く(通常は地面が隠す)
	col *= mix(1.0, 0.75, smoothstep(0.0, -0.4, up));

	// 太陽: 円盤と、にじみ
	float sdot = dot(dir, sd);
	float sun_vis = smoothstep(-0.02, 0.03, sd.y) * (1.0 - cloud_cover * 0.85);
	float disk = smoothstep(0.99905, 0.99955, sdot);
	float halo = pow(max(sdot, 0.0), 220.0) * 0.8 + pow(max(sdot, 0.0), 10.0) * 0.12;
	col += sun_color.rgb * (disk * 1.6 + halo) * sun_vis;

	// 月: 夜だけ、円盤とにじみ
	float mdot = dot(dir, md);
	float moon_vis = night * smoothstep(-0.02, 0.05, md.y) * (1.0 - cloud_cover * 0.7);
	float mdisk = smoothstep(0.99880, 0.99920, mdot);
	float mhalo = pow(max(mdot, 0.0), 80.0) * 0.18;
	col += moon_color.rgb * (mdisk * 0.9 + mhalo) * moon_vis;

	// 星: 方向を格子に切ったハッシュの点。ゆっくり瞬く
	float star_vis = night * smoothstep(0.02, 0.2, up) * (1.0 - cloud_cover * 0.8);
	if (star_vis > 0.001) {
		vec3 cell = floor(dir * 320.0);
		float h = fract(sin(dot(cell, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
		float tw = 0.75 + 0.25 * sin(time_sec * 1.7 + h * 60.0);
		float st = step(0.9968, h) * tw;
		col += vec3(0.85, 0.9, 1.0) * st * star_vis;
	}

	// 雲: 天頂付近の平面に投影し、風の向きに流す。地平近くはフェード
	float cm = smoothstep(0.02, 0.2, up);
	if (cm > 0.001 && cloud_cover > 0.02) {
		vec2 uv = dir.xz / (up + 0.2) * 2.0 + vec2(time_sec * 0.010, time_sec * 0.004);
		float n = cloud_fbm(uv);
		float thr = mix(0.80, 0.34, cloud_cover);
		float c = smoothstep(thr, thr + 0.2, n) * cm;
		// 太陽側が少し明るい
		float lit = 0.84 + 0.16 * clamp(dot(dir, sd) * 0.5 + 0.5, 0.0, 1.0);
		col = mix(col, cloud_color.rgb * lit, c * 0.94);
	}

	COLOR = col;
}
