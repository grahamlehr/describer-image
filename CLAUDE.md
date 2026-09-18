# describer-image

Builds the Raspberry Pi OS image for grahamlehr/describer with pi-gen.
The full brief is Phase 4 of docs/plans/easy-install.md in the describer repo; read it first.
The image runs describer's own deploy/install.sh provision in the chroot. Never duplicate install steps here.
Never commit an image, a key or a token.
