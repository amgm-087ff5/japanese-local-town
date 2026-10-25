#!/usr/bin/env python3
"""GitHub Pages 相当の _site を一時ディレクトリに組み立て、ヘッドレス Chromium で表示確認する。

使い方:
  python3 viewer/test/smoke_test.py [--mock-cdn] [--layout both|variants|legacy] [--real] [--out DIR] [--keep]

レイアウト:
  variants(新契約・複数モデル)
    index.html / app/index.html
    models/index.json                 [{"id":"A-2",...},{"id":"A-1",...}](先頭が最新)
    models/<id>/haiden_web.glb, models/<id>/stats.json
    renders/<id>/*.png
    models/haiden_web.glb, models/stats.json(後方互換:最新のコピー)
  legacy(従来・単一モデル)
    models/haiden_web.glb, models/stats.json, renders/*

GLB の出どころ:
  既定      … viewer/test/test_shrine_draco.glb を A-2、test_shrine.glb を A-1 として代用(stats/レンダはダミー生成)
  --real    … haiden/out/<id>/haiden_web.glb(+stats.json, renders/)があればそれを使う。
              A-1 は haiden/out/A-1/ が無ければ haiden/out/ 直下(従来の出力)を使う。無いものはテスト GLB で代用。
必要: pip の playwright(Chromium は PLAYWRIGHT_BROWSERS_PATH などで用意済みのもの)、ダミー画像生成に Pillow(任意)
"""
import argparse, functools, http.server, json, mimetypes, shutil, subprocess, sys, tarfile, tempfile, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIEWER = HERE.parent
REPO = VIEWER.parent
OUT = REPO / 'haiden' / 'out'
IDS = [('A-2', '拝殿A-2 ver1', 'test_shrine_draco.glb'), ('A-1', '拝殿A-1 ver1', 'test_shrine.glb')]


