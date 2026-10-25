#!/usr/bin/env python3
"""GitHub Pages 相当の _site を一時ディレクトリに組み立て、ヘッドレス Chromium で表示確認する。

使い方:
  python3 viewer/test/smoke_test.py [--mock-cdn] [--layout both|variants|legacy] [--real] [--out DIR] [--keep]

レイアウト:
  variants(新契約・複数モデル+仕上げ)
    index.html / app/index.html     (<meta name="build"> の __BUILD__ を TEST_BUILD に置換 = CI と同じ)
    models/index.json               A-2(ver2・仕上げ KHR_materials_variants)/ A-2v1(仕上げ別 GLB)/ A-1(仕上げなし)
    models/<id>/haiden_web.glb, models/<id>/stats.json, renders/<id>/*.png
    models/haiden_web.glb, models/stats.json(後方互換:最新のコピー)
  legacy(従来・単一モデル。__BUILD__ は置換しない → ?v= が付かないこと)
    models/haiden_web.glb, models/stats.json, renders/*

GLB の出どころ:
  既定      … test_shrine*.glb と make_finish_glbs.py で作る仕上げ付き GLB(stats/レンダはダミー生成)
  --real    … haiden/out/<id>/haiden_web.glb(+stats.json, renders/, 仕上げ別 GLB)があればそれを使う。無いものはテスト GLB で代用。
必要: pip の playwright(Chromium は PLAYWRIGHT_BROWSERS_PATH などで用意済みのもの)、ダミー画像生成に Pillow(任意)
"""
import argparse, functools, http.server, json, math, mimetypes, shutil, subprocess, sys, tarfile, tempfile, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIEWER = HERE.parent
REPO = VIEWER.parent
OUT = REPO / 'haiden' / 'out'
sys.path.insert(0, str(HERE))
import make_finish_glbs as mf  # noqa: E402

TEST_BUILD = 'testbuild123'
FINISHES = [{'id': fid, 'name': name} for fid, name, _, _ in mf.FINISHES]
# (id, name, 仕上げ方式)
IDS = [('A-2', '拝殿A-2 ver2', 'khr_variants'), ('A-2v1', '拝殿A-2 ver1', 'separate'), ('A-1', '拝殿A-1 ver1', None)]
SIZES = [('pc', 1280, 800, False), ('sp', 390, 844, True)]


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
    """haiden/out から実物を探す。(dir, glb, stats.json or None, renders dir or None)"""
    for d in [OUT / mid] + ([OUT] if mid == 'A-1' else []):
        if (d / 'haiden_web.glb').is_file():
            return d, d / 'haiden_web.glb', (d / 'stats.json') if (d / 'stats.json').is_file() else None, (d / 'renders') if (d / 'renders').is_dir() else None
    return None


def build_variants(dst: Path, real: bool, gen: Path) -> list:
    variants_glb = mf.make_variants(gen)
    sep = mf.make_separate(gen)
    index = []
    for i, (mid, name, mode) in enumerate(IDS):
        mdir = dst / 'models' / mid
        mdir.mkdir(parents=True)
        src = real_source(mid) if real else None
        entry = {'id': mid, 'name': name, 'glb': f'models/{mid}/haiden_web.glb', 'stats': f'models/{mid}/stats.json'}
        rdir = None
        if src:
            sdir, glb, stats_p, rdir = src
            stats = json.loads(stats_p.read_text()) if stats_p else {}
            name = entry['name'] = stats.get('name', name)
            shutil.copy(glb, mdir / 'haiden_web.glb')
            for f in stats.get('finishes') or []:   # 仕上げ別 GLB(実物)
                if isinstance(f, dict) and f.get('glb') and (sdir / Path(f['glb']).name).is_file():
                    shutil.copy(sdir / Path(f['glb']).name, mdir / Path(f['glb']).name)
                    f['glb'] = f'models/{mid}/{Path(f["glb"]).name}'
            if stats.get('finishes'):
                entry['finishes'] = stats['finishes']
                entry['finish_mode'] = stats.get('finish_mode')
        else:
            stats = {'triangles': 120000 + i * 3456, 'objects': 300 + i, 'materials': 12 + i, 'generated': f'2026-10-2{5 - i}T12:00'}
            if mode == 'khr_variants':
                glb = variants_glb
                stats.update(finishes=FINISHES, finish_mode=mode)
                entry.update(finishes=FINISHES, finish_mode=mode)   # index.json にも載せる
            elif mode == 'separate':
                glb = sep['nuri']
                fl = []
                for f in FINISHES:   # stats.json にだけ載せる(index.json には無い場合のテスト)
                    p = entry['glb'] if f['id'] == 'nuri' else f'models/{mid}/haiden_web_{f["id"]}.glb'
                    shutil.copy(sep[f['id']], dst / p)
                    fl.append({**f, 'glb': p})
                stats.update(finishes=fl, finish_mode=mode)
            else:
                glb = HERE / 'test_shrine_draco.glb'
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
        elif not src:
            col = [(160, 60, 40), (40, 90, 130), (60, 110, 60)][i % 3]
            for vv, t in [('front', '正面'), ('side', '側面'), ('top', '上')][: 3 - i]:
                if dummy_png(dst / 'renders' / mid / f'{vv}.png', f'{mid} {vv}', col):
                    renders.append({'src': f'renders/{mid}/{vv}.png', 'title': t})
        stats.update({'id': mid, 'name': name, 'glb_bytes': (mdir / 'haiden_web.glb').stat().st_size, 'renders': renders})
        (mdir / 'stats.json').write_text(json.dumps(stats, ensure_ascii=False))
        entry['_src'] = str(src[1] if src else glb)
        entry['_mode'] = (stats.get('finish_mode') or ('separate' if any(isinstance(f, dict) and f.get('glb') for f in stats.get('finishes') or []) else 'khr_variants')) if stats.get('finishes') else None
        index.append(entry)
    (dst / 'models' / 'index.json').write_text(json.dumps([{k: v for k, v in e.items() if not k.startswith('_')} for e in index], ensure_ascii=False))
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


