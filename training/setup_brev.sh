#!/usr/bin/env bash
# One-shot setup on the Brev GPU box: venv, deps, GPU check, frames, pre-labels.
#   bash training/setup_brev.sh            (run from ~/datathon, videos in ~/open/videos)
set -euo pipefail
cd "$(dirname "$0")/.."
VIDEOS="${VIDEOS:-$HOME/open/videos}"

# Crusoe's Ubuntu 22.04 image ships python3 without venv/ensurepip.
python3 -c "import ensurepip" 2>/dev/null || {
  sudo -n apt-get update -q && sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv python3-pip
}
if [ ! -d .venv-train ]; then
  python3 -m venv .venv-train
fi
. .venv-train/bin/activate
pip install -q --upgrade pip
# cu126 wheels run on drivers >= 560; newer default wheels may need a newer driver than the box has.
python -c "import torch" 2>/dev/null || pip install -q torch torchvision --index-url "${TORCH_INDEX:-https://download.pytorch.org/whl/cu126}"
pip install -q -r training/requirements.txt
python - <<'EOF'
import torch
assert torch.cuda.is_available(), "CUDA not visible to torch"
print("GPU:", torch.cuda.get_device_name(), "| torch", torch.__version__)
EOF

[ -f datasets/frames/manifest.csv ] || python training/extract_frames.py --videos "$VIDEOS" --out datasets/frames
[ -f datasets/frames/prelabels.coco.json ] || \
  python training/prelabel.py --frames datasets/frames --out datasets/frames/prelabels.coco.json
echo "done: datasets/frames/images + datasets/frames/prelabels.coco.json"
