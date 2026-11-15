# 実装担当むけ共通メモ(必読・短い)

- 設計の正本: `docs/architecture.md`(**15章が優先**)。API名・シグナル名・ファイル名を変えない。足りないAPIは自分のファイル内に足し、最終報告に書く。
- **自分の担当ファイルだけ**編集する。`project.godot` `scripts/main.gd` `scripts/core/*` `data/catalog.json` `tools/` は編集禁止(必要な変更は報告)。git操作禁止。
- 骨格の事実: Rect2i は position=最小の頂点index・size=個数。autoload は `Game` `Catalog`。Main は group "main"、`main.terrain / forest / objects / env / camera_rig / edit_mode / terrain_mode / walk_mode / hud`。Main が `process_mode` でモードの有効/無効を切り替える。世界は `Game.world`(WorldData)。`world_loaded` で各モジュールの再構築。
- グローバルシェーダ uniform は project.godot に定義済み: `g_season_grass`(color) `g_snow` `g_wet` `g_wind` `g_night` `g_leaf_density_deciduous`(float) `g_leaf_sugi/_matsu/_take/_sakura/_kaede`(color)。シェーダ側は `global uniform vec4 g_season_grass : source_color;` のように宣言。値を設定するのは EnvController だけ(`RenderingServer.global_shader_parameter_set`)。
- シェーダは Mobile と Compatibility の両方で動く書き方(テクスチャ配列・`hint_depth_texture`/`hint_screen_texture` を使わない、ループを固定回数に)。
- GDScript は静的型。Godot 4.7 の API を使う(3.x の書き方をしない)。不確かなAPIは `godot --doctool /tmp/doc` で出力したXMLか、小さなスクリプトで確かめる。
- 確認コマンド(リポジトリ直下で):
  - 構文・起動: `godot --headless --path game --quit-after 30 2>&1 | grep -E "ERROR|SCRIPT|Parse" `(何も出なければOK)
  - テスト: `godot --headless --path game --script res://tests/run_tests.gd`(自分の機能のテストは `tests/test_<担当>.gd` を新規に作り `extends SceneTree` で同様に実行。run_tests.gd は編集しない)
  - 画面: `xvfb-run -a -s "-screen 0 1600x1600x24" godot --path game --rendering-method mobile --resolution 720x1560 res://tools/shot.tscn -- out=/tmp/<名前>.png world=sample mode=edit cam=oblique dist=60 wait=2.5`(縦 720x1560 / 横 1560x720。引数は tools/shot.gd 冒頭)。ソフトウェア描画(lavapipe)なので遅い。撮った PNG は Read ツールで**自分の目で見て**直す(枚数は最小限、合計8枚以内を目安)。**`--script` 起動では autoload 名(Game/Catalog)がコンパイルできず main.gd が読めない。Main を使う確認・テストは必ずシーン起動(`godot --path game res://tools/shot.tscn -- ...` のように .tscn + `extends Node` の `_ready`)で行う**。独自の操作は tools/shot.gd を参考に自分用の .tscn+.gd を game/tests/ か /tmp に作る。
  - 他の担当も同時に同じプロジェクトで Godot を動かしている。`.godot` のインポートで変なエラーが出たら `godot --headless --path game --import` を流して再実行。他担当のファイルが未完成(STUB)でも自分の部分が動くように(null・メソッド有無を確認して呼ぶ)。
- モデル(assets/models/*.glb)は別担当が作成中。無い間は Catalog が箱を返す。
- 性能: モバイル前提。毎フレームの配列確保・全域走査を避ける。`print` を毎フレーム出さない。
- 最終報告は40行以内: 作ったファイル、公開API(設計書との差分)、確認結果(テスト・見た画像の所見)、既知の問題。
