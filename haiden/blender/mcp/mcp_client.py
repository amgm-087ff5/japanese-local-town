"""Minimal MCP stdio client: launches `mcp-for-blender` (ahujasid/blender-mcp
server) and calls a tool. The server forwards to the headless bridge socket.

usage: python mcp_client.py --server /path/to/venv/bin/mcp-for-blender list
       python mcp_client.py --server ... call get_scene_info '{}'
       python mcp_client.py --server ... call execute_blender_code '{"code":"..."}'
"""
import argparse, asyncio, json, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ap = argparse.ArgumentParser()
ap.add_argument("--server", required=True)
ap.add_argument("action", choices=["list", "call"])
ap.add_argument("tool", nargs="?")
ap.add_argument("args", nargs="?", default="{}")
a = ap.parse_args()

async def main():
    env = dict(os.environ, DISABLE_TELEMETRY="true", BLENDER_MCP_DISABLE_TELEMETRY="true")
    params = StdioServerParameters(command=a.server, args=[], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            if a.action == "list":
                for t in (await s.list_tools()).tools:
                    print(t.name)
            else:
                res = await s.call_tool(a.tool, json.loads(a.args))
                for c in res.content:
                    print(getattr(c, "text", c))
asyncio.run(main())
