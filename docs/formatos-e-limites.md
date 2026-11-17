# Formatos aceitos e limites de inspeção

Resumo no [README](../README.md). Este documento detalha o que a inspeção lê e os limites de trabalho aplicados.

## Formato

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

## Limites

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
