"""
Create scene6: three Rubik's cubes on a table (no bowl).

Run with:
    uv run python create_scene6.py

Generates assets/scene6_0.usd through assets/scene6_9.usd.
"""

import math
import random
import shutil
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

TEMPLATE_PATH = "assets/scene1_0.usd"
# Source prim to copy — this carries the collision child spec (RubikCube with convexHull)
CUBE_SRC_PATH = Sdf.Path("/World/rubiks_cube")
OUTPUT_DIR = Path("assets")
NUM_VARIANTS = 10

# Reachable workspace on the table surface
X_RANGE = (0.35, 0.55)
Y_RANGE = (-0.20, 0.20)
Z_HEIGHT = 0.103   # height of cube center above ground (from scene1 reference)
MIN_DIST = 0.09    # minimum center-to-center distance between cubes


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
            positions.append((x, y, Z_HEIGHT))
    return positions


def add_cube_prim(
    src_layer: Sdf.Layer,
    dst_layer: Sdf.Layer,
    stage: Usd.Stage,
    prim_path: str,
    pos: tuple,
    z_rot_deg: float = 0.0,
) -> None:
    """Copy the rubiks_cube prim spec (including collision child) then update its transform."""
    # CopySpec replicates the full spec tree: payload, APIs, collision child (RubikCube)
    Sdf.CopySpec(src_layer, CUBE_SRC_PATH, dst_layer, Sdf.Path(prim_path))

    prim = stage.GetPrimAtPath(prim_path)

    # Update transform to the new position/rotation
    prim.GetAttribute("xformOp:translate").Set(Gf.Vec3d(*pos))
    prim.GetAttribute("xformOp:rotateZYX").Set(Gf.Vec3f(0, 0, z_rot_deg))


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
        z_rot = rng.uniform(0, 360)
        add_cube_prim(src_layer, dst_layer, stage, f"/World/rubiks_cube_{i}", pos, z_rot_deg=z_rot)

    stage.Save()
    print(f"Saved {output_path}  positions={[(round(p[0],3), round(p[1],3)) for p in positions]}")


if __name__ == "__main__":
    for v in range(NUM_VARIANTS):
        create_variant(v)
    print("Done. Run with: uv run python tiptop_eval.py --scene 6 --instruction 'Pick up a Rubiks cube'")
