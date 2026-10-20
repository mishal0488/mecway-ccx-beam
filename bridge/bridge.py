# -*- coding: utf-8 -*-
"""Mecway native LIML to experimental CalculiX B31T/B31E bridge.

Compatible with Mecway IronPython 2.7 and CPython 3.
This version generates diagnostic input ONLY, not a solver-ready CCX deck.
"""
from __future__ import print_function

import argparse
import io
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

VERSION = '0.3'
FLOAT_RE = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$')
FORCE = {'N': 1.0, 'kN': 1000.0, 'MN': 1000000.0}
STRESS = {'Pa': 1.0, 'kPa': 1.0e3, 'MPa': 1.0e6, 'GPa': 1.0e9}
DENSITY = {'kg/m3': 1.0, u'kg/m\u00b3': 1.0}
ACCEL = {'m/s2': 1.0, u'm/s\u00b2': 1.0}


def to_quantity(raw, units):
    if raw is None:
        raise ValueError('Missing quantity')
    match = FLOAT_RE.match(raw)
    if not match:
        raise ValueError('Invalid quantity: {0}'.format(raw))
    unit = match.group(2)
    if unit not in units:
        raise ValueError('Unrecognised units {0!r} in {1!r}'.format(unit, raw))
    return float(match.group(1)) * units[unit]


def index_named(root, tag):
    return dict((item.get('name'), item) for item in root.findall(tag))


def lines(handle, rows):
    for row in rows:
        handle.write(u', '.join([u'{0}'.format(value) for value in row]) + u'\n')


def selection(selections, name, kind):
    if name not in selections:
        raise ValueError('Missing {0} selection: {1}'.format(kind, name))
    return selections[name]


