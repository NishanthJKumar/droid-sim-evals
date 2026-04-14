"""Create scene8: one Rubik's cube already packed in the bowl, plus two more
cubes on the open table.  The target task is something like "put the cubes
in the bowl" — and because the bowl already holds a cube, the robot must
either stack or remove the existing one before the remaining two can fit.

Built from scene1_0.usd (which has a Rubik's cube + bowl), following the same
pattern as create_scene6.py.  Using the Rubik's cube asset rather than
scene5's colored blocks because the Rubik's cube has a clean xform (physics
and visual are coincident), so it repositions correctly — scene5's blocks
have a 15 cm visual/physics offset that's impossible to reconcile when
placing inside the bowl.

Run with:
    python create_scene8.py

Generates assets/scene8_0.usd through assets/scene8_9.usd.
"""

import math
import os
import random
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_VENV_PKGS = _SCRIPT_DIR / ".venv/lib/python3.11/site-packages"
_USD_LIBS = _VENV_PKGS / "isaacsim/extscache/omni.usd.libs-1.0.1+8131b85d.lx64.r.cp311"
_USD_BIN = str(_USD_LIBS / "bin")

if _USD_LIBS.exists() and _USD_BIN not in os.environ.get("LD_LIBRARY_PATH", ""):
    import sysconfig
    ld = _USD_BIN + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        ld += ":" + libdir
    os.environ["LD_LIBRARY_PATH"] = ld
    os.execv(sys.executable, [sys.executable] + sys.argv)

if _USD_LIBS.exists():
    sys.path.insert(0, str(_USD_LIBS))

from pxr import Gf, Sdf, Usd, UsdGeom

TEMPLATE_PATH = "assets/scene1_0.usd"
# Source prim to copy — carries the payload, physics APIs, and collision spec.
CUBE_SRC_PATH = Sdf.Path("/World/rubiks_cube")
OUTPUT_DIR = Path("assets")
NUM_VARIANTS = 10

# Bowl center in scene1_0.usd (fixed across template).
BOWL_XY = (0.5022, 0.1144)

# Drop a single cube straight above the bowl center; physics settles it into
# the bowl's interior during settle_sim.
PACK_Z = 0.18
PACK_XY_JITTER = 0.008  # tiny offset so the cube doesn't balance perfectly vertically

# Reachable workspace for the two cubes that remain on the open table.
# Avoid the bowl (X≈0.50, Y≈0.11) and the Franka's default gripper footprint
# (X≈0.35, Y≈0) by staying in negative Y / positive X-of-table.
X_RANGE = (0.32, 0.60)
Y_RANGE = (-0.28, -0.10)
TABLE_Z_DROP = 0.18     # drop height; physics settles them onto the table
MIN_DIST = 0.10


def random_xy_positions(
    n: int,
    seed: int,
    x_range: tuple = X_RANGE,
    y_range: tuple = Y_RANGE,
    existing: list[tuple[float, float]] | None = None,
    min_dist: float = MIN_DIST,
) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    positions: list[tuple[float, float]] = list(existing or [])
    n_existing = len(positions)
    max_attempts = 10_000
    attempts = 0
    while len(positions) - n_existing < n:
        if attempts >= max_attempts:
            raise RuntimeError("Could not place cubes without overlap — adjust ranges or MIN_DIST")
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
    """Copy the rubiks_cube prim spec (payload + physics + collision) to a
    new path and author its transform."""
    Sdf.CopySpec(src_layer, CUBE_SRC_PATH, dst_layer, Sdf.Path(prim_path))
    prim = stage.GetPrimAtPath(prim_path)
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*pos))
    rz = Gf.Rotation(Gf.Vec3d(0, 0, 1), rot_zyx_deg[0])
    ry = Gf.Rotation(Gf.Vec3d(0, 1, 0), rot_zyx_deg[1])
    rx = Gf.Rotation(Gf.Vec3d(1, 0, 0), rot_zyx_deg[2])
    quat = (rz * ry * rx).GetQuat()
    prim.GetAttribute("xformOp:orient").Set(Gf.Quatd(quat.GetReal(), *quat.GetImaginary()))


def create_variant(variant: int) -> None:
    output_path = str(OUTPUT_DIR / f"scene8_{variant}.usd")
    shutil.copy(TEMPLATE_PATH, output_path)
    stage = Usd.Stage.Open(output_path)
    src_layer = Sdf.Layer.FindOrOpen(TEMPLATE_PATH)
    dst_layer = stage.GetRootLayer()

    # Remove the original cube; we add a fresh set below.
    orig = stage.GetPrimAtPath("/World/rubiks_cube")
    if orig.IsValid():
        stage.RemovePrim(orig.GetPath())

    rng = random.Random(variant * 131 + 7)

    # 1) One cube dropped into the bowl (will settle inside during settle_sim).
    jitter_x = rng.uniform(-PACK_XY_JITTER, PACK_XY_JITTER)
    jitter_y = rng.uniform(-PACK_XY_JITTER, PACK_XY_JITTER)
    bowl_cube_xy = (BOWL_XY[0] + jitter_x, BOWL_XY[1] + jitter_y)
    add_cube_prim(
        src_layer, dst_layer, stage,
        "/World/rubiks_cube_bowl",
        (bowl_cube_xy[0], bowl_cube_xy[1], PACK_Z),
        rot_zyx_deg=(rng.uniform(0, 360), 0.0, 0.0),
    )

    # 2) Two cubes on the open table.  Respect the bowl-cube's XY so we don't
    # collide with the bowl or the robot gripper area.
    table_xys = random_xy_positions(
        n=2, seed=variant * 77 + 31,
        existing=[bowl_cube_xy],
    )
    for i, (x, y) in enumerate(table_xys):
        add_cube_prim(
            src_layer, dst_layer, stage,
            f"/World/rubiks_cube_{i}",
            (x, y, TABLE_Z_DROP),
            rot_zyx_deg=(rng.uniform(0, 360), 0.0, 0.0),
        )

    stage.Save()
    print(f"Saved {output_path}  bowl_cube={tuple(round(v,3) for v in bowl_cube_xy)}  table={[tuple(round(v,3) for v in p) for p in table_xys]}")


if __name__ == "__main__":
    for v in range(NUM_VARIANTS):
        create_variant(v)
    print("Done. Run with: uv run python tiptop_eval.py --scene 8 --variant 0 --instruction 'Put the Rubiks cubes in the bowl.'")
