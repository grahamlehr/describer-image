"""The Imager repository helper. Offline: the official list is a small fixture."""

import hashlib
import json
import lzma
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import os_list  # noqa: E402

OFFICIAL = {
    "os_list": [
        {
            "name": "Raspberry Pi OS (64-bit)",
            "url": "https://x/2026-09-15-raspios-trixie-arm64.img.xz",
            "init_format": "cloudinit-rpi",
        },
        {
            "name": "Raspberry Pi OS (other)",
            "subitems": [
                {
                    "name": "Raspberry Pi OS Lite (64-bit)",
                    "url": "https://x/2026-09-15-raspios-trixie-arm64-lite.img.xz",
                    "init_format": "cloudinit-rpi",
                },
                {
                    "name": "Raspberry Pi OS (Legacy, 64-bit) Lite",
                    "url": "https://x/2026-09-15-raspios-bookworm-arm64-lite.img.xz",
                    "init_format": "systemd",
                },
            ],
        },
    ]
}


class OsListTests(unittest.TestCase):
    def test_measure_reports_the_uncompressed_image(self):
        data = b"describer" * 100_000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.img.xz"
            path.write_bytes(lzma.compress(data))

            got = os_list.measure(path)

        self.assertEqual(got["extract_size"], len(data))
        self.assertEqual(got["extract_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(got["image_download_size"], len(lzma.compress(data)))

    def test_the_entry_has_every_field_imager_needs(self):
        entry = os_list.build_entry(
            url="https://example/x.img.xz",
            release_date="2026-09-19",
            extract_size=3,
            extract_sha256="ab",
            image_download_size=2,
            init_format="cloudinit-rpi",
        )

        for field in (
            "name",
            "url",
            "extract_size",
            "extract_sha256",
            "image_download_size",
            "release_date",
            "init_format",
            "devices",
        ):
            self.assertIn(field, entry)
        self.assertEqual(entry["devices"], ["pi4-64bit"])

    def test_update_writes_a_single_entry_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "os_list.json"
            target.write_text('{"os_list": [{"name": "old"}, {"name": "older"}]}')

            code = os_list.main(
                [
                    "update",
                    "--file",
                    str(target),
                    "--url",
                    "https://example/x.img.xz",
                    "--release-date",
                    "2026-09-19",
                    "--extract-size",
                    "3",
                    "--extract-sha256",
                    "ab",
                    "--image-download-size",
                    "2",
                    "--init-format",
                    "cloudinit-rpi",
                ]
            )

            written = json.loads(target.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(len(written["os_list"]), 1)
        self.assertEqual(written["os_list"][0]["url"], "https://example/x.img.xz")

    def test_the_official_value_is_found_for_the_right_release(self):
        self.assertEqual(os_list.official_init_format(OFFICIAL, "trixie"), "cloudinit-rpi")
        self.assertEqual(os_list.official_init_format(OFFICIAL, "bookworm"), "systemd")
        with self.assertRaises(LookupError):
            os_list.official_init_format(OFFICIAL, "forky")

    def test_drift_from_the_official_value_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            official = Path(tmp) / "official.json"
            official.write_text(json.dumps(OFFICIAL))
            args = ["check-init-format", "--codename", "trixie", "--official", str(official)]

            self.assertEqual(os_list.main([*args, "--expect", "cloudinit-rpi"]), 0)
            self.assertEqual(os_list.main([*args, "--expect", "systemd"]), 1)

    def test_a_local_manifest_points_at_the_file_and_carries_init_format(self):
        data = b"describer" * 50_000
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image_2026-09-19-describer.img.xz"
            image.write_bytes(lzma.compress(data))

            code = os_list.main(["local", str(image)])

            manifest = Path(tmp) / "os_list_local.rpi-imager-manifest"
            entry = json.loads(manifest.read_text())["os_list"][0]
            self.assertEqual(code, 0)
            self.assertEqual(entry["url"], image.resolve().as_uri())
            self.assertTrue(entry["url"].startswith("file:///"))
            self.assertEqual(entry["init_format"], "cloudinit-rpi")
            self.assertEqual(entry["extract_size"], len(data))
            self.assertEqual(entry["extract_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(entry["devices"], ["pi4-64bit"])

    def test_a_missing_image_is_an_error_not_a_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = os_list.main(["local", str(Path(tmp) / "nope.img.xz")])

            self.assertEqual(code, 1)
            self.assertFalse((Path(tmp) / "os_list_local.rpi-imager-manifest").exists())

    def test_the_committed_os_list_is_valid(self):
        data = json.loads((ROOT / "os_list.json").read_text())
        self.assertIsInstance(data["os_list"], list)


class ScriptTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        for path in (
            ROOT / "stage-describer" / "prerun.sh",
            ROOT / "stage-describer" / "00-describer" / "00-run-chroot.sh",
        ):
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_stage_scripts_are_executable(self):
        """pi-gen only runs a script whose executable bit is set."""
        for path in (
            ROOT / "stage-describer" / "prerun.sh",
            ROOT / "stage-describer" / "00-describer" / "00-run-chroot.sh",
        ):
            self.assertTrue(path.stat().st_mode & 0o111, path)

    def test_the_stage_never_duplicates_install_steps(self):
        text = (ROOT / "stage-describer" / "00-describer" / "00-run-chroot.sh").read_text()
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertIn("deploy/install.sh provision", code)
        for forbidden in ("useradd", "pip install", "systemctl enable", "install -m", "install -d"):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
