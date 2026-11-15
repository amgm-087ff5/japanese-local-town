# ゲームエンジン調査: 和風箱庭ゲーム(3D / Android / 縦横両対応)

- 調査日: 2026-11-14
- 担当: researcher
- 前提制約: 開発・ビルドはLinuxコンテナ(GUIなし、2コア/7GB、到達先はGitHub・apt・pip・npm・dl.google.com程度)とGitHub Actions無料 ubuntu-latest。人がエディタを触らず、AIがテキストファイルを書いて作る。
- 記号: 「要確認」= 出典で確認できなかった、または未調査。推測は推測と明記。

## 1. 結論

| エンジン | 判定 | 理由 |
| --- | --- | --- |
| Godot 4.7.x | 可 | テキスト中心の構成で、Android書き出しの経路がある。Android要件・APKサイズ・モバイルレンダラ制限は要確認。 |
| Unreal Engine 5.8 | 困難(実質不可) | Editorは公式にLinux対応と読めるが、推奨32GB RAM・Ubuntu 22.04・ソースビルド前提の記述が中心。2コア/7GBでは現実的でない見込み。 |
| Unity 6.3 LTS | 困難 | Linux EditorはUbuntuのみ。Personalのヘッドレス認証は2023年の報告で動作せず、現行手段は要確認。Proは$2,200/席/年。 |
| Defold / Bevy / O3DE / Flax | 未調査 | 本調査の範囲外。3D箱庭への適性は要確認(第7節)。 |

- 推奨: Godot 4.7系(本調査時点の最新安定は4.7.2)を継続。
- 暫定判断(Godot 4.7.2)を覆す事実は確認できなかった。ただし4.8の安定版公開状況は要確認。

## 2. Godot 4.7

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| 4.7 公開 | 2026年6月18日付の記事で「is out now」 | https://linuxiac.com/?p=214411 |
| 4.7.1 安定版 | 2026年7月14日 | https://godotengine.org/article/maintenance-release-godot-4-7-1/ |
| 4.7.2 安定版 | 2026年8月18日、57件の修正 | https://godotengine.org/article/maintenance-release-godot-4-7-2/ |
| 4.8 | 開発スナップショットへの言及のみ。安定版の日付は要確認 | 4.7.1記事 |
| ライセンス | MIT(本調査で出典未取得) | 要確認 |

4.7の主な新機能(本件に関係するもの):

| 分野 | 内容 | 出典 |
| --- | --- | --- |
| Android | 安定版のGodot Android Build Environmentで、端末上から書き出し・公開が可能 | linuxiac記事 |
| Android | ピクチャーインピクチャー、埋め込みウィンドウの移動・リサイズ | linuxiac記事 |
| Android(4.7.1) | オンスクリーンキーボードでのバックスペース修正(GH-119798) | 4.7.1記事 |
| レンダリング | HDR出力はWindows/macOS/iOS/visionOS/Linux(Wayland)。Androidの記載なし | linuxiac記事 |
| レンダリング | AreaLight3D(矩形光源、リアルタイム照明) | linuxiac記事 |
| 注意 | 破壊的変更あり。移行ガイドの確認を推奨 | linuxiac記事 |

未確認項目(要確認):

| 項目 | 状況 |
| --- | --- |
| Androidの最小/対象SDK、必要JDK版 | 公式ページ(docs.godotengine.org/en/4.7/.../exporting_for_android.html)は長すぎて要件節まで到達できず |
| Android最小APKサイズ | 未取得 |
| モバイルレンダラの制限(影、Glow、HDR等) | 4.7版の公式制限ページ未取得 |
| ヘッドレス書き出し(CLI)の手順 | 未取得 |
| Android 16KBページ対応 | 未確認 |

