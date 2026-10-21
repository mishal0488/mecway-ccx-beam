# -*- coding: utf-8 -*-
"""
Mecway -> experimental B31T/B31E CalculiX bridge
Stable Mecway-tested single-file IronPython 2.7 / Microsoft.Scripting version.

This is the last version confirmed to run successfully inside Mecway.
No external CPython installation is required.
"""

import os
import sys
import math
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

import clr
clr.AddReference("System")
clr.AddReference("System.Windows.Forms")

from System.Windows.Forms import OpenFileDialog, SaveFileDialog, DialogResult, MessageBox

BEAM_TYPE = "B31T"

LENGTH = {'m': 1.0, 'mm': 0.001, 'cm': 0.01}
FORCE = {'N': 1.0, 'kN': 1000.0, 'MN': 1000000.0}
STRESS = {'Pa': 1.0, 'kPa': 1000.0, 'MPa': 1000000.0, 'GPa': 1000000000.0}
DENSITY = {'kg/m³': 1.0, 'kg/m3': 1.0}
ACCEL = {'m/s²': 1.0, 'm/s2': 1.0}


def quantity(text, units):
    import re
    s = str(text).strip()
    m = re.match(r'^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*)$', s)
    if not m:
        raise Exception("Cannot parse quantity: " + s)
    value = float(m.group(1))
    unit = m.group(2).strip()
    if unit not in units:
        raise Exception("Unexpected unit '%s' in '%s'" % (unit, s))
    return value * units[unit]


def selected(root, tag, name):
    for node in root.findall(tag):
        if node.get('name') == name:
            return node
    raise Exception("Missing selection %s: %s" % (tag, name))


def write_data(f, rows):
    for row in rows:
        f.write(', '.join([str(x) for x in row]) + '\n')