def build_site(dst: Path, layout: str, real: bool, gen: Path):
    (dst / 'app').mkdir(parents=True)
    shutil.copy(VIEWER / 'quick.html', dst / 'index.html')
    shutil.copy(VIEWER / 'index.html', dst / 'app' / 'index.html')
    if layout == 'variants':
        # CI と同じ置換(sed -i "s/__BUILD__/<sha>/g")
        for p in (dst / 'index.html', dst / 'app' / 'index.html'):
            p.write_text(p.read_text(encoding='utf-8').replace('__BUILD__', TEST_BUILD), encoding='utf-8')
        return build_variants(dst, real, gen)
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
    log_requests = None  # list でリクエストパスを記録

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.log_requests is not None:
            self.log_requests.append(self.path)
        return super().do_GET()


class Runner:
    def __init__(self, br, base, out, prefix, pkg, ver, reqlog, allow_404=()):
        self.br, self.base, self.out, self.prefix, self.pkg, self.ver, self.reqlog = br, base, out, prefix, pkg, ver, reqlog
        self.allow_404 = allow_404   # 想定内の 404(legacy の models/index.json 探索)
        self.ok = True
        self.n_ok = self.n_ng = 0

    def glbs(self):
        return [p for p in self.reqlog if p.split('?')[0].endswith('.glb')]

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
            if '404' in m.text and any(url.split('?')[0].endswith(x) for x in self.allow_404):
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
        if good:
            self.n_ok += 1
        else:
            self.n_ng += 1
        print(f"[{'OK' if good else 'NG'}] {label} {detail} -> {shot}")

    def shot(self, pg, name, stop_rotate=True):
        p = self.out / f'{self.prefix}_{name}.png'
        # quick 版の自動回転は止めて静止画で撮る(実物の重い GLB だと SwiftShader で毎フレーム描画が追いつかない)
        if stop_rotate and pg.locator('#btnRotate[aria-pressed="true"]').count() and pg.locator('#tabs').count():
            pg.click('#btnRotate'); pg.wait_for_timeout(800)
        pg.screenshot(path=str(p), timeout=180000)
        return p


def fit_check(pg, tol=2.0, need_fill=True):
    """モデルのボックスが、UI(上の情報パネル/下のボタン等)を除いた領域に収まっているか。"""
    b = pg.evaluate('viewerDebug.bounds()')
    if not b:
        return False, 'no bounds'
    i = b['ins']
    good = b['x0'] >= i['l'] - tol and b['x1'] <= b['w'] - i['r'] + tol and b['y0'] >= i['t'] - tol and b['y1'] <= b['h'] - i['b'] + tol
    # 小さくなりすぎない(使える幅か高さの 70% 以上を使う。自動回転で全方位に収める分の余裕を許容)
    fill = max((b['x1'] - b['x0']) / (b['w'] - i['l'] - i['r']), (b['y1'] - b['y0']) / (b['h'] - i['t'] - i['b']))
    return good and (fill > 0.7 or not need_fill), 'box=[%.0f,%.0f..%.0f,%.0f] area=[%.0f,%.0f..%.0f,%.0f] fill=%.2f' % (
        b['x0'], b['y0'], b['x1'], b['y1'], i['l'], i['t'], b['w'] - i['r'], b['h'] - i['b'], fill)


