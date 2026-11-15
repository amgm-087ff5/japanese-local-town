// 遠景の山並み: unshaded・fog 無効(霞は EnvController が色で作る)。
// 頂点色: COLOR.r = 稜線に近いほど 1(下端 0)、COLOR.g = 山の高さ(0〜1、雪の判定用)。
shader_type spatial;
render_mode unshaded, fog_disabled, cull_disabled;

uniform vec4 base_color : source_color = vec4(0.4, 0.45, 0.5, 1.0);
uniform vec4 snow_color : source_color = vec4(0.92, 0.94, 0.97, 1.0);
uniform float snow_amount = 0.0;

void fragment() {
	float top = COLOR.r;
	float peak = COLOR.g;
	float snow = snow_amount * smoothstep(0.55, 0.85, peak) * smoothstep(0.55, 0.95, top);
	vec3 c = mix(base_color.rgb, snow_color.rgb, snow);
	ALBEDO = c * mix(0.9, 1.0, top);
}
