#!/usr/bin/env python3
"""仕上げ切替テスト用の小さな GLB を作る(依存なし)。

  python3 viewer/test/make_finish_glbs.py [OUT_DIR]

- test_shrine_variants.glb … test_shrine.glb に KHR_materials_variants を付けたもの。
  バリアント名は「丹塗」「白木」「古色」(stats.json の finishes の name で対応付ける想定のテスト)。
- test_shrine_<id>.glb(nuri / shiraki / koshoku)… 仕上げ別 GLB 方式(separate)のダミー。
"""
import json, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'test_shrine.glb'

# (id, 表示名, 丹塗部の色, 木部の色)
FINISHES = [
    ('nuri', '丹塗', None, None),
    ('shiraki', '白木', [0.80, 0.64, 0.44, 1], [0.74, 0.58, 0.40, 1]),
    ('koshoku', '古色', [0.30, 0.15, 0.08, 1], [0.24, 0.16, 0.10, 1]),
]
SHU, WOOD = 0, 1   # test_shrine.glb のマテリアル番号(Shu_Vermilion, Wood)


def read_glb(p: Path):
    b = p.read_bytes()
    assert b[:4] == b'glTF'
    n = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    binchunk = b''
    if len(rest) >= 8:
        ln, typ = struct.unpack('<II', rest[:8])
        assert typ == 0x004E4942
        binchunk = rest[8:8 + ln]
    return j, binchunk


def write_glb(p: Path, j: dict, binchunk: bytes) -> None:
    js = json.dumps(j, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    js += b' ' * (-len(js) % 4)
    binchunk += b'\0' * (-len(binchunk) % 4)
    body = struct.pack('<II', len(js), 0x4E4F534A) + js
    if binchunk:
        body += struct.pack('<II', len(binchunk), 0x004E4942) + binchunk
    p.write_bytes(b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body)


def tinted(mat: dict, name: str, color) -> dict:
    m = json.loads(json.dumps(mat))
    m['name'] = name
    m.setdefault('pbrMetallicRoughness', {})['baseColorFactor'] = color
    m['pbrMetallicRoughness']['roughnessFactor'] = 0.82
    return m


def make_variants(dst: Path) -> Path:
    j, b = read_glb(SRC)
    mats = j['materials']
    extra = {}   # (finish index, base material) -> new material index
    for fi, (fid, _, shu, wood) in enumerate(FINISHES):
        for base, col in ((SHU, shu), (WOOD, wood)):
            if col:
                extra[(fi, base)] = len(mats)
                mats.append(tinted(mats[base], f'{mats[base]["name"]}_{fid}', col))
    for mesh in j['meshes']:
        for prim in mesh['primitives']:
            base = prim.get('material')
            if base not in (SHU, WOOD):
                continue
            mappings = {}
            for fi in range(len(FINISHES)):
                mappings.setdefault(extra.get((fi, base), base), []).append(fi)
            prim.setdefault('extensions', {})['KHR_materials_variants'] = {
                'mappings': [{'material': m, 'variants': vs} for m, vs in mappings.items()]}
    j.setdefault('extensions', {})['KHR_materials_variants'] = {'variants': [{'name': n} for _, n, _, _ in FINISHES]}
    j['extensionsUsed'] = sorted(set(j.get('extensionsUsed', [])) | {'KHR_materials_variants'})
    out = dst / 'test_shrine_variants.glb'
    write_glb(out, j, b)
    return out


def make_separate(dst: Path) -> dict:
    outs = {}
    for fid, _, shu, wood in FINISHES:
        j, b = read_glb(SRC)
        for base, col in ((SHU, shu), (WOOD, wood)):
            if col:
                j['materials'][base] = tinted(j['materials'][base], j['materials'][base]['name'] + '_' + fid, col)
        outs[fid] = dst / f'test_shrine_{fid}.glb'
        write_glb(outs[fid], j, b)
    return outs


if __name__ == '__main__':
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    d.mkdir(parents=True, exist_ok=True)
    print(make_variants(d))
    for p in make_separate(d).values():
        print(p)
