# -*- coding: utf-8 -*-
"""Mecway -> patched CalculiX solver comparison launcher v1.1.

Single Mecway/IronPython launcher.
No external CPython installation required.

Workflow:
1. Save active Mecway LIML.
2. Generate B31T test deck using bridge.py.
3. Locate user's patched ccx.exe (first run only).
4. Run: ccx.exe -i <jobname>
5. Save stdout/stderr to <jobname>.ccx_run.log.\n6. Request U/RF/S ASCII results in <jobname>.dat.
"""

from __future__ import print_function

import io
import os
import sys
import traceback

import clr
clr.AddReference("System")
clr.AddReference("System.Windows.Forms")

from System.Diagnostics import Process, ProcessStartInfo
from System.Windows.Forms import OpenFileDialog, DialogResult

BEAM_TYPE = 'B31T'
LAUNCHER_VERSION = '1.1'


def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _ccx_config_path():
    return os.path.join(_script_dir(), 'ccx_executable.txt')


def _read_saved_ccx():
    path = _ccx_config_path()

    if not os.path.isfile(path):
        return None

    try:
        with io.open(path, 'r', encoding='utf-8') as handle:
            value = handle.read().strip()

        if value and os.path.isfile(value):
            return value

    except Exception:
        pass

    return None


def _choose_ccx():
    picker = OpenFileDialog()
    picker.Title = 'Select your patched CalculiX executable'
    picker.Filter = (
        'CalculiX executable (*.exe)|*.exe|'
        'All files (*.*)|*.*'
    )

    if picker.ShowDialog() != DialogResult.OK:
        return None

    path = str(picker.FileName)

    if not os.path.isfile(path):
        raise RuntimeError(
            'Selected CCX executable does not exist:\n' + path
        )

    try:
        with io.open(
            _ccx_config_path(),
            'w',
            encoding='utf-8'
        ) as handle:
            handle.write(path)
            handle.write(u'\n')

    except Exception:
        # Failing to remember the path should not block a solve.
        pass

    return path


def _get_ccx():
    path = _read_saved_ccx()

    if path:
        return path

    return _choose_ccx()


def _quote_arg(value):
    # ProcessStartInfo.Arguments is one Windows command-line string.
    # Doubling internal quotes is enough for normal Windows paths here.
    return '"' + value.replace('"', '""') + '"'


def _run_ccx(ccx_path, input_path):
    workdir = os.path.dirname(input_path)
    filename = os.path.basename(input_path)

    if not filename.lower().endswith('.inp'):
        raise RuntimeError(
            'Generated CCX input does not end in .inp'
        )

    jobname = filename[:-4]

    psi = ProcessStartInfo()
    psi.FileName = ccx_path
    psi.WorkingDirectory = workdir
    psi.Arguments = '-i ' + _quote_arg(jobname)
    psi.UseShellExecute = False
    psi.RedirectStandardOutput = True
    psi.RedirectStandardError = True
    psi.CreateNoWindow = True

    proc = Process()
    proc.StartInfo = psi

    if not proc.Start():
        raise RuntimeError(
            'Windows could not start the CCX executable.'
        )

    stdout = proc.StandardOutput.ReadToEnd()
    stderr = proc.StandardError.ReadToEnd()

    proc.WaitForExit()
    exit_code = proc.ExitCode

    log_path = os.path.join(
        workdir,
        jobname + '.ccx_run.log'
    )

    with io.open(
        log_path,
        'w',
        encoding='utf-8'
    ) as handle:
        handle.write(
            u'MECWAY CCX BRIDGE SOLVER TEST v{0}\n'.format(
                LAUNCHER_VERSION
            )
        )
        handle.write(
            u'CCX executable: {0}\n'.format(
                ccx_path
            )
        )
        handle.write(
            u'Working directory: {0}\n'.format(
                workdir
            )
        )
        handle.write(
            u'Command: {0} -i "{1}"\n'.format(
                ccx_path,
                jobname
            )
        )
        handle.write(
            u'Exit code: {0}\n\n'.format(
                exit_code
            )
        )

        handle.write(u'===== STDOUT =====\n')
        handle.write(stdout or u'')
        handle.write(u'\n===== STDERR =====\n')
        handle.write(stderr or u'')
        handle.write(u'\n')

    expected = {}

    for ext in (
        '.frd',
        '.dat',
        '.sta',
        '.cvg'
    ):
        p = os.path.join(
            workdir,
            jobname + ext
        )
        expected[ext] = p if os.path.isfile(p) else None

    combined = (
        (stdout or '') +
        '\n' +
        (stderr or '')
    ).upper()

    contains_error = '*ERROR' in combined

    dat_size = 0
    if expected['.dat'] is not None:
        try:
            dat_size = os.path.getsize(expected['.dat'])
        except Exception:
            dat_size = 0

    success = (
        exit_code == 0 and
        not contains_error and
        expected['.frd'] is not None and
        expected['.dat'] is not None and
        dat_size > 0
    )

    return {
        'jobname': jobname,
        'workdir': workdir,
        'exit_code': exit_code,
        'contains_error': contains_error,
        'success': success,
        'log_path': log_path,
        'frd': expected['.frd'],
        'dat': expected['.dat'],
        'sta': expected['.sta'],
        'cvg': expected['.cvg'],
        'dat_size': dat_size
    }


