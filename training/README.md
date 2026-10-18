# Detector training (RF-DETR on Brev)

Stage 1 of the analyzer: an object/state detector. Its per-frame output feeds the event and rule
stage (`src/pipeline/analyzer.py`). Data and outputs (`datasets/`, `runs/`, `exports/`) are
git-ignored and must stay on team machines: no cloud labelling (app.cvat.ai, Roboflow upload)
and no sending frames to any external service.

| Step | Script | Where | Time |
|---|---|---|---|
| 1. Sample frames (2 fps, dedup) | `extract_frames.py` | anywhere | 2 min |
| 2. Zero-shot pre-labels | `prelabel.py` (Grounding DINO base, Apache-2.0) | Brev GPU | ~5 min |
| 3. Correct labels | CVAT, self-hosted | Brev or a laptop | 3 h, split 4 ways |
| 4. Build dataset | `build_dataset.py` | Brev | 1 min |
| 5. Train | `train.py` (RF-DETR Medium, Apache-2.0) | Brev GPU | ~1 h |
| 6. Check on clips | `infer_video.py` | Brev GPU | seconds per clip |

Default split (`splits.py`) keeps recordings of one scenario together: 40 unique videos →
train 25, validation 9 (X-4/5, X-22/23, X-38/39, X-43/44/45), test 6 (X-2/3, X-24/25, X-28/29).
X-47/X-48 are byte-identical copies of X-4/X-5 and are skipped everywhere (`DUPLICATE_OF`).
Compare model versions on validation only; look at test **once**, after the final model is
chosen. `--holdout-pov behind` trains on front clips only and validates on behind clips, to
estimate how badly a new camera angle hurts.

## 0. Brev box

One L40S or A100 with the PyTorch/CUDA image. Then:

```bash
# on your laptop (brev refresh adds the instance to ~/.ssh/config); videos are ~370 MB
rsync -av --exclude .venv --exclude frontend/node_modules datathon/ <instance>:~/datathon/
rsync -av open/videos/ <instance>:~/open/videos/
brev shell <instance>
cd ~/datathon
python -m venv .venv-train && . .venv-train/bin/activate
pip install -r training/requirements.txt
python -c "import torch; print(torch.cuda.get_device_name())"
```

If `ssh <instance>` times out, Brev's generated config may point at a closed port; connect
directly with `ssh -i ~/.brev/brev.pem -p 22 ubuntu@<instance IP>` (IP from `~/.brev/ssh_config`).
`training/setup_brev.sh` does the venv, deps (torch cu126 wheels), frames and pre-labels in one go.

No API tokens are needed: RF-DETR and Grounding DINO weights download anonymously. If you add a
Hugging Face token anyway, export it as `HF_TOKEN` in the shell, never in a file in the repo.

## 1–2. Frames and pre-labels

```bash
python training/extract_frames.py --videos ~/open/videos --out datasets/frames    # ~1,800 frames
python training/prelabel.py --frames datasets/frames --out datasets/frames/prelabels.coco.json
# or one file per annotator:
python training/prelabel.py --frames datasets/frames --only X-1,X-2,X-3 --out exports/pre_baga.json
```

## 3. Correcting labels in CVAT

Run CVAT yourselves (`docker compose up` from the CVAT repo) on Brev (`brev port-forward
<instance> -p 8080:8080`) or on a teammate's laptop. Create a task with the frame images, labels
exactly as in `training/classes.py`, then *Upload annotations → COCO 1.0* with the pre-label file.
Export the corrected task as COCO 1.0 into `exports/`.

Box rules (consistency beats precision):
- **person**: everyone visible, including people seen through a doorway.
- **cash_stack**: every stack or bundle, in hands, on the desk, in the counter's tray or reject pocket.
- **cash_bag**: collection bag, opened or closed. **id_card**: only when visible as a card.
- **keys**: in the safe lock, on the desk or in a hand.
- **safe_open / safe_closed**, **laptop_open / laptop_closed**, **door_open / door_closed**: one
  box per object, label by state. The pre-labeller always guesses closed safe, open laptop, closed
  door, so check these on every frame.
- **personal_item**: cups, phones, gum, jackets, handbags on the desk or in hand.
- If an object is more than half hidden, skip it. Don't box things outside the room.

## 4–6. Dataset, training and checking

```bash
python training/build_dataset.py --frames datasets/frames --coco exports/*.json --out datasets/rfdetr \
    --extra datasets/openimages        # optional: Open Images subset from training/openimages.py
python training/train.py --data datasets/rfdetr --size medium --epochs 60 --out runs/m1
python training/infer_video.py --weights runs/m1/checkpoint_best_total.pth \
    --video ~/open/videos/X-22.mov --out runs/m1/timelines/X-22.jsonl --preview runs/m1/X-22.mp4
```

Check the class table `build_dataset.py` prints: a class with no train boxes is dropped
by RF-DETR. Watch validation mAP per class, and open the preview videos for the validation clips.
The state classes (open/closed) matter most to the rules. If memory runs out, lower `--batch`
and raise `--grad-accum` so their product stays 16.
