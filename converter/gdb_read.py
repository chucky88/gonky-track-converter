"""Reader for AMS1's .gdb (the track's info sheet) and its translation to OMTT options.

The `.aiw` carries the geometry; the `.gdb` carries what the track IS. Without it, OMTT's exporter
writes `Oval=0` **on an oval** — and raises no error: the track loads, can be driven, and the AI
behaves as if it were a normal road course.

No `bpy`: it runs and is tested outside Blender.
"""

from __future__ import annotations

import re

_KV = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9 ]*?)\s*=\s*(.*?)\s*(?://.*)?$")


def parse(path: str) -> dict[str, str]:
    with open(path, "r", encoding="latin-1") as fh:
        return parse_text(fh.read())


def parse_text(text: str) -> dict[str, str]:
    """.gdb keys in lowercase and without spaces: `Max Vehicles` -> `max_vehicles`."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or s in ("{", "}"):
            continue
        m = _KV.match(line)
        if m:
            out[m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()
    return out


def es_oval(gdb: dict[str, str]) -> bool:
    """`TrackType = Speedway Oval`. "oval", "speedway" and "superspeedway" are accepted too."""
    tipo = gdb.get("tracktype", "").lower()
    return any(p in tipo for p in ("oval", "speedway"))


def longitud_m(gdb: dict[str, str]) -> float | None:
    """`Length = 1.5 miles` -> metres. Accepts miles, km and metres."""
    raw = gdb.get("length", "").lower()
    m = re.search(r"([-+]?\d*\.?\d+)", raw)
    if not m:
        return None
    v = float(m.group(1))
    if "mile" in raw or "mi" == raw.strip()[-2:]:
        return v * 1609.344
    if "km" in raw:
        return v * 1000.0
    return v


def max_vehiculos(gdb: dict[str, str]) -> int | None:
    try:
        return int(gdb["max_vehicles"])
    except (KeyError, ValueError):
        return None


def opciones_omtt(gdb: dict[str, str]) -> dict:
    """What has to be written into `scene.aiw_properties.track_features`."""
    return {
        "oval": es_oval(gdb),
        "nombre": gdb.get("trackname") or gdb.get("eventname"),
        "localidad": gdb.get("location"),
        "longitud_m": longitud_m(gdb),
        "max_vehiculos": max_vehiculos(gdb),
    }


MESES = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
         "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}


def fecha_de_carrera(gdb: dict):
    """`RaceDate = August 11` -> (8, 11). None if missing or not understood.

    🔴 The TRD's date came from Meadowdale (20 June 1963) while the right one was sitting right
    here. It is not cosmetic: the game uses it for the sun position and the length of the day.
    """
    import re

    v = (gdb or {}).get("racedate", "")
    m = re.match(r"\s*([A-Za-z]+)\s+(\d{1,2})", str(v))
    if not m:
        return None
    mes = MESES.get(m.group(1).lower())
    return (mes, int(m.group(2))) if mes else None


def limite_de_boxes(gdb: dict):
    """The pit lane speed limit in km/h, from the track itself. `RacePitKPH` takes precedence."""
    for k in ("racepitkph", "normalpitkph"):
        v = (gdb or {}).get(k)
        if v:
            try:
                return float(str(v).split()[0])
            except ValueError:
                pass
    return None


def maximo_de_coches(gdb: dict):
    """`Max Vehicles` from the .gdb: how many cars the track allows.

    ⚠️ The key is **`max_vehicles`**, with an underscore: that is how `parse_text` normalises
    `Max Vehicles`. Reading `maxvehicles` (a key that does not exist), Charlotte lost 3 grid slots
    (40 instead of 43) without any warning.
    """
    return max_vehiculos(gdb or {})


def pais(gdb: dict):
    """`Location = Concord, North Carolina` -> "USA".

    ⚠️ The TRD has TWO fields and they are not the same: `Track_Location` is the place (the city)
    and `Location` is the COUNTRY — all four reference tracks put a country there ("USA", "US"),
    and so do the docs. Putting the city in both is a mistake.
    """
    v = str((gdb or {}).get("location", "")).lower()
    ESTADOS = ("carolina", "virginia", "california", "texas", "alabama", "ohio", "indiana",
               "michigan", "wisconsin", "illinois", "arizona", "pennsylvania", "new york",
               "georgia", "florida", "kansas", "iowa", "nevada", "delaware", "tennessee",
               "new hampshire", "missouri", "kentucky", "maryland", "connecticut")
    if any(e in v for e in ESTADOS) or "usa" in v or "u.s.a" in v:
        return "USA"
    return None


# 🔴 Geographic coordinates per track. rFactor's `.gdb` **does not carry them**: its
# `Latitude = 50` is a sun parameter, not a real latitude (Charlotte is at 35.35).
#
# ⚠️ They cannot be hard-coded in `construir_paquete.py` with one track's values: that is the same
# bug as the TRD inheriting Meadowdale's (1,000 km away), rewritten with a different constant, and
# any other track would end up located at the example's.
#
# Whatever is not here **is not made up**: the template's value is kept and a warning is given.
COORDENADAS = {
    # EXACT folder name              lat        lon      alt(m) tz
    # ⚠️ The keys must be the REAL folder name in the pack: with three names that did not exist
    # (`JNSMartinsville`, `JNSIndianapolis`, `JNSNewHampshire`) the real coverage was 18 of 32,
    # not 21. Measured folder by folder.
    "JNSAtlanta":      (33.3861, -84.3147, 260, -5),
    "JNSAutoclub":     (34.0889, -117.5000, 350, -8),
    "JNSBristol":      (36.5156, -82.2570, 460, -5),
    "JNSCharlotte":    (35.3520, -80.6839, 230, -5),
    "JNSChicago":      (41.4747, -88.0570, 180, -6),
    "JNSDarlington":   (34.2958, -79.9058,  48, -5),
    "JNSDaytona":      (29.1852, -81.0709,   3, -5),
    "JNSDover":        (39.1897, -75.5300,  10, -5),
    "JNSGateway":      (38.6500, -90.1333, 130, -6),
    "JNSHampshire":    (43.3625, -71.4611, 140, -5),
    "JNSHomestead":    (25.4515, -80.4088,   2, -5),
    "JNSI70":          (38.9950, -94.0100, 250, -6),
    "JNSIndy":         (39.7950, -86.2347, 228, -5),
    "JNSIowa":         (41.6706, -93.0136, 290, -6),
    "JNSKansas":       (39.1155, -94.8308, 270, -6),
    "JNSKentucky":     (38.7111, -84.9194, 180, -5),
    "JNSLasVegas":     (36.2722, -115.0111, 640, -8),
    "JNSMansfield":    (40.7756, -82.5215, 380, -5),
    "JNSMarty":        (36.6339, -79.8508, 290, -5),
    "JNSMemphis":      (35.3350, -89.9000,  90, -6),
    "JNSMichigan":     (42.0656, -84.2414, 305, -5),
    "JNSMilwaukee":    (43.0206, -88.0086, 230, -6),
    "JNSMyrtleBeach":  (33.7500, -78.9800,  10, -5),
    "JNSNashvilleSS":  (36.1361, -86.4083, 170, -6),
    "JNSNazareth":     (40.7062, -75.3190, 130, -5),
    "JNSORP":          (39.7911, -86.3428, 240, -5),
    "JNSPhoenix":      (33.3750, -112.3110, 350, -7),
    "JNSPocono":       (41.0553, -75.5111, 430, -5),
    "JNSRichmond":     (37.5925, -77.4194,  60, -5),
    "JNSRock":         (34.9711, -79.6403,  99, -5),
    "JNSTalladega":    (33.5686, -86.0661, 168, -6),
    "JNSTexas":        (33.0369, -97.2828, 190, -6),
}



def coordenadas(nombre_gdb: str):
    """(lat, lon, alt_m, time zone) of the track, or None if unknown.

    `None` means "I don't know", and whoever writes the TRD must then **keep whatever value is
    there** and say so, not put in another place's value.
    """
    if not nombre_gdb:
        return None
    clave = nombre_gdb.strip()
    for k, v in COORDENADAS.items():
        if k.lower() == clave.lower():
            return v
    return None
