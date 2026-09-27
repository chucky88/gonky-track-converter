"""Reader for the AMS1 `.cam` file: the circuit's TV cameras, in place.

AMS1 ships with the circuit's cameras already made. AMS2 wants them in an XML with a
different skeleton, but the information is the same and **the coordinates do not change**
(both are Y-up, and the AIW already proved that the coordinate system is shared).

An AMS2 `TrackingCam` **follows the car on its own**: its `QuatOri` is only the resting
orientation. Measured on the template: its cameras do NOT point at the centre of their
activation zone (offsets of -95°, -31° and +23°), so there is no need to compute a
precise framing. What does matter is **where the camera is** and **on which stretch it
activates**.

No `bpy` and no dependencies.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_CAB = re.compile(r"^\s*(TrackingCam|StaticCam)\s*=\s*(\S+)", re.I)
_KV = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*$")


@dataclass
class Camara:
    nombre: str
    tipo: str                       # TrackingCam | StaticCam
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov_h: float = 40.0             # degrees
    fov_v: float = 25.0
    activacion: tuple[float, float, float] | None = None
    radio: float = 50.0

    @property
    def fov_rad(self) -> float:
        """AMS2 stores the FOV in RADIANS; AMS1, in degrees."""
        return math.radians(self.fov_h)

    def yaw_hacia_activacion(self) -> float:
        """Resting heading: looking at the stretch where the camera kicks in."""
        if not self.activacion:
            return 0.0
        dx = self.activacion[0] - self.pos[0]
        dz = self.activacion[2] - self.pos[2]
        return math.atan2(dx, -dz)

    def quat_ori(self) -> tuple[float, float, float, float]:
        """(w, x, y, z) rotating only about the vertical axis.

        The game's template uses exactly that form: `(a, 0, b, 0)` with a²+b²=1, i.e. a
        pure rotation about Y. The form is copied instead of inventing a general one.
        """
        mitad = self.yaw_hacia_activacion() / 2.0
        return (math.cos(mitad), 0.0, math.sin(mitad), 0.0)


def parse(path: str) -> list[Camara]:
    with open(path, "r", encoding="latin-1") as fh:
        return parse_text(fh.read())


def parse_text(texto: str) -> list[Camara]:
    camaras: list[Camara] = []
    actual: Camara | None = None
    for linea in texto.splitlines():
        cab = _CAB.match(linea)
        if cab:
            actual = Camara(nombre=cab.group(2), tipo=cab.group(1))
            camaras.append(actual)
            continue
        if actual is None:
            continue
        m = _KV.match(linea)
        if not m:
            continue
        clave = m.group(1).lower()
        nums = [float(x) for x in _NUM.findall(m.group(2))]
        if clave == "position" and len(nums) >= 3:
            actual.pos = tuple(nums[:3])
        elif clave == "fov" and len(nums) >= 2:
            actual.fov_h, actual.fov_v = nums[0], nums[1]
        elif clave == "activationlocation" and len(nums) >= 3:
            actual.activacion = tuple(nums[:3])
        elif clave == "activationradius" and nums:
            actual.radio = nums[0]
    return camaras


def solo_tracking(camaras) -> list[Camara]:
    return [c for c in camaras if c.tipo.lower() == "trackingcam"]