def _parse_dat(dat_path):
    result = {
        'displacements': {},
        'forces': {}
    }

    if not dat_path or not os.path.isfile(dat_path):
        return result

    with io.open(
        dat_path,
        'r',
        encoding='utf-8',
        errors='replace'
    ) as handle:
        rows = handle.readlines()

    mode = None

    for raw in rows:
        line = raw.strip()
        low = line.lower()

        if low.startswith('displacements ('):
            mode = 'displacements'
            continue

        if low.startswith('forces ('):
            mode = 'forces'
            continue

        if low.startswith('stresses ('):
            mode = None
            continue

        if not line:
            continue

        parts = line.split()

        if not parts or not parts[0].isdigit():
            continue

        try:
            nid = int(parts[0])

            if mode == 'displacements' and len(parts) >= 7:
                result['displacements'][nid] = [
                    float(x.replace('D', 'E'))
                    for x in parts[1:7]
                ]

            elif mode == 'forces' and len(parts) >= 4:
                result['forces'][nid] = [
                    float(x.replace('D', 'E'))
                    for x in parts[1:4]
                ]

        except Exception:
            pass

    return result


def _parse_beam_csv(csv_path):
    result = {
        'rows': 0,
        'max_combined_stress_Pa': 0.0,
        'max_stress_element': None,
        'max_stress_station_pct': None,
        'max_axial_force_N': 0.0,
        'max_shear_N': 0.0,
        'max_bending_moment_Nm': 0.0,
        'max_torsion_Nm': 0.0
    }

    if not os.path.isfile(csv_path):
        return result

    with io.open(
        csv_path,
        'r',
        encoding='utf-8',
        errors='replace'
    ) as handle:
        rows = handle.readlines()

    if not rows:
        return result

    header = [
        x.strip()
        for x in rows[0].strip().split(',')
    ]

    index = dict(
        (name, i)
        for i, name in enumerate(header)
    )

    needed = (
        'Element',
        'Station_Pct',
        'Fx_Axial',
        'Vy_Shear',
        'Vz_Shear',
        'Mx_Torsion',
        'My_Bending',
        'Mz_Bending',
        'Sxx_Max_Combined'
    )

    if not all(name in index for name in needed):
        return result

    for raw in rows[1:]:
        parts = [
            x.strip()
            for x in raw.strip().split(',')
        ]

        if len(parts) < len(header):
            continue

        try:
            eid = int(parts[index['Element']])
            station = int(parts[index['Station_Pct']])

            axial = abs(
                float(parts[index['Fx_Axial']])
            )

            vy = float(parts[index['Vy_Shear']])
            vz = float(parts[index['Vz_Shear']])

            shear = (
                vy * vy +
                vz * vz
            ) ** 0.5

            torsion = abs(
                float(parts[index['Mx_Torsion']])
            )

            my = float(parts[index['My_Bending']])
            mz = float(parts[index['Mz_Bending']])

            bending = (
                my * my +
                mz * mz
            ) ** 0.5

            combined = abs(
                float(parts[index['Sxx_Max_Combined']])
            )

            result['rows'] += 1

            if axial > result['max_axial_force_N']:
                result['max_axial_force_N'] = axial

            if shear > result['max_shear_N']:
                result['max_shear_N'] = shear

            if torsion > result['max_torsion_Nm']:
                result['max_torsion_Nm'] = torsion

            if bending > result['max_bending_moment_Nm']:
                result['max_bending_moment_Nm'] = bending

            if combined > result['max_combined_stress_Pa']:
                result['max_combined_stress_Pa'] = combined
                result['max_stress_element'] = eid
                result['max_stress_station_pct'] = station

        except Exception:
            pass

    return result


