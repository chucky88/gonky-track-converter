"""Reader for Assetto Corsa's `.kn5`: textures, materials and mesh tree.

    python3 kn5_read.py <file.kn5> [--volcar folder/]

Why it exists: an AMS1 track forces you to **guess**: which mesh collides comes from the `.scn`'s
`CollTarget` flags, and which surface each material is, from its name (`RDHI`, `GRASSA`…).
Assetto Corsa ships it **declared**: `surfaces.ini` states `IS_VALID_TRACK` and `IS_PITLANE` with
their friction, and the collision lives in a separate `.kn5`.

And the jump in content, measured on Mountain Peak (which is Charlotte under another name): 185 MB
of geometry against the 9.7 MB of the AMS1 version, and 1,470 racing line points against 463.

Format: `sc6969` header + version. From version 6 on there is an extra integer. Then the texture
table, the material table and a recursive node tree (1 = empty, 2 = mesh, 3 = animated mesh).
No dependencies: only `struct`.
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field


@dataclass
class Material:
    nombre: str
    shader: str
    mezcla_alfa: int = 0
    alfa_test: bool = False
    props: dict = field(default_factory=dict)
    vectores: dict = field(default_factory=dict)   # key -> raw (vec2, vec3, vec4)
    texturas: dict = field(default_factory=dict)   # slot -> texture name


@dataclass
class Malla:
    nombre: str
    material: int
    vertices: int
    indices: int
    padre: str = ""
    # Flags from the `.kn5` itself. They must be kept: the Charlotte by "13x" marks its physics
    # meshes (`1road_*`) as NOT RENDERABLE, and they carry the SAME material as the visible
    # asphalt (`vis_rd_*`). With both rendered, they z-fight on the same plane.
    visible: bool = True
    dibuja: bool = True
    lod_fuera: float = 0.0
    # only the counts are kept by default; with `con_geometria=True` the data is kept too
    pos: list = field(default_factory=list)
    nor: list = field(default_factory=list)
    uv: list = field(default_factory=list)
    caras: list = field(default_factory=list)


class Lector:
    def __init__(self, ruta):
        self.f = open(ruta, "rb")
        self.ruta = ruta

    def i(self):
        return struct.unpack("<i", self.f.read(4))[0]

    def u(self):
        return struct.unpack("<I", self.f.read(4))[0]

    def b(self):
        return self.f.read(1)[0]

    def fl(self):
        return struct.unpack("<f", self.f.read(4))[0]

    def s(self):
        n = self.i()
        return self.f.read(n).decode("utf-8", "replace")


# 🔴🔴 THE MIRROR, IN ONE SINGLE PLACE (symptom on track: you raced in the opposite direction to
# the real track). Assetto Corsa has the OPPOSITE HANDEDNESS to gMotor2. Same real track, two sources:
#
#   AMS1 Charlotte      signed area (x, z)  +382,135   turns left (the real one)
#   AC Mountain Peak    signed area (x, z)  −369,377   → in AMS2 it turned RIGHT
#
# Applying the AMS1 conversion to AC left the whole track MIRRORED, and consistent with itself:
# that is why the gates were green. ⚠️ The clue was in the faces, which came out with reversed
# winding: flipping them in `kn5_to_blender` fixed the symptom and left the world mirrored,
# because flipping the winding is exactly what a mirror does.
#
# Z is negated, not X: both fix the direction of travel, but only with Z do the pits end up on
# the same side of the oval as in AMS1's Charlotte (270° versus 290°; with X, 90°: the track
# turned around). With the mirror, AC ends up exactly like gMotor2 —positions AND winding—, so
# faces are reordered neither here nor in `kn5_to_blender`.
ESPEJO_Z = True


def _espejo(v):
    return (v[0], v[1], -v[2]) if ESPEJO_Z else v


def leer(ruta: str, con_geometria: bool = False, volcar_texturas: str | None = None):
    L = Lector(ruta)
    f = L.f
    magia = f.read(6)
    if magia != b"sc6969":
        raise ValueError(f"not a kn5: magic {magia!r}")
    version = L.i()
    if version > 5:
        L.i()                      # extra integer, no known use

    # --- textures ---------------------------------------------------------------------
    texturas = []
    for _ in range(L.i()):
        tipo = L.i()
        nombre = L.s()
        tam = L.i()
        if volcar_texturas:
            os.makedirs(volcar_texturas, exist_ok=True)
            datos = f.read(tam)
            with open(os.path.join(volcar_texturas, nombre), "wb") as g:
                g.write(datos)
        else:
            f.seek(tam, 1)
        texturas.append((nombre, tipo, tam))

    # --- materials --------------------------------------------------------------------
    materiales = []
    for _ in range(L.i()):
        m = Material(nombre=L.s(), shader=L.s(), mezcla_alfa=L.b(), alfa_test=bool(L.b()))
        L.i()                                  # depth mode
        for _ in range(L.i()):
            clave = L.s()
            valor = L.fl()
            # 🔴 After the scalar come a vec2, a vec3 and a vec4 (8 + 12 + 16 = 36 bytes), and they
            # must be READ: skipping them, the parameters the shader stores as vec2 come out as 0.
            # At Jarama `detailNMMult` is 25 (not 0) and the terrain's `multA` is 0.2 (not 0).
            # Source: AcTools (Kn5Material) and CSP's recreated shader (`multA` is a float2).
            v2 = struct.unpack("<2f", f.read(8))
            v3 = struct.unpack("<3f", f.read(12))
            v4 = struct.unpack("<4f", f.read(16))
            m.vectores[clave] = (v2, v3, v4)
            m.props[clave] = valor if (valor != 0.0 or not any(v2)) else v2[0]
        # ⚠️ No padding after it: slot name, index, texture name, and the next one starts. With
        # one extra byte the whole table goes out of alignment at the first material (checked
        # byte by byte).
        for _ in range(L.i()):
            slot = L.s()
            L.i()                              # sampler index
            m.texturas[slot] = L.s()
        materiales.append(m)

    # --- node tree --------------------------------------------------------------------
    mallas = []
    vacios = []

    IDENT = (1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0)

    def por(a, b):
        """a·b of row-major 4x4 matrices (AC/DirectX convention: v' = v·M)."""
        return tuple(sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
                     for r in range(4) for c in range(4))

    def aplicar(M, v, w=1.0):
        return tuple(v[0] * M[c] + v[1] * M[4 + c] + v[2] * M[8 + c] + w * M[12 + c]
                     for c in range(3))

    def nodo(padre="", M=IDENT):
        tipo = L.i()
        nombre = L.s()
        hijos = L.i()
        L.b()                                   # active
        propia = M
        if tipo == 1:
            # In Assetto Corsa the empties carry the grid and the pits: `AC_START_0..n`,
            # `AC_PIT_0..n`, `AC_HOTLAP_START_0`, `AC_TIME_0_L/R`… Keeping them means getting the
            # grid for FREE, instead of building it from the racing line as had to be done with
            # AMS1's Charlotte. The translation is in the last three values of the 4th row.
            local = struct.unpack("<16f", f.read(64))
            # 🔴 THE PARENTS' TRANSFORM. Taking only the node's own transform, meshes are placed
            # at their LOCAL coordinates: in the Charlotte by "13x" the 660 pit crew figures
            # (`ac_crew.kn5`) hang from offset nodes and ended up piled near the origin; the same
            # with the blimp and the Ferris wheel. Mountain Peak did not show it: everything
            # hangs from an identity node.
            m16 = propia = por(local, M)
            vacios.append((nombre, _espejo((m16[12], m16[13], m16[14])), m16))
        elif tipo in (2, 3):
            if tipo == 2:
                _sombras, visible, _transp = f.read(3)
                nv = L.u()
                if con_geometria:
                    crudo = f.read(nv * 44)
                else:
                    f.seek(nv * 44, 1)
                ni = L.u()
                if con_geometria:
                    idx = struct.unpack(f"<{ni}H", f.read(ni * 2))
                else:
                    f.seek(ni * 2, 1)
                mat = L.i()
                resto = f.read(29)              # layer, lodIn/Out, bounding sphere, renderable
                m = Malla(nombre=nombre, material=mat, vertices=nv, indices=ni, padre=padre,
                          visible=bool(visible), dibuja=bool(resto[28]),
                          lod_fuera=struct.unpack_from("<f", resto, 8)[0])
                if con_geometria:
                    identidad = M == IDENT
                    for k in range(nv):
                        o = k * 44
                        p = struct.unpack_from("<fff", crudo, o)
                        n = struct.unpack_from("<fff", crudo, o + 12)
                        if not identidad:
                            p = aplicar(M, p)
                            n = aplicar(M, n, 0.0)
                            ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1.0
                            n = (n[0] / ln, n[1] / ln, n[2] / ln)
                        m.pos.append(_espejo(p))
                        m.nor.append(_espejo(n))
                        m.uv.append(struct.unpack_from("<ff", crudo, o + 24))
                    # ⚠️ Faces are NOT reordered here (measured). After the mirror, AC has the
                    # SAME handedness and the same winding as gMotor2, and the axis conversion
                    # already handles them correctly. Flipping them "because a mirror flips the
                    # winding" adds a THIRD flip (mirror + this one + the axis conversion) and
                    # leaves the ground facing down: 50 faces up versus 98,342.
                    # Measured by the "ground faces up" gate.
                    m.caras = [tuple(idx[k:k + 3]) for k in range(0, ni - 2, 3)]
                mallas.append(m)
            else:
                # animated mesh: skipped entirely, a track does not use them for the layout
                f.seek(1, 1)
                for _ in range(L.i()):
                    L.s(); f.seek(64, 1)
                nv = L.u(); f.seek(nv * 44, 1)
                ni = L.u(); f.seek(ni * 2, 1)
                L.i(); f.seek(12, 1)
        for _ in range(hijos):
            nodo(nombre, propia)

    nodo()
    f.close()
    return {"version": version, "texturas": texturas, "materiales": materiales,
            "mallas": mallas, "vacios": vacios}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    volcar = argv[argv.index("--volcar") + 1] if "--volcar" in argv else None
    r = leer(argv[1], volcar_texturas=volcar)
    tex = r["texturas"]
    print(f"kn5 v{r['version']} · {len(tex)} textures ({sum(t[2] for t in tex)/1e6:.0f} MB) · "
          f"{len(r['materiales'])} materials · {len(r['mallas'])} meshes")
    print(f"  vertices: {sum(m.vertices for m in r['mallas']):,} · "
          f"triangles: {sum(m.indices for m in r['mallas'])//3:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
