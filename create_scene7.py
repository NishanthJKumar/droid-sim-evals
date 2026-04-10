"""
Create scene7: three Rubik's cubes on a table with a bowl and distractor objects.

This is a cluttered version of scene 6, analogous to how scene 4 adds distractors
to scene 1.  Uses scene4_0.usd as the template (which already has distractor prims
with correct collision specs), removes the single cube, then adds three randomized
cubes.  The bowl and distractors are kept and repositioned.

Run with:
    python create_scene7.py

Generates assets/scene7_0.usd through assets/scene7_9.usd.
"""

import math
import os
import random
import shutil
import sys
from pathlib import Path

# pxr lives inside the Isaac Sim extension cache and needs native libs on
# LD_LIBRARY_PATH *before* the process starts.  If the env isn't set up yet,
# re-exec ourselves with the right paths.
_SCRIPT_DIR = Path(__file__).resolve().parent
_VENV_PKGS = _SCRIPT_DIR / ".venv/lib/python3.11/site-packages"
_USD_LIBS = _VENV_PKGS / "isaacsim/extscache/omni.usd.libs-1.0.1+8131b85d.lx64.r.cp311"
_USD_BIN = str(_USD_LIBS / "bin")

if _USD_LIBS.exists() and _USD_BIN not in os.environ.get("LD_LIBRARY_PATH", ""):
    import sysconfig
    ld = _USD_BIN + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    # Also need libpython3.11.so for uv-managed interpreters
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        ld += ":" + libdir
    os.environ["LD_LIBRARY_PATH"] = ld
    os.execv(sys.executable, [sys.executable] + sys.argv)

if _USD_LIBS.exists():
    sys.path.insert(0, str(_USD_LIBS))

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

TEMPLATE_PATH = "assets/scene4_0.usd"
# Source prim to copy — this carries the collision child spec (RubikCube with convexHull)
CUBE_SRC_PATH = Sdf.Path("/World/rubiks_cube")
OUTPUT_DIR = Path("assets")
NUM_VARIANTS = 10

# Reachable workspace on the table surface
X_RANGE = (0.32, 0.55)
Y_RANGE = (-0.18, 0.18)
CUBE_Z = 0.091     # resting Z for Rubik's cube on the table (from scene4)
MIN_DIST = 0.08    # minimum center-to-center distance between objects

# Bowl + distractor objects kept from scene4, with their resting Z on the table
# (taken from scene4_0.usd — dropping from Z_DROP causes objects to bounce off)
OBJECT_Z = {
    "_24_bowl":            0.074,
    "_05_tomato_soup_can": 0.096,
    "_11_banana":          0.066,
    "_10_potted_meat_can": 0.095,
    "_25_mug":             0.078,
    "_04_sugar_box":       0.079,
    "_06_mustard_bottle":  0.140,
}

DISTRACTOR_PRIMS = [
    "_05_tomato_soup_can",
    "_11_banana",
    "_10_potted_meat_can",
    "_25_mug",
    "_04_sugar_box",
    "_06_mustard_bottle",
]


def random_xy_positions(
    n: int,
    seed: int,
    x_range: tuple = X_RANGE,
    y_range: tuple = Y_RANGE,
    existing: list[tuple[float, float]] | None = None,
    min_dist: float = MIN_DIST,
) -> list[tuple[float, float]]:
    """Generate n non-overlapping (x, y) positions on the table."""
    rng = random.Random(seed)
    positions: list[tuple[float, float]] = list(existing or [])
    n_existing = len(positions)
    max_attempts = 10_000
    attempts = 0
    while len(positions) - n_existing < n:
        if attempts >= max_attempts:
            raise RuntimeError("Could not place objects without overlap — adjust ranges or MIN_DIST")
        x = rng.uniform(*x_range)
        y = rng.uniform(*y_range)
        attempts += 1
        if all(math.hypot(x - px, y - py) >= min_dist for px, py in positions):
            positions.append((x, y))
    return positions[n_existing:]