def _vector_sum(vectors):
    total = [0.0, 0.0, 0.0]

    for vec in vectors:
        for i in range(3):
            total[i] += vec[i]

    return total


def _vector_norm(vec):
    return (
        vec[0] * vec[0] +
        vec[1] * vec[1] +
        vec[2] * vec[2]
    ) ** 0.5


def _write_validation(
    output_path,
    report,
    dat_result,
    beam_result,
    beam_csv_path
):
    jobroot = os.path.splitext(output_path)[0]
    validation_path = jobroot + '.validation.txt'

    fixed = report.get(
        'fixed_nodes',
        []
    )

    reactions = _vector_sum(
        [
            dat_result['forces'][nid]
            for nid in fixed
            if nid in dat_result['forces']
        ]
    )

    applied = report.get(
        'applied_force_vector_N',
        [0.0, 0.0, 0.0]
    )

    body = report.get(
        'body_force_vector_N',
        [0.0, 0.0, 0.0]
    )

    residual = [
        reactions[i] +
        applied[i] +
        body[i]
        for i in range(3)
    ]

    max_node = None
    max_disp = 0.0
    max_components = None

    for nid, values in dat_result['displacements'].items():
        mag = (
            values[0] * values[0] +
            values[1] * values[1] +
            values[2] * values[2]
        ) ** 0.5

        if mag > max_disp:
            max_disp = mag
            max_node = nid
            max_components = values[:3]

    with io.open(
        validation_path,
        'w',
        encoding='utf-8'
    ) as handle:
        handle.write(
            u'MECWAY CCX BRIDGE NUMERICAL VALIDATION v0.9\n\n'
        )

        handle.write(
            u'Model mass: {0:.9g} kg\n'.format(
                report.get('model_mass_kg', 0.0)
            )
        )

        handle.write(
            u'Applied nodal force [N]: '
            u'{0:.9g}, {1:.9g}, {2:.9g}\n'.format(
                applied[0],
                applied[1],
                applied[2]
            )
        )

        handle.write(
            u'Gravity/body force [N]: '
            u'{0:.9g}, {1:.9g}, {2:.9g}\n'.format(
                body[0],
                body[1],
                body[2]
            )
        )

        handle.write(
            u'Support reaction sum [N]: '
            u'{0:.9g}, {1:.9g}, {2:.9g}\n'.format(
                reactions[0],
                reactions[1],
                reactions[2]
            )
        )

        handle.write(
            u'Force equilibrium residual [N]: '
            u'{0:.9g}, {1:.9g}, {2:.9g}\n'.format(
                residual[0],
                residual[1],
                residual[2]
            )
        )

        handle.write(
            u'Force equilibrium residual norm [N]: '
            u'{0:.9g}\n\n'.format(
                _vector_norm(residual)
            )
        )

        handle.write(
            u'Max nodal translation: {0:.9g} m at node {1}\n'.format(
                max_disp,
                max_node
            )
        )

        if max_components:
            handle.write(
                u'  Ux,Uy,Uz = '
                u'{0:.9g}, {1:.9g}, {2:.9g} m\n\n'.format(
                    max_components[0],
                    max_components[1],
                    max_components[2]
                )
            )

        handle.write(
            u'Beam CSV: {0}\n'.format(
                beam_csv_path
            )
        )

        handle.write(
            u'Beam station rows: {0}\n'.format(
                beam_result['rows']
            )
        )

        handle.write(
            u'Max |axial force|: {0:.9g} N\n'.format(
                beam_result['max_axial_force_N']
            )
        )

        handle.write(
            u'Max resultant shear: {0:.9g} N\n'.format(
                beam_result['max_shear_N']
            )
        )

        handle.write(
            u'Max |torsion|: {0:.9g} N.m\n'.format(
                beam_result['max_torsion_Nm']
            )
        )

        handle.write(
            u'Max resultant bending moment: {0:.9g} N.m\n'.format(
                beam_result['max_bending_moment_Nm']
            )
        )

        handle.write(
            u'Max combined normal stress: {0:.9g} Pa '
            u'({1:.6g} MPa) at element {2}, station {3}%\n'.format(
                beam_result['max_combined_stress_Pa'],
                beam_result['max_combined_stress_Pa'] / 1.0e6,
                beam_result['max_stress_element'],
                beam_result['max_stress_station_pct']
            )
        )

        handle.write(
            u'\nNOTE: Generic *EL PRINT S output for UB31 is a mixed '
            u'beam-results carrier. Use the dedicated beam CSV for '
            u'internal force/stress interpretation.\n'
        )

    return validation_path, residual, max_node, max_disp

