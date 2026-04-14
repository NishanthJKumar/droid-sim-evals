"""Save exterior and wrist camera PNGs for a DROID sim scene.

Spawns the given scene/variant, settles physics, and writes:
    <output_dir>/scene<N>_<V>_ext.png
    <output_dir>/scene<N>_<V>_ext2.png   (second exterior view)
    <output_dir>/scene<N>_<V>_wrist.png

Run with:
    python save_scene_views.py --scene 8 --variant 1
"""
import logging
import argparse
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import torch
import gymnasium as gym
import tyro

from src.sim_evals.sim_utils import settle_sim

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _to_uint8_img(t: torch.Tensor) -> np.ndarray:
    arr = t[0].detach().cpu().numpy() if isinstance(t, torch.Tensor) else np.asarray(t[0])
    if arr.dtype != np.uint8:
        # obs tensors come through as float in [0, 1] or [0, 255]; normalize either way
        m = float(arr.max()) if arr.size else 1.0
        if m <= 1.0001:
            arr = (arr * 255.0).clip(0, 255)
        arr = arr.clip(0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    return arr


def main(
    scene: int = 1,
    variant: int = 0,
    output_dir: str = "docs",
    headless: bool = True,
):
    """Render exterior + wrist views of a scene and save them as PNGs.

    Args:
        scene: Scene number.
        variant: Scene variant.
        output_dir: Directory to write PNGs into (created if missing).
        headless: Run without GUI.
    """
    from isaaclab.app import AppLauncher

    parser = argparse.ArgumentParser()
    AppLauncher.add_app_launcher_args(parser)
    args_cli, _ = parser.parse_known_args()
    args_cli.enable_cameras = True
    args_cli.headless = headless
    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    import src.sim_evals.environments  # noqa: F401
    from isaaclab_tasks.utils import parse_env_cfg

    env_cfg = parse_env_cfg("DROID", device=args_cli.device, num_envs=1, use_fabric=True)
    env_cfg.set_scene(str(scene), variant)
    env = gym.make("DROID", cfg=env_cfg)

    obs, _ = env.reset()
    obs, _ = env.reset()  # second reset for correct material loading
    obs = settle_sim(env, obs, steps=100)

    # Debug: log rigid-body positions right before we render.
    for name in ["blue_block", "green_block", "red_block", "yellow_block", "basic_block", "_24_bowl"]:
        try:
            a = env.unwrapped.scene[name]
            pos = a.data.root_pos_w[0].cpu().numpy()
            logger.info(f"  RENDER POS {name:12s} = ({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:+.3f})")
        except KeyError:
            pass

    p = obs["policy"]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"scene{scene}_{variant}"

    views = {
        "ext":   p.get("external_cam"),
        "ext2":  p.get("external_cam_2"),
        "wrist": p.get("wrist_cam"),
    }
    for tag, tensor in views.items():
        if tensor is None:
            logger.warning(f"No obs key for {tag}; skipping")
            continue
        img = _to_uint8_img(tensor)
        path = out / f"{stem}_{tag}.png"
        imageio.imwrite(path, img)
        logger.info(f"Saved {path}  shape={img.shape}")

    env.close()
    simulation_app.close()


if __name__ == "__main__":
    tyro.cli(main)
