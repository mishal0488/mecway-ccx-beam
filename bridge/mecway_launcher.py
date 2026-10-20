# -*- coding: utf-8 -*-
"""Launch bridge.py from Mecway's IronPython 2.7 Tools > Scripts menu.

Mecway supplies 'mw' in its scripting context.  This launcher deliberately
avoids Windows Forms and uses the active saved LIML model automatically.
The CCX model is only a diagnostic draft at this stage; CCX is NOT run.
"""
import json
import os
import subprocess

BEAM_TYPE = 'B31T'


def _run():
    # The user can override the Python 3 launcher using an environment
    # variable (full path to python.exe), without editing this file.
    python_exe = os.environ.get('MECWAY_CCX_PYTHON', 'py.exe')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_path = os.path.join(script_dir, 'bridge.py')
    if not os.path.isfile(bridge_path):
        raise RuntimeError('bridge.py is not in the same folder as mecway_launcher.py:\n' + script_dir)

    # Save CURRENT Mecway model, including any pending model changes.
    mw.save()
    model_path = mw.file_name()
    if not model_path:
        raise RuntimeError('Mecway model has no saved file name. Save a .liml model and retry.')
    model_path = os.path.abspath(model_path)
    if not model_path.lower().endswith('.liml') or not os.path.isfile(model_path):
        raise RuntimeError('The active model is not a readable .liml file:\n' + model_path)

    output_path = os.path.splitext(model_path)[0] + '_ccx_draft.inp'
    report_path = os.path.splitext(output_path)[0] + '.report.json'
    log_path = os.path.splitext(output_path)[0] + '.launcher.log'

    command = [python_exe]
    if os.path.basename(python_exe).lower() in ('py.exe', 'py'):
        command.append('-3')
    command.extend([bridge_path, model_path, '--beam', BEAM_TYPE,
                    '--draft', '-o', output_path])

    try:
        process = subprocess.Popen(command, cwd=script_dir,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
    except OSError as exc:
        raise RuntimeError('Could not start Python 3: ' + str(exc) +
                           '\nCheck py -3 --version in Command Prompt, or set MECWAY_CCX_PYTHON.')
    output, unused = process.communicate()
    with open(log_path, 'wb') as handle:
        handle.write(output or b'')
    try:
        output_text = output.decode('utf-8', 'replace')
    except AttributeError:
        output_text = str(output)
    if process.returncode not in (0, 2):
        raise RuntimeError('Translator failed (exit code %s).\n%s\n\nLog: %s' %
                           (process.returncode, output_text[-2000:], log_path))
    if not os.path.isfile(report_path):
        raise RuntimeError('Python completed but did not create the validation report.\n' +
                           output_text[-2000:] + '\nLog: ' + log_path)

    with open(report_path, 'r') as handle:
        report = json.load(handle)
    errors = report.get('errors', [])
    status = 'VALIDATION BLOCKED: draft only; DO NOT SOLVE' if errors else 'Translation completed; CCX execution not implemented'
    details = '\n'.join(' - ' + str(e) for e in errors[:4])
    if len(errors) > 4:
        details += '\n ... %d more (see report)' % (len(errors) - 4)
    mw.message('Mecway CCX Beam Bridge\n\n' + status +
               '\nNodes: %s, Beam elements: %s\nProblems: %d' %
               (report.get('nodes', '?'), report.get('elements', '?'), len(errors)) +
               ('\n\n' + details if details else '') +
               '\n\nDraft: ' + output_path +
               '\nReport: ' + report_path +
               '\nLog: ' + log_path)


try:
    _run()
except Exception as exc:
    mw.message('Mecway CCX Beam Bridge error:\n\n' + str(exc))
