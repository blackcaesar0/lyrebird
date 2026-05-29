#!/usr/bin/env bash
set -eu -o pipefail

[ ! -e /etc/redhat-release ] && echo Only Redhat releases are supported && exit 1

# change PWD to repo root
cd "$(dirname "$0")/.."

INTERACTIVE_ARG="--assumeyes"
[[ $- == *i* ]] && INTERACTIVE_ARG=""
SUDO_CMD="sudo"
[[ $(id --user) == 0 ]] && SUDO_CMD=""
$SUDO_CMD dnf install "$INTERACTIVE_ARG" dnf-plugins-core rpm-build rpmdevtools

rpmdev-setuptree

# Build the source tarball locally from this checkout rather than downloading
# Source0 from GitHub releases (which only exist for tagged upstream releases).
# This keeps the RPM build self-contained and works for any version.
VERSION="$(awk '/^Version:/ { print $2; exit }' lyrebird.spec)"
NAME="$(awk '/^Name:/ { print $2; exit }' lyrebird.spec)"
SRCDIR="${NAME}-${VERSION}"
TARBALL="${HOME}/rpmbuild/SOURCES/v${VERSION}.tar.gz"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
mkdir -p "${STAGING}/${SRCDIR}"
cp -r app app.py icon.png lyrebird lyrebird.desktop lyrebird.spec \
      README.md CHANGELOG.md LICENSE "${STAGING}/${SRCDIR}/"
# Strip any development caches that may have been created.
find "${STAGING}/${SRCDIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +
tar -czf "$TARBALL" -C "$STAGING" "$SRCDIR"

$SUDO_CMD dnf builddep --assumeyes --spec lyrebird.spec
rpmbuild -bb lyrebird.spec

find "${HOME}/rpmbuild/RPMS" -name '*.rpm' -exec cp "{}" ./ci  \;
