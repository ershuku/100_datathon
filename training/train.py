"""Fine-tune RF-DETR (Apache-2.0 sizes only) on the dataset from build_dataset.py.

    python training/train.py --data datasets/rfdetr --size medium --epochs 60 --out runs/m1

Best weights land in <out>/checkpoint_best_total.pth.
"""

from __future__ import annotations

import argparse

from rfdetr import RFDETRLarge, RFDETRMedium, RFDETRSmall

# XL / 2XL are PML-licensed and need a Roboflow account: deliberately not offered.
SIZES = {"small": RFDETRSmall, "medium": RFDETRMedium, "large": RFDETRLarge}

# Overhead desk footage; the jury clip is filmed from another angle, so geometric jitter
# (perspective, affine, rotate) matters more than colour. Vertical flip is fine from above.
AUG = {
    "HorizontalFlip": {"p": 0.5},
    "VerticalFlip": {"p": 0.2},
    "Perspective": {"scale": (0.03, 0.12), "p": 0.5},
    "Affine": {"scale": (0.75, 1.25), "translate_percent": (-0.1, 0.1), "rotate": (-25, 25),
               "shear": (-8, 8), "p": 0.6},
    "RandomBrightnessContrast": {"brightness_limit": 0.2, "contrast_limit": 0.2, "p": 0.4},
    "HueSaturationValue": {"hue_shift_limit": 8, "sat_shift_limit": 20, "val_shift_limit": 15, "p": 0.3},
    "GaussianBlur": {"blur_limit": (3, 5), "p": 0.15},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", choices=list(SIZES), default="medium")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--no-aug", action="store_true")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--resolution", type=int, default=None,
                    help="input size; must be divisible by patch_size * num_windows (32 for Medium/Large)")
    args = ap.parse_args()

    model = SIZES[args.size]()
    extra = {"resolution": args.resolution} if args.resolution else {}
    model.train(
        **extra,
        dataset_dir=args.data,
        output_dir=args.out,
        epochs=args.epochs,
        batch_size=args.batch,
        grad_accum_steps=args.grad_accum,
        lr=args.lr,
        aug_config={} if args.no_aug else AUG,
        resume=args.resume,
        checkpoint_interval=10,
        device="cuda",
    )


if __name__ == "__main__":
    main()
