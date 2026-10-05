"""Apple Silicon sampler adapter for pinned OpenVDN.

The upstream sampler is mathematically device-agnostic except for CUDA-only
synchronization and its device-local Generator. PyTorch MPS still does not
provide the same Generator contract on all supported releases, so this preview
draws the initial noise from one seeded CPU generator and transfers it to MPS.
The denoising loop and scheduler arithmetic otherwise mirror pinned VDN.
"""
from __future__ import annotations

import time
import torch

from diffusers import MiniMaxH3Scheduler
from diffusers.modular_pipelines.minimax_h3.before_denoise import (
    MiniMaxH3PrepareLayoutStep, patchify_video_latents,
)
from diffusers.modular_pipelines.minimax_h3.modular_pipeline import (
    MINIMAX_H3_AUDIO_CHANNELS as AUDIO_CHANNELS,
    MINIMAX_H3_AUDIO_TAG as AUDIO_TAG,
    MINIMAX_H3_VIDEO_TAG as VIDEO_TAG,
    align_num_frames,
    audio_latent_num_frames,
    video_latent_num_frames,
)

from src.inference.render import LATENT_H, LATENT_W
from src.models.hybrid_transform import iter_hybrids, set_layout
from src.models.sequence_layout import layout_from_indices

from .device import synchronize


@torch.no_grad()
def generate_latents(transformer, prompt_embeds, text_token_tags, num_frames,
                     num_steps, seed, device, video_shift=12.0, audio_shift=3.0,
                     runtime=None, step_seconds=None, conditions=None):
    """MPS spelling of OpenVDN's text-to-video sampler.

    The first macOS preview deliberately supports text-to-video only, so
    reference/keyframe conditioning and distributed runtimes fail explicitly.
    """
    device = torch.device(device)
    if device.type != "mps":
        raise ValueError("The Apple sampler is only for an MPS device")
    if runtime is not None:
        raise ValueError("Distributed/Ulysses sampling is not enabled on MPS")
    if conditions:
        raise ValueError("Reference/keyframe conditioning is not enabled in the first MPS preview")

    num_frames = align_num_frames(num_frames, 17, 5)
    num_latent_frames = video_latent_num_frames(num_frames, 17, 5)
    num_audio_latents = audio_latent_num_frames(num_frames)
    patch = tuple(transformer.config.patch_size)
    channels = transformer.config.in_channels
    frame_h, frame_w = LATENT_H // patch[1], LATENT_W // patch[2]

    (position_ids, token_tags, video_indices, audio_indices, text_indices,
     num_condition_rows, _) = MiniMaxH3PrepareLayoutStep.build_packed_sequence(
        text_token_tags, num_latent_frames, LATENT_H, LATENT_W,
        num_audio_latents, patch, AUDIO_CHANNELS, AUDIO_TAG, VIDEO_TAG,
        keyframe_anchors=(),
    )
    if num_condition_rows:
        raise AssertionError("Text-to-video layout unexpectedly contains conditioning rows")

    position_ids, token_tags = position_ids.to(device), token_tags.to(device)
    video_indices, audio_indices, text_indices = (
        video_indices.to(device), audio_indices.to(device), text_indices.to(device)
    )

    if next(iter_hybrids(transformer), None) is not None:
        set_layout(transformer, layout_from_indices(
            video_indices, num_latent_frames, frame_h * frame_w,
            seq_len=position_ids.shape[0], frame_size=(frame_h, frame_w),
            text_indices=text_indices,
        ))

    scheduler = MiniMaxH3Scheduler(shift=video_shift)
    audio_scheduler = MiniMaxH3Scheduler(shift=audio_shift)
    scheduler.set_timesteps(num_steps, device=device)
    audio_scheduler.set_timesteps(num_steps, device=device)

    # CPU generator is intentional. It gives this port a stable seed contract
    # even on PyTorch builds where torch.Generator("mps") is unavailable.
    generator = torch.Generator(device="cpu").manual_seed(seed)

    def seeded_randn(shape):
        return torch.randn(shape, generator=generator, device="cpu",
                           dtype=torch.float32).to(device)

    latents = seeded_randn((1, channels, num_latent_frames, LATENT_H, LATENT_W))
    video_rows = patchify_video_latents(latents, patch)
    audio_rows = seeded_randn((num_audio_latents * AUDIO_CHANNELS, 32))

    seq_len = position_ids.shape[0]
    for t, audio_t in zip(scheduler.timesteps, audio_scheduler.timesteps):
        step_started = time.perf_counter()
        row_timesteps = torch.full(
            (seq_len,), float(t), dtype=torch.float32, device=device
        )
        row_timesteps[audio_indices] = float(audio_t)
        timestep, timestep_indices = torch.unique(
            row_timesteps, sorted=True, return_inverse=True
        )
        noise_pred, audio_noise_pred = transformer(
            hidden_states=video_rows[None],
            audio_hidden_states=audio_rows[None],
            encoder_hidden_states=prompt_embeds[None],
            timestep=timestep,
            timestep_indices=timestep_indices,
            token_tags=token_tags,
            position_ids=position_ids,
            video_indices=video_indices,
            audio_indices=audio_indices,
            text_indices=text_indices,
            return_dict=False,
        )
        video_rows = scheduler.step(
            noise_pred[0].float(), t, video_rows, return_dict=False
        )[0]
        audio_rows = audio_scheduler.step(
            audio_noise_pred[0].float(), audio_t, audio_rows, return_dict=False
        )[0]

        if step_seconds is not None:
            synchronize(device)
            step_seconds.append(time.perf_counter() - step_started)

    rows = video_rows.reshape(
        -1, num_latent_frames, frame_h, frame_w, channels, *patch
    )
    rows = rows.permute(0, 4, 1, 5, 2, 6, 3, 7)
    latents = rows.reshape(
        -1, channels, num_latent_frames, LATENT_H, LATENT_W
    ).contiguous()
    audio_latents = audio_rows.reshape(
        AUDIO_CHANNELS, num_audio_latents, 32
    ).permute(0, 2, 1).contiguous()
    return latents, audio_latents
