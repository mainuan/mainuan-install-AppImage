<div align="center">

<img src="src/AppImage.png" width="96" alt="Ícone do Mainuan Instalador de AppImage">

# Mainuan Instalador de AppImage

Inspeciona um AppImage sem executá-lo e o instala como pacote Debian, com menu, ícone e remoção pelo `apt`.

[![CI](https://github.com/mainuan/mainuan-install-AppImage/actions/workflows/ci.yml/badge.svg)](https://github.com/mainuan/mainuan-install-AppImage/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/mainuan/mainuan-install-AppImage)](https://github.com/mainuan/mainuan-install-AppImage/releases/latest)
[![Licença](https://img.shields.io/github/license/mainuan/mainuan-install-AppImage)](LICENSE)
![Plataforma](https://img.shields.io/badge/Kubuntu%2026.04%20%7C%20Plasma%206.6-0079c1)

**Português** · [English](README.en.md)

</div>

---

## O que é

O Mainuan Instalador de AppImage abre quando se clica num arquivo `.AppImage`
no Dolphin. Ele lê o nome, a versão, o ícone e as categorias do aplicativo
**sem executar o AppImage** e, com um clique em **Instalar**, gera e instala um
pacote Debian próprio: o AppImage fica em `/opt/mainuan-appimages/`, com
lançador e ícones no menu do Plasma.

A interface (Python, PyQt6, Qt Widgets) roda como usuário comum e recusa ser
executada como root. Só a instalação passa pelo PolicyKit, por um helper fixo
e restrito que refaz todas as verificações por conta própria.

## Funcionalidades

- Aceita **AppImage Type 2**: ELF little-endian com a assinatura `AI\x02` no offset 8 e SquashFS 4.0 válido. Arquiteturas reconhecidas: `amd64`, `arm64`, `i386` e `armhf`; a instalação só prossegue se a arquitetura for a do sistema. Type 1, outros ELF e SquashFS inválidos são recusados com explicação.
- Inspeção sem execução e sem extrair a árvore: só a raiz da imagem e os caminhos necessários para o `.desktop`, o `.DirIcon` e os ícones PNG convencionais.
- Limites de trabalho, entre eles: arquivo de até 8 GiB, inspeção de até 120 s, ícones de até 4 MiB e 8.192 px por lado. Lista completa em [docs/formatos-e-limites.md](docs/formatos-e-limites.md).
- Lançador gerado do zero, com caminho fixo para o AppImage: `Exec`, scripts e scripts de manutenção trazidos pelo arquivo não são aproveitados. As categorias do `.desktop` original são validadas contra a especificação freedesktop; sem categoria utilizável, vai para Utilitários.
- Pacote gerado só com arquivos de dados, sem scripts de manutenção, com nome `mainuan-appimage-<nome>-<hash>`.
- Reinstalação exige conteúdo idêntico; conteúdo diferente aparece como substituição. Nomes diferentes com o mesmo identificador são bloqueados como colisão.
- Tela de resultado com **Abrir aplicativo** e **Fechar**; o aplicativo só é executado depois do clique.
- Substitui o pacote antigo `appimage-installer` e bloqueia a instalação quando encontra um registro legado reconhecível no `dpkg`.
- Interface, ação do PolicyKit e tipo MIME traduzidos em 33 idiomas.

## Instalação

O instalador já vem na ISO do Mainuan Linux, associado aos arquivos `.AppImage`.

Em outro sistema Kubuntu/Ubuntu 26.04, baixe o `.deb` e o `SHA256SUMS` da
[última release](https://github.com/mainuan/mainuan-install-AppImage/releases/latest),
confira e instale:

```bash
sha256sum --check --ignore-missing SHA256SUMS
sudo apt install ./mainuan-install-appimage_2.1.0_all.deb
```

## Uso

Dê dois cliques num `.AppImage` no Dolphin ou execute:

```sh
mainuan-install-appimage "/caminho com espaços/Aplicativo.AppImage"
```

O comando recebe um único arquivo; sem argumento, abre o seletor de arquivos
(`man mainuan-install-appimage`). Preferências MIME já salvas pelo usuário
podem exigir escolher "Abrir com" uma vez.

Para remover um aplicativo instalado, use o nome do pacote:

```sh
dpkg-query -W -f='${Package} ${Version}\n' 'mainuan-appimage-*'
sudo apt remove nome-do-pacote
```

O runtime de cada AppImage pode precisar de FUSE e de outras bibliotecas, que
não são deduzidas nem instaladas automaticamente. Se uma falha do `dpkg`
interromper a transação, o instalador informa o erro e não declara sucesso,
mas não há rollback automático dos arquivos.

Se o menu do Plasma continuar mostrando a categoria antiga depois de uma
reinstalação, execute `kbuildsycoca6` como usuário da sessão.

## Informações técnicas

| Item | Valor |
|---|---|
| Linguagem | Python 3 (executado com `python3 -I`) |
| Toolkit | Qt 6 Widgets (PyQt6) |
| Base | Kubuntu 26.04 LTS, KDE Plasma 6.6 |
| Pacote | `mainuan-install-appimage`, `Architecture: all` |
| Dependências | `python3-pyqt6`, `qt6-wayland`, `squashfs-tools`, `pkexec`, `polkitd`, `shared-mime-info` |
| Privilégios | só a instalação, via PolicyKit (`br.com.mainuan.install-appimage.install`) |
| Arquitetura do sistema | amd64 |

### Modelo de segurança

| Etapa | Quem executa |
|---|---|
| Cópia privada e primeira inspeção | usuário da sessão |
| Autorização | agente PolicyKit (`auth_admin`, sem autorização retida) |
| Cópia administrativa e conferência do SHA-256 | root, sem interpretar ELF, SquashFS nem PNG |
| Nova inspeção independente (ELF, SquashFS, `.desktop`, ícones) | processo `nobody`, sem grupos suplementares, com `no_new_privs` e limites de recursos |
| Geração e validação do `.deb` (controle, manifesto fechado, hash do AppImage) | root, com `dpkg-deb` |
| Transação | `dpkg` |
| Abrir aplicativo | usuário da sessão, sem `pkexec` |

O helper `/usr/lib/mainuan-install-appimage/privileged-install` aceita apenas
`--install`, o caminho da cópia privada e o SHA-256; não aceita `.deb`,
destinos nem opções do `dpkg`. Isso é separação de privilégios, não uma
sandbox completa, e a ferramenta não verifica autoria nem assinatura do
aplicativo. Fronteira exata e riscos residuais: [SECURITY.md](SECURITY.md).
Arquitetura, identidade, transação e migração: [docs/arquitetura.md](docs/arquitetura.md).

## Compilação e testes

```bash
git clone https://github.com/mainuan/mainuan-install-AppImage.git
cd mainuan-install-AppImage
sudo apt build-dep ./
dpkg-buildpackage -us -uc -b      # gera ../mainuan-install-appimage_<versão>_all.deb
```

A versão vem de `debian/changelog`. O build não baixa nem executa binários
externos e roda a suíte de testes:

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Os testes criam AppImages de exemplo com `mksquashfs`, constroem pacotes
Debian e executam transações só numa raiz e numa base `dpkg` temporárias.

O workflow [`CI`](.github/workflows/ci.yml) executa ainda `po/i18n.sh
check-pot`, `po/i18n.sh validate`, `py_compile` do lançador e do helper e
`desktop-file-validate`; depois roda `lintian`, gera o `SHA256SUMS`, instala,
reinstala e remove o pacote num Ubuntu 26.04 limpo e faz um teste de fumaça:
o helper recusa rodar sem PolicyKit, a janela abre offscreen e um AppImage
sintético é inspecionado e empacotado. A release só é publicada por uma tag
`v*`.

O modo offscreen não valida a renderização real no Plasma; o roteiro de
validação manual em VM e os resultados históricos estão em
[VALIDATION.md](VALIDATION.md) e [docs/arquitetura.md](docs/arquitetura.md).

## Traduções

Catálogos gettext em `po/` (domínio `mainuan-install-appimage`, textos-fonte
em inglês), em 33 idiomas listados em `po/LINGUAS`. O `.desktop`, a ação do
PolicyKit e o tipo MIME são traduzidos com `msgfmt`. Como contribuir:
[docs/i18n/README.md](docs/i18n/README.md).

## Contribuição

Relate problemas em [Issues](https://github.com/mainuan/mainuan-install-AppImage/issues)
e envie mudanças por pull request para `main`. O
[CI](https://github.com/mainuan/mainuan-install-AppImage/actions/workflows/ci.yml)
precisa estar verde. Mudanças na fronteira de privilégios devem atualizar o
[SECURITY.md](SECURITY.md).

## Créditos

- Daigo ([@daigoasuka](https://github.com/daigoasuka)): migração para Qt 6 e versão 2.0.1.
- Rafael Ruscher ([@ruscher](https://github.com/ruscher)): internacionalização, empacotamento Debian e CI.

Origem: instalador de AppImage do Tiger OS, criado por **Natanael Barbosa
Santos**, cuja autoria e termos MIT estão preservados no [LICENSE](LICENSE).

## Licença

[MIT](LICENSE).
