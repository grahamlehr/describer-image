#!/usr/bin/env python3
"""The Imager repository file, os_list.json, and the checks around it.

Standard library only: it runs on a bare CI runner.

    os_list.py measure IMAGE.img.xz
        print extract_size, extract_sha256 and image_download_size as JSON
    os_list.py update --file os_list.json --url URL --release-date YYYY-MM-DD \\
            --extract-size N --extract-sha256 H --image-download-size N --init-format F
        rewrite os_list.json with this one image
    os_list.py check-init-format --codename trixie --expect cloudinit-rpi [--official FILE]
        fail unless Raspberry Pi's own Lite (64-bit) entry for that release says the same
    os_list.py local IMAGE.img.xz [--output FILE] [--init-format F]
        write a local Imager manifest for an image on disk, so Imager 2.x offers its
        Wi-Fi/user settings for it (a file chosen with "Use custom" gets none)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import sys
import urllib.request
from datetime import date
from pathlib import Path

#: What Imager opens by double-click, and accepts as a content repository.
LOCAL_MANIFEST = "os_list_local.rpi-imager-manifest"
#: Kept in step with INIT_FORMAT in .github/workflows/build.yml (the workflow
#: verifies that one against Raspberry Pi's own list).
DEFAULT_INIT_FORMAT = "cloudinit-rpi"
OFFICIAL_URL = "https://downloads.raspberrypi.com/os_list_imagingutility_v4.json"

NAME = "Describer (Raspberry Pi OS Lite, 64-bit)"
DESCRIPTION = (
    "A live UK rail departure board for a Raspberry Pi 4 and a TV, on Raspberry Pi OS Lite. "
    "Set your Wi-Fi in the settings, write the card, and scan the QR code on the screen."
)
#: Imager's device tags. Only the 4B is supported (the plan's scope).
DEVICES = ["pi4-64bit"]
CHUNK = 1024 * 1024


def measure(path: Path) -> dict[str, int | str]:
    """Sizes and the checksum of the *uncompressed* image, which is what Imager verifies."""
    digest = hashlib.sha256()
    size = 0
    with lzma.open(path, "rb") as image:
        while chunk := image.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return {
        "extract_size": size,
        "extract_sha256": digest.hexdigest(),
        "image_download_size": path.stat().st_size,
    }


def build_entry(
    *,
    url: str,
    release_date: str,
    extract_size: int,
    extract_sha256: str,
    image_download_size: int,
    init_format: str,
) -> dict[str, object]:
    return {
        "name": NAME,
        "description": DESCRIPTION,
        "url": url,
        "extract_size": extract_size,
        "extract_sha256": extract_sha256,
        "image_download_size": image_download_size,
        "release_date": release_date,
        "init_format": init_format,
        "devices": DEVICES,
        "capabilities": [],
    }


def write_os_list(path: Path, entry: dict[str, object]) -> None:
    """One entry: the latest image. Older ones stay downloadable from their Releases."""
    path.write_text(json.dumps({"os_list": [entry]}, indent=2) + "\n", encoding="utf-8")


def local_manifest(image: Path, init_format: str = DEFAULT_INIT_FORMAT) -> dict[str, list]:
    """A manifest for an image on disk: the same entry a Release gets, with a file: URL.

    Imager 2.x assumes ``init_format: none`` for an image picked with "Use custom",
    because nothing tells it how the OS wants to be customised, and offers no
    Wi-Fi/user settings. A manifest carries that metadata.
    """
    image = image.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    measured = measure(image)
    entry = build_entry(
        url=image.as_uri(),
        release_date=date.today().isoformat(),
        init_format=init_format,
        **measured,  # type: ignore[arg-type]
    )
    return {"os_list": [entry]}


def official_init_format(official: dict, codename: str) -> str:
    """The init_format of Raspberry Pi's own Lite (64-bit) entry for ``codename``."""

    def walk(items):
        for item in items:
            if "subitems" in item:
                yield from walk(item["subitems"])
            else:
                yield item

    for item in walk(official["os_list"]):
        if f"-{codename}-arm64-lite.img" in item.get("url", ""):
            return item["init_format"]
    raise LookupError(f"no {codename} arm64 Lite entry in the official os_list")


def _load_official(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    with urllib.request.urlopen(OFFICIAL_URL, timeout=60) as response:  # noqa: S310
        return json.load(response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("measure")
    p.add_argument("image", type=Path)

    p = sub.add_parser("update")
    p.add_argument("--file", type=Path, default=Path("os_list.json"))
    p.add_argument("--url", required=True)
    p.add_argument("--release-date", required=True)
    p.add_argument("--extract-size", type=int, required=True)
    p.add_argument("--extract-sha256", required=True)
    p.add_argument("--image-download-size", type=int, required=True)
    p.add_argument("--init-format", required=True)

    p = sub.add_parser("local")
    p.add_argument("image", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--init-format", default=DEFAULT_INIT_FORMAT)

    p = sub.add_parser("check-init-format")
    p.add_argument("--codename", required=True)
    p.add_argument("--expect", required=True)
    p.add_argument("--official", help="a saved copy of the official os_list (tests)")

    args = parser.parse_args(argv)

    if args.command == "measure":
        print(json.dumps(measure(args.image)))
        return 0
    if args.command == "update":
        entry = build_entry(
            url=args.url,
            release_date=args.release_date,
            extract_size=args.extract_size,
            extract_sha256=args.extract_sha256,
            image_download_size=args.image_download_size,
            init_format=args.init_format,
        )
        write_os_list(args.file, entry)
        return 0

    if args.command == "local":
        try:
            manifest = local_manifest(args.image, args.init_format)
        except FileNotFoundError as exc:
            print(f"no such image: {exc}", file=sys.stderr)
            return 1
        output = args.output or args.image.resolve().parent / LOCAL_MANIFEST
        output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {output}")
        return 0

    found = official_init_format(_load_official(args.official), args.codename)
    if found != args.expect:
        print(
            f"init_format drift: Raspberry Pi's own {args.codename} Lite entry says {found!r}, "
            f"this repo ships {args.expect!r}. Imager would not offer the Wi-Fi/user "
            "settings correctly. Update INIT_FORMAT in build.yml (and the pi-gen pin with it).",
            file=sys.stderr,
        )
        return 1
    print(f"init_format {found!r} matches the official {args.codename} Lite entry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
