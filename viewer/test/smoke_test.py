#!/usr/bin/env python3
"""GitHub Pages 相当の _site を一時ディレクトリに組み立て、ヘッドレス Chromium で表示確認する。

使い方:
  python3 viewer/test/smoke_test.py [--glb path/to/haiden_web.glb] [--out viewer/test/screenshots] [--keep]

_site 構成:
  index.html            <- viewer/quick.html
  app/index.html        <- viewer/index.html
  models/haiden_web.glb <- --glb / haiden/out/haiden_web.glb / viewer/test/test_shrine_draco.glb の順
  models/stats.json     <- haiden/out/stats.json があればそれ、無ければダミー
  renders/*             <- haiden/out/renders/ があればコピー
必要: pip の playwright(Chromium は PLAYWRIGHT_BROWSERS_PATH などで用意済みのもの)
"""
import argparse, functools, http.server, json, mimetypes, shutil, subprocess, sys, tarfile, tempfile, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIEWER = HERE.parent
REPO = VIEWER.parent


def build_site(dst: Path, glb: Path) -> None:
    (dst / 'app').mkdir(parents=True)
    (dst / 'models').mkdir()
    shutil.copy(VIEWER / 'quick.html', dst / 'index.html')
    shutil.copy(VIEWER / 'index.html', dst / 'app' / 'index.html')
    shutil.copy(glb, dst / 'models' / 'haiden_web.glb')
    out = REPO / 'haiden' / 'out'
    if (out / 'renders').is_dir():
        shutil.copytree(out / 'renders', dst / 'renders')
    if (out / 'stats.json').is_file():
        shutil.copy(out / 'stats.json', dst / 'models' / 'stats.json')
    else:
        # ダミー:テスト用のレンダ画像を1枚置く
        (dst / 'renders').mkdir(exist_ok=True)
        shot = HERE / 'screenshots' / 'desktop_plain.png'
        renders = []
        if shot.is_file():
            shutil.copy(shot, dst / 'renders' / 'dummy_front.png')
            renders = ['dummy_front.png']
        (dst / 'models' / 'stats.json').write_text(json.dumps({
            'triangles': 123456, 'objects': 321, 'materials': 12,
            'glb_bytes': glb.stat().st_size, 'generated': '2026-10-25T12:00', 'renders': renders,
        }))


def fetch_three(tmp: Path, ver: str) -> Path:
    """CDN に出られない環境用:npm から three を取得して展開する。"""
    subprocess.run(['npm', 'pack', f'three@{ver}', '--silent'], cwd=tmp, check=True, capture_output=True)
    with tarfile.open(tmp / f'three-{ver}.tgz') as t:
        t.extractall(tmp / 'three', filter='data')
    return tmp / 'three' / 'package'


def install_mock_cdn(ctx, pkg: Path, ver: str) -> None:
    prefix = f'https://cdn.jsdelivr.net/npm/three@{ver}/'

    def three(route):
        f = pkg / route.request.url[len(prefix):].split('?')[0]
        if f.is_file():
            ct = 'application/wasm' if f.suffix == '.wasm' else (mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
            if f.suffix == '.js':
                ct = 'text/javascript'
            route.fulfill(status=200, body=f.read_bytes(), headers={'content-type': ct, 'access-control-allow-origin': '*'})
        else:
            route.fulfill(status=404, body='not found')

    ctx.route(prefix + '**', three)
    ctx.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(status=200, body='', headers={'content-type': 'text/css', 'access-control-allow-origin': '*'}))
    ctx.route('https://fonts.gstatic.com/**', lambda r: r.fulfill(status=404, body=''))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb')
    ap.add_argument('--out', default=str(HERE / 'screenshots'))
    ap.add_argument('--prefix', default='site')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--mock-cdn', action='store_true', help='jsDelivr/Google Fonts をローカル(npm の three)で代替')
    a = ap.parse_args()
    cands = [a.glb] if a.glb else [REPO / 'haiden/out/haiden_web.glb', HERE / 'test_shrine_draco.glb']
    glb = next(Path(c) for c in cands if c and Path(c).is_file())
    print('GLB:', glb, glb.stat().st_size, 'bytes')

    tmp = Path(tempfile.mkdtemp(prefix='hakoniwa_site_'))
    site = tmp / '_site'
    build_site(site, glb)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ver = '0.170.0'
    pkg = fetch_three(tmp, ver) if a.mock_cdn else None

    from playwright.sync_api import sync_playwright
    ok = True
    pages = [('quick', '/'), ('app', '/app/?model=../models/haiden_web.glb'), ('app_auto', '/app/')]
    sizes = [('pc', 1280, 800, False), ('sp', 380, 760, True)]
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        for sname, w, h, mobile in sizes:
            for pname, path in pages:
                if pname == 'app_auto' and mobile:
                    continue
                ctx = br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
                if pkg:
                    install_mock_cdn(ctx, pkg, ver)
                pg = ctx.new_page()
                errors = []
                pg.on('console', lambda m, e=errors: m.type == 'error' and e.append(m.text))
                pg.on('pageerror', lambda ex, e=errors: e.append('pageerror: ' + str(ex)))
                pg.goto(base + path, wait_until='load')
                try:
                    pg.wait_for_function('window.viewerState && (window.viewerState.loaded || window.viewerState.error)', timeout=90000)
                except Exception as ex:  # noqa
                    errors.append('timeout: ' + str(ex).splitlines()[0])
                pg.wait_for_timeout(1500)
                st = pg.evaluate('window.viewerState')
                shot = out / f'{a.prefix}_{pname}_{sname}.png'
                pg.screenshot(path=str(shot))
                extra = ''
                if pname == 'quick':
                    extra = ' stats=%r renders=%d' % (pg.inner_text('#stats'), pg.locator('#renders img').count())
                good = bool(st and st.get('loaded')) and not st.get('error') and not errors
                ok &= good
                print(f"[{'OK' if good else 'NG'}] {sname} {path} tris={st and st.get('tris')} errors={errors}{extra} -> {shot}")
                ctx.close()
        br.close()
    srv.shutdown()
    if a.keep:
        print('site kept at', site)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
