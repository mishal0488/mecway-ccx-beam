# Mecway-to-CCX UB31 Beam Bridge v0.4 (development)

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

## v0.4 implementation

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

## Supplied test.liml findings

345 nodes; 360 line2 beams; three material profiles:

| Mecway | UB31 | SI dimensions |
|---|---|---|
| 152x152x30 | I | 0.1575, 0.1529, 0.0094, 0.1529, 0.0094, 0.0066 |
| C180x70 | CHAN | 0.18, 0.07, 0.011, 0.008 |
| 70x70x8 | L | 0.07, 0.07, 0.008 |

Five material+orientation groups. **Three unresolved validation items**:
beam end releases, beam offsets, and L-section principal-axis rotation.

## Safety and outstanding work

The UB31 native interface is source-checked in the uploaded
`CCX-UB31-B31T-B31E-update.zip`, not numerically regression-tested here.
Mecway's L-axis convention uses principal properties whereas UB31 rotates
L sections internally. Do not treat the L output as equivalent until
orientation compatibility is verified. Releases and offsets are intentionally
NOT translated; silently omitting them would change the structural model.
The `safe_to_solve` report flag remains **false**.

Next phase: verify each release at a selected member end and implement
UB31-compatible offsets; then carry out beam analytical regressions and
add CCX process launch and Mecway result import.

References for axis/shape mapping: uploaded patch README and Fortran
`e_c3d_ub31.f`; MecwayAsterBridge dev
`Scripts/bridge_from_liml.py` and `Scripts/bridge_mesh.py`.

To run standalone Python tests (not needed for Mecway):
`python -m unittest discover -s tests -v`.
