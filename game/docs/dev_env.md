# 開発環境: Godot 4.7.2 (ヘッドレステスト / ソフトウェア描画 / Android APK)

対象: Ubuntu 24.04 のLinuxコンテナ (root, 2コア, 7GB)。GitHub Actions ubuntu-latest でも同じスクリプトで整う。
再現手順は `game/tools/setup_env.sh` (環境構築, 冪等) と `game/tools/xvfb_godot.sh` (描画ラッパ)。

## 導入した版

| 項目 | 版 / 内容 | 備考 |
| --- | --- | --- |
| Godot | 4.7.2.stable.official.ed1daf0bf | `/usr/local/bin/godot` -> `/opt/godot/Godot_v4.7.2-stable_linux.x86_64` |
| JDK | OpenJDK 17.0.21 (`openjdk-17-jdk-headless`) | Godot の `platform/android/java/app/config.gradle` の `javaVersion=17`。コンテナ既定の java は 21 だが、Java設定は `java_sdk_path` で JDK 17 を指定 |
| Android build-tools | 36.1.0 | `buildTools` と一致 (apksigner, aapt2 等) |
| Android platform | android-36 | `compileSdk 36` と一致 |
| platform-tools | r37.0.1 | adb 等。APK 書き出しには不要 |
| cmdline-tools | build 13114758 | `sdkmanager` 用 (`/opt/android-sdk/cmdline-tools/latest`) |
| NDK | 不要 (未導入) | `ndkVersion 29.0.14206865` は Gradle ビルドやネイティブ拡張のときだけ必要。通常エクスポートでは使わない |
| エクスポートテンプレート | 4.7.2.stable | `~/.local/share/godot/export_templates/4.7.2.stable/` に Android 分のみ: `android_debug.apk`, `android_release.apk`, `android_source.zip`, `icudt_godot.dat`, `version.txt` (計 431MB) |
| ソフトウェア描画 | Mesa 25.2.8 (lavapipe, LLVM 20.1.2 / llvmpipe), Xvfb, xauth | `mesa-vulkan-drivers libgl1-mesa-dri libvulkan1` |
| 日本語フォント | Noto Sans CJK (`fonts-noto-cjk`) | Godot 既定フォントに日本語グリフは無い。プロジェクト側で CJK フォントを同梱する必要がある |

エディタ設定 (`~/.config/godot/editor_settings-4.7.tres`) の Android 関連キー:

```
export/android/android_sdk_path = "/opt/android-sdk"
export/android/java_sdk_path = "/usr/lib/jvm/java-17-openjdk-amd64"
```

ヘッドレスエクスポートはこの2つを読むので、環境変数では代替しなかった。Godot がエディタ起動時に設定ファイル全体を書き直すが、この2キーは残ることを確認した。

## 所要時間

- 新規環境の取得 (テンプレート 1.3GB の取得と展開 + cmdline-tools + SDK 導入 + Godot 設定): `setup_env.sh` を別 HOME・別 SDK 先で実行して **1分15秒** (apt は `SKIP_APT=1`。apt の導入時間は計測していない)
- 2回目以降の `setup_env.sh`: 全項目スキップで 1秒未満
- 最小プロジェクトの Android 書き出し (`--export-release`): **約17秒**。出力 APK は **42.7MB** (arm64-v8a のみ)
- 1フレーム時間 (xvfb 上、120フレームの平均、`--bench`):

| レンダラ | 720x1560 | 1560x720 | 起動 (1回目 目安) |
| --- | --- | --- | --- |
| Mobile (`vulkan`, lavapipe) | 42.8 ms | 57.3 ms | 約7〜11秒 |
| Compatibility (`opengl3`, llvmpipe) | 11.5 ms | 7.8 ms | 約1〜2秒 |

2コアの計測なので実機の性能とは比べられない。ラッパの既定は、プロジェクトのレンダラと同じ Mobile (`vulkan`) にした。速度を優先するなら `XVFB_RENDERER=opengl3` を使う。

## 確認したこと

1. `godot --headless --path /tmp/hello --import` : 成功 (exit 0)
2. xvfb スクリーンショット (4パターンすべて PNG 保存に成功。日本語 "こんにちは" の描画も目視確認):
   - Mobile (vulkan) 720x1560 / 1560x720
   - Compatibility (opengl3) 720x1560 / 1560x720
   - `game/tools/xvfb_godot.sh` 経由でも両レンダラ・両向きで成功
3. Android release APK の書き出し・署名: 成功 (`Signed`, exit 0)
4. `apksigner verify --print-certs`: `Verifies`, v2/v3 署名 true, RSA 2048, CN=Test (テスト用の一時 keystore)
5. `aapt2 dump badging`: `package: name='com.example.hello' versionCode='1' versionName='1.0'`, `minSdkVersion:'24'`, `targetSdkVersion:'36'`, `native-code: 'arm64-v8a'`, `uses-permission: INTERNET`

