"""Log per-step XYZ of each block in scene8 to see where/when they escape the bowl.

Usage: python debug_scene8_settle.py --scene 8 --variant 1
"""
import argparse
import logging

import torch
import gymnasium as gym
import tyro

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BLOCK_NAMES = ["blue_block", "green_block", "red_block", "yellow_block", "basic_block"]


def main(scene: int = 8, variant: int = 1, steps: int = 40, headless: bool = True):
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
    obs, _ = env.reset()

    # Resolve RigidObject handles by name
    assets = {}
    for name in BLOCK_NAMES + ["_24_bowl"]:
        try:
            assets[name] = env.unwrapped.scene[name]
        except KeyError:
            logger.warning(f"No scene entity named {name}; skipping")

    def snapshot(tag: str):
        row = [f"[{tag:>9s}]"]
        for name, a in assets.items():
            pos = a.data.root_pos_w[0].cpu().numpy()
            vel = a.data.root_lin_vel_w[0].cpu().numpy()
            row.append(f"{name:>12s} xyz=({pos[0]:+.3f},{pos[1]:+.3f},{pos[2]:+.3f}) |v|={float((vel**2).sum())**0.5:.3f}")
        print("\n  ".join(row))

    snapshot("post-reset")

    # Hold joints and step one physics step at a time
    action_space = env.action_space
    hold_action = torch.zeros((1, action_space.shape[1]), device=env.unwrapped.device)
    # Match the joint-hold pattern used by settle_sim: send the robot's current joint
    # pose as the action so the arm doesn't drift (gripper open = 1.0).
    try:
        joint_pos = env.unwrapped.scene["robot"].data.joint_pos[0, :7].unsqueeze(0)
        hold_action = torch.cat([joint_pos, torch.tensor([[1.0]], device=env.unwrapped.device)], dim=1)
    except Exception as e:
        logger.warning(f"Could not read robot joint_pos; using zero action ({e})")

    for i in range(steps):
        obs, _, _, _, _ = env.step(hold_action)
        snapshot(f"step {i+1}")

    env.close()
    simulation_app.close()


if __name__ == "__main__":
    tyro.cli(main)
