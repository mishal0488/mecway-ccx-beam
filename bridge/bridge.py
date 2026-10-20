"""Mecway LIML -> experimental native B31T/B31E CalculiX input bridge.

V0.1 intentionally refuses to produce a solver-ready deck for features whose
mapping has not yet been verified against the patched UB31 implementation.
Python 3.10+; standard library only.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

LENGTH = {'m': 1., 'mm': .001, 'cm': .01}
FORCE = {'N': 1., 'kN': 1000., 'MN': 1e6}
STRESS = {'Pa': 1., 'kPa': 1e3, 'MPa': 1e6, 'GPa': 1e9}
DENSITY = {'kg/m³': 1., 'kg/m3': 1.}
ACCEL = {'m/s²': 1., 'm/s2': 1.}

def quantity(text, units):
    s = str(text).strip()
    m = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*)', s)
    if not m:
        raise ValueError(f'Cannot parse quantity: {text!r}')
    value, unit = float(m[1]), m[2].strip()
    if unit not in units:
        raise ValueError(f'Unexpected unit {unit!r} in {text!r}')
    return value * units[unit]

def selected(root, tag, name):
    node = root.find(f"{tag}[@name='{name}']")
    if node is None:
        raise ValueError(f'Missing selection {tag}: {name}')
    return node

def write_data(f, rows):
    for row in rows:
        f.write(', '.join(map(str, row)) + '\n')

def translate(source: Path, target: Path, beam_type: str, draft: bool):
    root = ET.parse(source).getroot()
    if root.tag != 'liml':
        raise ValueError('Input does not have a LIML root')
    errors, warnings = [], []
    nodes = {int(n.get('nid')): (float(n.get('x')), float(n.get('y')), float(n.get('z'))) for n in root.findall('node')}
    elements, groups = {}, defaultdict(list)
    for group in root.findall('elset'):
        mat = group.get('material')
        for el in group.findall('elem'):
            eid = int(el.get('eid'))
            if el.get('shape') != 'line2':
                errors.append(f'Unsupported element {eid}, shape {el.get("shape")}')
                continue
            conn = tuple(map(int, el.get('nodes').split()))
            if len(conn) != 2 or any(n not in nodes for n in conn):
                errors.append(f'Bad connectivity for element {eid}')
                continue
            if eid in elements:
                errors.append(f'Duplicate element ID {eid}')
                continue
            elements[eid] = conn
            if mat:
                groups[mat].append(eid)
            else:
                errors.append(f'Element {eid} has no section/material')
    mats = {m.get('name'): m for m in root.findall('mat')}
    for material in groups:
        if material not in mats:
            errors.append(f'Unknown material {material}')
    # Unsupported semantic constructs are NOT dropped silently.
    for tag, description in [('flexiblejoint', 'Mecway beam end releases'),
                              ('offset', 'Mecway geometric member offsets')]:
        for item in root.findall(tag):
            selection = item.get('selection', '?')
            errors.append(f'Unsupported {description} ({selection}); requires verified UB31 mapping')
    # Mecway orientation records may contain angleu rotations; vx/vy/vz alone
    # must not be assumed to be an equivalent CCX orientation vector.
    for item in root.findall('orientation'):
        errors.append(f'Unverified beam orientation ({item.get("selection")}); axis rotation must be translated')
    # Material/section definitions: dimensions and ordering have not yet been
    # checked against the patched UB31 code. Fail closed rather than guess.
    for name in groups:
        if name in mats:
            geo = mats[name].find('geometric')
            typ = geo.get('type') if geo is not None else '?'
            errors.append(f'Unverified section geometry for {name} (Mecway type {typ}); UB31 dimension ordering must be checked')
    analysis = root.find('analysis')
    analysis_type = analysis.get('type') if analysis is not None else None
    if analysis_type not in {'S30'}:
        errors.append(f'Analysis type {analysis_type!r} not mapped; currently only S30 static is recognized')
    # Grab simple nodal forces and fixed beam-end constraints.
    cloads = []
    for load in root.findall('force'):
        sel = selected(root, 'nodeselection', load.get('selection'))
        for n in sel.findall('node'):
            for dof, axis in enumerate('xyz', 1):
                value = quantity(load.findtext(axis, '0 N'), FORCE)
                if value:
                    cloads.append((int(n.get('nid')), dof, f'{value:.12g}'))
    constraints = set()
    for fixed in root.findall('fixed'):
        sel = selected(root, 'faceselection', fixed.get('selection'))
        for face in sel.findall('face'):
            eid, fid = int(face.get('eid')), int(face.get('faceid'))
            if eid not in elements or fid not in (2, 3):
                errors.append(f'Cannot map fixed face element {eid}, face {fid}')
                continue
            # Mecway face2 maps to first node and face3 to second node
            node = elements[eid][fid - 2]
            constraints.add(node)
    gravities = []
    for gravity in root.findall('gravity'):
        vector = [quantity(gravity.findtext(axis, '0 m/s²'), ACCEL) for axis in 'xyz']
        magnitude = math.sqrt(sum(v*v for v in vector))
        if magnitude:
            gravities.append((f'{magnitude:.12g}', *(f'{v/magnitude:.12g}' for v in vector)))
    for item in root:
        if item.tag in {'node', 'elset', 'mat', 'analysis', 'orientation', 'flexiblejoint', 'fixed', 'force',
                        'gravity', 'offset', 'nodeselection', 'faceselection', 'elementselection',
                        'fieldvariable', 'solution'}:
            continue
        warnings.append(f'Unrecognized LIML top-level tag: {item.tag}')
    report = {
        'source': str(source), 'element_type': beam_type, 'analysis': analysis_type,
        'nodes': len(nodes), 'elements': len(elements),
        'materials': sorted(groups), 'element_groups': {k: len(v) for k,v in groups.items()},
        'fixed_nodes': sorted(constraints), 'nodal_forces': len(cloads),
        'gravity_loads': len(gravities), 'errors': sorted(set(errors)),
        'warnings': sorted(set(warnings)), 'safe_to_solve': not errors,
    }
    report_path = target.with_suffix('.report.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if errors and not draft:
        print(f'VALIDATION FAILED: {len(set(errors))} issue(s). Report: {report_path}', file=sys.stderr)
        return 2
    with target.open('w', encoding='utf-8', newline='\n') as f:
        f.write('** Experimental Mecway CCX bridge v0.1\n')
        f.write('** DO NOT SOLVE: UNVERIFIED/UNIMPLEMENTED MODEL FEATURES\n' if errors else '** Validated bridge output\n')
        f.write('*HEADING\nMecway experimental input\n*NODE\n')
        write_data(f, ((nid, *coords) for nid, coords in sorted(nodes.items())))
        for i, (name, ids) in enumerate(groups.items(), 1):
            label = f'BEAM_{i}'
            f.write(f'*ELEMENT, TYPE={beam_type}, ELSET={label}\n')
            write_data(f, ((eid, *elements[eid]) for eid in sorted(ids)))
        f.write('** SECTION CARDS OMITTED: section conventions not yet verified.\n')
        for name, m in mats.items():
            if name not in groups:
                continue
            mech = m.find('mechanical')
            density = m.find('density')
            if mech is None or mech.get('type') != 'Isotropic':
                errors.append(f'Unsupported mechanical data {name}')
                continue
            safe_name = f'MAT_{list(groups).index(name)+1}'
            f.write(f'*MATERIAL, NAME={safe_name}\n*ELASTIC\n')
            f.write(f'{quantity(mech.get("youngsmodulus"), STRESS):.12g}, {mech.get("poissonratio")}\n')
            if density is not None:
                f.write('*DENSITY\n')
                f.write(f'{quantity(density.get("density"), DENSITY):.12g}\n')
        f.write('*BOUNDARY\n')
        write_data(f, ((node, 1, 6) for node in sorted(constraints)))
        f.write('*STEP\n*STATIC\n')
        if cloads:
            f.write('*CLOAD\n');write_data(f, cloads)
        if gravities:
            f.write('*DLOAD\n')
            for accel in gravities:
                write_data(f, [('EALL', 'GRAV', *accel)])
            f.write('** NOTE: EALL definition and GRAV support for UB31 still require verification.\n')
        f.write('*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
    print(f'Draft written: {target}\nReport: {report_path}\nSafe to solve: {not errors}')
    return 2 if errors else 0

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('liml', type=Path, help='Mecway native .liml model')
    p.add_argument('-o', '--output', type=Path, help='CalculiX .inp output')
    p.add_argument('--beam', choices=['B31T', 'B31E'], default='B31T')
    p.add_argument('--draft', action='store_true', help='Write non-solver-ready draft even if translation is incomplete')
    a = p.parse_args()
    return translate(a.liml, a.output or a.liml.with_suffix('.inp'), a.beam, a.draft)

if __name__ == '__main__':
    sys.exit(main())