def _mecway_value(name, nid, last_step=None):
    """Safely read a Mecway solution node value."""

    try:
        if last_step is None:
            return solution.node_value(name, nid)
        return solution.node_value(name, nid, last_step)
    except Exception:
        try:
            return solution.node_value(name, nid)
        except Exception:
            return None


def _capture_mecway_solution():
    """Solve the current model with Mecway and capture nodal baseline results."""

    mw.message(
        'v1.0 comparison test:\n\n'
        'Mecway will solve the current model first to establish the '
        'independent reference solution. The model file itself was saved '
        'before this solve.'
    )

    mw.solve()

    try:
        nodes = list(solution.all_nodes() or [])
    except Exception:
        nodes = []

    if not nodes:
        raise RuntimeError(
            'Mecway solve returned no solution nodes.'
        )

    last_step = None

    try:
        steps = list(solution.time_steps() or [])
        if steps:
            last_step = steps[-1]
    except Exception:
        last_step = None

    names = (
        'displx',
        'disply',
        'displz',
        'rotx',
        'roty',
        'rotz',
        'reactionforcex',
        'reactionforcey',
        'reactionforcez'
    )

    values = dict(
        (name, {})
        for name in names
    )

    for node_obj in nodes:
        try:
            nid = int(node_obj)
        except Exception:
            try:
                nid = int(str(node_obj))
            except Exception:
                continue

        for name in names:
            value = _mecway_value(
                name,
                nid,
                last_step
            )

            if value is not None:
                try:
                    values[name][nid] = float(value)
                except Exception:
                    pass

    return {
        'nodes': sorted(
            set(
                nid
                for vals in values.values()
                for nid in vals
            )
        ),
        'values': values,
        'last_step': last_step
    }


