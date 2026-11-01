# Validação de categorias — 31/10/2026 — test20261031.2

Checkout na branch `port/qt6-mainuan`; alterações locais preservadas. Sem commit,
push, tag ou publicação. O dpkg real do host não recebeu transações.
Relatórios da etapa anterior preservados em `dist/categories-20261031.2/previous-reports/`;
artefatos anteriores permanecem em dist com seus identificadores próprios.

## Resultado real informado pelo usuário

Na VM, a instalação do Kdenlive terminou com sucesso e Abrir aplicativo funcionou.
A categoria exibida era Utilitários. Registrado como confirmação do usuário, sem
atribuir a este ambiente autenticação/instalação administrativa não executadas aqui.

## Novo pacote

- Versão: `2.0.0+test20261031.2`.
- Arquivo: `dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb`.
- SHA-256: `ef32ad9bc916b5ad3c653c137dc13a287e87e464cc70041e3e86d67dababa48f`.
- Checksum, a partir da raiz do projeto:
  `sha256sum -c dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb.sha256` → OK.
- Relatório: [REPORT.md](REPORT.md); segurança: [SECURITY.md](SECURITY.md).

## Comparação e causa

AppImage local usado: `/home/daigo/Downloads/kdenlive-26.08.2-x86_64.AppImage`,
SHA-256 `3194c0979bcfb7ec4a0b33ebc05178a51cffdf5b180c3a89bcf4da94e025bc78`.
Lido sem executar o AppImage, pela inspeção seletiva e -cat já existentes.

| Etapa | Categories |
| --- | --- |
| Desktop original org.kde.kdenlive.desktop | Qt;KDE;AudioVideo;AudioVideoEditing; |
| Gerador anterior, confirmado no código do .deb test20261031.1 | Utility; constante |
| Novo desktop gerado | Qt;KDE;AudioVideo;AudioVideoEditing; |
| Desktop instalado na VM | não lido diretamente; o usuário observou Utilitários, consistente com a constante anterior |

Origem: `_parse_desktop` não retornava Categories, Inspection não tinha esse campo,
o esquema do protocolo não o permitia e `_write_package` usava Utility fixo.
Agora o campo atravessa inspeção → dataclass → asdict/JSON do parser reduzido →
validação administrativa → geração canônica do desktop. Não há reinterpretação
privilegiada do desktop original nem confiança em um .deb preparado pela GUI.

Política genérica em categories.py, sem referência ao nome Kdenlive:

- Whitelist estática de identificadores registrados; comparação sensível a maiúsculas.
- Máximo 32 itens/1.024 caracteres, sintaxe alfanumérica com separador `;` e terminador.
  Quebras, controles, campos injetados e valores malformados não são copiados.
- Duplicações são removidas na inspeção; identificadores desconhecidos/customizados,
  reservados ou incompatíveis com Terminal=false não são preservados.
- Categorias adicionais sem relação com as principais presentes são descartadas.
  Havendo apenas adicional útil, infere-se uma principal relacionada pelo registro;
  Audio/Video recebem AudioVideo. Qt/KDE e outros frameworks conhecidos acompanham
  a classificação. Sem classificação útil, Utility; é o fallback.
- O helper exige lista JSON canônica não vazia, tipos/limites/identificadores exatos.
  No protocolo, valores malformados/desconhecidos/duplicados são recusados, sem
  correção silenciosa. O gerador aplica novamente a validação antes de escrever.
- Metadados são declarativos: isso não autentica autoria nem a função do aplicativo.

## Testes executados

Comando da suíte:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

**59 testes passaram, sem skips neste ambiente**: 51 existentes e oito em
`tests/test_categories.py`. Os novos cobrem:

1. Categorias do Kdenlive preservadas a partir de fixture extraída do valor real.
2. Development/IDE, Graphics/RasterGraphics, Office/Spreadsheet, Network/WebBrowser,
   filtragem de categorias não pertinentes e inferência de principal.
3. Campo ausente, desconhecido, sintaxe inválida, limites e fallback neutro.
4. Tentativas de injeção, incluindo escapes de newline no desktop; nenhum Exec
   arbitrário é copiado e só há um Exec gerado.
5. Protocolo completo com categorias e rejeição administrativa de entradas hostis,
   campo ausente e lista não canônica; o builder também recusa dado inválido.
6. Reinstalação real por dpkg em raiz/admin/log temporários: mesmo pacote, versão,
   AppImage e caminho desktop, trocando Utility pelas categorias AV; um único
   lançador depois da reinstalação, sem remoção prévia. desktop-file-validate passou.
7. Office/Spreadsheet de ponta a ponta: inspeção, protocolo, build, manifesto e
   validação do desktop gerado, sem inferência específica de aplicativo.
8. Inspeção do arquivo Kdenlive real disponível, confirmando o campo original.

Também executados:

```sh
bash -n build.sh
python3 -m compileall -q src/mainuan_install_appimage tests
desktop-file-validate packaging/mainuan-install-appimage.desktop
desktop-file-validate dist/categories-20261031.2/kdenlive-generated.desktop
./build.sh
lintian dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb
dpkg-deb -I dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb
dpkg-deb -c dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb
git diff --check
```