## 3. Unreal Engine 5.8 / UE6

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| UE 5.8 公開 | 2026年6月(公式記事の日付は2026-06-23) | https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available?lang=ja |
| 位置づけ | 公式記事は「UE5系の最後のメジャー版」と記載 | 同上 |
| UE6 | 早期アクセスは2027年末目標、正式版はその12〜18か月後(見出し・要旨ベース) | https://www.gamespark.jp/article/2026/06/18/168136.html 、https://www.gamer.ne.jp/news/202606230037/ |
| Android(5.8) | ワークステーション設定の自動化、ドキュメント更新、Remote appでのタッチ確認、cook高速化 | 公式記事 |

Android要件(UE 5.7版ページ):

| 項目 | 値 | 出典 |
| --- | --- | --- |
| 最小インストールSDK / コンパイル最低 / 推奨SDK / 既定の対象SDK | 26 / 35 / 35 / 35 | https://dev.epicgames.com/documentation/unreal-engine/android-development-requirements-for-unreal-engine |
| NDK / Build-tools / JDK | r27c / 35.0.1 / OpenJDK 21.0.3 | 同上 |

Linux(ホスト)関連:

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| Editor on Linux | 要件ページは「engine or editor」のLinux要件を記載。Ubuntu 22.04推奨 | https://dev.epicgames.com/documentation/unreal-engine/linux-development-requirements-for-unreal-engine?lang=zh-CN |
| ハードウェア推奨 | RAM 32GB推奨、GPU 8GB VRAM以上、CPUはクアッドコア2.5GHz以上 | 同上 |
| Linuxからのクロスコンパイル | Linux向けのクロスコンパイルはWindowsからのみ | 同上 |
| Linux上でのAndroid | 公式ページでは明記なし。UE5.6のソースビルド解説で「最低約500GBの空き容量、1TB NVMe推奨」(個人ブログ) | https://www.babaei.net/blog/build-unreal-engine-from-github-source-code-gnu-linux-with-android-support/ |
| Linux上のAndroid SDK | 2023年の報告でNDK r25bが必要(r25cでは失敗) | https://forums.unrealengine.com/t/ue5-build-for-headless-linux/1536853 |
| Epic配布バイナリのLinux版 | 要確認 | 要確認 |
| APKサイズ・ビルド時間・メモリ使用量 | 要確認 | 要確認 |

ライセンス(EULA):

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| ロイヤリティ | UE製品に帰属する生涯総収益のうち$1M超の部分に5% | https://www.unrealengine.com/en-US/license |
| Epic Games Store | 同ストアでの売上はロイヤリティ免除 | 同上 |
| 無料枠のソース | 「Access to the source code」を含むと記載 | 同上 |
| 他の商用利用者 | 12か月で$1M超の場合、席ごとのライセンス料$1,850/年 | 同上 |
| Epicアカウント連携・GitHub取得手順 | ページに記載なし | 要確認 |

## 4. Unity 6.x

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| 6.0 LTS | サポートは2026年10月まで(現時点で期限切れ) | https://unity.com/ja/releases/unity-6 |
| 6.3 LTS | サポートは2027年12月まで | 同上 |
| 6.4 | リリースの見出しのみ確認。日付は要確認 | 要確認 |
| Linux Editor | Ubuntuのみサポート。最終更新2026-10-03のドキュメント | https://docs.unity.com/en-us/engine/6000.3/manual/platform-specific/linux.md |
| Linux EditorからのAndroidビルド | 要確認 | 要確認 |

ライセンス・料金:

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| Personal | 無料。年間総収益+資金調達が$200,000以下が対象 | https://unity.com/ja/runtime-fee (機械翻訳。英語版は要確認) |
| Pro | $2,200/席/年(前払い)または$200/席/月。2026年1月12日から5%値上げ | 同上 |
| 手動アクティベーション(Personal) | 2023年の報告で、CIでの手動認証(.alf→.ulf)が動作しないとの報告 | https://discussions.unity.com/t/unity-no-longer-supports-manual-activation-of-personal-licenses/926760 |
| 現行のCI認証(Personal) | 公式(game.ci)ドキュメントを取得できず要確認 | 要確認 |
| CI secrets(Pro) | UNITY_LICENSE / UNITY_EMAIL / UNITY_PASSWORD / UNITY_SERIAL。ただし2021年の記事で、現行版は要確認 | https://zenn.dev/nikaera/articles/unity-gameci-github-actions?locale=en |

