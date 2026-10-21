# Mecway-to-CCX UB31 Beam Bridge v1.1

Confirmed working development build for Mecway IronPython 2.7 and the patched CalculiX 2.23 B31T/UB31 solver.

## Confirmed test model

The working regression model contains 345 nodes and 360 two-node beam elements: 60 I-section members, 220 C-channel members and 80 L-angle members. It also contains 220 offset members, 16 released beam ends, gravity and a 10 kN nodal load.

The bridge generated the CCX deck, launched the patched Windows CCX executable, and completed the static solve successfully.

## Correct profile-axis mapping

For Mecway I, C and L structural profiles, the Mecway V/W principal-axis convention is mapped to the native UB31 transverse basis as:

- UB31 local y = Mecway W
- UB31 local z = -Mecway V

L sections also compensate for UB31's internal principal-axis rotation.

Global or local beam offsets are transformed into this corrected final UB31 basis. Mecway flexible-joint rotational releases are translated to UB31 release masks; Mecway line2 face 2/3 maps to beam end 1/2.

## Solver and validation workflow

Keep `bridge.py` and `mecway_launcher.py` together and run `mecway_launcher.py` from Mecway **Tools > Scripts**.

The launcher:

1. saves and solves the current Mecway model as an independent reference;
2. translates the saved LIML to patched-CCX B31T input;
3. runs the selected patched CCX executable;
4. writes DAT/FRD/STA output plus dedicated multi-station UB31 beam CSV results;
5. performs mass, self-weight, equilibrium and released-end checks;
6. writes node-by-node Mecway-vs-CCX displacement, rotation and reaction comparisons.

The selected CCX executable path is stored locally in `ccx_executable.txt`.

## Confirmed B31T numerical results

For the confirmed 360-element model:

- global force-equilibrium residual: approximately 4.7e-4 N;
- dedicated UB31 beam output: 3960 rows (360 elements × 11 stations);
- all 16 released ends: released bending moments zero to output precision;
- after the I/C/L profile-axis correction, Mecway-vs-CCX nodal responses were strongly correlated;
- maximum Ux differed by about 1.4%;
- maximum Uz differed by about 3.8%;
- major rotations differed by about 0.4–1.2%.

This is the latest user-confirmed working **B31T** build. The separate B31E comparison remains experimental until it is run and confirmed.

## Repository note

`bridge/releases/Mecway_CCX_v1_1_axis_fix.zip` preserves the exact user-tested v1.1 package.