def add_cube_prim(
    src_layer: Sdf.Layer,
    dst_layer: Sdf.Layer,
    stage: Usd.Stage,
    prim_path: str,
    pos: tuple,
    rot_zyx_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Copy the rubiks_cube prim spec (including collision child) then update its transform."""
    Sdf.CopySpec(src_layer, CUBE_SRC_PATH, dst_layer, Sdf.Path(prim_path))

    prim = stage.GetPrimAtPath(prim_path)

    # Update transform to the new position/rotation
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*pos))
    rz = Gf.Rotation(Gf.Vec3d(0, 0, 1), rot_zyx_deg[0])
    ry = Gf.Rotation(Gf.Vec3d(0, 1, 0), rot_zyx_deg[1])
    rx = Gf.Rotation(Gf.Vec3d(1, 0, 0), rot_zyx_deg[2])
    quat = (rz * ry * rx).GetQuat()
    prim.GetAttribute("xformOp:orient").Set(Gf.Quatd(quat.GetReal(), *quat.GetImaginary()))


def create_variant(variant: int) -> None:
    output_path = str(OUTPUT_DIR / f"scene7_{variant}.usd")
    # Binary-copy the template so payloads/table/lights/distractors stay intact
    shutil.copy(TEMPLATE_PATH, output_path)
    stage = Usd.Stage.Open(output_path)
    src_layer = Sdf.Layer.FindOrOpen(TEMPLATE_PATH)
    dst_layer = stage.GetRootLayer()

    # Remove the original single cube (keep the bowl)
    prim = stage.GetPrimAtPath("/World/rubiks_cube")
    if prim.IsValid():
        stage.RemovePrim(prim.GetPath())

    # Generate non-overlapping (x, y) positions for the 3 cubes
    cube_xys = random_xy_positions(n=3, seed=variant * 42 + 7)
    rng = random.Random(variant * 99 + 13)

    for i, (x, y) in enumerate(cube_xys):
        rot = (rng.uniform(0, 360), 0.0, 0.0)  # yaw only — full 3D rotation causes bouncing
        add_cube_prim(src_layer, dst_layer, stage, f"/World/rubiks_cube_{i}", (x, y, CUBE_Z), rot_zyx_deg=rot)

    # Randomize bowl + distractor positions (seeded per variant),
    # respecting cube positions for spacing
    all_prims_to_place = ["_24_bowl"] + DISTRACTOR_PRIMS
    extra_xys = random_xy_positions(
        n=len(all_prims_to_place),
        seed=variant * 77 + 31,
        existing=list(cube_xys),
        min_dist=MIN_DIST,
    )

    dist_rng = random.Random(variant * 53 + 17)
    for name, (x, y) in zip(all_prims_to_place, extra_xys):
        prim = stage.GetPrimAtPath(f"/World/{name}")
        if not prim.IsValid():
            continue
        z = OBJECT_Z[name]
        translate_attr = prim.GetAttribute("xformOp:translate")
        if translate_attr.GetTypeName() == Sdf.ValueTypeNames.Float3:
            translate_attr.Set(Gf.Vec3f(x, y, z))
        else:
            translate_attr.Set(Gf.Vec3d(x, y, z))
        # Randomize yaw only for distractors (keep them upright)
        yaw = dist_rng.uniform(0, 360)
        rz = Gf.Rotation(Gf.Vec3d(0, 0, 1), yaw)
        quat = rz.GetQuat()
        # Match the attribute's type (some prims use GfQuatf, others GfQuatd)
        orient_attr = prim.GetAttribute("xformOp:orient")
        if orient_attr.GetTypeName() == Sdf.ValueTypeNames.Quatf:
            orient_attr.Set(Gf.Quatf(quat.GetReal(), *quat.GetImaginary()))
        else:
            orient_attr.Set(Gf.Quatd(quat.GetReal(), *quat.GetImaginary()))

    stage.Save()
    print(f"Saved {output_path}  cubes={[(round(x,3), round(y,3)) for x, y in cube_xys]}")


if __name__ == "__main__":
    for v in range(NUM_VARIANTS):
        create_variant(v)
    print("Done. Run with: uv run python tiptop_eval.py --scene 7 --instruction 'Pick up a Rubiks cube'")
