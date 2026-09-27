#!/usr/bin/env python3
"""Joins several already-built layouts into ONE mod: one track with variants, like the official ones.

    python3 join_layouts.py <output.zip> --group Charlotte_Motor_Speedway \\
        <oval.zip>:charlottecms:Oval:1 <roval.zip>:charlotteroval:Roval:2 \\
        [--photo charlotteroval=resources/charlotte_roval_photo.jpg]

Like the official tracks: one venue with several variants. The game groups layouts by the TRD's
`Track Group` (the three COTA ones: `Circuit_of_the_Americas`) and names each one by
`Track_Variation`; `Order Override` sets the order. Each layout is still its own folder
(`Tracks/<nombre>`, its paks, its GUI): the packages are merged, geometry is NOT shared (that would
be a different pipeline), so the zip weighs the sum of all of them.

🔴 If two packages carry the SAME path with different content, one would silently overwrite the
other on install: it stops. Identical paths with identical content are written once.
"""
import hashlib
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _trd(texto, grupo, variante, orden):
    for clave, valor in (("Track Group", grupo), ("Track_Variation", variante), ("Order Override", str(orden))):
        texto, n = re.subn(r'(<prop name="' + re.escape(clave) + r'" data=")[^"]*(")',
                           lambda m: m.group(1) + valor + m.group(2), texto)
        if n != 1:
            raise SystemExit(f'🔴 the TRD does not have «{clave}» exactly once (it has {n})')
    return texto


def main(argv):
    # English names → internal ones (the Spanish ones still work)
    argv = [{'--group': '--grupo', '--photo': '--foto'}.get(a, a) for a in argv]
    if len(argv) < 4 or '--grupo' not in argv:
        print(__doc__)
        return 2
    salida = argv[1]
    grupo = argv[argv.index('--grupo') + 1]
    fotos = {}
    if '--foto' in argv:
        for f in argv[argv.index('--foto') + 1].split(','):
            nombre, ruta = f.split('=', 1)
            fotos[nombre] = ruta
    trazados = [a for a in argv[2:] if a.count(':') == 3 and a.endswith(tuple('0123456789'))]
    vistos, hechos, creditos = {}, [], []
    tmp = salida + '.tmp'
    with zipfile.ZipFile(tmp, 'w') as out:
        for t in trazados:
            ruta, nombre, variante, orden = t.rsplit(':', 3)
            z = zipfile.ZipFile(ruta)
            for info in z.infolist():
                if info.is_dir():
                    continue
                if info.filename in ('CREDITS.txt', 'CREDITOS.txt'):        # one per layout → merged into one (creditos.py)
                    c = z.read(info).decode('utf-8')
                    if c not in creditos:
                        creditos.append(c)
                    continue
                datos = z.read(info)
                if info.filename.lower().endswith(f'tracks/{nombre}/{nombre}.trd'.lower()):
                    datos = _trd(datos.decode('utf-8'), grupo, variante, orden).encode('utf-8')
                    hechos.append(f'{nombre}: Track Group={grupo} · Track_Variation={variante} · Order Override={orden}')
                if nombre in fotos and info.filename.lower().endswith(f'gui/trackphotos/{nombre}.dds'.lower()):
                    import generar_mapa as GM
                    dds = salida + f'.{nombre}.dds'
                    ok, err = GM.a_dds(fotos[nombre], dds, compresion='dxt1', tamano=GM.FOTO)
                    if not ok:
                        raise SystemExit(f'🔴 the photo of {nombre}: {err}')
                    datos = open(dds, 'rb').read()
                    os.remove(dds)
                    hechos.append(f'{nombre}: menu photo ← {fotos[nombre]}')
                h = hashlib.sha256(datos).hexdigest()
                if info.filename in vistos:
                    if vistos[info.filename] != h:
                        os.remove(tmp)
                        raise SystemExit(f'🔴 {info.filename} comes in two packages with different content')
                    continue
                vistos[info.filename] = h
                out.writestr(info, datos, compress_type=info.compress_type)
        if creditos:
            out.writestr('CREDITS.txt', ('\n' + '-' * 72 + '\n\n').join(creditos), compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, salida)
    for h in hechos:
        print('  ' + h)
    print(f'✅ {salida}: {len(vistos)} files from {len(trazados)} layouts · {os.path.getsize(salida) / 2**20:.0f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
