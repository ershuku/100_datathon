Model weights go here (not committed). The Dockerfile copies this directory into the image at
build time so the container needs no internet after build.

Expected by the real analyzer (`PIPELINE=real`, see `src/pipeline/analyzer.py`):

    models/detector/checkpoint_best_total.pth   # RF-DETR detector (training/train.py output)

Override with `DETECTOR_WEIGHTS`. Record which run and SHA-256 you baked in, e.g.
`sha256sum models/detector/checkpoint_best_total.pth`.
