<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="web/assets/freevideo.svg">
    <img alt="FreeVideo" src="web/assets/freevideo-light.svg" width="65%">
  </picture>
</div>

<p align="center">
| <a href="https://github.com/FlashML-org/FreeVideo/releases/download/windows-preview/FreeVideo.exe"><b>Download</b></a> | <a href="https://discord.gg/MsA277cJzZ"><b>Discord</b></a> | <a href="https://freevideo-community.pages.dev/qq"><b>QQ Group</b></a> | <a href="https://freevideo-community.pages.dev/wechat"><b>WeChat Group</b></a> |
</p>

<p align="center">English · <a href="README.zh-CN.md">中文</a></p>

Make videos on the computer you already own. Powered by [Video DeltaNet (VDN)](https://openvdn.github.io/), FreeVideo runs MiniMax H3 in as little as 8 GB of VRAM and 16 GB of RAM, with acceleration adapted to your&nbsp;hardware.

https://github.com/user-attachments/assets/ecda7d0d-7fbe-4e0c-8c29-8f3315bafc15

## About

FreeVideo is a local inference engine for MiniMax H3 on consumer GPUs, built on [OpenVDN](https://github.com/OpenVDN)'s 8-step [VDN-H3](https://huggingface.co/OpenVDN/vdn-minimax-h3) model with [Video DeltaNet](https://openvdn.github.io/)'s hybrid attention.

It coordinates VRAM, system memory and disk, adapting weight placement, compute precision and attention kernels to the available hardware. FreeVideo runs as a ComfyUI plugin, with a Windows launcher for setup and command-line support on Linux. Its core features include:

- **Hardware-adaptive execution**: Chooses the FP8 compute path for each GPU architecture, either native FP8 or FP8 storage with BF16 compute, and automatically probes the available attention kernels.
- **Low-memory inference**: Weight streaming, asynchronous prefetching and chunked computation keep peak memory low, enabling inference with as little as 8 GB of VRAM and 16 GB of RAM.
- **Multimodal inputs**: Text prompts, first and last frames, and image, video and audio references.
- **Community LoRAs**: Use MiniMax H3 LoRAs in your workflow. See [examples](docs/LoRA.md).
- **ComfyUI integration**: A dedicated creative workspace inside ComfyUI that supports two-pass sampling and batch generation and keeps a history of past creations. For finer control, switch to the node view to add LoRAs or customize the workflow.
- **One-click deployment**: The Windows launcher sets up ComfyUI, the runtime environment and the models, reuses existing models, and supports offline installation.

## Getting Started

### Windows

1. [Download FreeVideo.exe](https://github.com/FlashML-org/FreeVideo/releases/download/windows-preview/FreeVideo.exe) and run it.
2. Select an existing ComfyUI folder or install a new one. Existing model folders can be added for reuse; missing models are downloaded automatically.
3. Click **Install & launch**. ComfyUI opens in the browser with the FreeVideo workspace.

<div align="center">
  <img alt="FreeVideo creative workspace" src="https://github.com/user-attachments/assets/7647a6f8-4306-403c-b147-45d7a393e18d" width="92%">
</div>

**Offline installation:** Download the packages from [Quark](https://pan.quark.cn/s/c51235b84618) and drag the ZIP files into the launcher without extracting them. The common models and the model pack for your GPU (30/40 series or 50 series) are required; a new ComfyUI installation also requires the environment package.

### Existing ComfyUI

Install FreeVideo as a custom node:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/FlashML-org/FreeVideo.git
```

Restart ComfyUI, open **Workflow → Browse Templates → FreeVideo → FreeVideo-All-in-One**, and complete the setup in FreeVideo **Settings**.

### macOS — experimental Apple Silicon preview

This fork contains an experimental **MPS/Metal** backend for Apple Silicon. It is a
correctness-first port, not a performance-qualified release. The first preview supports
**one-pass text-to-video only** and intentionally disables CUDA/Triton/SageAttention/
FlashAttention paths, two-pass refinement, LoRAs and resident worker caching.

Current memory target: **48 GB unified memory minimum, 64 GB or more recommended**.
The transformer remains in compact FP8 storage in CPU/unified memory and each wide
linear is expanded temporarily for BF16/FP16 MPS compute.

Install the runtime and pinned model-code dependencies:

```bash
git clone https://github.com/AbdullahBahmani/FreeVideo.git
cd FreeVideo
git checkout experimental/macos-mps
chmod +x setup_macos.sh freevideo
./setup_macos.sh
```

Run the MPS smoke test at any time:

```bash
.venv-macos/bin/python scripts/check_macos.py
```

Download the pinned compact model bundle, VAE/audio assets and H3 text encoder:

```bash
./setup_macos.sh --models
```

Then create `prompt.txt` and start with a small, one-pass request:

```bash
./freevideo generate --prompt-file prompt.txt \
  --cache prepared/edge-ae041e5aec51f851/rowwise/cache \
  --base models/h3-base \
  --checkpoint models/stage-dmd-step-250 \
  --encoder-root vendor/ComfyUI \
  --model-paths encoder-paths.yaml \
  --no-two-pass --width 512 --height 288 --frames 73 \
  --out video.mp4
```

`setup_macos.sh --models` prints the exact paths for the pinned revision after download.
The MPS port still needs validation on real Apple hardware, especially the pinned NVFP4
H3 text encoder. If that dependency rejects MPS, the error is intentionally surfaced
instead of silently moving the 32B encoder to CPU.

### Linux

Install:

```bash
git clone https://github.com/FlashML-org/FreeVideo.git && cd FreeVideo
./setup.sh
```

Generate a video from a prompt file:

```bash
./freevideo generate --prompt-file prompt.txt --out video.mp4
```

### More details

- [FreeVideo Adaptive Execution Planner](docs/execution-planning.md)

### Support

Report bugs in [GitHub Issues](https://github.com/FlashML-org/FreeVideo/issues), or ask questions on [Discord](https://discord.gg/MsA277cJzZ), [QQ](https://freevideo-community.pages.dev/qq) or [WeChat](https://freevideo-community.pages.dev/wechat).

## Citation

FreeVideo is based on VDN-H3. If you use FreeVideo in your research, please cite the [Video DeltaNet paper](https://arxiv.org/abs/2609.20744):

```bibtex
@article{xi2026videodeltanet,
  title={Video DeltaNet: A Video-Native Hybrid Attention for Livestream Video Generation},
  author={Xi, Haocheng and Xie, Yiming and Zhao, Hexu and Zhang, Yiwen and Liu, Michael and Creavin, Thomas and Keutzer, Kurt and Li, Xiuyu and Lv, Zhaoyang and Xu, Chenfeng and Feng, Haiwen},
  journal={arXiv preprint arXiv:2609.20744},
  year={2026}
}
```

## Team

### Project Team

[Bowen Xue](https://github.com/KBRASK) · [Shuo Yang](https://github.com/andy-yang-1) · [Haocheng Xi](https://github.com/haochengxi) · [Xiaoze Fan](https://github.com/jason-fxz) · [Chenfeng Xu](https://github.com/chenfengxu714)

### Special Thanks

Special thanks to [**AIwood爱屋研究室**](https://space.bilibili.com/503934057) and [**T8star-Aix**](https://space.bilibili.com/385085361) for testing the project and providing valuable feedback.

*Listed in chronological order of participation.*

## Acknowledgment

We thank [OpenVDN](https://github.com/OpenVDN) for [Video DeltaNet / VDN-H3](https://github.com/OpenVDN/vdn-minimax-h3) and its open-source model weights, training code and inference implementation.

We thank Impossible Research for providing computation resources.

We also thank [MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) for the base model and the following projects:
[ComfyUI](https://github.com/Comfy-Org/ComfyUI),
[Diffusers](https://github.com/huggingface/diffusers),
[SageAttention](https://github.com/thu-ml/SageAttention),
the [MiniMax H3 latent upscaler](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler),
the [H3 text encoder for ComfyUI](https://huggingface.co/t8star/Vdn-Minimax-H3-Comfy) and
[Qt for Python](https://doc.qt.io/qtforpython-6/).

## License

The code is released under the [Apache License 2.0](LICENSE). The model weights are licensed under the [MiniMax H3 Community License](https://huggingface.co/OpenVDN/vdn-minimax-h3-edge/blob/main/LICENSE), which includes territorial and acceptable-use restrictions.