Build/sintaxe/desktop-file-validate passaram; lintian sem apontamentos. A GUI não
foi alterada: gui.py foi comparado byte a byte com o contido no .deb test20261031.1
(evidência em gui-unchanged.txt). Título e todo o visual aprovado são preservados;
a suíte anterior de interface/ordens de botões continua passando offscreen.

## Menu Plasma: teste do gerador, não confirmação visual

O arquivo `/etc/xdg/menus/plasma-applications.menu` inclui AudioVideo no grupo
Multimedia; `kf5-multimedia.directory` tem Name[pt_BR]=Multimídia.
Foi executado `kbuildsycoca6 --menutest` em HOME e XDG_DATA_HOME/CONFIG_HOME/CACHE_HOME
privados temporários, sem DBus da sessão, sem mexer nos caches/configurações reais.
O mesmo ID de desktop foi testado antes/depois, mudando o campo Categories:

```text
Utilities/   mainuan-appimage-org-kde-kdenlive-b1eea056c4.desktop
Multimedia/  mainuan-appimage-org-kde-kdenlive-b1eea056c4.desktop
```

Cada saída continha exatamente uma ocorrência. Como o executável instalado em
/opt não existe neste host, a cópia privada usada só nesse teste substituiu
TryExec por `/usr/bin/true` para não ser filtrada. Nenhum aplicativo foi executado;
o desktop gerado real preserva o TryExec fixo correto e não recebeu essa adaptação.
A primeira tentativa sem adaptar TryExec foi corretamente filtrada por ausência
do executável; seu log também foi conservado. Não se apresenta isso como teste
visual do Kickoff ou como instalação administrativa do Kdenlive neste host.

Evidências em `dist/categories-20261031.2/`:

- kdenlive-original.desktop e kdenlive-generated.desktop;
- category-comparison.json;
- plasma-menutest-before.log e plasma-menutest-after.log (roteamento confirmado);
- plasma-menutest.log (tentativa inicial com TryExec ainda ausente);
- tests.log, lintian.log, package-control.txt, package-contents.txt, gui-unchanged.txt.

Não se introduziram comandos de reconstrução de cache no helper root. A sessão
KDE monitora mudanças de desktop files por KService/kded; a atualização padrão
fica com esse mecanismo. `update-desktop-database` cuida de associações MIME,
não é uma correção de categorias e não foi adicionado a este fluxo.

## Repetir na VM

1. Conferir o SHA-256 do novo `.deb` e instalar:

   ```sh
   sudo apt install ./mainuan-install-appimage_2.0.0+test20261031.2_all.deb
   dpkg-query -W -f='${Version}\n' mainuan-install-appimage
   ```

   Esperado: versão `2.0.0+test20261031.2`. Não remover Kdenlive previamente.

2. Abrir **o mesmo AppImage** usado na instalação bem-sucedida, pelo Dolphin ou:

   ```sh
   mainuan-install-appimage '/caminho/kdenlive-26.08.2-x86_64.AppImage'
   ```

   Esperado: mesma tela mínima e título Instalador de AppImage; ação Reinstalar.
   Clicar Reinstalar e autorizar. O hash idêntico permite identificar reinstalação;
   não é necessária mudança de versão textual para substituir o arquivo desktop.

3. Conferir o lançador (para o hash/identidade local testados):

   ```sh
   P='mainuan-appimage-org-kde-kdenlive-b1eea056c4'
   D="/usr/share/applications/$P.desktop"
   grep '^Categories=' "$D"
   dpkg-query -S "$D"
   find /usr/share/applications -maxdepth 1 -name "$P.desktop" -print
   ```

   Esperado: `Categories=Qt;KDE;AudioVideo;AudioVideoEditing;`, propriedade do mesmo
   pacote e um único arquivo no mesmo destino. Se outro AppImage tiver identidade
   desktop diferente, obter o nome exato com `dpkg-query -W 'mainuan-appimage-*'`.
   `desktop-file-validate "$D"`, quando disponível, deve retornar 0.

4. Fechar/reabrir o menu do Plasma e procurar Kdenlive em **Multimídia**.
   Se a sessão ainda mostrar categoria antiga, executar como usuário comum:

   ```sh
   kbuildsycoca6
   ```

   Reabrir o menu. Não usar sudo, não apagar caches/configurações e não reiniciar
   a transação para limpar menus. Se persistir, verificar apenas por leitura se
   existe override do mesmo desktop em `~/.local/share/applications/`; não excluí-lo
   automaticamente. Preferências manuais de menu podem alterar o agrupamento.

5. Abrir pelo menu e conferir ausência de segundo lançador. A instalação e o botão
   Abrir já foram confirmados pelo usuário no build anterior; a **categoria visual
   após esta correção** e a reinstalação administrativa deste novo build continuam
   pendentes de confirmação na VM. Não há promessa de rollback em falha de dpkg.

Referências: [categorias principais](https://specifications.freedesktop.org/menu/latest/category-registry.html),
[categorias adicionais](https://specifications.freedesktop.org/menu/latest/additional-category-registry.html),
[KService e atualização dos arquivos desktop](https://api.kde.org/ksycoca.html).