## 注意点 / ハマった点

- **`--headless` を付けてスクリーンショットや計測をすると止まる。** 描画が走らず `RenderingServer.frame_post_draw` が来ないため、`save_png` も計測も完了しない。描画系は xvfb 上で `--headless` 無しで起動する (ラッパはこれを守っている)。
- **Android 書き出しには ETC2/ASTC が必須。** 設定 `rendering/textures/vram_compression/import_etc2_astc=true` が無いと、`Cannot export project ... ETC2/ASTC texture compression is required` で失敗する。
- keystore はプリセットに書かず、環境変数で渡すと成功した (下記コマンド)。
- `aapt` (v1) は `failed to read attribute 'android:required'` を出して exit 1 になるが、Godot が生成した manifest の解釈上の問題で、`aapt2 dump badging` は exit 0 で正常。確認には `aapt2` を使う。
- `aapt2` は `warn: resource com.godot.game:mipmap/themed_icon ... no such path exists` という警告を出すが、無害。
- ALSA の警告 (`cannot find card '0'`) は音声デバイスが無いため。`--audio-driver Dummy` で出力を抑えられる。
- `cannot connect to daemon at tcp:5037` は adb が無いときの無害なメッセージ。
- `ERROR: No project icon specified` は書き出し自体には影響しない (launcher アイコン未設定の警告)。本番ではアイコンを設定する。
- 横向きの撮影では、ビューポートの `visible_rect` が `3380x1560` と表示されるが、保存された PNG は `1560x720`。`aspect="expand"` による仮想領域で、PNG はウィンドウのピクセルサイズになる。
- 画面回転: `display/window/handheld/orientation=6` (SCREEN_SENSOR) で、APK の manifest は `android:screenOrientation="13"` (fullUser。端末の自動回転設定に従う) になることを確認。
- テスト用 keystore (`/tmp/hello/test-release.p12`) はテスト専用。本番の署名鍵は別途管理すること (リポジトリには含めない)。
- 未検証: debug 書き出し、Gradle ビルド (`use_gradle_build=true`) 、NDK 必要な経路。
- ダウンロードは HTTPS プロキシ経由で成功した。TLS 検証は無効化していない。

## 使い方

```bash
# 環境構築 (冪等。新しいコンテナで1回)
game/tools/setup_env.sh
# SKIP_APT=1 game/tools/setup_env.sh   # apt を飛ばす (導入済みの CI 等)

# ソフトウェア描画でスクリーンショット (縦 / 横)
game/tools/xvfb_godot.sh 720 1560 -- --path game -- --shot=/tmp/shot_720x1560.png
XVFB_RENDERER=opengl3 game/tools/xvfb_godot.sh 1560 720 -- --path game -- --shot=/tmp/shot_1560x720.png

# Android release APK (keystore は環境変数で渡す)
export GODOT_ANDROID_KEYSTORE_RELEASE_PATH=/secure/path/release.keystore
export GODOT_ANDROID_KEYSTORE_RELEASE_USER=alias
export GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD='***'
godot --headless --path game --export-release "Android" /tmp/game.apk

# 検証
/opt/android-sdk/build-tools/36.1.0/apksigner verify --verbose --print-certs /tmp/game.apk
/opt/android-sdk/build-tools/36.1.0/aapt2 dump badging /tmp/game.apk
```

スクリーンショット用スクリプトの要点 (`/tmp/hello/main.gd` より抜粋):

```gdscript
var out := ""
for a in OS.get_cmdline_user_args():
	if a.begins_with("--shot="):
		out = a.substr(7)
if out != "":
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var err := get_viewport().get_texture().get_image().save_png(out)
	get_tree().quit(0 if err == OK else 1)
```

## 検証に使ったプロジェクト (/tmp/hello) の設定

`project.godot` (全文):

```ini
; Engine configuration file.
config_version=5

[application]

config/name="Hello"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.7", "Mobile")

[display]

window/size/viewport_width=720
window/size/viewport_height=1560
window/stretch/mode="canvas_items"
window/stretch/aspect="expand"
window/handheld/orientation=6

[rendering]

renderer/rendering_method="mobile"
renderer/rendering_method.mobile="mobile"

textures/vram_compression/import_etc2_astc=true
```

`export_presets.cfg` (全文。`--export-release "Android"` で通った内容。`keystore/*` は空で、環境変数から読ませた):

