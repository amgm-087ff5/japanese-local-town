# Blender MCP(ヘッドレス)

ahujasid/blender-mcp のアドオンは `blender -b`(bpy)では起動を拒否する(`bpy.app.timers` が背景モードで回らないため)。
`headless_bridge.py` はアドオンを読み込み、同じ TCP ソケット(localhost:9876)を開いて、メインスレッドのループで `_drain_command_queue()` を直接回す。

## 手順(確認済み 2026-10-25, bpy 5.2.3)
```bash
git clone --depth 1 https://github.com/ahujasid/blender-mcp.git /tmp/blender-mcp
python3 -m venv /tmp/mcpvenv && /tmp/mcpvenv/bin/pip install /tmp/blender-mcp   # mcp-for-blender + mcp SDK

# 1) ブリッジ起動(任意で .blend を開く)
python3 haiden/blender/mcp/headless_bridge.py --addon /tmp/blender-mcp/addon.py \
    --blend haiden/out/haiden.blend --timeout 600 &

# 2) MCP クライアント(stdio)経由でツール呼び出し
/tmp/mcpvenv/bin/python haiden/blender/mcp/mcp_client.py --server /tmp/mcpvenv/bin/mcp-for-blender list
/tmp/mcpvenv/bin/python haiden/blender/mcp/mcp_client.py --server /tmp/mcpvenv/bin/mcp-for-blender call get_scene_info '{}'
/tmp/mcpvenv/bin/python haiden/blender/mcp/mcp_client.py --server /tmp/mcpvenv/bin/mcp-for-blender \
    call execute_blender_code '{"code":"import bpy; print(len(bpy.data.objects))"}'
```
ソケット直叩きも可: `{"type":"get_scene_info","params":{}}` を JSON で送る。

## 制約
- `get_viewport_screenshot` などGUI依存ツールは不可。レンダは `execute_blender_code` で `bpy.ops.render.render` を呼ぶ。
- 1コマンドは同期実行(長いレンダ中は他コマンドがブロック)。
- 公式 lab/blender_mcp(projects.blender.org)はこの環境のネットワーク許可外で未検証。
- モデル生成本体は再現性のため `build_haiden.py`(CLI)で行い、MCPはシーン検査用途。

## A-2(本瓦葺)の検査(2026-10-25)
```bash
python3 haiden/blender/mcp/headless_bridge.py --addon /tmp/blender-mcp/addon.py --blend haiden/out/A-2/haiden.blend --timeout 900 &
python3 -c 'import json;print(json.dumps({"code":open("haiden/blender/mcp/inspect_kawara.py").read()}))' > /tmp/args.json
/tmp/mcpvenv/bin/python haiden/blender/mcp/mcp_client.py --server /tmp/mcpvenv/bin/mcp-for-blender call execute_blender_code "$(cat /tmp/args.json)"
```
出力 `INSPECT_JSON {...}`: 瓦の枚数、浮き(>0.10m)・めり込み(<-0.03m)の件数、オブジェクト別tris、地面下オブジェクト。結果は haiden/docs/progress.md。
