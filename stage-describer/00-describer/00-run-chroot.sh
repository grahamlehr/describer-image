#!/bin/bash
# The whole Describer stage. pi-gen runs this inside the image's chroot by
# feeding it to bash on stdin (which is why nothing below may read stdin, and
# why it says `set` for itself rather than relying on a `-e` flag).
#
# It does not install anything itself: it runs describer's own
# `deploy/install.sh provision`, the same script a person runs on a Pi, and then
# checks what came out. Never duplicate install steps here.
set -euo pipefail

: "${DESCRIBER_REF:?DESCRIBER_REF is not set: the workflow exports it from config}"

REPO_URL=https://github.com/grahamlehr/describer.git
CHECKOUT=/opt/describer

export DEBIAN_FRONTEND=noninteractive
# install.sh migrates an old per-user install when it is run through sudo.
unset SUDO_USER

# The one thing we need before install.sh can run: a way to fetch it.
apt-get update
apt-get install -y --no-install-recommends git ca-certificates

# /tmp is a tmpfs pi-gen mounts inside the chroot; it goes with the build.
git clone --quiet "$REPO_URL" /tmp/describer
git -C /tmp/describer checkout --quiet "$DESCRIBER_REF"

# </dev/null: this script is our stdin, and a tool that reads stdin would eat it.
DESCRIBER_REF="$DESCRIBER_REF" /tmp/describer/deploy/install.sh provision </dev/null
rm -rf /tmp/describer

# ---------------------------------------------------------------------------
# The updater must work from first boot, and it will not update a checkout that
# is on a detached HEAD, on another branch, or with commits of its own
# (describer's updater.py). install.sh clones origin and checks out a commit,
# which leaves a detached HEAD, so put the checkout on main at that commit,
# tracking origin/main. Then refuse to ship anything that is not right.
# ---------------------------------------------------------------------------
as_describer() { runuser -u describer -- env HOME=/var/lib/describer "$@"; }
in_checkout() { as_describer git -C "$CHECKOUT" "$@"; }

in_checkout checkout --quiet -B main "$DESCRIBER_REF"
in_checkout branch --quiet --set-upstream-to=origin/main main

fail() {
  echo "IMAGE CHECK FAILED: $*" >&2
  exit 1
}

[ "$(in_checkout remote get-url origin)" = "$REPO_URL" ] || fail "origin is not $REPO_URL"
[ "$(in_checkout symbolic-ref --short HEAD)" = main ] || fail "the checkout is not on main"
[ "$(in_checkout rev-parse --abbrev-ref 'main@{upstream}')" = origin/main ] \
  || fail "main does not track origin/main"
[ "$(in_checkout rev-parse HEAD)" = "$(in_checkout rev-parse "$DESCRIBER_REF^{commit}")" ] \
  || fail "the checkout is not at $DESCRIBER_REF"
in_checkout merge-base --is-ancestor HEAD origin/main \
  || fail "$DESCRIBER_REF is not on origin/main, so the updater could never fast-forward it"
[ -z "$(in_checkout status --porcelain --untracked-files=no)" ] || fail "the checkout has local changes"

# A config.yaml here would shadow /etc/describer/config.yaml.
[ ! -e "$CHECKOUT/config.yaml" ] || fail "$CHECKOUT/config.yaml exists"
[ -f /etc/describer/config.yaml ] || fail "no /etc/describer/config.yaml"
as_describer "$CHECKOUT/.venv/bin/python" -c '
import sys, yaml
cfg = yaml.safe_load(open("/etc/describer/config.yaml"))
sys.exit(0 if cfg["sources"]["fallback"] is None else "sources.fallback is not null")
' || fail "sources.fallback is not null in the shipped config"

# No key, ever: the image is the same for everyone and each person brings their own.
[ -f /etc/describer/describer.env ] || fail "no /etc/describer/describer.env"
if grep -Eq '^(RDM_API_KEY|RTT_TOKEN)=.' /etc/describer/describer.env; then
  fail "a credential is baked into describer.env"
fi

for unit in describer kiosk shutdown-button; do
  [ -e "/etc/systemd/system/$unit.service" ] || fail "$unit.service is not installed"
done
[ -e /etc/systemd/system/multi-user.target.wants/describer.service ] || fail "describer is not enabled"
[ -e /etc/systemd/system/graphical.target.wants/kiosk.service ] || fail "kiosk is not enabled"
[ -x /usr/local/sbin/describer-apply-deploy ] || fail "describer-apply-deploy is not installed"
[ -f /etc/polkit-1/rules.d/50-describer.rules ] || fail "the polkit rules are not installed"

# Leave nothing of the build behind.
apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache /var/lib/describer/.cache
echo "Describer stage done: $(in_checkout rev-parse --short HEAD) on main"