def _write_mecway_comparison(
    output_path,
    report,
    baseline,
    dat_result
):
    root = os.path.splitext(output_path)[0]
    csv_path = root + '.mecway_compare.csv'
    txt_path = root + '.mecway_compare.txt'

    mapping = (
        ('displx', 0, 'displacements', 'm'),
        ('disply', 1, 'displacements', 'm'),
        ('displz', 2, 'displacements', 'm'),
        ('rotx',   3, 'displacements', 'rad'),
        ('roty',   4, 'displacements', 'rad'),
        ('rotz',   5, 'displacements', 'rad'),
        ('reactionforcex', 0, 'forces', 'N'),
        ('reactionforcey', 1, 'forces', 'N'),
        ('reactionforcez', 2, 'forces', 'N')
    )

    summaries = []

    with io.open(
        csv_path,
        'w',
        encoding='utf-8'
    ) as csv:
        csv.write(
            u'node,variable,unit,mecway,ccx,difference,absolute_difference\n'
        )

        for name, idx, ccx_group, unit in mapping:
            mec = baseline['values'].get(
                name,
                {}
            )

            ccx = dat_result.get(
                ccx_group,
                {}
            )

            common = sorted(
                set(mec) &
                set(ccx)
            )

            rows = []
            max_mec = 0.0
            max_ccx = 0.0
            max_diff = 0.0
            max_node = None
            sum_sq = 0.0

            for nid in common:
                try:
                    a = float(mec[nid])
                    b = float(ccx[nid][idx])
                except Exception:
                    continue

                diff = b - a
                ad = abs(diff)

                csv.write(
                    u'{0},{1},{2},{3:.12g},{4:.12g},{5:.12g},{6:.12g}\n'.format(
                        nid,
                        name,
                        unit,
                        a,
                        b,
                        diff,
                        ad
                    )
                )

                rows.append(
                    (
                        nid,
                        a,
                        b,
                        diff
                    )
                )

                max_mec = max(
                    max_mec,
                    abs(a)
                )

                max_ccx = max(
                    max_ccx,
                    abs(b)
                )

                sum_sq += diff * diff

                if ad > max_diff:
                    max_diff = ad
                    max_node = nid

            if rows:
                rms = (
                    sum_sq /
                    float(len(rows))
                ) ** 0.5

                rel = (
                    max_diff / max_mec
                    if max_mec > 0.0
                    else 0.0
                )

                summaries.append(
                    {
                        'name': name,
                        'unit': unit,
                        'count': len(rows),
                        'max_mecway': max_mec,
                        'max_ccx': max_ccx,
                        'max_difference': max_diff,
                        'max_difference_node': max_node,
                        'relative_to_max_mecway': rel,
                        'rms_difference': rms
                    }
                )

    with io.open(
        txt_path,
        'w',
        encoding='utf-8'
    ) as out:
        out.write(
            u'MECWAY vs PATCHED CCX COMPARISON v1.1\n\n'
        )

        out.write(
            u'Mecway reference nodes captured: {0}\n'.format(
                len(baseline.get('nodes', []))
            )
        )

        out.write(
            u'CCX displacement nodes: {0}\n'.format(
                len(
                    dat_result.get(
                        'displacements',
                        {}
                    )
                )
            )
        )

        out.write(
            u'CCX force nodes: {0}\n\n'.format(
                len(
                    dat_result.get(
                        'forces',
                        {}
                    )
                )
            )
        )

        for item in summaries:
            out.write(
                u'{0} [{1}]\n'.format(
                    item['name'],
                    item['unit']
                )
            )

            out.write(
                u'  compared nodes: {0}\n'.format(
                    item['count']
                )
            )

            out.write(
                u'  max |Mecway|: {0:.12g}\n'.format(
                    item['max_mecway']
                )
            )

            out.write(
                u'  max |CCX|:    {0:.12g}\n'.format(
                    item['max_ccx']
                )
            )

            out.write(
                u'  max |difference|: {0:.12g} at node {1}\n'.format(
                    item['max_difference'],
                    item['max_difference_node']
                )
            )

            out.write(
                u'  max difference / max |Mecway|: {0:.6%}\n'.format(
                    item['relative_to_max_mecway']
                )
            )

            out.write(
                u'  RMS difference: {0:.12g}\n\n'.format(
                    item['rms_difference']
                )
            )

        out.write(
            u'Interpretation:\n'
            u'  This file compares the unchanged Mecway model solved by '
            u'Mecway with the same LIML translated to the patched CCX '
            u'B31T/UB31 route. Global force equilibrium alone is not enough: '
            u'nodal displacements/rotations and support-force distribution '
            u'must also correlate before the bridge is treated as validated.\n'
        )

    return txt_path, csv_path, summaries

