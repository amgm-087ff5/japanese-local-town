"""Headless bridge for ahujasid/blender-mcp addon.

The addon's BlenderMCPServer.start() refuses to run when bpy.app.background is
True because bpy.app.timers never fire in background mode. This bridge loads the
addon module, opens the same TCP socket (default localhost:9876), and drains the
command queue from a plain loop on the main thread instead of a timer.

usage: python3 headless_bridge.py --addon /path/to/blender-mcp/addon.py [--blend file.blend] [--port 9876]
"""
import argparse, importlib.util, socket, threading, time, sys
import bpy

ap = argparse.ArgumentParser()
ap.add_argument("--addon", required=True)
ap.add_argument("--blend")
ap.add_argument("--port", type=int, default=9876)
ap.add_argument("--timeout", type=float, default=1800, help="auto-exit seconds")
a = ap.parse_args()

if a.blend:
    bpy.ops.wm.open_mainfile(filepath=a.blend)

spec = importlib.util.spec_from_file_location("blender_mcp_addon", a.addon)
mod = importlib.util.module_from_spec(spec)
sys.modules["blender_mcp_addon"] = mod
spec.loader.exec_module(mod)
try:
    mod.register()
except Exception as e:  # UI classes may fail in background; core still usable
    print("register warning:", e)

srv = mod.BlenderMCPServer(host="localhost", port=a.port)
srv.running = True
srv.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.socket.bind((srv.host, srv.port))
srv.socket.listen(5)
srv.server_thread = threading.Thread(target=srv._server_loop, daemon=True)
srv.server_thread.start()
print(f"HEADLESS_BRIDGE_READY localhost:{a.port}", flush=True)

t0 = time.time()
try:
    while srv.running and time.time() - t0 < a.timeout:
        srv._drain_command_queue()   # main-thread execution of queued commands
        time.sleep(0.05)
finally:
    srv.running = False
    srv.socket.close()
