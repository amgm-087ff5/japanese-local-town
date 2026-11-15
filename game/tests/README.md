# テストの実行

作業ディレクトリはリポジトリ直下(`japanese-local-town/`)。`game` は Godot プロジェクトのフォルダ。
失敗が1つでもあれば終了コード 1。

## 一括

```sh
game/tools/run_all_tests.sh        # --import のあと全テストを流し、表で PASS / FAIL を出す
```

## 個別

初回・ファイルを増減した後は先に import する。

```sh
godot --headless --path game --import
```

| テスト | 内容 | 実行コマンド |
|---|---|---|
| run_tests | 骨格: Geom(スナップ・to_world)・WorldData 直列化・Game の Undo・保存・生成・Catalog | `godot --headless --path game --script res://tests/run_tests.gd` |
| test_terrain | 地形: ブラシ・整地・当たり・地表 | `godot --headless --path game --script res://tests/test_terrain.gd` |
| test_env | 環境: 時刻・季節・天気・遠景 | `godot --headless --path game --script res://tests/test_env.gd` |
| test_objects | 配置物(ObjectLayer)・森(Forest)・歩行時の幹の当たり・見本の配置の重なり・編集の枠・川べり・地表の境目 | `godot --headless --path game --script res://tests/test_objects.gd` |
| test_edit | 配置モード: 仮置き・スナップ・ドラッグ・Undo・カメラ | `godot --headless --path game --script res://tests/test_edit.gd` |
| test_walk | 歩行: 立つ・歩く・範囲・水・段差・見本の鳥居と拝殿・開始位置・終了時の保存 | `godot --headless --path game --script res://tests/test_walk.gd` |
| test_ui | 画面(Hud): 縦 720×1560・横 1560×720 の配置・タッチの大きさ・モード・戻るボタン・スナップ表示 | `godot --headless --path game --scene res://tests/test_ui.tscn` |

- `--script` は SceneTree のテスト(autoload の Game / Catalog は実行時に `root` から取る)。
- `--scene` は Node のテスト(`test_ui.tscn`)。UI は `--script` では autoload を解決できないため。

## 注意

- テストが作る世界は終了時に消し、`last_world_id` は元の値に戻す。
- 異常系(壊れた base64・壊れた JSON・未知の version)は意図的に壊したデータを読むため、エンジンのエラーログ(base64 / JSON parse)が出る。想定どおり。
- `compute_snap`(物100個)の時間は表示のみ(目標 1ms を超えたら WARNING。失敗にはしない)。
- 川べりの折れ・山の谷の値は地形がランダムな seed で作られるため、表示の値は実行ごとに少し変わる。
- 歩行のテストは歩行HUD(スティック)を隠して API を直接動かす(HUD は表示中は毎フレーム stick を送るため)。
