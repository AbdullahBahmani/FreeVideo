#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

INSTALL_MODELS=0
case "${1:-}" in
  "") ;;
  --models) INSTALL_MODELS=1 ;;
  --help|-h)
    cat <<'EOF'
FreeVideo Apple Silicon preview

  ./setup_macos.sh           Install the MPS runtime and pinned source code.
  ./setup_macos.sh --models  Also download the compact video model and common assets.

The model option downloads many gigabytes. Existing verified files are reused.
EOF
    exit 0 ;;
  *)
    echo "Unknown option: $1 (use --help)" >&2
    exit 2 ;;
esac

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "FreeVideo macOS preview requires an Apple Silicon Mac running arm64." >&2
  echo "If Terminal is running under Rosetta, disable 'Open using Rosetta' and retry." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Git is required. Run: xcode-select --install" >&2
  exit 1
fi

PYTHON=""
for candidate in python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  cat >&2 <<'EOF'
Python 3.12 is required.
If you use Homebrew:
  brew install python@3.12
Then rerun ./setup_macos.sh
EOF
  exit 1
fi

VENV="$ROOT/.venv-macos"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
# PyPI macOS arm64 PyTorch wheels include MPS. Never install CUDA/Triton here.
"$VENV/bin/python" -m pip install torch torchvision torchaudio
"$VENV/bin/python" -m pip install -e '.[runtime]'
"$VENV/bin/python" -m pip install -r constraints/encoder-runtime.txt

export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"

# Fail fast before cloning sources or downloading models.
"$VENV/bin/python" scripts/check_macos.py

echo "Installing pinned OpenVDN + patched Diffusers source..."
"$VENV/bin/python" -m freevideo_engine setup --vdn-root "$ROOT/vendor/vdn" --install-packages

echo "Installing the pinned minimal ComfyUI source used by the H3 text encoder..."
"$VENV/bin/python" - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
deps = json.loads((root / "freevideo_engine/dependencies.json").read_text(encoding="utf-8"))
spec = deps["encoder"]
from freevideo_engine import network
network.clone(
    root / "vendor" / "ComfyUI",
    spec["comfy_url"],
    spec["comfy_commit"],
    sparse=["/comfy/", "/utils/", "/folder_paths.py", "/node_helpers.py", "/LICENSE"],
)
PY

if (( INSTALL_MODELS )); then
  echo "Downloading pinned compact model bundle and common H3 assets..."
  "$VENV/bin/python" scripts/setup_macos_models.py --root "$ROOT"
fi

cat <<EOF

FreeVideo Apple Silicon preview environment is ready.

Activate it with:
  source "$VENV/bin/activate"

MPS fallback is enabled by the launcher automatically.

EOF

if [[ -f "$ROOT/.freevideo/macos-paths.json" ]]; then
  "$VENV/bin/python" - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
p = json.loads((root / ".freevideo/macos-paths.json").read_text())
print("Model files are ready. First create prompt.txt, then try a conservative one-pass run:")
print()
print(f'  ./freevideo generate --prompt-file prompt.txt --cache "{p["cache"]}" \\')
print(f'    --base "{p["base"]}" --checkpoint "{p["checkpoint"]}" \\')
print(f'    --encoder-root "{root / "vendor/ComfyUI"}" --model-paths "{root / "encoder-paths.yaml"}" \\')
print('    --no-two-pass --width 512 --height 288 --frames 73 --out video.mp4')
PY
else
  echo "Models were not downloaded. When ready, run:"
  echo "  ./setup_macos.sh --models"
fi
