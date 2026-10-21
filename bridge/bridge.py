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

VERSION = '0.5'
FLOAT_RE = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$')
FORCE = {'N': 1.0, 'kN': 1000.0, 'MN': 1000000.0}
STRESS = {'Pa': 1.0, 'kPa': 1.0e3, 'MPa': 1.0e6, 'GPa': 1.0e9}
DENSITY = {'kg/m3': 1.0, u'kg/m\u00b3': 1.0}
ACCEL = {'m/s2': 1.0, u'm/s\u00b2': 1.0}
LENGTH = {'m':1., 'mm':.001, 'cm':.01, 'km':1000., 'in':.0254, 'inch':.0254, 'ft':.3048}
ANGLE = {'rad':1., 'deg':math.pi/180., u'\u00b0':math.pi/180., '':1.}


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


def finite(x):
    return not (math.isnan(x) or math.isinf(x))


def fmt(x):
    return '{0:.12g}'.format(x)


def geom_ub31(g):
    """Mecway section geometry -> (UB31 shape, dimension tuple, area)."""
    if g is None:
        raise ValueError('Missing geometric section')
    kind = g.get('type')
    def dim(k):
        value = to_quantity(g.get(k), LENGTH)
        if value <= 0 or not finite(value):
            raise ValueError('Invalid nonpositive dimension ' + k)
        return value
    if kind == 'I':
        h,b,tf,tw = [dim('i'+k) for k in 'abcd']
        if 2*tf >= h or tw >= b:
            raise ValueError('I-section flange/web dimensions inconsistent')
        return 'I', (h,b,tf,b,tf,tw), 2*b*tf+(h-2*tf)*tw
    if kind == 'C':
        b,h,tf,tw = [dim('c'+k) for k in 'abcd']
        if 2*tf >= h or tw >= b:
            raise ValueError('Channel flange/web dimensions inconsistent')
        return 'CHAN', (h,b,tf,tw), 2*b*tf+(h-2*tf)*tw
    if kind == 'L':
        b,h,t = [dim('l'+k) for k in 'abc']
        if t >= min(b,h):
            raise ValueError('Angle thickness exceeds leg dimension')
        return 'L', (b,h,t), t*(b+h-t)
    if kind == 'RectBar':
        b,h = dim('recta'),dim('rectb')
        return 'RECT',(b,h),b*h
    if kind == 'CircularBar':
        d = dim('roundod')
        return 'CIRC',(d/2.,),math.pi*d*d/4.
    if kind == 'UniformCircularTube':
        od, di = dim('roundod'),dim('roundid')
        if di >= od:
            raise ValueError('Tube inner diameter >= outer diameter')
        return 'PIPE',(od/2.,(od-di)/2.),math.pi*(od*od-di*di)/4.
    if kind == 'RectTube':
        b,h,t = dim('recta'),dim('rectb'),dim('rectthickness')
        if 2*t >= min(b,h):
            raise ValueError('Tube wall thickness exceeds half width')
        return 'BOX',(h,b,t,t,t,t),b*h-(b-2*t)*(h-2*t)
    raise ValueError('Unsupported section type ' + str(kind))


def dot3(a,b):
    return sum(a[i]*b[i] for i in range(3))


def unit3(a):
    length = math.sqrt(dot3(a,a))
    if length <= 1.e-14:
        raise ValueError('Zero-length vector')
    return tuple(x/length for x in a)


