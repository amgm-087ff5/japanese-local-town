shader_type spatial;

// 建物の屋根の材質。元の色(albedo_color)を保ち、上を向いた面だけ g_snow に応じて白くする。
// Mobile / Compatibility の両方で動く書き方(テクスチャ配列・画面テクスチャを使わない)。
global uniform float g_snow;
uniform vec4 albedo_color : source_color = vec4(0.5, 0.5, 0.5, 1.0);
uniform float roughness_base = 0.8;

void fragment() {
	// NORMAL は視点空間。ワールドの上向きの成分を取り出す
	float up = (INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).y;
	float snow = g_snow * smoothstep(0.45, 0.75, up);
	ALBEDO = mix(albedo_color.rgb, vec3(0.94, 0.95, 0.97), snow);
	ROUGHNESS = mix(roughness_base, 0.9, snow);
}
