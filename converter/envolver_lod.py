"""Wraps every SGX object in a LOD node, as the reference circuits do.

    python3 envolver_lod.py <track.sgx>

Why. The TWO circuits built with this toolkit by its own author —Mid-Ohio and
GJ Kartway— wrap **every object** in a **single-level** `LOD` node, with
`Distances="1000 "`. 118 out of 118 and 156 out of 156, without a single exception. What
comes out of the current exporter is bare `OBJECT` objects: **0 out of 51** in the
measured conversion.

It is not a style choice by the author: it is what his exporter emitted. The current one
only writes a `LOD` if it finds an `SMS_LOD_` empty with **two or more** assigned levels
(`_collect_lod_groups`: *«LOD control needs at least two assigned meshes»*), so the shape
of the references cannot be reproduced that way — one level comes out, and it skips it.

It is done after exporting, on the XML, which is an exact and verifiable transformation:

    <NODE type="OBJECT" Name="X" MatrixNumber="-1" instances="1" userflags="U">
        <RESOURCE/> <SPHERE/> <MATRIX/>
    </NODE>

becomes

    <NODE type="LOD" Name="X" MatrixNumber="-1" matrices="1" subobjects="1">
        <SPHERE/> <MATRIX/> <CONTROL Distances="1000 "/>
        <NODE type="OBJECT" Name="X" MatrixNumber="0" instances="1" userflags="U">
            <RESOURCE/> <SPHERE/>
        </NODE>
    </NODE>

The sphere goes **in both** and the matrix **only in the LOD**; the child becomes
`MatrixNumber="0"`, which means «use the parent's». Copied from the reference, not deduced.
"""

import sys
import xml.etree.ElementTree as ET

DISTANCIA = "1000 "   # the trailing space is in both references; copied verbatim


def envolver(sgx_path: str) -> dict:
    tree = ET.parse(sgx_path)
    scene = tree.getroot()
    hechos, ya = 0, 0
    for obj_id in scene.findall("OBJ_ID"):
        nodo = obj_id.find("NODE")
        if nodo is None:
            continue
        if nodo.get("type") == "LOD":
            ya += 1
            continue
        if nodo.get("type") != "OBJECT":
            continue
        recurso = nodo.find("RESOURCE")
        esfera = nodo.find("SPHERE")
        matriz = nodo.find("MATRIX")
        if recurso is None or esfera is None or matriz is None:
            continue

        lod = ET.Element("NODE", {
            "type": "LOD",
            "Name": nodo.get("Name", ""),
            "MatrixNumber": "-1",
            "matrices": "1",
            "subobjects": "1",
        })
        lod.append(copiar(esfera))
        lod.append(copiar(matriz))
        ET.SubElement(lod, "CONTROL", {"Distances": DISTANCIA})

        hijo = ET.SubElement(lod, "NODE", {
            "type": "OBJECT",
            "Name": nodo.get("Name", ""),
            "MatrixNumber": "0",
            "instances": nodo.get("instances", "1"),
            "userflags": nodo.get("userflags", ""),
        })
        hijo.append(copiar(recurso))
        hijo.append(copiar(esfera))

        obj_id.remove(nodo)
        obj_id.append(lod)
        hechos += 1

    reordenadas = _orden_de_las_particiones(scene)

    ET.indent(tree, space="    ")
    tree.write(sgx_path, encoding="utf-8", xml_declaration=True)
    return {"envueltos": hechos, "ya_estaban": ya, "particiones": reordenadas}


def _orden_de_las_particiones(scene) -> int:
    """`CHILD_OBJS` before `CHILD_PARTITIONS`, which is how both references come out.

    The exporter writes them the other way round. It makes no difference to any XML
    reader — but the engine is not an XML reader, it is a custom parser and «extremely
    intolerant» (the tutorial's words). Matching the order is free; finding out whether it
    cares is not.
    """
    n = 0
    for part in scene.findall("PARTITION_ID"):
        objs = part.find("CHILD_OBJS")
        parts = part.find("CHILD_PARTITIONS")
        if objs is None or parts is None:
            continue
        if list(part).index(objs) > list(part).index(parts):
            part.remove(objs)
            part.insert(list(part).index(parts), objs)
            n += 1
    return n


def copiar(el):
    nuevo = ET.Element(el.tag, dict(el.attrib))
    return nuevo


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    r = envolver(argv[1])
    print(f"✅ SGX: {r['envueltos']} objects wrapped in LOD"
          + (f" · {r['ya_estaban']} already were" if r["ya_estaban"] else "")
          + (f" · {r['particiones']} partition(s) reordered" if r["particiones"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
