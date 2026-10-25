# japanese-local-town 作業ルール

## サブエージェントのモデル割り当て（必須・使用制限対策）
- 原則すべてHaiku。Opusはモデリング等の難易度が非常に高い作業だけ。Sonnetは使わない（ユーザー指示 2026-10-25）。

| 作業 | モデル | エージェント定義 |
| --- | --- | --- |
| Web調査・資料まとめ・docs更新（versions/spec/progress/knowledge） | Haiku | `.claude/agents/researcher.md` |
| CI（.github/workflows）・ビューア（viewer/）・小〜中規模のコード | Haiku | `.claude/agents/dev.md` |
| Blenderモデリングなど難易度が非常に高い作業 | Opus | `.claude/agents/modeler.md` |

- Opusにはモデリング以外（調査・CI・docs・ビューア）を混ぜない。1つの依頼に複数種類が含まれる場合は、作業ごとに分けて別エージェントに出す。
- 統括（メイン）は設計・分担・git操作・確認だけを行い、実作業はしない。
- 起動後、`subagents/*.jsonl`（またはタスク出力）の `message.model` で実際のモデルを確認する。
- ユーザーが特定のモデルを指定した場合も、指定の対象作業（例: モデリング）以外には広げない。範囲が曖昧なら起動前に確認する。

## モデル作業の前に
- `haiden/docs/knowledge.md`（モデリング知識ノート）を必ず読む。
- 凍結版の扱いは `haiden/docs/versions.md`。
