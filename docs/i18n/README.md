# Internacionalização (i18n)

Contrato comum: `docs/03-arquitetura-i18n-kde.md` do repositório `mainuan`.

## Resumo

| Item | Valor |
|---|---|
| Domínio gettext | `mainuan-install-appimage` (nome do pacote Debian) |
| Idioma-fonte (msgid) | inglês |
| Catálogos | `po/<lang>.po`; idiomas instalados em `po/LINGUAS` (hoje só `pt_BR`) |
| Modelo | `po/mainuan-install-appimage.pot` (versionado) |
| Fontes extraídas | `po/POTFILES.in` |
| Instalado em | `/usr/share/locale/<lang>/LC_MESSAGES/mainuan-install-appimage.mo` |
| Código | `src/mainuan_install_appimage/i18n.py` (`_`, `N_`, `pgettext`, `ngettext`, `Message`) |

O idioma vem da sessão (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`), nunca é
forçado. Os diálogos padrão do Qt (seletor de arquivos, botões de
`QMessageBox`) usam `qtbase_<lang>.qm` carregado para `QLocale.system()`
(pacote `qt6-translations-l10n`).

Procura dos `.mo`, nesta ordem: `$MAINUAN_INSTALL_APPIMAGE_LOCALEDIR` (opcional),
`build/locale` quando executado a partir do checkout, `/usr/share/locale`.

## Tarefas

```bash
po/i18n.sh extract            # regenera o POT a partir de POTFILES.in
po/i18n.sh update             # mescla o POT em cada po/<lang>.po
po/i18n.sh validate           # msgfmt --check + placeholders (gate de CI)
po/i18n.sh check-pot          # falha se o POT commitado estiver desatualizado (CI)
po/i18n.sh coverage           # estatística por idioma
po/i18n.sh add es             # novo idioma (Plural-Forms verificado) + LINGUAS
po/i18n.sh compile build/locale   # para rodar do código-fonte
```

Rodar a interface traduzida a partir do checkout:

```bash
po/i18n.sh compile build/locale
LANGUAGE=pt_BR PYTHONPATH=src python3 -m mainuan_install_appimage.gui
```

Testes (a suíte fixa `LANGUAGE=C` e compara msgids em inglês;
`tests/test_i18n.py` compila `po/pt_BR.po` num diretório temporário e verifica
pt_BR e inglês executando o código real; requer `msgfmt`):

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

## Empacotamento

`debian/rules` (requer `gettext`):

* compila `po/*.po` em `usr/share/locale/<lang>/LC_MESSAGES/`;
* `packaging/mainuan-install-appimage.desktop`, `packaging/br.com.mainuan.install-appimage.policy`
  e `packaging/appimage-mime.xml` são **modelos em inglês**; o build gera as versões
  instaladas com `msgfmt --desktop` / `msgfmt --xml`. Os nomes instalados e o ID da
  ação polkit não mudam;
* as regras ITS de polkit e shared-mime-info estão em `po/its/` (exportadas via
  `GETTEXTDATADIRS`), sem depender de pacotes de desenvolvimento;
* `msgfmt --xml` grava `xml:lang="pt-BR"`; o build converte para `pt_BR`, que é o
  que o polkitd (procura por `pt_BR` e `pt`) e o Qt/KDE consultam.

## Fronteira privilegiada

O helper root (`privileged.py`) e o parser sem privilégios (`reduced.py`) **não
traduzem nada** (`disable_translation()`): o processo root não tem o ambiente do
usuário. Mensagens que atravessam a fronteira viajam como uma linha

```
MESSAGE:{"id": "<msgid em inglês>", "args": {"nome": "texto" | {mensagem aninhada}}}
```

e a GUI as traduz (`i18n.render_line`) antes de exibi-las nos detalhes. O
formato é validado (somente `id`/`args`, strings, profundidade ≤ 4, tamanho
limitado) e a substituição é só `{nome}` → texto, sem `str.format`. Linhas que
não seguem o formato (saída bruta do dpkg) aparecem como estão. Os marcadores
`STAGE:*` continuam como antes.

## Não traduzido de propósito

* Dados que entram no pacote gerado ou no protocolo: a versão sentinela
  `Não informada`, o nome/comentário de fallback `Aplicativo AppImage` gravados
  no `.desktop` do aplicativo instalado, o `Description:` do controle Debian do pacote
  gerado (validado byte a byte), identificadores de categoria freedesktop.
* Saída bruta de `dpkg`/`unsquashfs`/Python (`OSError` etc.).
* Motivos internos descartados sem exibição (`installation_state`) e a guarda
  `Refusing to read SquashFS as root.` dentro do leitor isolado.
* Página de manual (`packaging/mainuan-install-appimage.1`) e textos do
  workflow de release.

## Pendências

* `inspector._parse_desktop` prefere `Name[pt_BR]`/`Name[pt]`/`Comment[pt_BR]` do
  AppImage ao montar o lançador instalado. Isso fixa o idioma do lançador gerado,
  mas mudar exigiria copiar todas as chaves localizadas para o `.desktop` gerado
  (mudança de protocolo/pacote); mantido como está.
* Categorias de menu não são exibidas na interface hoje; se vierem a ser,
  traduzir só o rótulo (com `pgettext`), nunca o identificador.
* `po/i18n.sh check-pot` não foi executado com o xgettext do Ubuntu 24.04 (CI);
  diferenças de versão do gettext podem exigir regenerar o POT.
