# Mecway → patched CCX B31T/B31E bridge (prototype v0.1)

This prototype reads a Mecway 34 native `.liml` XML file and identifies beam meshes, materials, elementary loads and fixed supports. It writes a detailed JSON compatibility report.

**Engineering warning:** The bridge does **not** currently produce solver-ready models with correct cross-section data, end releases, offsets or beam orientation. Never use `--draft` files for numerical results; they deliberately omit essential cards.

## Requirements

Python 3.10+ only; no third-party packages. Designed for Windows as well as Linux.

## Run directly from Mecway (recommended)

The `mecway_launcher.py` script is for Mecway's embedded **IronPython 2.7**.
It follows the same Mecway integration mechanism used in
[MecwayAsterBridge](https://github.com/mishal0488/MecwayAsterBridge/tree/dev):
`mw.save()`, `mw.file_name()` and an external `subprocess` call.

1. Install a separate CPython 3.10+ on Windows. In Command Prompt, verify `py -3 --version`.
2. Place `mecway_launcher.py` and `bridge.py` together in the same folder.
3. In Mecway choose **Tools > Scripts... > New** and select `mecway_launcher.py`.
4. Open your Mecway model and choose **Tools > mecway_launcher**.
5. Mecway saves the *currently open* model and executes `bridge.py` with Python 3.
   The launcher displays a summary using `mw.message()`, without using Windows Forms.

Next to the saved `.liml` you will find:
- `<model>_ccx_draft.inp` -- **unsafe for solver use**, diagnostic only
- `<model>_ccx_draft.report.json` -- validation issues and extracted model statistics
- `<model>_ccx_draft.launcher.log` -- Python output, useful for debugging

If `py.exe` is unavailable, set environment variable `MECWAY_CCX_PYTHON` to
the full path of your Python 3 `python.exe`, then restart Mecway.
The launcher always produces a diagnostic draft and **never starts CCX yet**.
It has been locally integration-tested with a simulated Mecway `mw` API
and the supplied `test.liml`; testing with actual Mecway IronPython is pending.

## Run from Windows PowerShell

```powershell
py bridge.py "C:\path\to\test.liml" --beam B31T
```

A safety report is generated next to the requested output (extension `.report.json`). If unsupported features are present, this command returns exit code 2 and does not generate an `.inp`.

To produce a **diagnostic draft only**:

```powershell
py bridge.py "C:\path\to\test.liml" --beam B31T --draft -o "C:\path\to\test_draft.inp"
```

The draft deliberately omits beam sections and does not guarantee valid CalculiX syntax. It must not be run in CCX.

## Current capabilities

- Reads `<node>` coordinates and two-node `<elem shape="line2">` beam connectivity
- Groups elements by Mecway material
- Identifies isotropic Young's modulus, Poisson's ratio and density
- Converts simple nodal forces to N and fixed beam-end support faces to node constraints
- Identifies gravitational acceleration
- Reports unverified orientations, releases, offsets and section geometry and blocks solving
- Allows B31T/B31E element selection

## Next work

1. Verify UB31 section input conventions for I / CHAN / L, then implement accurate beam section cards.
2. Verify orientation vector plus `angleu` transformation against Mecway's local-axes definition.
3. Decode `<flexiblejoint>` face ID and local DOF mapping, and implement the specific UB31 release syntax.
4. Translate spatial offsets or connector kinematics without adding spurious stiffness.
5. Add supported static/nonlinear/dynamic steps and result compatibility.
6. Validate the IronPython launcher in Mecway 34, then implement CCX invocation and FRD import.

The packaged repository's native interface is source-checked but not runtime-regression-certified. Solve simple reference problems and compare analytical displacement/reaction/force results before extending to frames.
