"""Shared simulation utilities."""

import torch


def settle_sim(env, obs: dict, steps: int = 100, reset_episode_buf: bool = False) -> dict:
    """Step the simulator holding the current joint pose until objects settle.

    Args:
        env: The gymnasium environment.
        obs: Current observation dict (must contain ``policy`` keys).
        steps: Number of steps to hold.
        reset_episode_buf: If True, zero out the episode length buffer after
            settling so the settle steps do not count toward episode length.

    Returns:
        The observation after settling.
    """
    for _ in range(steps):
        hold_action = torch.cat(
            [
                obs["policy"]["arm_joint_pos"],
                obs["policy"]["gripper_pos"],
            ],
            dim=-1,
        )
        obs, _, _, _, _ = env.step(hold_action)

    if reset_episode_buf:
        env.env.episode_length_buf[:] = 0

    return obs
