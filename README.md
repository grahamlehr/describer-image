# describer-image

Builds the Raspberry Pi OS image for [Describer](https://github.com/grahamlehr/describer), a UK rail
departure board for a Raspberry Pi 4B and a TV, and publishes it so Raspberry Pi Imager can offer it.

The plan this implements is Phase 4 of `docs/plans/easy-install.md` in the describer repo. This repo
holds only the image build; the app and its install script live there.

## What the image is

Raspberry Pi OS **Lite, 64-bit, Trixie** (built with pi-gen) plus one stage, `stage-describer`, that
runs describer's own `deploy/install.sh provision` inside the image. So there is one install script,
run in two places: on a Pi by hand, and here. Nothing in this repo re-implements an install step.

After the stage the image has `/opt/describer` (a clone of the public repo, on `main`, tracking
`origin/main`, so the in-app updater works from first boot), the `describer` user, the three
services, the polkit rules, `/etc/describer/config.yaml` (with `sources.fallback: null`) and an empty
`/etc/describer/describer.env`. **No key or token is ever in the image**; each person brings their
own Rail Data Marketplace key through the setup screen on first boot.

The stage ends with checks that fail the build if any of that is not true (wrong origin, detached
HEAD, a `config.yaml` in the checkout, a credential in `describer.env`, a missing unit).

## Layout

```
config                       pi-gen config (shell; variable names are from pi-gen's README at the pin)
stage-describer/
  prerun.sh                  copy_previous
  EXPORT_IMAGE               makes this stage the one that exports the image
  00-describer/
    00-run-chroot.sh         the whole stage
scripts/os_list.py           measures the image, writes os_list.json, checks init_format
scripts/try-stage-in-docker.sh   run the stage in a Trixie arm64 container (minutes, not an hour)
os_list.json                 the Imager repository, rewritten by the workflow
tests/                       stdlib unittest, no dependencies
.github/workflows/build.yml  the build
```

## Building

The **Build image** workflow does everything, on GitHub's free `ubuntu-24.04-arm` runners (this repo is
public). Run it from the Actions tab:

- `describer_ref`: the describer commit or branch to bake in (default `main`). It must be on `main`,
  or the updater could never fast-forward it.
- `publish`: tick it to make a Release and update `os_list.json`. Left unticked, the image is only
  attached to the run for a week, so you can flash it and look before anything is published.

A monthly run (the 1st) always publishes, so images carry recent Raspberry Pi OS fixes.

Publishing makes a Release `image-YYYY.MM.DD` (`-2`, `-3` on the same day) with the `.img.xz` and a
`.sha256`, and commits `os_list.json` to `main`. It refuses to publish from any other branch.

**Why pi-gen's own `build-docker.sh` and not `usimd/pi-gen-action`.** On an arm64 runner
`build-docker.sh` builds natively (it skips binfmt/qemu on aarch64), it is pinned to exactly the same
tag as everything else in this repo, and there is no third-party action holding write access to
Releases and `main`. The action would add convenience we do not need for one Lite-plus-one-stage image.

### Moving to a new Raspberry Pi OS release

Three values in `build.yml`'s `env:` move together: `PIGEN_TAG` (pi-gen tags are
`<date>-raspios-<release>-<arch>`; use the `arm64` one), `RELEASE_CODENAME`, and `INIT_FORMAT`. The
workflow checks `INIT_FORMAT` against Raspberry Pi's own list on every build and fails on drift, so a
release that changes it (Bookworm was `systemd`, Trixie is `cloudinit-rpi`) cannot ship silently with
the wrong value. Then check the pi-gen README at the new tag for any renamed variable in `config`.

### `init_format`

This is what makes Imager show its Wi-Fi, username and hostname settings for a custom image, and it
must match how the OS applies them on first boot. It is copied from Raspberry Pi's own "Raspberry Pi OS
Lite (64-bit)" entry in `https://downloads.raspberrypi.com/os_list_imagingutility_v4.json`, not chosen
by hand.

## Using it (Raspberry Pi Imager 2.x)

Add the repository under **App Options → Content repository**:

```
https://raw.githubusercontent.com/grahamlehr/describer-image/main/os_list.json
```

then choose **Raspberry Pi 4** and **Describer**. **Always set the Wi-Fi, username and password in
Imager's settings.** The image keeps pi-gen's defaults for the first user (as the official Lite image
does) and relies on Imager to configure it through cloud-init.

**Do not pick the image with "Use custom".** Imager 2.x cannot know how a file it has been handed
wants to be customised, so it assumes `init_format: none` and offers no Wi-Fi or user settings
(Raspberry Pi documents this in `doc/os_customisation_formats.md` in rpi-imager). What you get is
what a first boot with no settings does: a console dialog, **"Please enter new username:"**, and no
network but Ethernet. That is what the first G5 attempt showed.

### Testing a build before it is published

Give Imager a local manifest for the image, which carries the `init_format`. Download the
`describer-image` artifact from a run of **Build image**, unzip it, then:

```bash
python3 scripts/os_list.py local /path/to/image_2026-..-..-describer.img.xz
```

That writes `os_list_local.rpi-imager-manifest` next to the image (the same entry a Release gets, with a
`file://` URL). Double-click it to open it in Imager, or use **App Options → Content Repository → EDIT
→ Use custom file**, choose the manifest and **APPLY & RESTART**. The OS page then lists Describer and
the settings step appears. (Imager's own `create_local_json.py` only matches Raspberry Pi's official
image filenames, so it cannot be used for this image.)

## Checking things without a full build

```bash
python3 -m unittest discover -s tests -v     # the helper and the stage scripts' static checks
python3 scripts/os_list.py local IMAGE.img.xz  # a local Imager manifest for an unpublished build
scripts/try-stage-in-docker.sh               # the stage, for real, in Trixie arm64 (needs Docker)
TWICE=1 scripts/try-stage-in-docker.sh       # ...and again over the install: nothing is clobbered
```

The container approximates the image build; it does not replace it. It adds the Raspberry Pi apt
archive (which Pi OS has and plain Debian does not) as `trusted=yes`, in the throwaway container only.

## Not done

- **A wifi-file fallback** (`describer-wifi.txt` on the boot partition). Built only if Gate G5 shows
  Imager will not apply its settings to this image.
- **Any Pi other than the 4B.** `os_list.json` lists only the `pi4-64bit` device.
- **An icon** in `os_list.json`.
