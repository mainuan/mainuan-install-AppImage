#!/usr/bin/env bash
set -euo pipefail
umask 022

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(sed -n 's/^Version: //p' "${ROOT}/DEBIAN/control")"
OUTPUT="${1:-${ROOT}/dist/mainuan-install-appimage_${VERSION}_all.deb}"
PACKAGE_DIR="$(mktemp -d)"
trap 'rm -rf -- "$PACKAGE_DIR"' EXIT

# Translations: GNU gettext (msgfmt) is a build dependency.
command -v msgfmt >/dev/null || { echo "build.sh: msgfmt not found; install gettext" >&2; exit 1; }
# ITS rules for the polkit policy and the MIME package live in po/its.
export GETTEXTDATADIRS="${ROOT}/po${GETTEXTDATADIRS:+:${GETTEXTDATADIRS}}"

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
  "${PACKAGE_DIR}/usr/share/polkit-1/actions" \
  "${PACKAGE_DIR}/usr/share/locale"

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
# packaging/ holds English templates; msgfmt merges every language in po/LINGUAS.
msgfmt --desktop --template="${ROOT}/packaging/mainuan-install-appimage.desktop" -d "${ROOT}/po" \
  -o "${PACKAGE_DIR}/usr/share/applications/mainuan-install-appimage.desktop"
msgfmt --xml --template="${ROOT}/packaging/br.com.mainuan.install-appimage.policy" -d "${ROOT}/po" \
  -o "${PACKAGE_DIR}/usr/share/polkit-1/actions/br.com.mainuan.install-appimage.policy"
msgfmt --xml --template="${ROOT}/packaging/appimage-mime.xml" -d "${ROOT}/po" \
  -o "${PACKAGE_DIR}/usr/share/mime/packages/mainuan-appimage.xml"
# msgfmt writes BCP 47 tags (xml:lang="pt-BR"); polkitd looks translations up by
# POSIX locale (pt_BR, then pt), and so do Qt/KDE MIME comments. Use underscores.
# zh-Hans-CN / zh-Hant-TW (language-script-region) become zh_CN / zh_TW.
sed -i -E -e 's/xml:lang="([a-z]{2,3})-[A-Z][a-z]{3}-([A-Z]{2})"/xml:lang="\1_\2"/g' \
    -e 's/xml:lang="([a-z]{2,3})-([A-Za-z0-9]+)"/xml:lang="\1_\2"/g' \
  "${PACKAGE_DIR}/usr/share/polkit-1/actions/br.com.mainuan.install-appimage.policy" \
  "${PACKAGE_DIR}/usr/share/mime/packages/mainuan-appimage.xml"
chmod 0644 \
  "${PACKAGE_DIR}/usr/share/applications/mainuan-install-appimage.desktop" \
  "${PACKAGE_DIR}/usr/share/polkit-1/actions/br.com.mainuan.install-appimage.policy" \
  "${PACKAGE_DIR}/usr/share/mime/packages/mainuan-appimage.xml"
# Message catalogs: /usr/share/locale/<lang>/LC_MESSAGES/mainuan-install-appimage.mo
"${ROOT}/po/i18n.sh" compile "${PACKAGE_DIR}/usr/share/locale"
find "${PACKAGE_DIR}/usr/share/locale" -type f -name '*.mo' -exec chmod 0644 {} +

install -d "${PACKAGE_DIR}/usr/share/man/man1"
gzip -n -9 -c "${ROOT}/packaging/changelog" > "${PACKAGE_DIR}/usr/share/doc/mainuan-install-appimage/changelog.gz"
gzip -n -9 -c "${ROOT}/packaging/mainuan-install-appimage.1" > "${PACKAGE_DIR}/usr/share/man/man1/mainuan-install-appimage.1.gz"
find "${PACKAGE_DIR}" -type d -exec chmod 0755 {} +
mkdir -p "$(dirname -- "${OUTPUT}")"
dpkg-deb --build --root-owner-group "${PACKAGE_DIR}" "${OUTPUT}"
printf 'Pacote gerado: %s\n' "${OUTPUT}"