def translate(source, target=None, beam_type='B31T', draft=False):
    """Read LIML, create a JSON report and optionally an unsafe diagnostic INP."""
    source = os.path.abspath(source)
    if not os.path.isfile(source):
        raise IOError('Model file not found: {0}'.format(source))
    if beam_type not in ('B31T', 'B31E'):
        raise ValueError('Beam formulation must be B31T or B31E')
    if target is None:
        target = os.path.splitext(source)[0] + '_ccx_draft.inp'
    target = os.path.abspath(target)
    if os.path.normcase(target) == os.path.normcase(source):
        raise ValueError('Output cannot overwrite original LIML')
    root = ET.parse(source).getroot()
    if root.tag != 'liml':
        raise ValueError('Expected LIML XML root')
    errors = []
    nodes = {}
    for item in root.findall('node'):
        nid = int(item.get('nid'))
        if nid in nodes:
            errors.append('Duplicate node ID {0}'.format(nid))
        nodes[nid] = (float(item.get('x')), float(item.get('y')), float(item.get('z')))

    elements = {}
    groups = {}
    for group in root.findall('elset'):
        material = group.get('material')
        for elem in group.findall('elem'):
            eid = int(elem.get('eid'))
            shape = elem.get('shape')
            if shape != 'line2':
                errors.append('Unsupported shape {0} for element {1}'.format(shape, eid))
                continue
            conn = [int(v) for v in elem.get('nodes', '').split()]
            if eid in elements:
                errors.append('Duplicate element ID {0}'.format(eid))
                continue
            if len(conn) != 2 or any(nid not in nodes for nid in conn):
                errors.append('Invalid connectivity for element {0}'.format(eid))
                continue
            elements[eid] = conn
            if material:
                groups.setdefault(material, []).append(eid)
            else:
                errors.append('Element {0} has no section/material'.format(eid))

    materials = index_named(root, 'mat')
    for name in sorted(groups):
        if name not in materials:
            errors.append('Unknown material {0}'.format(name))
        else:
            geo = materials[name].find('geometric')
            kind = geo.get('type') if geo is not None else 'missing'
            errors.append('Unverified UB31 section mapping for {0} (Mecway {1})'.format(name, kind))

    for tag, feature in (('orientation', 'beam local-axis orientation'),
                         ('flexiblejoint', 'beam end releases'),
                         ('offset', 'member offsets')):
        for item in root.findall(tag):
            errors.append('Unsupported {0}: selection {1}'.format(feature, item.get('selection')))

    analysis = root.find('analysis')
    analysis_type = analysis.get('type') if analysis is not None else None
    if analysis_type != 'S30':
        errors.append('Unsupported analysis type: {0}'.format(analysis_type))

    node_selections = index_named(root, 'nodeselection')
    face_selections = index_named(root, 'faceselection')
    applied_forces = []
    for force in root.findall('force'):
        group = selection(node_selections, force.get('selection'), 'node')
        for item in group.findall('node'):
            nid = int(item.get('nid'))
            if nid not in nodes:
                errors.append('Force references missing node {0}'.format(nid))
                continue
            for dof, axis in enumerate(('x', 'y', 'z'), 1):
                value = to_quantity(force.findtext(axis, '0 N'), FORCE)
                if value:
                    applied_forces.append((nid, dof, '{0:.12g}'.format(value)))

    fixed_nodes = set()
    for fixed in root.findall('fixed'):
        group = selection(face_selections, fixed.get('selection'), 'face')
        for face in group.findall('face'):
            eid = int(face.get('eid'))
            fid = int(face.get('faceid'))
            if eid not in elements or fid not in (2, 3):
                errors.append('Invalid fixed face: element {0}, face {1}'.format(eid, fid))
                continue
            # Mecway line2: face 2 is node 1 and face 3 is node 2.
            fixed_nodes.add(elements[eid][fid - 2])

    gravity = []
    for item in root.findall('gravity'):
        vec = [to_quantity(item.findtext(axis, '0 m/s2'), ACCEL)
               for axis in ('x', 'y', 'z')]
        magnitude = math.sqrt(sum(v * v for v in vec))
        if magnitude:
            gravity.append((magnitude, [v / magnitude for v in vec]))

    known = set(('analysis', 'node', 'elset', 'mat', 'nodeselection',
                 'faceselection', 'elementselection', 'fieldvariable',
                 'solution', 'force', 'fixed', 'gravity', 'orientation',
                 'flexiblejoint', 'offset'))
    for item in root:
        if item.tag not in known:
            errors.append('Unmapped LIML feature {0}'.format(item.tag))

    elastic_data = {}
    for name in sorted(groups):
        if name not in materials:
            continue
        mat = materials[name]
        mech = mat.find('mechanical')
        if mech is None or mech.get('type') != 'Isotropic':
            errors.append('Unsupported mechanical material {0}'.format(name))
            continue
        try:
            young = to_quantity(mech.get('youngsmodulus'), STRESS)
            poisson = float(mech.get('poissonratio'))
            density_node = mat.find('density')
            density = (to_quantity(density_node.get('density'), DENSITY)
                       if density_node is not None else None)
            elastic_data[name] = (young, poisson, density)
        except (ValueError, TypeError) as exc:
            errors.append('Material {0} invalid: {1}'.format(name, exc))

    errors = sorted(set(errors))
    report = {
        'version': VERSION, 'source': source, 'element_type': beam_type,
        'analysis': analysis_type, 'nodes': len(nodes),
        'elements': len(elements), 'materials': sorted(groups),
        'element_groups': dict((name, len(items)) for name, items in groups.items()),
        'fixed_nodes': sorted(fixed_nodes), 'nodal_forces': len(applied_forces),
        'gravity_loads': len(gravity), 'errors': errors, 'warnings': [],
        'safe_to_solve': False, 'draft_written': bool(draft)
    }
    report_path = os.path.splitext(target)[0] + '.report.json'
    with io.open(report_path, 'w', encoding='utf-8') as out:
        out.write(json.dumps(report, indent=2, ensure_ascii=True))
        out.write(u'\n')
    if not draft:
        return report

    with io.open(target, 'w', encoding='utf-8') as out:
        out.write(u'** Mecway CCX bridge v{0} - DIAGNOSTIC ONLY\n'.format(VERSION))
        out.write(u'** DO NOT SOLVE: beam sections, releases, offsets, axes unverified\n')
        out.write(u'*HEADING\nMecway diagnostic CCX input\n*NODE\n')
        lines(out, ((nid, '{0:.12g}'.format(p[0]), '{0:.12g}'.format(p[1]),
                     '{0:.12g}'.format(p[2])) for nid, p in sorted(nodes.items())))
        for idx, name in enumerate(sorted(groups), 1):
            out.write(u'*ELEMENT, TYPE={0}, ELSET=BEAM_{1}\n'.format(beam_type, idx))
            lines(out, ((eid, elements[eid][0], elements[eid][1])
                        for eid in sorted(groups[name])))
        out.write(u'** BEAM SECTION CARDS OMITTED: mapping not validated.\n')
        for idx, name in enumerate(sorted(groups), 1):
            if name not in elastic_data:
                continue
            young, poisson, density = elastic_data[name]
            out.write(u'*MATERIAL, NAME=MAT_{0}\n*ELASTIC\n'.format(idx))
            lines(out, [('{0:.12g}'.format(young), '{0:.12g}'.format(poisson))])
            if density is not None:
                out.write(u'*DENSITY\n')
                lines(out, [('{0:.12g}'.format(density),)])
        if gravity:
            out.write(u'*ELSET, ELSET=EALL\n')
            lines(out, ((eid,) for eid in sorted(elements)))
        if fixed_nodes:
            out.write(u'*BOUNDARY\n')
            lines(out, ((nid, 1, 6) for nid in sorted(fixed_nodes)))
        out.write(u'*STEP\n*STATIC\n')
        if applied_forces:
            out.write(u'*CLOAD\n')
            lines(out, applied_forces)
        if gravity:
            out.write(u'*DLOAD\n')
            for magnitude, direction in gravity:
                lines(out, [('EALL', 'GRAV', '{0:.12g}'.format(magnitude)) +
                            tuple('{0:.12g}'.format(v) for v in direction)])
        out.write(u'*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
    return report


def main():
    parser = argparse.ArgumentParser(description='Experimental Mecway CCX bridge')
    parser.add_argument('liml')
    parser.add_argument('--beam', default='B31T', choices=('B31T', 'B31E'))
    parser.add_argument('--draft', action='store_true', help='Diagnostic only')
    parser.add_argument('-o', '--output', default=None)
    args = parser.parse_args()
    report = translate(args.liml, args.output, args.beam, args.draft)
    print('Nodes: {0}; beams: {1}; validation issues: {2}'.format(
        report['nodes'], report['elements'], len(report['errors'])))
    print('SAFE TO SOLVE: NO')
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