def _run():
    script_dir = _script_dir()

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    mw.save()

    model_path = mw.file_name()

    if not model_path:
        raise RuntimeError(
            'Save the current Mecway model as a .liml first.'
        )

    model_path = os.path.abspath(
        model_path
    )

    if (
        not model_path.lower().endswith('.liml') or
        not os.path.isfile(model_path)
    ):
        raise RuntimeError(
            'Active model is not a readable .liml:\n' +
            model_path
        )

    # Independent reference: solve the original, unchanged model in Mecway
    # before creating/running the CCX deck.
    baseline = _capture_mecway_solution()

    from bridge import translate

    output = (
        os.path.splitext(model_path)[0] +
        '_ccx_draft.inp'
    )

    report = translate(
        model_path,
        output,
        BEAM_TYPE,
        draft=True
    )

    report_path = (
        os.path.splitext(output)[0] +
        '.report.json'
    )

    if report['errors']:
        mw.message(
            'Mecway CCX Beam Bridge v{0}\n\n'
            'Export completed, but validation found {1} error(s).\n\n'
            'CCX WILL NOT BE STARTED.\n\n'
            'Input: {2}\n'
            'Report: {3}\n\n'
            'Send the report back for correction.'.format(
                LAUNCHER_VERSION,
                len(report['errors']),
                output,
                report_path
            )
        )
        return

    ccx_path = _get_ccx()

    if not ccx_path:
        mw.message(
            'CCX executable selection was cancelled.\n\n'
            'The v0.6 deck was still generated:\n' +
            output
        )
        return

    result = _run_ccx(
        ccx_path,
        output
    )

    dat_path = result.get('dat')

    beam_csv_name = report.get(
        'beam_csv_file',
        os.path.basename(
            os.path.splitext(output)[0]
        ) + '_beam.csv'
    )

    beam_csv_path = os.path.join(
        os.path.dirname(output),
        beam_csv_name
    )

    dat_result = _parse_dat(
        dat_path
        if dat_path
        else ''
    )

    beam_result = _parse_beam_csv(
        beam_csv_path
    )

    (
        validation_path,
        equilibrium_residual,
        max_disp_node,
        max_disp
    ) = _write_validation(
        output,
        report,
        dat_result,
        beam_result,
        beam_csv_path
    )

    (
        compare_txt,
        compare_csv,
        compare_summaries
    ) = _write_mecway_comparison(
        output,
        report,
        baseline,
        dat_result
    )

    files = []

    for label, key in (
        ('FRD', 'frd'),
        ('DAT', 'dat'),
        ('STA', 'sta'),
        ('CVG', 'cvg')
    ):
        if result[key]:
            files.append(
                '{0}: {1}'.format(
                    label,
                    result[key]
                )
            )

    if os.path.isfile(beam_csv_path):
        files.append(
            'BEAM CSV: ' + beam_csv_path
        )

    if os.path.isfile(validation_path):
        files.append(
            'VALIDATION: ' + validation_path
        )

    if os.path.isfile(compare_txt):
        files.append(
            'MECWAY COMPARISON: ' + compare_txt
        )

    if os.path.isfile(compare_csv):
        files.append(
            'COMPARISON CSV: ' + compare_csv
        )

    files_text = (
        '\n'.join(files)
        if files
        else 'No CCX result files detected.'
    )

    if result['success']:
        heading = 'CCX TEST RUN COMPLETED'
    else:
        heading = 'CCX TEST RUN NEEDS REVIEW'

    comparison_headline = 'No comparable Mecway fields were found.'

    if compare_summaries:
        worst = max(
            compare_summaries,
            key=lambda x: x['relative_to_max_mecway']
        )

        comparison_headline = (
            'Worst nodal comparison: {0}, {1:.3%} of '
            'max |Mecway|'.format(
                worst['name'],
                worst['relative_to_max_mecway']
            )
        )

    message = (
        'Mecway CCX Beam Bridge v{0}\n\n'
        '{1}\n\n'
        'Nodes: {2}\n'
        'Beam elements: {3}\n'
        'Offsets: {4}\n'
        'Released ends: {5}\n'
        'L-axis compensated: {6}\n'
        'I/C/L axis-mapped elements: {19}\n'
        'Bridge validation errors: {7}\n\n'
        'CCX exit code: {8}\n'
        'CCX *ERROR detected: {9}\n'
        'DAT size: {10} bytes\n'
        'Beam CSV rows: {11}\n'
        'Max translation: {12:.6g} m at node {13}\n'
        'Equilibrium residual norm: {14:.6g} N\n'
        'Max combined beam stress: {15:.6g} MPa\n'
        '{16}\n\n'
        '{17}\n\n'
        'Solver log:\n{18}\n\n'
        'Please send the .mecway_compare.txt and .mecway_compare.csv back.'
    ).format(
        LAUNCHER_VERSION,
        heading,
        report['nodes'],
        report['elements'],
        report['offset_elements'],
        report['released_element_ends'],
        report['l_axis_compensated_elements'],
        len(report['errors']),
        result['exit_code'],
        'YES' if result['contains_error'] else 'NO',
        result['dat_size'],
        beam_result['rows'],
        max_disp,
        max_disp_node,
        _vector_norm(equilibrium_residual),
        beam_result['max_combined_stress_Pa'] / 1.0e6,
        comparison_headline,
        files_text,
        result['log_path'],
        report.get('profile_axis_swapped_elements', 0)
    )

    mw.message(message)


try:
    _run()

except Exception:
    message = traceback.format_exc()

    try:
        log_path = os.path.join(
            _script_dir(),
            'mecway_launcher_error.log'
        )

        with io.open(
            log_path,
            'w',
            encoding='utf-8'
        ) as handle:
            handle.write(message)

    except Exception:
        pass

    mw.message(
        'Mecway CCX Beam Bridge failed:\n\n' +
        message[-3500:]
    )
