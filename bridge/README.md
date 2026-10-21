# Mecway-to-CCX UB31 Beam Bridge v0.5 (development)

Native Mecway IronPython 2.7 bridge for patched CalculiX B31T / B31E beams.
**No external Python installation is required for Mecway operation.**

## Installation

Download/clone the dev branch. Keep `bridge.py` and
`mecway_launcher.py` in the same directory. In Mecway, select
**Tools > Scripts... > New** and register `bridge/mecway_launcher.py`.
Open and save a Mecway .liml file; then use
**Tools > mecway_launcher** to export diagnostics.

The launcher saves the currently open model through `mw.save()` and reads
the model path through `mw.file_name()`. Generated files are placed next to
the saved model:

- `<model>_ccx_draft.inp`: **DIAGNOSTIC ONLY**; never use for design or reliable numerical solutions
- `<model>_ccx_draft.report.json`: counts, material/section dimensions, validation errors

## v0.5 implementation

- I-beams: Mecway `ia,ib,ic,id` map to UB31 `SECTION=I`:
  `h,b,tf,b,tf,tw`
- C channels: Mecway `ca,cb,cc,cd` map to
  `SECTION=CHAN`: `h,b,tf,tw`
- L angles: Mecway `la,lb,lc` map to
  `SECTION=L`: `b,h,t`
- Rectangular bars, rectangular tubes, circular bars and circular tubes
  are translated into RECT, BOX, CIRC and PIPE cards.
- Mecway `<orientation>` selections are mapped per element; the supplied
  vector is projected normal to the member and its `angleu` is applied
  with a right-handed rotation about the beam axis. The missing-orientation
  default matches the vector rule in MecwayAsterBridge dev.
- Members with the same section but different transverse orientation are
  written in separate `BEAM_####` elsets, with a `*BEAM SECTION` per group.
- All dimensions are SI (m), and the output includes material, density,
  basic loads, fixed beam-end support nodes and gravity.
- Mecway `Flexible joint on beam` is translated directly from its face
  selection. `rotu/rotv/rotw` map to UB31 torsion/M1/M2 release bits and
  Mecway line2 face 2/3 maps to element end 1/2.
- Mecway beam `Element offset` supports both global X/Y/Z and local U/V/W
  vectors. Global vectors are transformed into each beam's local U/V/W frame,
  and the generated `*BEAM SECTION` uses matching `OFFSET1/OFFSET2` values.
  Element sets are split where necessary so each section card has one
  orientation and one local offset.

## Supplied test.liml findings

345 nodes; 360 line2 beams; three material profiles:

| Mecway | UB31 | SI dimensions |
|---|---|---|
| 152x152x30 | I | 0.1575, 0.1529, 0.0094, 0.1529, 0.0094, 0.0066 |
| C180x70 | CHAN | 0.18, 0.07, 0.011, 0.008 |
| 70x70x8 | L | 0.07, 0.07, 0.008 |

The supplied model can now translate its beam end releases and beam offsets. The remaining section-specific validation item is L-section principal-axis rotation/equivalence against Mecway.

## Safety and outstanding work

The UB31 native interface is source-checked in the uploaded
`CCX-UB31-B31T-B31E-update.zip`, not numerically regression-tested here.
Mecway's L-axis convention uses principal properties whereas UB31 rotates
L sections internally. Do not treat the L output as equivalent until
orientation compatibility is verified. Releases and offsets are now translated. The `safe_to_solve` report flag remains **false** while L-section principal-axis equivalence and full CCX numerical regression are outstanding.

Next phase: validate the generated deck against the patched CCX executable,
resolve the L-section axis convention, then add CCX process launch and Mecway result import.

References for axis/shape mapping: uploaded patch README and Fortran
`e_c3d_ub31.f`; MecwayAsterBridge dev
`Scripts/bridge_from_liml.py` and `Scripts/bridge_mesh.py`.

To run standalone Python tests (not needed for Mecway):
`python -m unittest discover -s tests -v`.


## Stable Mecway-tested baseline

For a known-working Mecway/IronPython baseline, use
`bridge/mecway_ccx_bridge_stable.py`.

This single-file script is the last version confirmed to execute successfully
inside Mecway and generate both an experimental `.inp` file and a
`.report.json` validation report. It intentionally does not translate section
cards, orientations, releases or offsets yet. The v0.4 `bridge.py` /
`mecway_launcher.py` pair remains the development implementation.