def no_hscroll(pg):
    return pg.evaluate('''() => {
        const t = document.getElementById('titleBox') || document.querySelector('.topbar');
        const r = t.getBoundingClientRect();
        return document.documentElement.scrollWidth <= innerWidth && r.right <= innerWidth + 0.5 && r.left >= 0;
    }''')


def run_legacy(r: Runner):
    for sname, w, h, mobile in SIZES:
        for pname, path in [('quick', '/'), ('app', '/app/')]:
            ctx, pg, errors = r.open(path, mobile, w, h)
            st = pg.evaluate('window.viewerState')
            reqs = [p for p in r.reqlog if p.split('?')[0].endswith(('.glb', '.json', '.png'))]
            fit_ok, fit_d = fit_check(pg)
            shot = r.shot(pg, f'legacy_{pname}_{sname}')
            good = bool(st and st.get('loaded')) and not st.get('error') and not errors and fit_ok
            # build 未置換 → ?v= なし
            good &= st.get('build') == '' and not any('v=' in p for p in reqs)
            extra = f'build={st.get("build")!r} reqs={reqs} fit={fit_d}'
            if pname == 'quick':
                tabs_hidden = pg.locator('#tabs').is_hidden() and pg.locator('#finish').is_hidden()
                extra += ' tabs_hidden=%s stats=%r renders=%d' % (tabs_hidden, pg.inner_text('#stats'), pg.locator('#renders img').count())
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


def cam_close(a, b, frac=0.02):
    dist = sum((a[i] - a[i + 3]) ** 2 for i in range(3)) ** 0.5
    return max(abs(x - y) for x, y in zip(a, b)) < dist * frac


