





# Mainuan Instalador de AppImage

Aplicativo em Python e Qt Widgets para inspecionar AppImages sem executá-los e
instalá-los como pacotes Debian no Mainuan, baseado em Kubuntu 26.04, Plasma 6
e Wayland.

## Formatos e limites

Esta versão aceita somente AppImage Type 2: contêiner ELF little-endian, assinatura `AI\x02` no offset 8, com
SquashFS 4.0 estruturalmente válido. As arquiteturas reconhecidas são `amd64`,
`arm64`, `i386` e `armhf`; a instalação só prossegue quando a arquitetura
coincide com a do sistema. AppImage Type 1, outros formatos ELF, arquiteturas
desconhecidas ou estruturas SquashFS inválidas são recusados com uma mensagem
explicativa.

A inspeção não executa o AppImage e não extrai sua árvore. Lista somente a raiz
(`-max-depth 1`) e consulta literalmente os caminhos necessários para resolver
`.desktop`, `.DirIcon` e localizações convencionais de PNG. Links são resolvidos
por componentes dentro da imagem, sem `-follow-symlinks`. Arquivos internos não
consultados são apenas bytes do AppImage copiado, não são extraídos nem validados
individualmente. SHA-256 e localização estrutural do SquashFS ainda leem o arquivo
bruto completo. O unsquashfs pode ler tabelas internas mesmo em uma consulta exata.

Os limites são de trabalho, não uma declaração de arquivo inválido:

- Arquivo: 8 GiB; inspeção de metadados: 120 s totais e 30 s por comando.
- Listagens selecionadas: 10.000 registros examinados acumulados (incluindo
  ancestrais repetidos entre consultas), 4 MiB de saída, linha de até 4 KiB,
  no máximo 64 consultas e caminhos de até 12 componentes/512 caracteres.
  O cache mantém apenas os caminhos consultados, com leitura incremental da saída.
  O total de arquivos internos do aplicativo não é contado.
- Até dez candidatos `.desktop` na raiz, 128 KiB por arquivo, linhas de até
  4.096 caracteres. Nenhum erro de limite/ferramenta vira metadados de fallback.
- Ícones: até 4 MiB somados de dados lidos, 8.192 pixels por dimensão e
  32 milhões de pixels. Ícones ausentes ou de formato não suportado usam fallback;
  exceder limites ou falhar a leitura aborta com diagnóstico.
- Cada leitor unsquashfs: cache de 64 MiB, espaço de endereçamento de 1 GiB,
  CPU de 30 s, stderr de até 16 KiB. O processo reduzido administrativo mantém
  seus limites de CPU 120 s, memória virtual 1 GiB e supervisor de 180 s.
  São limites por processo, não uma quota global ou sandbox.

A raiz costuma conter poucas entradas; os tetos anteriores de 10.000 e 4 MiB
foram mantidos, aplicados agora apenas às consultas necessárias. Isso permite
inspecionar imagens com dezenas de milhares de arquivos em subdiretórios sem
remover a proteção contra uma raiz abusivamente grande. Não é feita uma busca
recursiva por ícones arbitrários; se não houver um PNG nas referências/localizações
convencionais permitidas, usa-se o ícone padrão. Formato/metadados, limite
operacional e erro do unsquashfs são diferenciados nos detalhes técnicos.

Nome, descrição, versão, referência de ícone e categorias são lidos como dados do `.desktop`. O lançador Debian é
gerado pelo instalador com um caminho fixo para o AppImage; `Exec`, scripts e
scripts de manutenção fornecidos pelo arquivo não são preservados.

## Construção e uso

Dependências de construção: `bash`, `coreutils`, `findutils`, `gzip` e `dpkg`
(para `dpkg-deb`). Para testes: `python3-pyqt6` e `squashfs-tools`;
`lintian` para análise do pacote. A construção não baixa
nem executa binários externos:

```sh
./build.sh
```

O pacote de teste é criado em
`dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb`. Instale-o com o gerenciador de
pacotes da distribuição. Depois, abra um AppImage pelo Dolphin ou execute:

```sh
mainuan-install-appimage "/caminho com espaços/Aplicativo.AppImage"
```

Sem argumento, o seletor de arquivos é aberto. A interface e a inspeção rodam
como usuário comum. Somente a instalação passa pelo PolicyKit e por um helper
fixo e restrito. O helper aceita exclusivamente uma cópia temporária privada
do usuário, confere novamente o hash, formato, arquitetura e identidade e
constrói o pacote Debian por conta própria. O pacote gerado contém apenas
arquivos de dados e não possui scripts de manutenção.

O `dpkg` instala, reinstala ou substitui a versão em uma transação normal; o
instalador não remove a versão existente antes da transação. Não há comparação
textual de versões para anunciar atualizações. Em caso de erro do `dpkg`, o
instalador informa a falha e não declara sucesso. Como em qualquer transação do
`dpkg`, uma falha durante o desempacotamento pode deixar o pacote em estado
parcial; não há promessa de rollback automático dos arquivos. Não se executa
uma reparação manual da base de pacotes.

Para remover um aplicativo instalado, use o nome do pacote exibido pelo
`dpkg-query`:

```sh
dpkg-query -W -f='${Package} ${Version}\n' 'mainuan-appimage-*'
sudo apt remove nome-do-pacote
```

## Migração de instalações antigas

O pacote do instalador usa `Provides`, `Conflicts` e `Replaces` para substituir
o pacote antigo `appimage-installer` em uma instalação Debian normal. Isso não
remove nem reconstrói os registros falsos que versões antigas gravaram
diretamente em `/var/lib/dpkg/status` e `/var/lib/dpkg/info`. Se a identidade do
aplicativo corresponder a um registro legado reconhecível, a instalação é
bloqueada e os arquivos existentes são preservados. Registros sem metadados
confiáveis não podem ser distinguidos com segurança de pacotes de terceiros;
eles não são alterados automaticamente. Nesses casos, faça cópia de segurança
e examine o estado do `dpkg` manualmente antes de qualquer migração.

## Testes

