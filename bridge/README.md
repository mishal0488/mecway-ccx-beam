# Mecway → patched CCX B31T/B31E bridge (prototype v0.1)

This prototype reads a Mecway 34 native `.liml` XML file and identifies beam meshes, materials, elementary loads and fixed supports. It writes a detailed JSON compatibility report.

**Engineering warning:** The bridge does **not** currently produce solver-ready models with correct cross-section data, end releases, offsets or beam orientation. Never use `--draft` files for numerical results; they deliberately omit essential cards.

## Requirements

Python 3.10+ only; no third-party packages. Designed for Windows as well as Linux.

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
6. Integrate with Mecway's external script launcher, then CCX invocation and FRD import.

The packaged repository's native interface is source-checked but not runtime-regression-certified. Solve simple reference problems and compare analytical displacement/reaction/force results before extending to frames.
