"""
Create scene6: three Rubik's cubes on a table (no bowl).

Run with:
    python create_scene6.py

Generates assets/scene6_0.usd through assets/scene6_9.usd.
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

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

TEMPLATE_PATH = "assets/scene1_0.usd"
# Source prim to copy — this carries the collision child spec (RubikCube with convexHull)
CUBE_SRC_PATH = Sdf.Path("/World/rubiks_cube")
OUTPUT_DIR = Path("assets")
NUM_VARIANTS = 10

# Reachable workspace on the table surface
X_RANGE = (0.30, 0.60)
Y_RANGE = (-0.25, 0.25)
Z_DROP = 0.25      # spawn slightly above table so objects settle during settle_sim()
MIN_DIST = 0.15    # minimum center-to-center distance between cubes


def random_positions(n: int = 3, seed: int = 0) -> list[tuple[float, float, float]]:
    """Generate n non-overlapping positions on the table."""
    rng = random.Random(seed)
    positions: list[tuple[float, float, float]] = []
    max_attempts = 10_000
    attempts = 0
    while len(positions) < n:
        if attempts >= max_attempts:
            raise RuntimeError("Could not place cubes without overlap — adjust X/Y ranges or MIN_DIST")
        x = rng.uniform(*X_RANGE)
        y = rng.uniform(*Y_RANGE)
        attempts += 1
        if all(math.hypot(x - px, y - py) >= MIN_DIST for px, py, _ in positions):
            positions.append((x, y, Z_DROP))
    return positions


def add_cube_prim(
    src_layer: Sdf.Layer,
    dst_layer: Sdf.Layer,
    stage: Usd.Stage,
    prim_path: str,
    pos: tuple,
    rot_zyx_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Copy the rubiks_cube prim spec (including collision child) then update its transform."""
    # CopySpec replicates the full spec tree: payload, APIs, collision child (RubikCube)
    Sdf.CopySpec(src_layer, CUBE_SRC_PATH, dst_layer, Sdf.Path(prim_path))

    prim = stage.GetPrimAtPath(prim_path)

    # Update transform to the new position/rotation
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*pos))
    # Convert ZYX euler angles to quaternion and set xformOp:orient,
    # because dynamic_scene() reads orient (not rotateZYX) for InitialStateCfg.
    rz = Gf.Rotation(Gf.Vec3d(0, 0, 1), rot_zyx_deg[0])
    ry = Gf.Rotation(Gf.Vec3d(0, 1, 0), rot_zyx_deg[1])
    rx = Gf.Rotation(Gf.Vec3d(1, 0, 0), rot_zyx_deg[2])
    quat = (rz * ry * rx).GetQuat()
    prim.GetAttribute("xformOp:orient").Set(Gf.Quatd(quat.GetReal(), *quat.GetImaginary()))


def create_variant(variant: int) -> None:
    output_path = str(OUTPUT_DIR / f"scene6_{variant}.usd")
    # Binary-copy the template so payloads/table/lights stay intact
    shutil.copy(TEMPLATE_PATH, output_path)
    stage = Usd.Stage.Open(output_path)
    src_layer = Sdf.Layer.FindOrOpen(TEMPLATE_PATH)
    dst_layer = stage.GetRootLayer()

    # Remove the original single cube (we replace it with three below)
    # Keep the bowl — it stays as-is from the template
    prim = stage.GetPrimAtPath("/World/rubiks_cube")
    if prim.IsValid():
        stage.RemovePrim(prim.GetPath())

    # Generate non-overlapping positions (seeded per variant for reproducibility)
    positions = random_positions(n=3, seed=variant * 42 + 7)
    rng = random.Random(variant * 99 + 13)

    for i, pos in enumerate(positions):
        rot = (rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))
        add_cube_prim(src_layer, dst_layer, stage, f"/World/rubiks_cube_{i}", pos, rot_zyx_deg=rot)

    stage.Save()
    print(f"Saved {output_path}  positions={[(round(p[0],3), round(p[1],3)) for p in positions]}")


if __name__ == "__main__":
    for v in range(NUM_VARIANTS):
        create_variant(v)
    print("Done. Run with: uv run python tiptop_eval.py --scene 6 --instruction 'Pick up a Rubiks cube'")
