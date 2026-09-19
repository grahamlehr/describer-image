# describer-image

Builds the Raspberry Pi OS image for grahamlehr/describer with pi-gen.
The full brief is Phase 4 of docs/plans/easy-install.md in the describer repo; read it first.
The image runs describer's own deploy/install.sh provision in the chroot. Never duplicate install steps here.
Never commit an image, a key or a token.

- `PIGEN_TAG`, `RELEASE_CODENAME` and `INIT_FORMAT` in `.github/workflows/build.yml` move together.
  `init_format` is copied from Raspberry Pi's own Lite (64-bit) entry, never guessed; the workflow checks it.
- pi-gen feeds `00-run-chroot.sh` to bash on **stdin**, so nothing in it may read stdin (`</dev/null` on
  install.sh), and `/tmp` in the chroot is a tmpfs. pi-gen's config variables are not exported unless
  pi-gen exports them: `DESCRIBER_REF` is `export`ed by the workflow.
- install.sh leaves `/opt/describer` on a detached HEAD; the stage puts it on `main` tracking
  `origin/main` and fails the build if the checkout is not exactly what the updater needs.
- Publish only from `main`. Never put a key in the image.
