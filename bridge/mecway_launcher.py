# -*- coding: utf-8 -*-
"""Native Mecway IronPython 2.7 launcher - no external Python required.

Run using Tools > Scripts; works on the currently open Mecway LIML model.
Generates diagnostics ONLY. It does not execute CalculiX.
"""
from __future__ import print_function
import io
import os
import sys
import traceback

BEAM_TYPE = 'B31T'


def _run():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    # Uses the Mecway scripting API as in MecwayAsterBridge.
    mw.save()
    model_path = mw.file_name()
    if not model_path:
        raise RuntimeError('Save the current Mecway model as a .liml first.')
    model_path = os.path.abspath(model_path)
    if not model_path.lower().endswith('.liml') or not os.path.isfile(model_path):
        raise RuntimeError('Active model is not a readable .liml:\n' + model_path)

    from bridge import translate
    output = os.path.splitext(model_path)[0] + '_ccx_draft.inp'
    report = translate(model_path, output, BEAM_TYPE, draft=True)
    report_path = os.path.splitext(output)[0] + '.report.json'
    message = ('Mecway CCX Beam Bridge v0.4\n\n'
               'Diagnostic export completed.\n'
               'Nodes: {0}\nBeam elements: {1}\nBeam section/orientation groups: {5}\nValidation issues: {2}\n\n'
               'DO NOT SOLVE: beam definitions have not been validated.\n\n'
               'Input draft: {3}\nValidation report: {4}').format(
                   report['nodes'], report['elements'], len(report['errors']),
                   output, report_path, report['beam_section_orientation_groups'])
    mw.message(message)


try:
    _run()
except Exception:
    message = traceback.format_exc()
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'mecway_launcher_error.log')
        with io.open(log_path, 'w', encoding='utf-8') as handle:
            handle.write(message)
    except Exception:
        pass
    mw.message('Mecway CCX Beam Bridge failed:\n\n' + message[-3500:])
