# Mecway to patched CCX B31T/B31E bridge (v0.3 prototype)

A diagnostic bridge for Mecway 34 native `.liml` models and the patched CCX
UB31/B31T/B31E beam solver.

**IMPORTANT: NOT SOLVER-READY.** The bridge currently extracts node and
element connectivity, material properties, fixed end nodes, nodal forces, and
gravity. It detects beam sections, local orientations, end releases and offsets,
but the exact UB31 mappings are not implemented. The generated `.inp` is a
**diagnostic draft only** and MUST NOT be run as an engineering simulation.

## Requirements

- Windows with Mecway scripting support (its built-in IronPython 2.7).
- The two Python files in this folder.
- **No standalone Python 3 installation is needed.**
- There is no requirement for Windows Forms, .NET UI setup, pip, or Ubuntu.

The IronPython approach follows the Mecway API use in
[MecwayAsterBridge](https://github.com/mishal0488/MecwayAsterBridge/tree/dev):
`mw.save()`, `mw.file_name()` and `mw.message()`.

## Run from inside Mecway

1. Download the current `dev` branch and extract it into a folder.
2. Keep `bridge.py` and `mecway_launcher.py` **in the same folder**.
3. In Mecway, use **Tools > Scripts... > New** and select
   `bridge/mecway_launcher.py`.
4. Open your Mecway model (`.liml`) and run
   **Tools > mecway_launcher**.
5. Mecway saves the **currently open** model and processes it directly.
   No file picker is used.

The script writes two files beside the Mecway model:

- `<model>_ccx_draft.inp` - UNSAFE diagnostic CCX deck.
- `<model>_ccx_draft.report.json` - counts and validation issues.

If the script fails, the traceback is shown via `mw.message()` and
best-effort logged to `bridge/mecway_launcher_error.log`.

## Expected result with provided test.liml

- 345 nodes
- 360 two-node beam elements
- Fixed support nodes: 1, 4, 8
- Three section/material groups
- Seven validation issues (three sections, two local orientations,
  one flexible joint and one member offset)

This validates **model extraction**, not physical accuracy.

## Use from a Python CLI (optional)

```powershell
python bridge.py "C:\models\test.liml" --beam B31T --draft
```

The script also permits B31E using `--beam B31E`.
Without `--draft`, it writes the validation report only and deliberately
refuses to generate an input file suitable for solving.

## Next work

1. Verify the patched UB31 `*BEAM SECTION` conventions for I, CHAN and L
   sections and implement correct CCX section cards.
2. Convert Mecway beam local-axis rotations and eccentricities correctly.
3. Translate element-end releases, distinguishing first/second beam ends.
4. Verify gravity and constraint translations on small benchmark models.
5. Enable CCX execution only after a complete safe translation.
6. Read FRD/DAT results back into Mecway with verified units/quantities.

### Development safety

Do not load a `*_ccx_draft.inp` into CCX and rely on numerical results.
This v0.3 has been exercised with a simulated Mecway API under CPython and
the provided Mecway model. Actual Mecway/IronPython testing is still required.
