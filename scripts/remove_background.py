#!/usr/bin/env python3
"""Generate foreground masks suitable for COLMAP feature extraction."""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove
from tqdm import tqdm


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def postprocess_mask(alpha: np.ndarray, threshold: int, close_size: int, dilate: int) -> np.ndarray:
    """Convert a soft alpha matte into a conservative binary feature mask."""
    mask = np.where(alpha >= threshold, 255, 0).astype(np.uint8)
    if close_size > 0:
        size = close_size if close_size % 2 == 1 else close_size + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    if dilate > 0:
        size = 2 * dilate + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.dilate(mask, kernel)
    return mask


def make_overlay(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Create a QA image with a dimmed background and green mask contour."""
    foreground = mask > 0
    overlay = (rgb.astype(np.float32) * 0.18).astype(np.uint8)
    overlay[foreground] = rgb[foreground]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
    cv2.drawContours(overlay_bgr, contours, -1, (0, 255, 0), 2)
    return overlay_bgr


def suppress_vegetation(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Remove green vegetation that a saliency model joins through letter gaps."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, saturation, value = cv2.split(hsv)
    vegetation = (
        (hue >= 30)
        & (hue <= 85)
        & (saturation >= 40)
        & (value >= 20)
    )
    refined = mask.copy()
    refined[vegetation] = 0
    return refined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model", default="isnet-general-use", help="rembg ONNX model name")
    parser.add_argument("--threshold", type=int, default=48, choices=range(1, 255))
    parser.add_argument("--close-size", type=int, default=7)
    parser.add_argument("--dilate", type=int, default=5, help="Mask expansion radius in pixels")
    parser.add_argument(
        "--suppress-green",
        action="store_true",
        help="Remove vegetation-colored pixels retained between the sign letters",
    )
    args = parser.parse_args()

    image_dir = args.image_dir.resolve()
    if not image_dir.is_dir():
        raise SystemExit(f"Image directory does not exist: {image_dir}")
    image_paths = sorted(
        path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_paths:
        raise SystemExit(f"No supported images found in: {image_dir}")

    output_dir = args.output_dir.resolve()
    masks_dir = output_dir / "masks"
    foreground_dir = output_dir / "foreground"
    masked_rgb_dir = output_dir / "masked_rgb"
    overlays_dir = output_dir / "overlays"
    for directory in (masks_dir, foreground_dir, masked_rgb_dir, overlays_dir):
        directory.mkdir(parents=True, exist_ok=True)

    session = new_session(args.model)
    rows = []
    for image_path in tqdm(image_paths, desc="Removing background"):
        image = Image.open(image_path).convert("RGB")
        rgb = np.asarray(image)
        alpha_image = remove(image, session=session, only_mask=True)
        alpha = np.asarray(alpha_image.convert("L"))
        mask = postprocess_mask(alpha, args.threshold, args.close_size, args.dilate)
        if args.suppress_green:
            mask = suppress_vegetation(rgb, mask)
        coverage = float(np.count_nonzero(mask)) / mask.size

        # COLMAP appends .png to the full source filename, including its extension.
        mask_path = masks_dir / f"{image_path.name}.png"
        cv2.imwrite(str(mask_path), mask)

        rgba = np.dstack((rgb, mask))
        Image.fromarray(rgba, mode="RGBA").save(foreground_dir / f"{image_path.stem}.png")
        masked_rgb = rgb.copy()
        masked_rgb[mask == 0] = 0
        Image.fromarray(masked_rgb, mode="RGB").save(masked_rgb_dir / image_path.name, quality=95)
        cv2.imwrite(str(overlays_dir / image_path.name), make_overlay(rgb, mask))
        rows.append((image_path.name, f"{coverage:.6f}", int(np.count_nonzero(mask))))

    stats_path = output_dir / "mask_stats.csv"
    with stats_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("image", "foreground_fraction", "foreground_pixels"))
        writer.writerows(rows)

    coverages = np.array([float(row[1]) for row in rows])
    print(f"Processed {len(rows)} images")
    print(f"Masks:       {masks_dir}")
    print(f"Masked RGB:  {masked_rgb_dir}")
    print(f"QA overlays: {overlays_dir}")
    print(
        "Foreground coverage: "
        f"min={coverages.min():.1%}, median={np.median(coverages):.1%}, max={coverages.max():.1%}"
    )


if __name__ == "__main__":
    main()
