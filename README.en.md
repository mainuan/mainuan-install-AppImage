<div align="center">

<img src="src/AppImage.png" width="96" alt="Mainuan AppImage Installer icon">

# Mainuan AppImage Installer

Inspects an AppImage without running it and installs it as a Debian package, with a menu entry, icon and removal through `apt`.

[![CI](https://github.com/mainuan/mainuan-install-AppImage/actions/workflows/ci.yml/badge.svg)](https://github.com/mainuan/mainuan-install-AppImage/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/mainuan/mainuan-install-AppImage)](https://github.com/mainuan/mainuan-install-AppImage/releases/latest)
[![License](https://img.shields.io/github/license/mainuan/mainuan-install-AppImage)](LICENSE)
![Platform](https://img.shields.io/badge/Kubuntu%2026.04%20%7C%20Plasma%206.6-0079c1)

[Português](README.md) · **English**

</div>

---

## About

The installer opens when an `.AppImage` file is clicked in Dolphin. It reads
the name, version, icon and categories **without executing the AppImage** and,
on **Install**, builds and installs a dedicated Debian package: the AppImage
goes to `/opt/mainuan-appimages/`, with a launcher and icons in the Plasma
menu. The Python/PyQt6 (Qt Widgets) interface runs as a regular user and
refuses to run as root; only the installation goes through PolicyKit and a
fixed, restricted helper that repeats every check on its own.

## Features

- **AppImage Type 2** only (little-endian ELF, `AI\x02` at offset 8, valid SquashFS 4.0); `amd64`, `arm64`, `i386`, `armhf` recognised, installation only for the system architecture.
- No execution and no tree extraction; working limits such as 8 GiB per file and 120 s of inspection ([details](docs/formatos-e-limites.md), Portuguese).
- Launcher generated from scratch with a fixed path; the AppImage's own `Exec`, scripts and maintainer scripts are never reused. Categories are validated against the freedesktop specification.
- Generated packages contain data files only, no maintainer scripts, named `mainuan-appimage-<name>-<hash>`.
- **Open application** runs the app only after a click.
- Replaces the legacy `appimage-installer` package.
- Interface, PolicyKit action and MIME type in 33 languages.

## Security model

The administrative helper accepts only `--install`, the private copy path and
its SHA-256 (no `.deb`, destinations or dpkg options). Root copies and hashes
the file without parsing it; ELF, SquashFS, `.desktop` and icons are parsed
again by a `nobody` process with `no_new_privs` and resource limits; root then
builds and validates the package and calls `dpkg`. This is privilege
separation, not a full sandbox, and the tool does not verify the authorship or
signatures of applications. See [SECURITY.md](SECURITY.md).

## Installation

Preinstalled in the Mainuan Linux ISO. On another Kubuntu/Ubuntu 26.04 system,
download the `.deb` and `SHA256SUMS` from the
[latest release](https://github.com/mainuan/mainuan-install-AppImage/releases/latest):

```bash
sha256sum --check --ignore-missing SHA256SUMS
sudo apt install ./mainuan-install-appimage_2.1.0_all.deb
```

## Usage

```sh
mainuan-install-appimage "/path/App.AppImage"     # without an argument: file chooser
dpkg-query -W -f='${Package} ${Version}\n' 'mainuan-appimage-*'
sudo apt remove package-name
```

AppImage runtimes may need FUSE or other libraries, which are not installed
automatically.

## Building and testing

```bash
git clone https://github.com/mainuan/mainuan-install-AppImage.git
cd mainuan-install-AppImage
sudo apt build-dep ./
dpkg-buildpackage -us -uc -b
# tests run by the build:
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

CI ([`ci.yml`](.github/workflows/ci.yml)) also runs the translation checks,
`py_compile` and `desktop-file-validate`, then lints the package, installs,
reinstalls and removes it in a clean Ubuntu 26.04 container and smoke-tests
it (helper refused without PolicyKit, offscreen window, synthetic AppImage
inspected and packaged). Releases are published only from `v*` tags. Manual
VM validation: [VALIDATION.md](VALIDATION.md).

## Translations

33 languages via gettext; see [docs/i18n/README.md](docs/i18n/README.md).

## Credits

Daigo ([@daigoasuka](https://github.com/daigoasuka)) and Rafael Ruscher
([@ruscher](https://github.com/ruscher)). Based on the Tiger OS AppImage
installer by **Natanael Barbosa Santos**.

## License

[MIT](LICENSE).