## 5. Google Play の最近の要件(ビルド関連)

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| 16KBページサイズ | 2025年11月1日から、Android 15+(API 35+)を対象とする新規・更新アプリは64bitデバイスで16KB対応必須 | https://developer.android.com/guide/practices/page-sizes |
| 対象の判断 | ネイティブコードを含むアプリが対象。Java/Kotlinのみなら対応済み | 同上 |
| ネイティブ.soの要件 | ELF LOADセグメントは2**14以上で整列、非圧縮ライブラリはzip 16KB整列 | 同上 |
| NDK | r28以上は既定で16KB整列。r27は追加フラグが必要 | 同上 |
| AGP | 8.5.1以上で非圧縮ライブラリを推奨 | 同上 |
| 対象API(2026年時点) | 公式の最新値は未確認。UE5.7版ページでは「Google Playは対象API 35を要求」と記載 | UE 5.7版Androidページ |
| Godot 4.7の16KB対応 | 要確認 | 要確認 |
| UE 5.8の16KB対応 | 要確認 | 要確認 |
| Unity 6の16KB対応 | 要確認 | 要確認 |

## 6. 利用状況の指標

- GitHubスター数、公式のエンジン別シェア(Steam、ゲームジャム、モバイル): 本調査では未取得。要確認。
- 参考値のみ: VoxBoosterの2026年8月22日付マーケティング記事(https://voxbooster.com/blog/game-engine-market-share-statistics-2026)は、Steamでの全ゲームのシェアとしてUnity 48.2%、Unreal 19.4%、新規インディタイトルのGodot 6.8%を挙げる。ただし出典は多くが総称で、元データの日付・手法も不明。判断の根拠には使わない。
- 同記事内のGodot 14.0%(インディ開発者の割合)は、対象の説明が不一致。要確認。

## 7. その他の候補(未調査)

| エンジン | 一般的な特徴(推測) | 判定 |
| --- | --- | --- |
| Defold | 軽量、2D・モバイル向けに強い。3D箱庭は情報が少ない | 要確認 |
| Bevy | Rust製のECS。エディタは未成熟と推測 | 要確認 |
| O3DE | 大規模向けで重い。Linux対応は要確認 | 要確認 |
| Flax | C#で3D対応。コミュニティは小規模と推測 | 要確認 |

## 8. 制約との照合

| 制約 | Godot 4.7 | UE 5.8 | Unity 6.3 |
| --- | --- | --- | --- |
| Linuxコンテナ(2コア/7GB) | 軽量と推測。要確認 | RAM 32GB推奨のため不適 | Editorは重いと推測。要確認 |
| GitHub Actions無料ランナー | 要確認 | ソースビルドは時間とディスクが不足する見込み | 認証方式が未確定 |
| 人がエディタを触らない | テキスト形式のシーン・スクリプトで構成可能と推測 | ソース・アセットのバイナリ依存が大きいと推測 | 同左 |
| Android SDK取得 | dl.google.comに到達可能なら可 | 同左 | 同左 |

## 9. 残課題(要確認)

1. Godot 4.7のAndroid要件(min/target SDK、JDK)、APKサイズ、モバイルレンダラの制限。
2. Godot 4.8の安定版の有無と日付。
3. UE on Linuxでのパッケージング可否(Epic公式の手順)、Epicアカウント連携・GitHub取得条件。
4. Unity Personal のCI認証の現行手順と、Linux EditorでのAndroidビルド可否。
5. 16KB対応の各エンジンの状況。2026年のGoogle Play対象API。
6. GitHubスター数などの公式な利用指標。