def cross3(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def beam_v(p,q,orient=None):
    """Mecway transverse V: project vector then rotate around U (right-handed)."""
    u = unit3(tuple(q[i]-p[i] for i in range(3)))
    if orient:
        vec, angle = orient
        v = tuple(vec[i]-dot3(vec,u)*u[i] for i in range(3))
        if dot3(v,v) <= 1.e-18*dot3(vec,vec):
            raise ValueError('Specified V axis parallel to beam')
        v=unit3(v); w=cross3(u,v)
        return unit3(tuple(v[i]*math.cos(angle)+w[i]*math.sin(angle)
                           for i in range(3)))
    if math.sqrt(u[0]**2+u[1]**2) < 1.e-4*abs(u[2]):
        return (0.,1.,0.)
    return unit3(cross3((0.,0.,1.),u))


def all_beam_axes(root,elements,nodes,errors):
    """Selection-based <orientation> plus legacy element attributes."""
    selections = index_named(root,'elementselection')
    assigned={}
    for card in root.findall('orientation'):
        if card.get('suppressed') == 'true':
            continue
        selection_name=card.get('selection')
        selection=selections.get(selection_name)
        if selection is None:
            errors.append('Missing orientation selection: ' + str(selection_name))
            continue
        try:
            vec=tuple(float(card.findtext(x,'0')) for x in ('vx','vy','vz'))
            if dot3(vec,vec) <= 0 or not all(finite(x) for x in vec):
                raise ValueError('Bad V vector')
            angle=to_quantity(card.findtext('angleu','0 rad'),ANGLE)
            orient=(vec,angle)
        except (ValueError,TypeError) as exc:
            errors.append('Orientation {0}: {1}'.format(selection_name,exc))
            continue
        for e in selection.findall('element'):
            eid=int(e.get('eid'))
            if eid not in elements:
                errors.append('Orientation refers to missing beam ' + str(eid))
            elif eid in assigned and assigned[eid] != orient:
                errors.append('Conflicting V-axis orientation on beam ' + str(eid))
            else:
                assigned[eid]=orient
    for group in root.findall('elset'):
        for el in group.findall('elem'):
            attrs=('orientationvx','orientationvy','orientationvz')
            if not any(el.get(x) is not None for x in attrs):
                continue
            eid=int(el.get('eid'))
            if eid not in elements:
                continue
            try:
                vec=tuple(float(el.get(x,'0')) for x in attrs)
                orient=(vec,to_quantity(el.get('angle','0 rad'),ANGLE))
                if eid in assigned and assigned[eid] != orient:
                    errors.append('Conflicting card/element axes ' + str(eid))
                else:
                    assigned[eid]=orient
            except (TypeError,ValueError) as exc:
                errors.append('Bad element orientation {0}: {1}'.format(eid,exc))
    axes={}
    for eid,conn in sorted(elements.items()):
        try:
            axes[eid]=beam_v(nodes[conn[0]],nodes[conn[1]],assigned.get(eid))
        except ValueError as exc:
            errors.append('Beam {0}: {1}'.format(eid,exc))
    return axes,assigned


def beam_frame(p,q,v):
    """Return right-handed local U,V,W unit vectors for one beam."""
    u=unit3(tuple(q[i]-p[i] for i in range(3)))
    v=unit3(tuple(v[i]-dot3(v,u)*u[i] for i in range(3)))
    w=unit3(cross3(u,v))
    return u,v,w


def read_offset_card(card):
    """Read Mecway <offset> as either global X/Y/Z or local U/V/W."""
    global_axes=any(card.find(k) is not None for k in ('x','y','z'))
    local_axes=any(card.find(k) is not None for k in ('u','v','w'))
    if global_axes and local_axes:
        raise ValueError('Offset mixes global X/Y/Z and local U/V/W components')
    if not global_axes and not local_axes:
        return 'global',(0.,0.,0.)
    names=(('x','y','z') if global_axes else ('u','v','w'))
    vec=tuple(to_quantity(card.findtext(k,'0 m'),LENGTH) for k in names)
    if not all(finite(x) for x in vec):
        raise ValueError('Offset components must be finite')
    return ('global' if global_axes else 'local'),vec


def all_beam_offsets(root,elements,nodes,axes,errors):
    """Map Mecway element offsets to local UB31 U/V/W vectors per element."""
    selections=index_named(root,'elementselection')
    offsets={}
    for card in root.findall('offset'):
        if card.get('suppressed') == 'true':
            continue
        name=card.get('selection')
        chosen=selections.get(name)
        if chosen is None:
            errors.append('Missing offset element selection: ' + str(name))
            continue
        try:
            frame,vec=read_offset_card(card)
        except (ValueError,TypeError) as exc:
            errors.append('Offset {0}: {1}'.format(name,exc))
            continue
        for item in chosen.findall('element'):
            eid=int(item.get('eid'))
            if eid not in elements or eid not in axes:
                errors.append('Offset refers to missing/non-beam element ' + str(eid))
                continue
            if eid in offsets:
                errors.append('Overlapping offset definitions on beam ' + str(eid))
                continue
            if frame == 'local':
                local=vec
            else:
                conn=elements[eid]
                u,v,w=beam_frame(nodes[conn[0]],nodes[conn[1]],axes[eid])
                local=(dot3(vec,u),dot3(vec,v),dot3(vec,w))
            offsets[eid]=local
    return offsets


def all_beam_releases(root,elements,errors):
    """Map Mecway flexiblejoint face selections to UB31 release bitmasks.

    Mecway rotu/rotv/rotw are rotations about local U/V/W. UB31 uses
    T/RX=8, M1/RY=16, M2/RZ=32. Mecway line2 face 2 is end 1 and
    face 3 is end 2.
    """
    selections=index_named(root,'faceselection')
    releases={}
    bits={'rotu':8,'rotv':16,'rotw':32}
    for card in root.findall('flexiblejoint'):
        if card.get('suppressed') == 'true':
            continue
        name=card.get('selection')
        chosen=selections.get(name)
        if chosen is None:
            errors.append('Missing flexible-joint face selection: ' + str(name))
            continue
        code=0
        invalid=False
        for child in list(card):
            if child.tag not in bits or child.attrib or (child.text or '').strip():
                invalid=True
                break
            code |= bits[child.tag]
        if invalid or code == 0:
            errors.append('Flexible joint {0}: only free rotu/rotv/rotw releases are supported'.format(name))
            continue
        for face in chosen.findall('face'):
            eid=int(face.get('eid'))
            fid=int(face.get('faceid'))
            if eid not in elements or fid not in (2,3):
                errors.append('Invalid flexible-joint face: element {0}, face {1}'.format(eid,fid))
                continue
            end=(1 if fid == 2 else 2)
            key=(eid,end)
            releases[key]=releases.get(key,0) | code
    return releases


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
    section_specs={}
    for name in sorted(groups):
        if name not in materials:
            errors.append('Unknown material ' + name)
            continue
        try:
            section_specs[name]=geom_ub31(materials[name].find('geometric'))
        except ValueError as exc:
            errors.append('Material {0}: {1}'.format(name,exc))
    axes,assigned=all_beam_axes(root,elements,nodes,errors)
    offsets=all_beam_offsets(root,elements,nodes,axes,errors)
    releases=all_beam_releases(root,elements,errors)
    if any(spec[0]=='L' for spec in section_specs.values()):
        errors.append('L principal-axis rotation vs Mecway V unverified in patched UB31')

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

    # Each BEAM SECTION carries one V axis and one uniform local offset.
    # Split by material + V axis + local U/V/W offset.
    subsets={}
    for name,eids in groups.items():
        for eid in eids:
            if eid in axes:
                off=offsets.get(eid,(0.,0.,0.))
                key=(name,tuple(round(x,9) for x in axes[eid]),
                     tuple(round(x,9) for x in off))
                subsets.setdefault(key,[]).append(eid)
    sorted_keys=sorted(subsets)
    sections_report=dict((name,{'ccx_section':spec[0],
                                'dimensions_m':list(spec[1]),'area_m2':spec[2]})
                         for name,spec in section_specs.items())
    errors = sorted(set(errors))
    report = {
        'version': VERSION, 'source': source, 'element_type': beam_type,
        'analysis': analysis_type, 'nodes': len(nodes),
        'elements': len(elements), 'materials': sorted(groups),
        'section_definitions': sections_report,
        'oriented_elements': len(assigned),
        'offset_elements': len(offsets),
        'released_element_ends': len(releases),
        'beam_section_orientation_groups': len(sorted_keys),
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
        out.write(u'** DO NOT SOLVE: L-section principal-axis equivalence still requires regression\n')
        out.write(u'*HEADING\nMecway diagnostic CCX input\n*NODE\n')
        lines(out, ((nid, '{0:.12g}'.format(p[0]), '{0:.12g}'.format(p[1]),
                     '{0:.12g}'.format(p[2])) for nid, p in sorted(nodes.items())))
        for idx,key in enumerate(sorted_keys,1):
            out.write(u'*ELEMENT, TYPE={0}, ELSET=BEAM_{1:04d}\n'.format(beam_type,idx))
            lines(out, ((eid,elements[eid][0],elements[eid][1])
                        for eid in sorted(subsets[key])))
        mat_names=dict((name,'MAT_{0:03d}'.format(i))
                       for i,name in enumerate(sorted(groups),1))
        for name in sorted(groups):
            if name not in elastic_data:
                continue
            young,poisson,density=elastic_data[name]
            out.write(u'*MATERIAL, NAME={0}\n*ELASTIC\n'.format(mat_names[name]))
            lines(out,[(fmt(young),fmt(poisson))])
            if density is not None:
                out.write(u'*DENSITY\n')
                lines(out,[(fmt(density),)])
        for idx,key in enumerate(sorted_keys,1):
            name=key[0]
            if name not in section_specs or name not in elastic_data:
                continue
            shape,dims,area=section_specs[name]
            out.write(u'** Mecway section {0} ideal area {1} m2\n'.format(name,fmt(area)))
            offset=key[2]
            header=u'*BEAM SECTION, ELSET=BEAM_{0:04d}, MATERIAL={1}, SECTION={2}'.format(
                idx,mat_names[name],shape)
            if any(abs(x) > 1.e-14 for x in offset):
                vals=u','.join(fmt(x) for x in offset)
                header += u', OFFSET1=({0}), OFFSET2=({0})'.format(vals)
            out.write(header + u'\n')
            lines(out,[tuple(fmt(x) for x in dims)])
            eid=subsets[key][0]
            lines(out,[tuple(fmt(x) for x in axes[eid])])
        if releases:
            out.write(u'*USER BEAM RELEASE\n')
            lines(out, ((eid,end,code) for (eid,end),code in sorted(releases.items())))
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
    print('Nodes: {0}; beams: {1}; V-groups: {2}; issues: {3}'.format(
        report['nodes'],report['elements'],
        report['beam_section_orientation_groups'],len(report['errors'])))
    print('SAFE TO SOLVE: NO')
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
