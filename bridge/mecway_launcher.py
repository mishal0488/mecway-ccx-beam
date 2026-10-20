# -*- coding: utf-8 -*-
"""IronPython 2.7 launcher for the CPython 3 Mecway/CCX bridge.

Run from Mecway's Python script menu. This prototype asks for a saved LIML
file; it does not yet capture unsaved changes or invoke CalculiX.
"""
import os
import System
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows.Forms import OpenFileDialog, DialogResult, MessageBox

PYTHON_EXE = 'py.exe'
PYTHON_SWITCH = '-3'

script_dir = os.path.dirname(os.path.abspath(__file__))
bridge = os.path.join(script_dir, 'bridge.py')
if not os.path.isfile(bridge):
    MessageBox.Show('bridge.py must be in the same folder as mecway_launcher.py')
    raise Exception('Missing bridge.py')

picker = OpenFileDialog()
picker.Title = 'Select saved Mecway LIML model'
picker.Filter = 'Mecway models (*.liml)|*.liml|All files (*.*)|*.*'
if picker.ShowDialog() != DialogResult.OK:
    raise SystemExit

liml = str(picker.FileName)
def quote_arg(value):
    return '"' + str(value).replace('"', '\"') + '"'

args = '%s %s %s --beam B31T --draft' % (
    PYTHON_SWITCH, quote_arg(bridge), quote_arg(liml))
info = ProcessStartInfo()
info.FileName = PYTHON_EXE
info.Arguments = args
info.UseShellExecute = False
info.CreateNoWindow = True
info.RedirectStandardOutput = True
info.RedirectStandardError = True

try:
    process = Process.Start(info)
    stdout = process.StandardOutput.ReadToEnd()
    stderr = process.StandardError.ReadToEnd()
    process.WaitForExit()
    result = 'Exit code: %s\n\n%s\n%s' % (process.ExitCode, stdout, stderr)
    MessageBox.Show(result[:4000], 'Mecway CCX Bridge v0.1')
except Exception as exc:
    MessageBox.Show('Could not start external Python 3:\n%s' % exc,
                    'Mecway CCX Bridge')
    raise
