"""What makes AMS2 treat a track as an OVAL, copied from the OFFICIAL ovals.

Source: `BOOTFLOW.bff` (the game's 263 TRDs) and `Daytona_Physics.bff` (its AIW), extracted from
the game (see `open_bff.py`). No `bpy`: it is used by `construir_paquete.py` (inside Blender, the
TRD) and `convertir_ac.py` (outside, the AIW).
"""

import math
import re

# 🔴 What the official OVALS have and the template (Meadowdale, a road course) does not, copied
# from `BOOTFLOW.bff/tracks/daytona/daytona.trd`.
# Declaration (Reflection schema) + value. ⚠️ `Track Type=Oval` WITHOUT a declared `Oval Type`
# leaves the track loading forever (measured): they go together or not at all.
TRD_OVALO_NUEVOS = [   # (name, type, value) — added if missing
    ("Oval Type", "U32", None),               # None = whichever type applies (see tipo_de_ovalo)
    ("AIDirtyAirBehaviourEnabled", "S32", "-1"),
    ("AIOvertakeInsideEnabled", "Bool", "false"),
    ("MaxPuddleDepthRoad", "F32", "0.04"),
    ("MaxPuddleDepthOffroad", "F32", "0.20"),
    ("MaxPuddleDepthDriven", "F32", "0.03"),
]
TRD_OVALO_VALORES = {   # already declared in the template: only the value changes
    "Track Type": "Oval",
    "TrackGradeFilter": "Oval",
    "PresetFilter": "Grade1Oval,SUSAG1,SUSAG2,SUSAG3",
    "RollingStartPoleSide": "0",
}


def tipo_de_ovalo(largo_m: float) -> int:
    """The `Oval Type` of the official ovals by length: 2 up to 3 km (Gateway 2,012,
    Jacarepaguá 3,000), 5 above that (Fontana, Indianapolis, Pocono). 6 is Daytona."""
    return 2 if largo_m <= 3000 else 5


def trd_de_ovalo(ruta: str, largo_m: float) -> list:
    """Turns the template's TRD into an OVAL one with what the official ones carry."""
    texto = open(ruta, encoding="utf-8", errors="ignore").read()
    tipo = str(tipo_de_ovalo(largo_m))
    hechos = []
    for nombre, t, valor in TRD_OVALO_NUEVOS:
        valor = tipo if valor is None else valor
        if f'<prop name="{nombre}" type=' not in texto:
            texto = re.sub(r'(\n(\s*)<prop name="Track Type" type="String" />)',
                           lambda m: m.group(1) + f'\n{m.group(2)}<prop name="{nombre}" type="{t}" />',
                           texto, count=1)
        if f'<prop name="{nombre}" data=' in texto:
            texto = re.sub(rf'(<prop name="{re.escape(nombre)}" data=")[^"]*(")',
                           lambda m: m.group(1) + valor + m.group(2), texto, count=1)
        else:
            texto = re.sub(r'(\n(\s*)<prop name="Track Type" data="[^"]*" />)',
                           lambda m: m.group(1) + f'\n{m.group(2)}<prop name="{nombre}" data="{valor}" />',
                           texto, count=1)
        hechos.append(f"{nombre}={valor}")
    for nombre, valor in TRD_OVALO_VALORES.items():
        texto, n = re.subn(rf'(<prop name="{re.escape(nombre)}" data=")[^"]*(")',
                           lambda m: m.group(1) + valor + m.group(2), texto, count=1)
        if n:
            hechos.append(f"{nombre}={valor}")
    open(ruta, "w", encoding="utf-8").write(texto)
    return hechos



# The AIW [Features] of an OFFICIAL oval (Daytona): OMTT's exporter writes `Oval` as yes/no (1)
# and a road course's anticipation distances (40/80/160), TWICE Daytona's: the AI looks twice as
# far ahead. `Oval` = the same `Oval Type` as in the TRD.
ANTICIPACION_OVALO = {"AnticipationDistMin": 20.0, "AnticipationDistOffRoad": 40.0,
                      "AnticipationDistWall": 80.0}


def largo_de_vuelta(aiw) -> float:
    ps = [w.pos for w in aiw.main_path] + [aiw.main_path[0].pos]
    return sum(math.dist(p, q) for p, q in zip(ps, ps[1:]))


def aiw_de_ovalo(ruta: str) -> list:
    """Rewrites the oval [Features] in an already exported AIW."""
    import aiw_read as A
    tipo = tipo_de_ovalo(largo_de_vuelta(A.parse(ruta)))
    texto = open(ruta, encoding="utf-8", errors="ignore").read()
    valores = {"Oval": str(tipo), **{k: f"{v:.6f}" for k, v in ANTICIPACION_OVALO.items()}}
    hechos = []
    for k, v in valores.items():
        texto, n = re.subn(rf"(?m)^({re.escape(k)}=).*$", lambda m: m.group(1) + v, texto, count=1)
        hechos.append(f"{k}={v}" if n else f"🔴 {k} is not in the AIW")
    open(ruta, "w", encoding="utf-8").write(texto)
    return hechos