def run_variants(r: Runner, index, real: bool):
    names = {e['id']: e['name'] for e in index}
    modes = {e['id']: e['_mode'] for e in index}
    first = index[0]['id']
    vq = f'?v={TEST_BUILD}'
    fin_ids = lambda mid: [f['id'] for f in FINISHES] if modes[mid] else []   # noqa: E731
    # 実物 GLB は SwiftShader では重い(数百万△)ので PC 幅だけ
    sizes = SIZES[:1] if real else SIZES

    # 1) 表示確認(PC / 390x844 縦長)
    pages = [('quick', '/', first, None), ('quick_m_A-1', '/?m=A-1', 'A-1', None), ('quick_f_koshoku', '/?f=koshoku', first, 'koshoku'),
             ('app', '/app/', first, None), ('app_m_A-1', '/app/?m=A-1', 'A-1', None), ('app_f_koshoku', '/app/?f=koshoku', first, 'koshoku')]
    for sname, w, h, mobile in sizes:
        for pname, path, want, wf in pages:
            if real and wf and not modes[want]:
                continue
            ctx, pg, errors = r.open(path, mobile, w, h)
            st = pg.evaluate('window.viewerState')
            glbs = r.glbs()
            jsons = [p for p in r.reqlog if p.split('?')[0].endswith(('.json', '.png'))]
            fit_ok, fit_d = fit_check(pg)
            # 実物 GLB は SwiftShader だと回転描画が重いので止めてから撮る(フィットは回転前に確認済み)
            shot = r.shot(pg, f'{pname}_{sname}')
            good = bool(st and st.get('loaded')) and not st.get('error') and not errors and fit_ok and no_hscroll(pg)
            good &= st.get('build') == TEST_BUILD and all(p.endswith(vq) for p in glbs + jsons)   # キャッシュ回避クエリ
            want_f = wf or (fin_ids(want)[0] if fin_ids(want) else None)
            good &= st.get('finish') == want_f and st.get('finishes') == fin_ids(want)
            if wf and modes[want] == 'khr_variants':
                good &= st.get('variant') == dict((f['id'], f['name']) for f in FINISHES)[wf] and f'f={wf}' in pg.url
            if pname.startswith('quick'):
                sel = pg.locator('.tab[aria-selected="true"]').inner_text()
                rsrc = pg.eval_on_selector_all('#renders img', 'els => els.map(e => e.getAttribute("src"))')
                ok_r = all(f'renders/{want}/' in s and s.endswith(vq) for s in rsrc)
                ok_net = glbs == [f'/models/{want}/haiden_web.glb{vq}']   # 表示中のモデルだけを取得(プリロードなし)
                fin_vis = pg.locator('#finish').is_visible()
                good &= st.get('current') == want and sel == names[want] and ok_r and ok_net and fin_vis == bool(modes[want])
                detail = f'current={st.get("current")} tab={sel!r} finish={st.get("finish")} variant={st.get("variant")} glb={glbs} renders={len(rsrc)} app_link={pg.get_attribute("#appLink", "href")}'
            else:
                good &= st.get('name') == names[want] and st.get('samples') == [e['id'] for e in index]
                good &= pg.locator('#finish').is_visible() == bool(modes[want])
                detail = f'name={st.get("name")!r} finish={st.get("finish")} variant={st.get("variant")} glb={glbs}'
            r.report(good, f'variants {sname} {path}', shot, f'tris={st.get("tris")} errors={errors} fit={fit_d} {detail}')
            ctx.close()

    # 2) 自動回転中も全体が収まる(縦長・横長):ホーム視点のまま方位を 15° 刻みで一周
    for sname, w, h, mobile in sizes + ([] if real else [('sp_land', 844, 390, True)]):
        ctx, pg, errors = r.open('/', mobile, w, h)
        worst = []
        for k in range(24):
            pg.evaluate(f'viewerDebug.rotate({math.pi * 2 / 24})')
            ok, d = fit_check(pg, need_fill=False)
            if not ok:
                worst.append((k * 15, d))
        shot = r.shot(pg, f'rotate_fit_{sname}', stop_rotate=False)
        r.report(not worst and not errors, f'rotate-fit {sname} {w}x{h}', shot, f'fails={worst[:3]} errors={errors}')
        ctx.close()

    # 3) quick: タブ切替(同じ視点 ON → 視点維持 / OFF → ホーム視点)、URL 更新、メモリ解放
    for sname, w, h, mobile in sizes:
        ctx, pg, errors = r.open('/?m=A-1', mobile, w, h)
        mem_a1 = pg.evaluate('viewerDebug.mem()')
        ctx.close()
        ctx, pg, errors = r.open('/', mobile, w, h)
        mem_a2 = pg.evaluate('viewerDebug.mem()')
        pg.click('#btnRotate')
        c = pg.evaluate('viewerDebug.cam()')
        pg.evaluate('(c) => viewerDebug.setCam(c)', [-c[2] * 0.8, c[1] * 0.6, c[0] * 0.8, c[3], c[4] * 0.9, c[5]])
        if pg.locator('#btnMore').is_visible():   # スマホは詳細(同じ視点で切替)を開く
            pg.click('#btnMore')
        cam0 = settle(pg)
        pg.click('.tab[data-id="A-1"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-1"')
        cam1 = pg.evaluate('viewerDebug.cam()')
        mem1 = pg.evaluate('viewerDebug.mem()')
        url1 = pg.url
        rsrc = pg.eval_on_selector_all('#renders img', 'els => els.map(e => e.getAttribute("src"))')
        shot = r.shot(pg, f'switch_A-1_{sname}')
        same = cam_close(cam0, cam1)
        good = same and url1.endswith('?m=A-1') and mem1['geometries'] == mem_a1['geometries'] and all('renders/A-1/' in s for s in rsrc) \
            and pg.locator('#finish').is_hidden() and not errors
        r.report(good, f'switch {sname} {first}→A-1 (同じ視点 ON)', shot,
                 f'cam_kept={same} url={url1} mem_before={mem_a2} mem_after={mem1} mem_fresh_A1={mem_a1} errors={errors}')
        pg.click('#chkSame')
        pg.click(f'.tab[data-id="{first}"]')
        r.wait_loaded(pg, errors, f'window.viewerState.current === "{first}"')
        cam2 = pg.evaluate('viewerDebug.cam()')
        mem2 = pg.evaluate('viewerDebug.mem()')
        moved = not cam_close(cam1, cam2, 0.05)
        shot = r.shot(pg, f'switch_back_{first}_{sname}')
        good = moved and pg.url.endswith(f'?m={first}') and mem2['geometries'] == mem_a2['geometries'] and not errors
        r.report(good, f'switch {sname} A-1→{first} (同じ視点 OFF)', shot, f'cam_reset={moved} url={pg.url} mem={mem2} errors={errors}')
        if real:   # 実物では読込中の連打はメインスレッドが詰まりクリック待ちが時間切れになるので省略
            ctx.close()
            continue
        pg.click('#chkSame')
        pg.click('.tab[data-id="A-1"]'); pg.click(f'.tab[data-id="{first}"]'); pg.click('.tab[data-id="A-1"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-1"')
        mem3 = pg.evaluate('viewerDebug.mem()')
        good = pg.evaluate('viewerState.current') == 'A-1' and mem3 == mem_a1 and not errors
        r.report(good, f'switch {sname} 連打', '-', f'mem={mem3} errors={errors}')
        ctx.close()

    if real and not any(modes.values()):
        return
    # 4) quick: 仕上げ切替(KHR_materials_variants → 仕上げ別 GLB → 仕上げなし → 戻る)
    for sname, w, h, mobile in sizes:
        ctx, pg, errors = r.open('/', mobile, w, h)
        pg.click('#btnRotate')
        cam0 = settle(pg)
        r.reqlog.clear()
        pg.click('#finSeg button[data-id="shiraki"]')
        pg.wait_for_timeout(600)
        st = pg.evaluate('window.viewerState')
        mats = pg.evaluate('viewerDebug.mats()')
        shot = r.shot(pg, f'finish_shiraki_{sname}')
        good = st['finish'] == 'shiraki' and st.get('variant') == '白木' and 'f=shiraki' in pg.url and not r.glbs() \
            and any(m.endswith('_shiraki') for m in mats) and cam_close(cam0, pg.evaluate('viewerDebug.cam()')) and not errors
        good &= pg.get_attribute('#appLink', 'href').endswith('&f=shiraki')
        r.report(good, f'finish {sname} khr 丹塗→白木', shot, f'finish={st["finish"]} variant={st.get("variant")} mats={mats} glb={r.glbs()} url={pg.url} errors={errors}')

        sep_id = next((e['id'] for e in index if e['_mode'] == 'separate'), None)
        if sep_id:
            r.reqlog.clear()
            pg.click(f'.tab[data-id="{sep_id}"]')
            r.wait_loaded(pg, errors, f'window.viewerState.current === "{sep_id}"')
            st = pg.evaluate('window.viewerState')
            mats = pg.evaluate('viewerDebug.mats()')
            # 同じ仕上げ(白木)を維持し、最初から白木の GLB だけを取得
            good = st['finish'] == 'shiraki' and st['finishMode'] == 'separate' and r.glbs() == [f'/models/{sep_id}/haiden_web_shiraki.glb{vq}'] \
                and any(m.endswith('_shiraki') for m in mats) and 'f=shiraki' in pg.url and not errors
            shot = r.shot(pg, f'finish_sep_shiraki_{sname}')
            r.report(good, f'finish {sname} {first}→{sep_id} 白木維持(separate)', shot, f'finish={st["finish"]} glb={r.glbs()} mats={mats} errors={errors}')
            cam0 = settle(pg)
            r.reqlog.clear()
            pg.click('#finSeg button[data-id="koshoku"]')
            r.wait_loaded(pg, errors, 'window.viewerState.finish === "koshoku" && !document.querySelector("#finSeg [aria-busy]")')
            mats = pg.evaluate('viewerDebug.mats()')
            good = r.glbs() == [f'/models/{sep_id}/haiden_web_koshoku.glb{vq}'] and any(m.endswith('_koshoku') for m in mats) \
                and cam_close(cam0, pg.evaluate('viewerDebug.cam()')) and 'f=koshoku' in pg.url and not errors
            shot = r.shot(pg, f'finish_sep_koshoku_{sname}')
            r.report(good, f'finish {sname} separate 白木→古色(視点維持)', shot, f'glb={r.glbs()} mats={mats} url={pg.url} errors={errors}')

        pg.click('.tab[data-id="A-1"]')
        r.wait_loaded(pg, errors, 'window.viewerState.current === "A-1"')
        st = pg.evaluate('window.viewerState')
        good = st['finish'] is None and pg.locator('#finish').is_hidden() and 'f=' not in pg.url and not errors
        r.report(good, f'finish {sname} →A-1 仕上げ非表示', '-', f'url={pg.url} errors={errors}')
        pg.click(f'.tab[data-id="{first}"]')
        r.wait_loaded(pg, errors, f'window.viewerState.current === "{first}"')
        st = pg.evaluate('window.viewerState')
        want = 'koshoku' if sep_id else 'shiraki'
        good = st['finish'] == want and st.get('variant') == {'koshoku': '古色', 'shiraki': '白木'}[want] and f'f={want}' in pg.url and not errors
        shot = r.shot(pg, f'finish_back_{first}_{sname}')
        r.report(good, f'finish {sname} →{first} 仕上げ復帰', shot, f'finish={st["finish"]} variant={st.get("variant")} url={pg.url} errors={errors}')
        ctx.close()

    # 5) app: サンプルメニュー・仕上げ
    for sname, w, h, mobile in sizes:
        ctx, pg, errors = r.open('/app/', mobile, w, h)
        pg.click('#btnSamples')
        pg.wait_for_timeout(300)
        shot_menu = r.shot(pg, f'app_menu_{sname}')
        pg.click('#sampleMenu button[data-id="A-1"]')
        r.wait_loaded(pg, errors, f'window.viewerState.name === {json.dumps(names["A-1"])}')
        shot = r.shot(pg, f'app_menu_A-1_{sname}')
        st = pg.evaluate('window.viewerState')
        good = st.get('name') == names['A-1'] and pg.url.endswith('/app/?m=A-1') and pg.locator('#sampleMenu').is_hidden() and pg.locator('#finish').is_hidden() and not errors
        r.report(good, f'app {sname} サンプル→A-1', f'{shot_menu}, {shot}', f'name={st.get("name")!r} url={pg.url} errors={errors}')
        if any(modes.values()):
            pg.click('#btnSamples'); pg.wait_for_timeout(200)
            pg.click(f'#sampleMenu button[data-id="{first}"]')
            r.wait_loaded(pg, errors, f'window.viewerState.name === {json.dumps(names[first])} && window.viewerState.finish')
            pg.click('#finSeg button[data-id="shiraki"]')
            pg.wait_for_timeout(500)
            st = pg.evaluate('window.viewerState')
            mats = pg.evaluate('viewerDebug.mats()')
            shot = r.shot(pg, f'app_finish_shiraki_{sname}')
            good = st['finish'] == 'shiraki' and st.get('variant') == '白木' and any(m.endswith('_shiraki') for m in mats) and 'f=shiraki' in pg.url and not errors
            r.report(good, f'app {sname} 仕上げ→白木', shot, f'finish={st["finish"]} variant={st.get("variant")} url={pg.url} errors={errors}')
            sep_id = next((e['id'] for e in index if e['_mode'] == 'separate'), None)
            if sep_id:
                r.reqlog.clear()
                pg.click('#btnSamples'); pg.wait_for_timeout(200)
                pg.click(f'#sampleMenu button[data-id="{sep_id}"]')
                r.wait_loaded(pg, errors, f'window.viewerState.name === {json.dumps(names[sep_id])} && window.viewerState.finish')
                st = pg.evaluate('window.viewerState')
                mats = pg.evaluate('viewerDebug.mats()')
                good = st['finish'] == 'shiraki' and r.glbs() == [f'/models/{sep_id}/haiden_web_shiraki.glb{vq}'] and any(m.endswith('_shiraki') for m in mats) and not errors
                shot = r.shot(pg, f'app_finish_sep_{sname}')
                r.report(good, f'app {sname} {sep_id} 白木維持(separate)', shot, f'finish={st["finish"]} glb={r.glbs()} errors={errors}')
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
    gen = tmp / 'gen'; gen.mkdir()

    from playwright.sync_api import sync_playwright
    ok = True
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        for layout in layouts:
            site = tmp / f'_site_{layout}'
            index = build_site(site, layout, a.real, gen)
            if index:
                for e in index:
                    print(f"model {e['id']}: {e['_src']} finish_mode={e['_mode']}")
            reqlog = []
            handler = type('H', (QuietHandler,), {'log_requests': reqlog})
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(handler, directory=str(site)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            r = Runner(br, f'http://127.0.0.1:{srv.server_address[1]}', out, a.prefix, pkg, ver, reqlog,
                       allow_404=('/models/index.json',) if layout == 'legacy' else ())
            print(f'== {layout} ==')
            run_variants(r, index, a.real) if layout == 'variants' else run_legacy(r)
            print(f'-- {layout}: OK {r.n_ok} / NG {r.n_ng}')
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