Os testes automatizados criam AppImages de fixture com `mksquashfs`, constroem
pacotes Debian e executam transações somente em uma raiz e base `dpkg`
temporárias:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
lintian dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb
```

O modo offscreen não valida renderização real no Plasma, tema claro/escuro,
escala de fontes nem integração visual com Wayland. Para uma validação final,
use uma VM descartável Kubuntu 26.04/Plasma 6: instale o pacote de teste, teste
tema claro e escuro e escala de fonte ampliada, associe e abra um `.AppImage`
no Dolphin sob Wayland; teste recusa/autorização do PolicyKit, instalação,
reinstalação, substituição de versão, remoção pelo `apt` e falhas do `dpkg`.
Confirme também que a base de pacotes e os arquivos da instalação anterior
permanecem intactos se a preparação falhar.

## Arquitetura e identidade

`gui.py` contém os Qt Widgets, workers e processo assíncrono de autenticação;
`staging.py` mantém a cópia privada; `inspector.py` lê o contêiner;
`installer.py` consulta dpkg e constrói o pacote; `privileged.py` é a entrada
administrativa. O helper e a GUI usam Python em modo isolado (`-I`). A GUI
recusa execução como root. O helper não aceita um `.deb` nem destinos livres.
A cópia recebida é aberta sem seguir links, copiada para uma área de root e
conferida por SHA-256 antes de inspeção e geração independentes.

O identificador Debian deriva do nome do `.desktop`, com slug e hash estáveis.
O marcador protegido, pertencente ao pacote, também registra o nome original
não localizado e o hash do AppImage. Nomes diferentes com o mesmo identificador
são bloqueados como colisão. Reinstalação exige conteúdo idêntico; conteúdo
diferente é apresentado como substituição, mesmo que a versão textual coincida.
Dois produtores que usem o mesmo nome e identidade `.desktop` não podem ser
distinguidos criptograficamente: esta ferramenta não verifica autoria ou
assinaturas do aplicativo. Renomear o `.desktop` pode produzir outra identidade.

O runtime de cada AppImage pode precisar de FUSE e bibliotecas adicionais;
esses requisitos não podem ser inferidos com segurança só do contêiner e não
são instalados automaticamente. Não há garantia de compatibilidade em execução.
A revalidação administrativa interpreta ELF, SquashFS, `.desktop` e ícones em
um processo com UID/GID `nobody`, sem grupos suplementares, com `no_new_privs`
e limites de recursos. Root confere um protocolo restrito, gera e valida controle, manifesto e hash do pacote
e chama dpkg. Isso é separação de privilégios, não uma sandbox completa.
Consulte [SECURITY.md](SECURITY.md) para a fronteira exata e os riscos residuais.

A tela carregada apresenta ícone, nome, versão declarada em formato reconhecido, sem inferência pelo nome do arquivo e
Instalar → Fechar. Reinstalação/substituição recebem apenas uma frase curta.
Progresso é indeterminado, com etapa curta; detalhes técnicos de erro ficam
recolhidos. O seletor aparece ao iniciar sem argumento, e cancelar encerra a GUI.
O resultado apresenta Abrir aplicativo → Fechar; o aplicativo só executa após clique.

## Validação desta entrega

Veja [VALIDATION.md](VALIDATION.md) para resultados executados, simulações,
limitações e roteiro de VM. O `.deb` é um artefato de teste local, sem publicação.
A associação instalada anuncia o MIME AppImage ao Dolphin; preferências MIME
já salvas pelo usuário podem exigir selecionar “Abrir com” uma vez.

## Créditos e licença

Migração para Mainuan do instalador originalmente criado por Natanael Barbosa
Santos. Mantidos a autoria histórica e os termos MIT em [LICENSE](LICENSE).



## Consolidação de 30/10/2026

Os ajustes preservam Qt Widgets/PyQt6 e o fluxo existente. A tela carregada não
exibe caminho, nome do arquivo, tipo repetido, estado “Não instalado” ou seletor.
Instalar e Abrir aplicativo ficam à esquerda de Fechar em seus respectivos
estados, com layout LTR explícito, ação principal e foco nativos. A linha de
progresso vazia é ocultada fora de operação; versões malformadas não aparecem.

A validação administrativa agora confere integralmente controle e manifesto do
.deb privado, incluindo hash do AppImage, e impede a conversão de ícones como
root. Chaves JSON duplicadas/profundidade excessiva falham de forma controlada.
A transição declara conflito com qualquer versão de `appimage-installer` e
anuncia extensões `.AppImage` e `.appimage`, sem apagar associações de terceiros.
Veja o relatório e o roteiro atualizado em [VALIDATION.md](VALIDATION.md).


## Categorias do menu

O lançador é gerado do zero. `Categories` é transportado pela inspeção reduzida,
com lista canônica validada novamente pelo helper e pelo gerador. Identificadores
registrados na especificação freedesktop são preservados, sem copiar comandos
ou o `.desktop` original. O limite é 32 identificadores/1.024 caracteres, com
ponto e vírgula final; não se aceitam espaços, controles, escapes de linhas ou
campos injetados. Duplicações são removidas na inspeção. Tokens desconhecidos,
customizados `X-*`, reservados ou incompatíveis com o lançador são descartados.
Adicionais relacionados a outra categoria principal são filtrados; quando só há
uma classificação adicional utilizável, ela fornece uma principal relacionada.
Audio/Video incluem AudioVideo. Sem classificação utilizável, usa-se Utility.
O protocolo administrativo recusa entradas não canônicas, em vez de repará-las.

A reinstalação substitui o mesmo arquivo de lançador, sem mudar a identidade do
pacote por causa da categoria. O Plasma normalmente detecta a alteração através
do KService/kded. Se a sessão ainda mostrar a categoria antiga, execute
`kbuildsycoca6` como usuário da sessão e reabra o menu. Não é preciso apagar caches,
configurações ou associações; não se executa kbuildsycoca como root pelo helper.
