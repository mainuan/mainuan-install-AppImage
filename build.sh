#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(sed -n 's/^Version: //p' "${ROOT}/DEBIAN/control")"
OUTPUT="${1:-${ROOT}/dist/mainuan-install-appimage_${VERSION}_all.deb}"
PACKAGE_DIR="$(mktemp -d)"
trap 'rm -rf -- "$PACKAGE_DIR"' EXIT

install -d \
  "${PACKAGE_DIR}/DEBIAN" \
  "${PACKAGE_DIR}/usr/bin" \
  "${PACKAGE_DIR}/usr/lib/mainuan-install-appimage" \
  "${PACKAGE_DIR}/usr/lib/python3/dist-packages/mainuan_install_appimage" \
  "${PACKAGE_DIR}/usr/share/mainuan-install-appimage" \
  "${PACKAGE_DIR}/usr/share/doc/mainuan-install-appimage" \
  "${PACKAGE_DIR}/usr/share/applications" \
  "${PACKAGE_DIR}/usr/share/icons/hicolor/128x128/apps" \
  "${PACKAGE_DIR}/usr/share/mime/packages" \
  "${PACKAGE_DIR}/usr/share/polkit-1/actions"

install -m 0644 "${ROOT}/DEBIAN/control" "${PACKAGE_DIR}/DEBIAN/control"
install -m 0755 "${ROOT}/packaging/mainuan-install-appimage" \
  "${PACKAGE_DIR}/usr/bin/mainuan-install-appimage"
install -m 0755 "${ROOT}/packaging/privileged-install" \
  "${PACKAGE_DIR}/usr/lib/mainuan-install-appimage/privileged-install"
install -m 0644 "${ROOT}"/src/mainuan_install_appimage/*.py \
  "${PACKAGE_DIR}/usr/lib/python3/dist-packages/mainuan_install_appimage/"
install -m 0644 "${ROOT}/README.md" "${ROOT}/SECURITY.md" "${PACKAGE_DIR}/usr/share/doc/mainuan-install-appimage/"
install -m 0644 "${ROOT}/LICENSE" "${PACKAGE_DIR}/usr/share/doc/mainuan-install-appimage/copyright"
install -m 0644 "${ROOT}/src/AppImage.png" \
  "${PACKAGE_DIR}/usr/share/mainuan-install-appimage/AppImage.png"
install -m 0644 "${ROOT}/src/AppImage.png" \
  "${PACKAGE_DIR}/usr/share/icons/hicolor/128x128/apps/mainuan-install-appimage.png"
install -m 0644 "${ROOT}/packaging/mainuan-install-appimage.desktop" \
  "${PACKAGE_DIR}/usr/share/applications/mainuan-install-appimage.desktop"
install -m 0644 "${ROOT}/packaging/br.com.mainuan.install-appimage.policy" \
  "${PACKAGE_DIR}/usr/share/polkit-1/actions/br.com.mainuan.install-appimage.policy"
install -m 0644 "${ROOT}/packaging/appimage-mime.xml" \
  "${PACKAGE_DIR}/usr/share/mime/packages/mainuan-appimage.xml"

install -d "${PACKAGE_DIR}/usr/share/man/man1"
gzip -n -9 -c "${ROOT}/packaging/changelog" > "${PACKAGE_DIR}/usr/share/doc/mainuan-install-appimage/changelog.gz"
gzip -n -9 -c "${ROOT}/packaging/mainuan-install-appimage.1" > "${PACKAGE_DIR}/usr/share/man/man1/mainuan-install-appimage.1.gz"
find "${PACKAGE_DIR}" -type d -exec chmod 0755 {} +
mkdir -p "$(dirname -- "${OUTPUT}")"
dpkg-deb --build --root-owner-group "${PACKAGE_DIR}" "${OUTPUT}"
printf 'Pacote gerado: %s\n' "${OUTPUT}"
