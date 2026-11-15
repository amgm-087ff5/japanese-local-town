// 葉(architecture.md 9章・15.4)。配置物の木と森の MultiMesh の両方で使う。
// 種ごとに ShaderMaterial を1つずつ作り、uniform kind で色を選ぶ(色は EnvController が global uniform で配る)。
// INSTANCE_CUSTOM に依存しない。Mobile / Compatibility 両対応(固定回数のループなし・テクスチャ無し)。
shader_type spatial;
render_mode cull_back, diffuse_lambert, specular_disabled;

global uniform vec4 g_leaf_sugi : source_color;
global uniform vec4 g_leaf_matsu : source_color;
global uniform vec4 g_leaf_take : source_color;
global uniform vec4 g_leaf_sakura : source_color;
global uniform vec4 g_leaf_kaede : source_color;
global uniform float g_leaf_density_deciduous;
global uniform float g_snow;
global uniform float g_wind;
global uniform float g_night;

// 0 杉 1 松 2 竹 3 桜 4 楓
uniform int kind = 0;
// 落葉樹(桜・楓)。true のとき密度に g_leaf_density_deciduous を使う。
uniform bool deciduous = false;
// 揺れの振幅(高さ1単位あたり)。幹の根元は動かない。
uniform float sway = 0.03;
// 塊の明暗の強さ。
uniform float shade_noise = 0.12;

varying vec3 v_world;
varying vec3 v_normal_world;
varying float v_shade;
varying float v_inst;

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

void vertex() {
	// 頂点ごとの明暗(塊感)。揺らす前のローカル座標で計算し、フレーム間で変わらないようにする。
	v_shade = hash13(VERTEX * 3.7);
	// インスタンスごとの色のばらつき(MultiMesh なら各木、配置物ならノードの位置)。
	vec3 origin = MODEL_MATRIX[3].xyz;
	v_inst = hash13(vec3(origin.x, origin.z, origin.x + origin.z) * 0.37);

	// 風: 高さに比例して頂点を横へ揺らす(VERTEX のローカル y で重み付け)。
	float phase = TIME * 1.4 + origin.x * 0.7 + origin.z * 0.5;
	float bend = max(VERTEX.y, 0.0);
	float gust = g_wind * sway * bend;
	VERTEX.x += sin(phase + VERTEX.y * 0.5) * gust;
	VERTEX.z += cos(phase * 0.8 + VERTEX.y * 0.4) * gust * 0.6;

	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_normal_world = normalize(mat3(MODEL_MATRIX) * NORMAL);
}

void fragment() {
	// 冬の落葉樹は枝だけに見えるよう、ワールド座標の格子(約0.33m)ごとに間引く(discard)。
	float density = deciduous ? g_leaf_density_deciduous : 1.0;
	if (density < 0.999) {
		float keep = hash13(floor(v_world * 3.0));
		if (keep >= density) {
			discard;
		}
	}

	vec3 base;
	if (kind == 0) {
		base = g_leaf_sugi.rgb;
	} else if (kind == 1) {
		base = g_leaf_matsu.rgb;
	} else if (kind == 2) {
		base = g_leaf_take.rgb;
	} else if (kind == 3) {
		base = g_leaf_sakura.rgb;
	} else {
		base = g_leaf_kaede.rgb;
	}

	// 塊ごとの明暗と、木ごとのわずかな色味のばらつき
	float shade = 1.0 + shade_noise * (v_shade - 0.5) * 2.0;
	base *= shade * (0.92 + 0.16 * v_inst);

	// 夜の色味(彩度を落として青みの暗い色へ。昼は素通し)
	float l = dot(base, vec3(0.2126, 0.7152, 0.0722));
	base = mix(base, vec3(l) * vec3(1.02, 1.16, 0.64), g_night * 0.75) * mix(1.0, 0.55, g_night);

	// 積雪: 上向きの面が白くなる
	float up = clamp(v_normal_world.y, 0.0, 1.0);
	float snow_amount = g_snow * smoothstep(0.35, 0.8, up);
	base = mix(base, vec3(0.94, 0.95, 0.97), snow_amount);

	ALBEDO = base;
	ROUGHNESS = 0.85;
}
