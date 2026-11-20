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
os_list.json                 the old Imager repository file; Imager now reads the one on the `imager` branch
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
`.sha256`, and commits `os_list.json` to the **`imager` branch**. It refuses to publish from any branch
but `main`.

**Why a separate branch.** `main` is protected (changes only by pull request), so the workflow cannot
commit to it: the November 2026 run made its Release and then failed at the push, leaving Imager on the
October image. The `imager` branch holds nothing but `os_list.json`, shares no history with `main`, and
must stay unprotected. The workflow creates it on the first publish. The `os_list.json` on `main` is the
old location, kept so the old URL still answers; nothing updates it.

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

## Building locally

The same steps as the workflow, by hand, on an arm64 machine with Docker (an Apple Silicon Mac builds
natively, in about 15 minutes). Use this to try a change on a card before anything is published.
`build.yml` is the source of truth: if it and this section disagree, follow `build.yml` and fix this.

Run everything from the repo root, on an up-to-date `main`.

```bash
# 1. The describer commit to bake in. It must be on main.
git ls-remote https://github.com/grahamlehr/describer.git refs/heads/main
```

```bash
# 2. pi-gen at the pinned tag (PIGEN_TAG in build.yml). Once; pi-gen/ is gitignored.
git clone --depth 1 --branch 2026-09-15-raspios-trixie-arm64 https://github.com/RPi-Distro/pi-gen.git pi-gen
```

```bash
# 3. Our stage and config, fresh each time, and the commit from step 1.
rm -rf pi-gen/stage-describer pi-gen/deploy
cp -R stage-describer pi-gen/stage-describer
touch pi-gen/stage2/SKIP_IMAGES
cp config pi-gen/config
echo "export DESCRIBER_REF=<full sha from step 1>" >> pi-gen/config
```

```bash
# 4. Build. A container left by an interrupted build stops the next one, so remove it first.
docker rm -v pigen_work 2>/dev/null; (cd pi-gen && ./build-docker.sh)
```

The build has worked when the log says `Describer stage done: <sha> on main` and
`pi-gen/deploy/` holds one `image_<date>-describer.img.xz`.

```bash
# 5. Package it where Imager can find it. out/ is gitignored.
mkdir -p out && mv pi-gen/deploy/image_*-describer.img.xz out/
(cd out && shasum -a 256 image_*-describer.img.xz > "$(ls image_*-describer.img.xz).sha256")
python3 scripts/os_list.py local out/image_*-describer.img.xz
```

Then flash it with the manifest, as in "Testing a build before it is published" below.

### Checking first boot before flashing

The stage's checks see the image as built. Raspberry Pi OS's first-boot user setup runs later and
changes systemd state (cloud-init calls `/usr/lib/userconf-pi/userconf`, which ends in
`/usr/bin/cancel-rename`), and two images that passed every file check failed there: one left the TV on
a login prompt, the next asked for a username for ever. describer's `docs/traps.md` has both.

So run that script against the image's own files before handing a card to anyone:

1. Decompress the image and mount its second partition read-only in a `--privileged` Debian container
   (start sector at byte 470 of the MBR; the Debian base image has no `xz`, so decompress on the host).
2. Put a tmpfs overlay on it, empty `/etc/fstab`, and mask `describer.service` (so nothing polls an
   upstream), the `cloud-*` services, `userconfig.service` and NetworkManager.
3. Bind `/proc`, `/sys` and `/dev` into it and `exec chroot <root> /lib/systemd/systemd`. The container
   needs `--cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw`.
4. In it, run `/usr/lib/userconf-pi/userconf <name> "$(openssl passwd -6 <throwaway>)"`.

It passes when `userconf` exits 0, `systemctl is-active kiosk` still says `activating` (it is waiting
for the masked backend) and `getty@tty1` is `inactive`. This does not prove cage and Chromium on a TV,
or that Imager's Wi-Fi settings apply. Only a flashed card does.

A good first boot on the card: no username prompt, no failed cloud services, and the "Set up your
departure board" screen with its QR code, still there after a reboot.

## Using it (Raspberry Pi Imager 2.x)

Add the repository under **App Options → Content repository**:

```
https://raw.githubusercontent.com/grahamlehr/describer-image/imager/os_list.json
```

then choose **Raspberry Pi 4** and **Describer**. **Always set the Wi-Fi, username and password in
Imager's settings.** The image keeps pi-gen's defaults for the first user (as the official Lite image
does) and relies on Imager to configure it through cloud-init. Any username will do except
`describer`: the image already has a system user of that name, which the board runs as.

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
