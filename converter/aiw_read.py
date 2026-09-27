"""Reader for the AMS1 / gMotor2 .aiw (rFactor, GSC, AMS1).

No dependencies and NO `bpy`: this runs and is tested outside Blender, which is the only way to
see it fail. The bridge to Blender lives in `aiw_to_blender.py`.

The format is an INI inherited from ISI and shares the same trunk as AMS2's .aiw.

Coordinate system: gMotor2 is Y-up. Blender is Z-up. `to_blender()` applies the SAME swap as the
GMT importer (x, y, z) -> (x, z, y), so that geometry and waypoints land in the same place. It is
a swap, not a rotation: it flips handedness, so the track ends up mirrored relative to the real
one. That does not matter as long as both things go together, but you need to know it before
comparing with a photo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# "wp_pos=(1.0,-2,3)" or "GarPos=(0,1.0,2,3)"  ->  name and list of numbers.
_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*(?://.*)?$")
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _nums(raw: str) -> list[float]:
    return [float(x) for x in _NUM.findall(raw)]


def _d2(a, b) -> float:
    return sum((p - q) ** 2 for p, q in zip(a, b))


def to_blender(v) -> tuple[float, float, float]:
    """gMotor2's (x, y_up, z) -> Blender's (x, y, z_up)."""
    x, y, z = v
    return (x, z, y)


@dataclass
class Waypoint:
    pos: tuple[float, float, float]
    perp: tuple[float, float, float] = (0.0, 0.0, 0.0)
    vect: tuple[float, float, float] = (0.0, 0.0, 0.0)
    width: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    dwidth: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    path: tuple[float, float] = (0.0, 0.0)
    branch_id: int = 0
    bitfields: int = 0
    pitlane: int = 0
    sector: int = 0
    dist: float = 0.0
    ptrs: tuple[int, int, int, int] = (-1, -1, -1, -1)  # prev, next, branch, branch path

    @property
    def is_path(self) -> bool:
        """⚠️ `wp_bitfields=1` means "does not form a path": these are the PIT LANE points.

        Measured at Charlotte: 901 with bitfields=0 (463 on branch 0 + 438 on branch 1) and 149
        with bitfields=1, and the latter fit in a strip X -153..-127, right over the pit boxes
        (X -140..-127). Confusing them with "branch ≠ 0 = pit lane" adds a whole extra lap to the
        pit lane.
        """
        return self.bitfields == 0

    @property
    def is_main(self) -> bool:
        return self.branch_id == 0 and self.is_path

    def edge(self, side: str, kind: str = "road", ancho: float | None = None):
        """Point on the track edge: pos offset along `perp` according to wp_width/wp_dwidth.

        side: 'left' | 'right'. kind: 'road' (wp_width) | 'wall' (wp_dwidth).
        `ancho` caps the offset (to draw outlines without the pit lane spikes).
        """
        w = self.width if kind == "road" else self.dwidth
        v = w[0] if side == "left" else w[1]
        if ancho is not None:
            v = min(v, ancho)
        d = v if side == "left" else -v
        return tuple(p + d * q for p, q in zip(self.pos, self.perp))

    def racing_line(self):
        """The dry racing line: `pos` offset along `perp` by the lateral value of `wp_path[0]`.

        🔴 **With the sign flipped, and it is measured.** OMTT negates the offset on export
        (`racing_offset: -racing_offset` in `waypoint_processor.py`) even though it writes
        `wp_perp` pointing outwards, so the racing line came out **mirrored**: in the banked turns
        the exported `wp_path` gave a median of **+3.01** when the AMS1 original gives **−3.29**
        and Texas —an official AMS2 oval— gives **−4.02**; on the straights, the exported −3.40
        against +3.41 and +2.00.

        `wp_perp` points to the outside of the oval on **463/463** waypoints in all three files,
        so the sign leaves no room for interpretation. Effect: the AI climbed to the HIGH groove
        against the wall in the turns —where the corridor only declares 4.44 m outwards— and
        dropped to the apron on the straights. At metre 2031 the racing line was **0.05 m from the
        outer edge**, which is a wall.

        **No reference track exercises** that OMTT path: `wp_path` is 0 on 560/560 of Mid-Ohio,
        255/255 of GJ Kartway and 657/657 of Meadowdale, so the bug does not show when comparing
        with the official tracks.
        """
        return tuple(p - self.path[0] * q for p, q in zip(self.pos, self.perp))


@dataclass
class Placement:
    """A slot with position and orientation: grid, teleport, pit box or garage."""

    index: int
    pos: tuple[float, float, float]
    ori: tuple[float, float, float]  # radians (pitch, yaw, roll) on AMS1's axes
    sub: int = 0  # for garages: 0=A, 1=B, 2=C…

    def blender_rotation(self) -> tuple[float, float, float]:
        """XYZ Euler for Blender, with "forward" = +Y (OMTT's convention).

        **MEASURED, not deduced.** Charlotte's 102 grid slots came out facing backwards — and a
        track with a backwards grid loads, starts and raises no error. The four combinations were
        tested against the racing line's tangent:

        | rotation | mean error |
        |---|---|
        | `(pitch, roll, -yaw)`      | 170.3° |
        | `(pitch, roll, +yaw + π)`  |  98.6° |
        | **`(pitch, roll, -yaw + π)`** | **0.8°** (worst case 2.3°) |

        And it had to be measured with the TELEPORTs, not with the grid: on an oval's straight the
        yaw is ~0.03 rad, so both sign options tied (9.7° against 11.3°) and the π was proven but
        the sign was not. The 104 teleports go all the way round (yaw from +0.33 to +2.30 rad) and
        there the difference is 0.8° against 98.6°.
        **A flat test case cannot tell two hypotheses apart.**
        """
        pitch, yaw, roll = self.ori
        return (pitch, roll, -yaw + math.pi)


@dataclass
class Pit:
    team_index: int
    pos: tuple[float, float, float]
    ori: tuple[float, float, float]
    garages: list[Placement] = field(default_factory=list)


@dataclass
class Aiw:
    features: dict[str, float] = field(default_factory=dict)
    waypoints: list[Waypoint] = field(default_factory=list)
    grid: list[Placement] = field(default_factory=list)
    altgrid: list[Placement] = field(default_factory=list)
    teleport: list[Placement] = field(default_factory=list)
    pits: list[Pit] = field(default_factory=list)
    lap_length: float = 0.0
    waypoint_span: float = 0.0

    @property
    def main_path(self) -> list[Waypoint]:
        """The main racing line: `SMS_AIW_CENTERLINE`."""
        return [w for w in self.waypoints if w.is_main]

    @property
    def rama_del_pit_lane(self) -> int | None:
        """Which branch ≠0 is the REAL PIT LANE.

        🔴 Why: the AI went into the pits instead of completing the lap. The pit lane was exported
        as an **alternative racing line** —that is, offered to the AI as a racing line— and the 149
        pit slots as the pit lane, with a **117 m** jump between consecutive waypoints and the entry
        and exit at the same point of the straight.

        At Charlotte branch 1 has **438 chained waypoints** (436 of 437 steps via `WP_PTRS`), its
        first point is **−2.4 m** from the centre line and its `prev` points to a waypoint of the
        main racing line: that is a pit entry. Identical signature to Texas's (399 wp, entry at
        −3.7 m) and Mid-Ohio's (entry at 0.0 m).

        The signal that identifies it is **where it starts from**, not how many points it has: the
        pit lane is the only branch that starts hanging off the main racing line.
        """
        principal = {i for i, w in enumerate(self.waypoints) if w.branch_id == 0 and w.is_path}
        if not principal:
            return None
        candidatas: dict[int, list[int]] = {}
        for i, w in enumerate(self.waypoints):
            if w.is_path and w.branch_id != 0:
                candidatas.setdefault(w.branch_id, []).append(i)
        mejor, mejor_n = None, 0
        for rama, idxs in candidatas.items():
            engancha = sum(1 for i in idxs
                           if self.waypoints[i].ptrs and self.waypoints[i].ptrs[0] in principal)
            if engancha and len(idxs) > mejor_n:
                mejor, mejor_n = rama, len(idxs)
        return mejor

    @property
    def alt_paths(self) -> dict[int, list[Waypoint]]:
        """Alternative racing lines (an oval's *grooves*), per branch.

        AMS2 does not import them: their equivalent is `LaneSpacing` and the TRD's multipath.
        """
        pit = self.rama_del_pit_lane
        out: dict[int, list[Waypoint]] = {}
        for w in self.waypoints:
            if w.is_path and w.branch_id != 0 and w.branch_id != pit:
                out.setdefault(w.branch_id, []).append(w)
        return out

    @property
    def pit_waypoints(self) -> list[Waypoint]:
        """The pit LANE: the branch that starts hanging off the main racing line.

        Careful: `bitfields != 0` **are not the lane but the SLOTS** —and those already come out
        of the `[PITS]` block as `SMS_AIW_PITBOX_*` and `SMS_AIW_GARAGE_*`—.
        See `rama_del_pit_lane`.
        """
        rama = self.rama_del_pit_lane
        if rama is None:
            return [w for w in self.waypoints if not w.is_path]
        return [w for w in self.waypoints if w.is_path and w.branch_id == rama]

    def pit_path_ordered(self) -> list[Waypoint]:
        """The pit lane in driving order, following `WP_PTRS` (prev, next, …).

        OMTT requires ascending vertex indices along the path; in the file the pit lane points do
        not come in that order. If the pointers do not chain, it falls back to ordering by
        proximity to the previous point, which is enough for a straight pit lane.
        """
        pit = self.pit_waypoints
        if not pit:
            return []
        by_index = {id(w): w for w in pit}
        pos_of = {i: w for i, w in enumerate(self.waypoints)}
        chain, seen = [], set()
        # Start at the ENTRY: the point whose `prev` falls OUTSIDE the branch, i.e. the one
        # hanging off the main racing line. Looking for "the one nobody points to as next" does
        # not work: at Charlotte the pit lane is a closed loop where every point is pointed to,
        # it fell on `pit[0]`, started halfway and the proximity ordering introduced a **376 m
        # jump**. Measured: the pointers chain **437 of 438** with global indices.
        idx_de = {id(w): i for i, w in enumerate(self.waypoints)}
        dentro = {idx_de[id(w)] for w in pit}
        start = next((w for w in pit if w.ptrs and w.ptrs[0] not in dentro), pit[0])
        cur = start
        while cur is not None and id(cur) not in seen and len(chain) < len(pit):
            seen.add(id(cur))
            chain.append(cur)
            nxt = pos_of.get(cur.ptrs[1])
            cur = nxt if (nxt is not None and id(nxt) in by_index) else None
        # 🔴 What does NOT chain **is not glued on by proximity**. Measured at Charlotte: the pit
        # lane branch contains TWO paths, not one — the pit lane proper (396 points, indices
        # 463..858) and the **garage access lane** (42, 859..900), each with its own entry.
        # Gluing them by proximity produced a **376 m jump** between two consecutive waypoints,
        # i.e. a pit lane that teleports. Only the chained path is returned; the rest is
        # something else and already comes out of the `[PITS]` block as slots.
        return chain


def parse(path: str) -> Aiw:
    with open(path, "r", encoding="latin-1") as fh:
        aiw = parse_text(fh.read())
    # Where it came from: some header data is not modelled (the sectors) and has to be read
    # from the raw file.
    aiw._ruta = path
    return aiw


def parse_text(text: str) -> Aiw:
    aiw = Aiw()
    section = None
    wp: Waypoint | None = None
    place: dict | None = None  # [GRID]/[ALTGRID]/[TELEPORT] slot being read
    pit: Pit | None = None

    def flush_wp():
        nonlocal wp
        if wp is not None:
            aiw.waypoints.append(wp)
            wp = None

    def flush_place():
        nonlocal place
        if place is not None and "pos" in place:
            p = Placement(place["index"], place["pos"], place.get("ori", (0.0, 0.0, 0.0)))
            {"[GRID]": aiw.grid, "[ALTGRID]": aiw.altgrid, "[TELEPORT]": aiw.teleport}[
                place["section"]
            ].append(p)
        place = None

    def flush_pit():
        nonlocal pit
        if pit is not None:
            aiw.pits.append(pit)
            pit = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            flush_wp()
            flush_place()
            flush_pit()
            section = stripped
            continue

        m = _LINE.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        low = key.lower()
        nums = _nums(raw)

        if section == "[Features]":
            if nums:
                aiw.features[low] = nums[0]
            if low == "waypointspan":
                aiw.waypoint_span = nums[0]

        elif section in ("[GRID]", "[ALTGRID]", "[TELEPORT]"):
            if low == "gridindex":
                flush_place()
                place = {"section": section, "index": int(nums[0])}
            elif place is not None and low == "pos" and len(nums) >= 3:
                place["pos"] = tuple(nums[:3])
            elif place is not None and low == "ori" and len(nums) >= 3:
                place["ori"] = tuple(nums[:3])

        elif section == "[PITS]":
            if low == "teamindex":
                flush_pit()
                pit = Pit(int(nums[0]), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            elif pit is not None and low == "pitpos" and len(nums) >= 3:
                pit.pos = tuple(nums[:3])
            elif pit is not None and low == "pitori" and len(nums) >= 3:
                pit.ori = tuple(nums[:3])
            elif pit is not None and low == "garpos" and len(nums) >= 4:
                # GarPos=(sub, x, y, z)
                pit.garages.append(
                    Placement(pit.team_index, tuple(nums[1:4]), (0.0, 0.0, 0.0), int(nums[0]))
                )
            elif pit is not None and low == "garori" and len(nums) >= 4:
                sub = int(nums[0])
                for g in pit.garages:
                    if g.sub == sub:
                        g.ori = tuple(nums[1:4])
                        break

        elif section == "[Waypoint]":
            if low == "wp_pos":
                flush_wp()
                wp = Waypoint(pos=tuple(nums[:3]))
            elif low == "number_waypoints" and nums:
                aiw.features["number_waypoints"] = nums[0]
            elif low == "lap_length" and nums:
                aiw.lap_length = nums[0]
            elif wp is not None:
                if low == "wp_perp" and len(nums) >= 3:
                    wp.perp = tuple(nums[:3])
                elif low == "wp_vect" and len(nums) >= 3:
                    wp.vect = tuple(nums[:3])
                # 🔴 AMS1 writes FOUR numbers and OMTT's exporter, TWO (left/right). With ">= 4"
                # OMTT's stayed at (0,0,0,0) without error, and everything that reads the exported
                # AIW —map, limits trimming, triggers, gates— worked with a zero-width track.
                # Whatever is missing goes to 0.
                elif low == "wp_width" and len(nums) >= 2:
                    wp.width = tuple((nums + [0.0, 0.0])[:4])
                elif low == "wp_dwidth" and len(nums) >= 2:
                    wp.dwidth = tuple((nums + [0.0, 0.0])[:4])
                elif low == "wp_path" and len(nums) >= 2:
                    wp.path = tuple(nums[:2])
                elif low == "wp_branchid" and nums:
                    wp.branch_id = int(nums[0])
                elif low == "wp_bitfields" and nums:
                    wp.bitfields = int(nums[0])
                elif low == "wp_pitlane" and nums:
                    wp.pitlane = int(nums[0])
                elif low == "wp_score" and len(nums) >= 2:
                    wp.sector, wp.dist = int(nums[0]), nums[1]
                elif low == "wp_ptrs" and len(nums) >= 4:
                    wp.ptrs = tuple(int(x) for x in nums[:4])

    flush_wp()
    flush_place()
    flush_pit()
    return aiw


# --- curvature: where corner_type and corner_state come from -------------------------------
#
# AMS1's .aiw does not store the corner type OMTT asks for, but the geometry does tell it.
# OMTT warns that without corner data the AI "drives itself off the track".

CORNER_STRAIGHT, CORNER_LEFT, CORNER_RIGHT = 0, 3, 4
STATE_STRAIGHT, STATE_ENTRY, STATE_APEX, STATE_EXIT = 0, 1, 2, 3


def signed_curvature(pts, i: int, closed: bool = True) -> float:
    """Turn rate (rad/m) at point i of a closed path, in AMS1's horizontal plane.

    Positive = left. It uses the previous and the next neighbour, so the result does not depend on
    the spacing between waypoints.
    """
    n = len(pts)
    if not closed and (i == 0 or i == n - 1):
        return 0.0
    a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
    v1 = (b[0] - a[0], b[2] - a[2])
    v2 = (c[0] - b[0], c[2] - b[2])
    l1 = math.hypot(*v1)
    l2 = math.hypot(*v2)
    if l1 < 1e-6 or l2 < 1e-6:
        return 0.0
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    return math.atan2(cross, dot) / ((l1 + l2) / 2.0)


def classify_corners(
    waypoints,
    threshold: float = 0.004,
    smooth: int = 5,
    closed: bool = True,
    min_straight: float = 60.0,
):
    """Returns (corner_type[], corner_state[]) for the given list of waypoints.

    `threshold` in rad/m: below it is a straight. 0.004 rad/m ≈ a 250 m radius, which leaves out
    the wiggle of a straight and keeps in the banked turns of an oval.

    `closed=False` for a standalone stretch: otherwise the ends get joined and a very tight corner
    appears that does not exist.

    `min_straight` (m): two stretches turning the same way separated by less straight than this
    are THE SAME corner. Without it, at Charlotte turns 1-2 came out split in three by momentary
    dips in curvature, and the AI would brake three times in one single corner.
    """
    pts = [w.pos for w in waypoints]
    n = len(pts)
    if n < 3:
        return [CORNER_STRAIGHT] * n, [STATE_STRAIGHT] * n

    raw = [signed_curvature(pts, i, closed=closed) for i in range(n)]
    # circular moving average: a single waypoint must not open a corner
    half = max(1, smooth // 2)
    curv = [
        sum(raw[(i + d) % n] for d in range(-half, half + 1)) / (2 * half + 1) for i in range(n)
    ]

    types = [
        CORNER_LEFT if c > threshold else CORNER_RIGHT if c < -threshold else CORNER_STRAIGHT
        for c in curv
    ]

    runs = _runs(types, closed=closed)
    runs = _merge_runs(runs, types, pts, closed=closed, min_straight=min_straight)

    states = [STATE_STRAIGHT] * n
    for idxs in runs:
        for i in idxs:  # a merged stretch drags along the gap that split it
            types[i] = types[idxs[0]]
        # 🔴 The APEX is a PLATEAU, not a point. Marking a single waypoint —the one with maximum
        # curvature— left everything before it as "entry". Measured at Charlotte: **144 entry, 4
        # apex and 51 exit**, i.e. the AI believed it was ENTERING the corner for **335 of the
        # 424 m** of T1-2 and **380 of the 532** of T3-4: braking and turning in where, on a 24°
        # banking, you go flat out.
        #
        # On an oval the curvature is almost constant along the whole turn, so "the point of
        # maximum curvature" is numerical noise. Everything reaching **90 % of the stretch's peak**
        # is marked as apex, and entry/exit stay on either side.
        picos = [abs(curv[i]) for i in idxs]
        umbral_apex = max(picos) * 0.9
        meseta = [k for k, v in enumerate(picos) if v >= umbral_apex]
        primero, ultimo = meseta[0], meseta[-1]
        for k, i in enumerate(idxs):
            states[i] = (STATE_ENTRY if k < primero
                         else STATE_EXIT if k > ultimo
                         else STATE_APEX)
    return types, states


def _runs(types, closed: bool = True):
    """Corner stretches as LISTS OF INDICES, in driving order.

    On a track, a corner can cross the finish line: at Charlotte the dogleg of the main straight
    starts at metre 2,251 and ends at metre 142 of the next lap. Treating the list as linear
    splits it into two corners that do not exist. It is solved by rotating the origin to a
    straight before walking it.
    """
    n = len(types)
    if n == 0:
        return []
    offset = 0
    if closed:
        first_straight = next((i for i, t in enumerate(types) if t == CORNER_STRAIGHT), None)
        if first_straight is None:
            return [list(range(n))]  # all corner: a banked oval with no straights
        offset = first_straight

    out, cur = [], []
    for k in range(n):
        i = (offset + k) % n
        if types[i] == CORNER_STRAIGHT:
            if cur:
                out.append(cur)
                cur = []
        elif cur and types[i] != types[cur[-1]]:
            out.append(cur)  # changes direction: new corner
            cur = [i]
        else:
            cur.append(i)
    if cur:
        out.append(cur)
    return out


def _arc(pts, i: int, j: int, n: int) -> float:
    """Metres travelled from i to j going forwards (circular)."""
    total, k = 0.0, i
    while k != j:
        nxt = (k + 1) % n
        total += math.dist(pts[k], pts[nxt])
        k = nxt
    return total


def _merge_runs(runs, types, pts, closed: bool, min_straight: float):
    """Merges same-direction stretches separated by very little straight."""
    if len(runs) < 2:
        return runs
    n = len(types)
    merged = [list(runs[0])]
    for run in runs[1:]:
        prev = merged[-1]
        gap = _arc(pts, prev[-1], run[0], n)
        if types[run[0]] == types[prev[0]] and gap < min_straight:
            i = prev[-1]
            while i != run[0]:  # the gap becomes part of the corner
                i = (i + 1) % n
                prev.append(i)
            prev.extend(run[1:])
        else:
            merged.append(list(run))
    # and the lap closure: the last stretch may join up with the first
    if closed and len(merged) > 1:
        first, last = merged[0], merged[-1]
        gap = _arc(pts, last[-1], first[0], n)
        if types[first[0]] == types[last[0]] and gap < min_straight:
            i = last[-1]
            while i != first[0]:
                i = (i + 1) % n
                last.append(i)
            last.extend(first)
            merged = merged[1:-1] + [last]
    return merged


def garajes_de_verdad(garajes):
    """Removes the garage slots that are **at the origin** in the AMS1 AIW.

    🔴 Measured at Charlotte. Its AIW declares `garagespots=3`, but of the three sub-slots of each
    pit box **only `A` has a position**: the other two come as `GarPos=(n, 0.000, 0.050, 0.000)`,
    i.e. the world origin. Of 135 slots, **90 are at (0,0,0)** — and that was already like that in
    the original AMS1 file, the exporter does not make it up.

    gMotor2 skips them. Madness does NOT: it places a car in each one, so when going to the pits
    cars show up piled at the origin and **flying through the sky**. Without any error.

    And the number does not need to be touched by hand: OMTT derives `garagespots` from the
    maximum number of letters per box, so removing the empty ones makes it drop to 1 by itself —
    which is what Mid-Ohio declares.
    """
    return [g for g in garajes if not _en_el_origen(g.pos)]


def _en_el_origen(pos, margen: float = 0.5) -> bool:
    """An "empty" AIW slot: X and Z at zero. Y does not count, it comes with 0.05 of ride height."""
    return abs(pos[0]) < margen and abs(pos[2]) < margen


def curvas_adaptativo(waypoints, umbrales=(0.004, 0.003, 0.0022, 0.0015)):
    """Classifies corners lowering the threshold until some appear. Returns (types, states, threshold).

    🔴 Why: the fixed threshold of 0.004 rad/m is equivalent to a 250 m radius. Measured on a
    synthetic oval: with R=120 m it works; with **R=400 m (curvature 0.0025) `classify_corners`
    returns ZERO corners**. And that is not hypothetical: **Talladega has a radius of ≈340 m**
    (0.0029 rad/m) and would come out with `Number Of Turns = 0`, `corner_type = 0` on every
    waypoint —which according to the OMTT tutorial makes "the AI drive itself off the track"— and
    an undetermined direction of rotation.

    It is the same bug as the inherited `Is Clockwise`, reintroduced through a constant.
    Charlotte is right at the cliff edge: with 0.004 you get 4 corners, with 0.005 you get 6 and
    with 0.006 you get **0**.

    The threshold is lowered, never raised: lowering finds wider corners; raising makes them up.
    """
    for u in umbrales:
        tipos, estados = classify_corners(waypoints, threshold=u)
        if any(t != CORNER_STRAIGHT for t in tipos):
            return tipos, estados, u
    return [CORNER_STRAIGHT] * len(waypoints), [STATE_STRAIGHT] * len(waypoints), umbrales[-1]


def gira_a_derechas(waypoints):
    """Is the layout driven CLOCKWISE? (the TRD's `Is Clockwise`).

    🔴 Why it exists: the TRD inherited `Is Clockwise = true` from Meadowdale and **Charlotte
    turns left**, like every American oval. Our own AIW says so unambiguously —199 corner
    waypoints, **all 199 of type 3 (LEFT)** and none of type 4— and the TRD said the opposite. The
    AI is guided by both.

    It is not computed from raw geometry: it counts over the **corner classification already used
    for the AIW**, which is what the game will read. That way the two declarations cannot
    contradict each other — which was exactly the bug.
    """
    tipos, _estados, _u = curvas_adaptativo(waypoints)
    izq = sum(1 for t in tipos if t == CORNER_LEFT)
    der = sum(1 for t in tipos if t == CORNER_RIGHT)
    if izq == der:
        # "I don't know" is an answer. Returning False here would declare ANTICLOCKWISE any
        # track whose corners were not classified — which is exactly the bug this function exists
        # to avoid, from the other side.
        return None
    return der > izq


def parrilla_fuera_de_pista(aiw, margen: float = 2.0) -> float:
    """Median distance from the grid to the centre line, in track half-widths.

    🔴 Why: the `[GRID]` in Charlotte's AMS1 AIW **is in the pit lane**: measured, the first 18
    slots are **46-69 m from the centre line** —with the track declaring **a 6 m half-width**— and
    **7-16 m from the pit boxes**. In AMS1 that works because ovals form up on pit road; AMS2
    places the cars there and the race starts on the grass.

    Returns how many track half-widths the grid is away. Below `margen` the AMS1 grid is good and
    is kept.
    """
    import math

    centro = [w.pos for w in aiw.main_path]
    if not centro or not aiw.grid:
        return 0.0
    # `wp_width` is FOUR numbers (left/right of track and of limit); the useful half-width is
    # the smaller of the first two.
    anchos = sorted(min(w.width[0], w.width[1]) for w in aiw.main_path
                    if getattr(w, "width", None) and len(w.width) >= 2)
    semi = anchos[len(anchos) // 2] if anchos else 6.0
    d = sorted(
        min(math.hypot(g.pos[0] - c[0], g.pos[2] - c[2]) for c in centro)
        for g in aiw.grid[:20]
    )
    return (d[len(d) // 2] / semi) if semi else 0.0


# 🔴 AMS2 GRID CEILING: **32**. It is not a preference, it is the game's maximum.
# Actual distribution of the game's 230 tracks by `grid_size`:
#     32 → 155 · 30 → 19 · 28 → 9 · 26 → 17 · 24 → 2 · 20 → 13 · 16 → 4 · 14 → 4 · 8 → 7
# None goes above 32. And exceeding it does not give a clean error: on a dedicated server, Reiza's
# `lib_rotate` **warns on the console and lets the setup through**, and the server ends up loading
# another track.
TECHO_PARRILLA = 32


def parrilla_desde_la_linea(aiw, puestos: int = TECHO_PARRILLA, por_fila: int = 2,
                            separacion: float = 9.0, lateral: float = 2.6):
    """Builds the grid on the centre line, backwards from the finish line.

    Nothing about the layout is made up: it uses the AIW's waypoints —which are the track— and
    places the rows **behind the finish line**, which is where a grid forms up. Each slot faces
    the layout's direction of travel, taken from the waypoints themselves.

    `lateral` is the offset to each side of the centre. It stays well inside the half-width (6 m
    at Charlotte) so that no car spawns on top of the edge line.
    """
    import math

    pts = [w.pos for w in aiw.main_path]
    n = len(pts)
    if n < 3:
        return []

    # cumulative distance backwards from waypoint 0 (the finish line)
    fuera = []
    fila = 0
    i = 0
    recorrido = 0.0
    while len(fuera) < puestos and fila < n:
        objetivo = separacion * (fila + 1)
        while recorrido < objetivo and i < n:
            a, b = pts[-i % n], pts[-(i + 1) % n]
            recorrido += math.hypot(a[0] - b[0], a[2] - b[2])
            i += 1
        c = pts[-i % n]
        sig = pts[-(i - 1) % n]
        dx, dz = sig[0] - c[0], sig[2] - c[2]
        largo = math.hypot(dx, dz) or 1.0
        dx, dz = dx / largo, dz / largo
        # perpendicular in the plane
        px, pz = -dz, dx
        # 🔴 `+ π`, and it is MEASURED. `blender_rotation()` applies `-yaw + π` because that is
        # the convention of AMS1's `.aiw`, and this yaw **is not in that convention**: it is a
        # plain ordinary heading taken from two points. Feeding it as is through that transform
        # left it **exactly 180.0° backwards**: the race started in the opposite direction.
        # With `+ π`, error 0.0°.
        #
        # It is the same bug `blender_rotation` already documents, from the other end: a
        # backwards grid **loads, starts and raises no error**. That is why the heading is checked
        # with `error_de_rumbo()` on every conversion, instead of reasoning about it.
        yaw = math.atan2(dx, dz) + math.pi
        for k in range(por_fila):
            if len(fuera) >= puestos:
                break
            desvio = lateral * (1 if k % 2 == 0 else -1)
            fuera.append(Placement(
                index=len(fuera),
                pos=(c[0] + px * desvio, c[1], c[2] + pz * desvio),
                ori=(0.0, yaw, 0.0),
            ))
        fila += 1
    return fuera


def error_de_rumbo(aiw, puestos=None) -> float:
    """The worst deviation, in degrees, between a grid slot's heading and the layout.

    A track with a backwards grid loads, starts and raises no error — it happened with the 102
    slots read from AMS1 and happened again with the ones built on the centre line (exactly
    180.0°). Measuring it costs nothing.
    """
    import math

    puestos = puestos if puestos is not None else parrilla_desde_la_linea(aiw)
    pts = [w.pos for w in aiw.main_path]
    if not pts or not puestos:
        return 0.0
    peor = 0.0
    for pl in puestos:
        k = min(range(len(pts)),
                key=lambda i: math.hypot(pts[i][0] - pl.pos[0], pts[i][2] - pl.pos[2]))
        c, sig = pts[k], pts[(k + 1) % len(pts)]
        dx, dz = sig[0] - c[0], sig[2] - c[2]
        r = math.hypot(dx, dz) or 1.0
        th = pl.blender_rotation()[2]
        fx, fz = -math.sin(th), math.cos(th)   # the marker's +Y, rotated
        cos = max(-1.0, min(1.0, fx * dx / r + fz * dz / r))
        peor = max(peor, math.degrees(math.acos(cos)))
    return peor


def numero_de_curvas(estados) -> int:
    """How many corners there are: consecutive apex STRETCHES, not apex waypoints.

    While the apex was a point, "counting apexes" and "counting corners" gave the same result, and
    half a dozen places took that for granted — including the TRD's `Number Of Turns`. When the
    apex became a plateau, Charlotte would have declared **146 corners** instead of 4.

    It counts in a circle: a corner that crosses the finish line is one, not two.
    """
    n = len(estados)
    if n == 0:
        return 0
    es = [e == STATE_APEX for e in estados]
    if all(es):
        return 1
    curvas = 0
    for i in range(n):
        if es[i] and not es[i - 1]:
            curvas += 1
    return curvas