```ini
[preset.0]

name="Android"
platform="Android"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="/tmp/hello/hello.apk"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
gradle_build/use_gradle_build=false
gradle_build/gradle_build_directory=""
gradle_build/android_source_template=""
gradle_build/compress_native_libraries=false
gradle_build/export_format=0
gradle_build/min_sdk=""
gradle_build/target_sdk=""
architectures/armeabi-v7a=false
architectures/arm64-v8a=true
architectures/x86=false
architectures/x86_64=false
version/code=1
version/name="1.0"
package/unique_name="com.example.hello"
package/name="Hello"
package/signed=true
package/app_category=2
package/retain_data_on_uninstall=false
package/exclude_from_recents=false
package/show_in_android_tv=false
package/show_in_app_library=true
package/show_as_launcher_app=false
launcher_icons/main_192x192=""
launcher_icons/adaptive_foreground_432x432=""
launcher_icons/adaptive_background_432x432=""
launcher_icons/adaptive_monochrome_432x432=""
graphics/opengl_debug=false
xr_features/xr_mode=0
gesture/swipe_to_dismiss=false
screen/immersive_mode=true
screen/support_small=true
screen/support_normal=true
screen/support_large=true
screen/support_xlarge=true
user_data_backup/allow=false
command_line/extra_args=""
apk_expansion/enable=false
permissions/access_checkin_properties=false
permissions/access_coarse_location=false
permissions/access_fine_location=false
permissions/access_location_extra_commands=false
permissions/access_media_location=false
permissions/access_mock_location=false
permissions/access_network_state=false
permissions/access_surface_flinger=false
permissions/access_wifi_state=false
permissions/account_manager=false
permissions/add_voicemail=false
permissions/authenticate_accounts=false
permissions/battery_stats=false
permissions/bluetooth=false
permissions/bluetooth_admin=false
permissions/bluetooth_privileged=false
permissions/broadcast_package_removed=false
permissions/broadcast_sms=false
permissions/broadcast_sticky=false
permissions/broadcast_wap_push=false
permissions/call_phone=false
permissions/camera=false
permissions/change_network_state=false
permissions/change_wifi_multicast_state=false
permissions/change_wifi_state=false
permissions/clear_app_cache=false
permissions/clear_app_user_data=false
permissions/control_location_updates=false
permissions/delete_cache_files=false
permissions/delete_packages=false
permissions/device_power=false
permissions/diagnostic=false
permissions/disable_keyguard=false
permissions/expand_status_bar=false
permissions/factory_test=false
permissions/flashlight=false
permissions/get_accounts=false
permissions/get_package_size=false
permissions/get_tasks=false
permissions/get_top_activity_info=false
permissions/global_search=false
permissions/hardware_test=false
permissions/inject_events=false
permissions/install_location_provider=false
permissions/install_packages=false
permissions/instant_app=false
permissions/internal_system_window=false
permissions/internet=true
permissions/kill_background_processes=false
permissions/location_hardware=false
permissions/manage_accounts=false
permissions/manage_app_tokens=false
permissions/manage_documents=false
permissions/manage_external_storage=false
permissions/master_clear=false
permissions/media_content_control=false
permissions/modify_audio_settings=false
permissions/modify_phone_state=false
permissions/mount_format_filesystems=false
permissions/mount_unmount_filesystems=false
permissions/nfc=false
permissions/persistent_activity=false
permissions/post_notifications=false
permissions/process_outgoing_calls=false
permissions/read_calendar=false
permissions/read_call_log=false
permissions/read_contacts=false
permissions/read_external_storage=false
permissions/read_frame_buffer=false
permissions/read_history_bookmarks=false
permissions/read_input_state=false
permissions/read_logs=false
permissions/read_media_audio=false
permissions/read_media_images=false
permissions/read_media_video=false
permissions/read_phone_state=false
permissions/read_profile=false
permissions/read_sms=false
permissions/read_social_stream=false
permissions/read_sync_settings=false
permissions/read_sync_stats=false
permissions/read_user_dictionary=false
permissions/reboot=false
permissions/record_audio=false
permissions/reorder_tasks=false
permissions/restart_packages=false
permissions/send_respond_via_message=false
permissions/send_sms=false
permissions/set_animation_scale=false
permissions/set_debug_app=false
permissions/set_process_limit=false
permissions/set_time=false
permissions/set_time_zone=false
permissions/set_wallpaper=false
permissions/set_wallpaper_hints=false
permissions/signal_persistent_processes=false
permissions/status_bar=false
permissions/system_alert_window=false
permissions/transmit_ir=false
permissions/uninstall_shortcut=false
permissions/update_device_stats=false
permissions/use_sip=false
permissions/vibrate=false
permissions/wake_lock=false
permissions/write_apn_settings=false
permissions/write_calendar=false
permissions/write_call_log=false
permissions/write_contacts=false
permissions/write_external_storage=false
permissions/write_gservices=false
permissions/write_history_bookmarks=false
permissions/write_profile=false
permissions/write_secure_settings=false
permissions/write_settings=false
permissions/write_sync_settings=false
permissions/write_user_dictionary=false
keystore/debug=""
keystore/debug_user=""
keystore/debug_password=""
keystore/release=""
keystore/release_user=""
keystore/release_password=""
```