def dummy_png(path: Path, text: str, color) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    im = Image.new('RGB', (320, 200), color)
    d = ImageDraw.Draw(im)
    d.rectangle([8, 8, 311, 191], outline=(255, 255, 255), width=3)
    d.text((20, 20), text, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return True


def real_source(mid: str):
    """haiden/out から実物を探す。(glb, stats.json or None, renders dir or None)"""
    for d in [OUT / mid] + ([OUT] if mid == 'A-1' else []):
        if (d / 'haiden_web.glb').is_file():
            return d / 'haiden_web.glb', (d / 'stats.json') if (d / 'stats.json').is_file() else None, (d / 'renders') if (d / 'renders').is_dir() else None
    return None


def build_variants(dst: Path, real: bool) -> list:
    index = []
    for i, (mid, name, test_glb) in enumerate(IDS):
        mdir = dst / 'models' / mid
        mdir.mkdir(parents=True)
        src = real_source(mid) if real else None
        if src:
            glb, stats_p, rdir = src
            stats = json.loads(stats_p.read_text()) if stats_p else {}
        else:
            glb, rdir = HERE / test_glb, None
            stats = {'triangles': 120000 + i * 3456, 'objects': 300 + i, 'materials': 12 + i, 'generated': f'2026-10-2{5 - i}T12:00'}
        shutil.copy(glb, mdir / 'haiden_web.glb')
        renders = []
        if rdir:
            for r in stats.get('renders') or [{'src': p.name} for p in sorted(rdir.glob('*.png'))]:
                s0 = r if isinstance(r, str) else r.get('src', '')
                f = rdir / Path(s0).name
                if f.is_file():
                    (dst / 'renders' / mid).mkdir(parents=True, exist_ok=True)
                    shutil.copy(f, dst / 'renders' / mid / f.name)
                    renders.append({'src': f'renders/{mid}/{f.name}', 'title': (r.get('title') if isinstance(r, dict) else None) or f.stem})
        else:
            col = [(160, 60, 40), (40, 90, 130)][i % 2]
            for v, t in [('front', '正面'), ('side', '側面')][: 2 - i]:
                if dummy_png(dst / 'renders' / mid / f'{v}.png', f'{mid} {v}', col):
                    renders.append({'src': f'renders/{mid}/{v}.png', 'title': t})
        stats.update({'id': mid, 'name': name, 'version': 'ver1', 'glb_bytes': glb.stat().st_size, 'renders': renders})
        (mdir / 'stats.json').write_text(json.dumps(stats, ensure_ascii=False))
        index.append({'id': mid, 'name': name, 'glb': f'models/{mid}/haiden_web.glb', 'stats': f'models/{mid}/stats.json', '_src': str(glb)})
    (dst / 'models' / 'index.json').write_text(json.dumps([{k: v for k, v in e.items() if k != '_src'} for e in index], ensure_ascii=False))
    # 後方互換
    shutil.copy(dst / 'models' / IDS[0][0] / 'haiden_web.glb', dst / 'models' / 'haiden_web.glb')
    shutil.copy(dst / 'models' / IDS[0][0] / 'stats.json', dst / 'models' / 'stats.json')
    return index


def build_legacy(dst: Path, glb: Path) -> None:
    (dst / 'models').mkdir(parents=True, exist_ok=True)
    shutil.copy(glb, dst / 'models' / 'haiden_web.glb')
    renders = []
    if dummy_png(dst / 'renders' / 'dummy_front.png', 'legacy front', (90, 90, 60)):
        renders = ['dummy_front.png']
    (dst / 'models' / 'stats.json').write_text(json.dumps({
        'triangles': 123456, 'objects': 321, 'materials': 12,
        'glb_bytes': glb.stat().st_size, 'generated': '2026-10-25T12:00', 'renders': renders,
    }))


def build_site(dst: Path, layout: str, real: bool):
    (dst / 'app').mkdir(parents=True)
    shutil.copy(VIEWER / 'quick.html', dst / 'index.html')
    shutil.copy(VIEWER / 'index.html', dst / 'app' / 'index.html')
    if layout == 'variants':
        return build_variants(dst, real)
    build_legacy(dst, HERE / 'test_shrine_draco.glb')
    return None


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
    log_requests = None  # list で GLB リクエストを記録

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.log_requests is not None and self.path.endswith('.glb'):
            self.log_requests.append(self.path)
        return super().do_GET()


class Runner:
    def __init__(self, br, base, out, prefix, pkg, ver, reqlog, allow_404=()):
        self.br, self.base, self.out, self.prefix, self.pkg, self.ver, self.reqlog = br, base, out, prefix, pkg, ver, reqlog
        self.allow_404 = allow_404   # 想定内の 404(legacy の models/index.json 探索)
        self.ok = True

    def open(self, path, mobile, w, h):
        ctx = self.br.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
        if self.pkg:
            install_mock_cdn(ctx, self.pkg, self.ver)
        pg = ctx.new_page()
        errors = []
        def on_console(m, e=errors):
            if m.type != 'error':
                return
            url = (m.location or {}).get('url', '')
            if '404' in m.text and any(url.endswith(x) for x in self.allow_404):
                return
            e.append(m.text + (f' ({url})' if url else ''))
        pg.on('console', on_console)
        pg.on('pageerror', lambda ex, e=errors: e.append('pageerror: ' + str(ex)))
        self.reqlog.clear()
        pg.goto(self.base + path, wait_until='load')
        self.wait_loaded(pg, errors)
        return ctx, pg, errors

    @staticmethod
    def wait_loaded(pg, errors, cond='true'):
        try:
            pg.wait_for_function(f'window.viewerState && (window.viewerState.error || (window.viewerState.loaded && ({cond})))', timeout=90000)
        except Exception as ex:  # noqa
            errors.append('timeout: ' + str(ex).splitlines()[0])
        pg.wait_for_timeout(1200)

    def report(self, good, label, shot, detail=''):
        self.ok &= bool(good)
        print(f"[{'OK' if good else 'NG'}] {label} {detail} -> {shot}")

    def shot(self, pg, name):
        p = self.out / f'{self.prefix}_{name}.png'
        # quick 版の自動回転は止めて静止画で撮る(実物の重い GLB だと SwiftShader で毎フレーム描画が追いつかない)
        if pg.locator('#btnRotate[aria-pressed="true"]').count() and pg.locator('#tabs, #variants').count():
            pg.click('#btnRotate'); pg.wait_for_timeout(800)
        pg.screenshot(path=str(p), timeout=180000)
        return p


def run_legacy(r: Runner):
    for sname, w, h, mobile in [('pc', 1280, 800, False), ('sp', 380, 760, True)]:
        for pname, path in [('quick', '/'), ('app', '/app/')]:
            ctx, pg, errors = r.open(path, mobile, w, h)
            st = pg.evaluate('window.viewerState')
            shot = r.shot(pg, f'legacy_{pname}_{sname}')
            extra = ''
            good = bool(st and st.get('loaded')) and not st.get('error') and not errors
            if pname == 'quick':
                tabs_hidden = pg.locator('#variants').is_hidden()
                extra = 'tabs_hidden=%s stats=%r renders=%d' % (tabs_hidden, pg.inner_text('#stats'), pg.locator('#renders img').count())
                good &= tabs_hidden
            r.report(good, f'legacy {sname} {path}', shot, f'tris={st and st.get("tris")} errors={errors} {extra}')
            ctx.close()


def settle(pg, tries=40):
    """OrbitControls の減衰(慣性)が収まるまで待ってカメラ値を返す。"""
    prev = pg.evaluate('viewerDebug.cam()')
    for _ in range(tries):
        pg.wait_for_timeout(500)
        cur = pg.evaluate('viewerDebug.cam()')
        if max(abs(a - b) for a, b in zip(prev, cur)) < 1e-3:
            return cur
        prev = cur
    return prev


def run_variants(r: Runner, index):
    names = {e['id']: e['name'] for e in index}
    # 1) 表示確認(PC / 380px)
    for sname, w, h, mobile in [('pc', 1280, 800, False), ('sp', 380, 760, True)]:
        for pname, path, want in [('quick', '/', 'A-2'), ('quick_m_A-1', '/?m=A-1', 'A-1'), ('app', '/app/', 'A-2'), ('app_m_A-1', '/app/?m=A-1', 'A-1')]:
            ctx, pg, errors = r.open(path, mobile, w, h)
            st = pg.evaluate('window.viewerState')
            glbs = list(r.reqlog)
            shot = r.shot(pg, f'{pname}_{sname}')
            good = bool(st and st.get('loaded')) and not st.get('error') and not errors
            if pname.startswith('quick'):
                sel = pg.locator('.tab[aria-selected="true"]').inner_text()
                rsrc = pg.eval_on_selector_all('#renders img', 'els => els.map(e => e.getAttribute("src"))')
                ok_r = all(f'renders/{want}/' in s for s in rsrc)
                # 表示中のモデルだけを取得していること(プリロードなし)
                ok_net = glbs == [f'/models/{want}/haiden_web.glb']
                good &= st.get('current') == want and sel == names[want] and ok_r and ok_net
                detail = f'current={st.get("current")} tab={sel!r} renders={rsrc} glb_requests={glbs} stats={pg.inner_text("#stats")!r} app_link={pg.get_attribute("#appLink", "href")}'
            else:
                good &= st.get('name') == names[want] and st.get('samples') == [e['id'] for e in index]
                detail = f'name={st.get("name")!r} samples={st.get("samples")} glb_requests={glbs}'
            r.report(good, f'variants {sname} {path}', shot, f'tris={st.get("tris")} errors={errors} {detail}')
            ctx.close()

    # 2) quick: タブ切替(同じ視点 ON → 視点維持 / OFF → ホーム視点)、URL 更新、メモリ解放
    for sname, w, h, mobile in [('pc', 1280, 800, False), ('sp', 380, 760, True)]:
        ctx, pg, errors = r.open('/?m=A-1', mobile, w, h)
        mem_a1 = pg.evaluate('viewerDebug.mem()')
        ctx.close()
        ctx, pg, errors = r.open('/', mobile, w, h)
        mem_a2 = pg.evaluate('viewerDebug.mem()')
        # 自動回転を止め、ホームとは違う視点にする(ドラッグの慣性は低 fps だと長く残るので直接設定)
        pg.click('#btnRotate')
        c = pg.evaluate('viewerDebug.cam()')
        pg.evaluate('(c) => viewerDebug.setCam(c)', [-c[2] * 0.8, c[1] * 0.6, c[0] * 0.8, c[3], c[4] * 0.9, c[5]])
        cam0 = settle(pg)
        pg.click('.tab[data-id="A-1"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-1"')
        cam1 = pg.evaluate('viewerDebug.cam()')
        mem1 = pg.evaluate('viewerDebug.mem()')
        url1 = pg.url
        rsrc = pg.eval_on_selector_all('#renders img', 'els => els.map(e => e.getAttribute("src"))')
        shot = r.shot(pg, f'switch_A-1_{sname}')
        # OrbitControls の減衰が低 fps でゆっくり残るので、距離の 2% 以内なら「維持」とみなす
        dist = sum((cam0[i] - cam0[i + 3]) ** 2 for i in range(3)) ** 0.5
        same = max(abs(a - b) for a, b in zip(cam0, cam1)) < dist * 0.02
        good = same and url1.endswith('?m=A-1') and mem1 == mem_a1 and all('renders/A-1/' in s for s in rsrc) and not errors
        r.report(good, f'switch {sname} A-2→A-1 (同じ視点 ON)', shot,
                 f'cam_kept={same} url={url1} mem_before={mem_a2} mem_after={mem1} mem_fresh_A1={mem_a1} renders={rsrc} errors={errors}')
        # OFF にして戻す → ホーム視点に戻る
        pg.click('#chkSame')
        pg.click('.tab[data-id="A-2"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-2"')
        cam2 = pg.evaluate('viewerDebug.cam()')
        mem2 = pg.evaluate('viewerDebug.mem()')
        moved = max(abs(a - b) for a, b in zip(cam1, cam2)) > dist * 0.05
        shot = r.shot(pg, f'switch_back_A-2_{sname}')
        good = (moved or mobile) and pg.url.endswith('?m=A-2') and mem2 == mem_a2 and not errors
        r.report(good, f'switch {sname} A-1→A-2 (同じ視点 OFF)', shot, f'cam_reset={moved} url={pg.url} mem={mem2} errors={errors}')
        # 連打(読込中の切替)でも最後の選択が残り、エラーにならない
        pg.click('#chkSame')
        pg.click('.tab[data-id="A-1"]'); pg.click('.tab[data-id="A-2"]'); pg.click('.tab[data-id="A-1"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-1"')
        mem3 = pg.evaluate('viewerDebug.mem()')
        good = pg.evaluate('viewerState.current') == 'A-1' and mem3 == mem_a1 and not errors
        r.report(good, f'switch {sname} 連打', '-', f'mem={mem3} errors={errors}')
        ctx.close()

    # 3) app: サンプルメニューから開く
    for sname, w, h, mobile in [('pc', 1280, 800, False), ('sp', 380, 760, True)]:
        ctx, pg, errors = r.open('/app/', mobile, w, h)
        pg.click('#btnSamples')
        pg.wait_for_timeout(300)
        shot_menu = r.shot(pg, f'app_menu_{sname}')
        pg.click('#sampleMenu button[data-id="A-1"]')
        r.wait_loaded(pg, errors, f'window.viewerState.name === {json.dumps(names["A-1"])}')
        shot = r.shot(pg, f'app_menu_A-1_{sname}')
        st = pg.evaluate('window.viewerState')
        good = st.get('name') == names['A-1'] and pg.url.endswith('/app/?m=A-1') and pg.locator('#sampleMenu').is_hidden() and not errors
        r.report(good, f'app {sname} サンプル→A-1', f'{shot_menu}, {shot}', f'name={st.get("name")!r} url={pg.url} errors={errors}')
        ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(HERE / 'screenshots'))
    ap.add_argument('--prefix', default='site')
    ap.add_argument('--layout', choices=['both', 'variants', 'legacy'], default='both')
    ap.add_argument('--real', action='store_true', help='haiden/out の実物 GLB を使う(あるものだけ)')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--mock-cdn', action='store_true', help='jsDelivr/Google Fonts をローカル(npm の three)で代替')
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix='hakoniwa_site_'))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ver = '0.170.0'
    pkg = fetch_three(tmp, ver) if a.mock_cdn else None
    layouts = ['variants', 'legacy'] if a.layout == 'both' else [a.layout]

    from playwright.sync_api import sync_playwright
    ok = True
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        for layout in layouts:
            site = tmp / f'_site_{layout}'
            index = build_site(site, layout, a.real)
            if index:
                for e in index:
                    print(f"model {e['id']}: {e['_src']}")
            reqlog = []
            handler = type('H', (QuietHandler,), {'log_requests': reqlog})
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(handler, directory=str(site)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            r = Runner(br, f'http://127.0.0.1:{srv.server_address[1]}', out, a.prefix, pkg, ver, reqlog,
                       allow_404=('/models/index.json',) if layout == 'legacy' else ())
            print(f'== {layout} ==')
            run_variants(r, index) if layout == 'variants' else run_legacy(r)
            ok &= r.ok
            srv.shutdown()
        br.close()
    if a.keep:
        print('site kept at', tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print('RESULT:', 'OK' if ok else 'NG')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
