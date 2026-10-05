#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "FreeVideo macOS preview requires an Apple Silicon Mac running arm64." >&2
  echo "If Terminal is running under Rosetta, disable 'Open using Rosetta' and retry." >&2
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
# PyPI's macOS arm64 PyTorch wheels include MPS; do not install CUDA/Triton.
"$VENV/bin/python" -m pip install torch torchvision torchaudio
"$VENV/bin/python" -m pip install -e '.[runtime]'

export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
"$VENV/bin/python" scripts/check_macos.py

cat <<EOF

FreeVideo Apple Silicon environment is ready:
  $VENV

Activate it with:
  source "$VENV/bin/activate"

This branch is an experimental MPS port.  The smoke test verifies Metal/MPS and
the portable attention path without downloading the large video model.
EOF