def translate(source, target, beam_type):
    tree = ET.parse(source)
    root = tree.getroot()

    if root.tag != 'liml':
        raise Exception("Input does not have a LIML root")

    errors = []
    warnings = []

    nodes = {}
    for n in root.findall('node'):
        nodes[int(n.get('nid'))] = (
            float(n.get('x')),
            float(n.get('y')),
            float(n.get('z'))
        )

    elements = {}
    groups = defaultdict(list)

    for group in root.findall('elset'):
        mat = group.get('material')
        for el in group.findall('elem'):
            eid = int(el.get('eid'))
            shape = el.get('shape')

            if shape != 'line2':
                errors.append("Unsupported element %s, shape %s" % (eid, shape))
                continue

            conn = tuple([int(x) for x in el.get('nodes').split()])

            if len(conn) != 2:
                errors.append("Bad connectivity for element %s" % eid)
                continue

            bad = False
            for nid in conn:
                if nid not in nodes:
                    bad = True
            if bad:
                errors.append("Bad connectivity for element %s" % eid)
                continue

            elements[eid] = conn

            if mat:
                groups[mat].append(eid)
            else:
                errors.append("Element %s has no section/material" % eid)

    mats = {}
    for m in root.findall('mat'):
        mats[m.get('name')] = m

    for item in root.findall('flexiblejoint'):
        errors.append(
            "Unsupported Mecway beam end release (%s); release mapping not implemented yet"
            % item.get('selection', '?')
        )

    for item in root.findall('offset'):
        errors.append(
            "Unsupported Mecway geometric member offset (%s); mapping not implemented yet"
            % item.get('selection', '?')
        )

    for item in root.findall('orientation'):
        errors.append(
            "Unverified beam orientation (%s); orientation mapping not implemented yet"
            % item.get('selection', '?')
        )

    for name in groups:
        if name in mats:
            geo = mats[name].find('geometric')
            typ = geo.get('type') if geo is not None else '?'
            errors.append(
                "Unverified section geometry for %s (Mecway type %s)"
                % (name, typ)
            )

    analysis = root.find('analysis')
    analysis_type = analysis.get('type') if analysis is not None else None

    cloads = []
    for load in root.findall('force'):
        selname = load.get('selection')
        try:
            sel = selected(root, 'nodeselection', selname)
        except:
            continue

        for n in sel.findall('node'):
            nid = int(n.get('nid'))
            dof = 1
            for axis in ('x', 'y', 'z'):
                value = quantity(load.findtext(axis, '0 N'), FORCE)
                if value != 0.0:
                    cloads.append((nid, dof, "%.12g" % value))
                dof += 1

    constraints = set()
    for fixed in root.findall('fixed'):
        selname = fixed.get('selection')
        try:
            sel = selected(root, 'faceselection', selname)
        except:
            continue

        for face in sel.findall('face'):
            eid = int(face.get('eid'))
            fid = int(face.get('faceid'))

            if eid not in elements or fid not in (2, 3):
                errors.append(
                    "Cannot map fixed face element %s, face %s" % (eid, fid)
                )
                continue

            node = elements[eid][fid - 2]
            constraints.add(node)

    gravities = []
    for gravity in root.findall('gravity'):
        vector = []
        for axis in ('x', 'y', 'z'):
            vector.append(
                quantity(gravity.findtext(axis, '0 m/s²'), ACCEL)
            )

        magnitude = math.sqrt(sum([v*v for v in vector]))

        if magnitude:
            gravities.append((
                "%.12g" % magnitude,
                "%.12g" % (vector[0] / magnitude),
                "%.12g" % (vector[1] / magnitude),
                "%.12g" % (vector[2] / magnitude)
            ))

    report = {
        'source': source,
        'element_type': beam_type,
        'analysis': analysis_type,
        'nodes': len(nodes),
        'elements': len(elements),
        'materials': sorted(groups.keys()),
        'errors': sorted(list(set(errors))),
        'warnings': sorted(list(set(warnings))),
        'safe_to_solve': len(errors) == 0
    }

    report_path = os.path.splitext(target)[0] + ".report.json"
    rf = open(report_path, "w")
    try:
        rf.write(json.dumps(report, indent=2))
    finally:
        rf.close()

    f = open(target, "w")
    try:
        f.write("** Experimental Mecway CCX bridge - IronPython\n")
        if errors:
            f.write("** DO NOT SOLVE: UNVERIFIED/UNIMPLEMENTED MODEL FEATURES\n")
        else:
            f.write("** Validated bridge output\n")

        f.write("*HEADING\n")
        f.write("Mecway experimental input\n")
        f.write("*NODE\n")

        rows = []
        for nid in sorted(nodes.keys()):
            rows.append((nid, nodes[nid][0], nodes[nid][1], nodes[nid][2]))
        write_data(f, rows)

        idx = 1
        for name in groups:
            label = "BEAM_%s" % idx
            f.write("*ELEMENT, TYPE=%s, ELSET=%s\n" % (beam_type, label))

            rows = []
            for eid in sorted(groups[name]):
                rows.append((eid, elements[eid][0], elements[eid][1]))
            write_data(f, rows)

            idx += 1

        f.write("** SECTION CARDS OMITTED: section mapping not yet verified.\n")

        if constraints:
            f.write("*BOUNDARY\n")
            rows = []
            for node in sorted(constraints):
                rows.append((node, 1, 6))
            write_data(f, rows)

        f.write("*STEP\n")
        f.write("*STATIC\n")

        if cloads:
            f.write("*CLOAD\n")
            write_data(f, cloads)

        if gravities:
            f.write("** Gravity detected but EALL generation still needs verification.\n")

        f.write("*NODE FILE\n")
        f.write("U\n")
        f.write("*EL FILE\n")
        f.write("S\n")
        f.write("*END STEP\n")

    finally:
        f.close()

    return report_path, errors


def main():
    picker = OpenFileDialog()
    picker.Title = "Select saved Mecway LIML model"
    picker.Filter = "Mecway models (*.liml)|*.liml|All files (*.*)|*.*"

    if picker.ShowDialog() != DialogResult.OK:
        return

    source = str(picker.FileName)
    target = os.path.splitext(source)[0] + ".inp"

    try:
        report_path, errors = translate(source, target, BEAM_TYPE)

        msg = (
            "Input written:\n%s\n\n"
            "Report written:\n%s\n\n"
            "Element type: %s\n"
            "Validation issues: %s"
        ) % (
            target,
            report_path,
            BEAM_TYPE,
            len(errors)
        )

        if errors:
            msg += (
                "\n\nThe file is a DRAFT only. "
                "Section/orientation/release mapping is not yet complete."
            )

        MessageBox.Show(msg, "Mecway CCX Bridge")

    except Exception as exc:
        MessageBox.Show(
            "Bridge error:\n%s" % str(exc),
            "Mecway CCX Bridge"
        )
        raise


main()
