#!/usr/bin/env bash
# Run the Describer stage script for real in a throwaway Debian Trixie arm64
# container, without pi-gen. It is an approximation of the image build, not a
# substitute for it: it proves `install.sh provision` and the checks after it
# work on a clean Trixie, and takes minutes rather than an hour. Needs Docker
# running, and network (apt, GitHub, PyPI, Hugging Face).
#
#   scripts/try-stage-in-docker.sh [describer-ref]     # default: main
#   TWICE=1 scripts/try-stage-in-docker.sh             # then run it again over the
#                                                      # install, and check config and
#                                                      # credentials survive
#
# Nothing here calls Realtime Trains, and no key is involved.
set -euo pipefail

cd "$(dirname "$0")/.."
ref="${1:-main}"
url=https://github.com/grahamlehr/describer.git

sha="$(git ls-remote "$url" "refs/heads/$ref" | cut -f1)"
if [ -z "$sha" ]; then
  sha="$ref" # already a commit
fi
echo "Describer commit: $sha"

docker run --rm --platform linux/arm64 \
  -e "DESCRIBER_REF=$sha" -e "TWICE=${TWICE:-0}" \
  -v "$PWD/stage-describer/00-describer/00-run-chroot.sh:/stage.sh:ro" \
  debian:trixie bash -euo pipefail -c '
    apt-get update
    apt-get install -y --no-install-recommends systemd util-linux
    # What Pi OS has and a bare container does not: the Raspberry Pi apt archive
    # (python3-lgpio lives there) and the hardware groups.
    # trusted=yes: the published archive key is SHA-1 signed, which Trixie apt
    # refuses, and a real image ships the updated Raspberry Pi keyring package.
    # Fine for a container that is thrown away; never do this on a Pi.
    echo "deb [trusted=yes] http://archive.raspberrypi.com/debian/ trixie main" \
      > /etc/apt/sources.list.d/raspi.list
    groupadd -f video; groupadd -f render; groupadd -f input; groupadd -f audio; groupadd -f gpio
    bash /stage.sh </dev/null
    if [ "$TWICE" = 1 ]; then
      echo "=== second run, over the existing install ==="
      # Something a person would have changed since the first run.
      echo "# edited by hand" >> /etc/describer/config.yaml
      echo "# kept across a second provision" >> /etc/describer/describer.env
      echo "marker" > /opt/describer/voices/keep-me
      chown describer:describer /opt/describer/voices/keep-me
      bash /stage.sh </dev/null
      grep -q "# edited by hand" /etc/describer/config.yaml
      grep -q "# kept across a second provision" /etc/describer/describer.env
      test -f /opt/describer/voices/keep-me
      echo "second run left config, credentials and the checkout alone"
    fi
  '
