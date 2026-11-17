# Arquitetura, identidade e transação

Resumo no [README](../README.md). A fronteira de privilégios completa está em [SECURITY.md](../SECURITY.md).

## Módulos e identidade

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
Consulte [SECURITY.md](../SECURITY.md) para a fronteira exata e os riscos residuais.

A tela carregada apresenta ícone, nome, versão declarada em formato reconhecido, sem inferência pelo nome do arquivo e
Instalar → Fechar. Reinstalação/substituição recebem apenas uma frase curta.
Progresso é indeterminado, com etapa curta; detalhes técnicos de erro ficam
recolhidos. O seletor aparece ao iniciar sem argumento, e cancelar encerra a GUI.
O resultado apresenta Abrir aplicativo → Fechar; o aplicativo só executa após clique.

## Transação do dpkg

O `dpkg` instala, reinstala ou substitui a versão em uma transação normal; o
instalador não remove a versão existente antes da transação. Não há comparação
textual de versões para anunciar atualizações. Em caso de erro do `dpkg`, o
instalador informa a falha e não declara sucesso. Como em qualquer transação do
`dpkg`, uma falha durante o desempacotamento pode deixar o pacote em estado
parcial; não há promessa de rollback automático dos arquivos. Não se executa
uma reparação manual da base de pacotes.

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

## Ajustes de 30/10/2026

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
Veja o relatório e o roteiro atualizado em [VALIDATION.md](../VALIDATION.md).

## Validação manual em VM

O modo offscreen não valida renderização real no Plasma, tema claro/escuro,
escala de fontes nem integração visual com Wayland. Para uma validação final,
use uma VM descartável Kubuntu 26.04/Plasma 6: instale o pacote gerado, teste
tema claro e escuro e escala de fonte ampliada, associe e abra um `.AppImage`
no Dolphin sob Wayland; teste recusa/autorização do PolicyKit, instalação,
reinstalação, substituição de versão, remoção pelo `apt` e falhas do `dpkg`.
Confirme também que a base de pacotes e os arquivos da instalação anterior
permanecem intactos se a preparação falhar.

Resultados históricos: [VALIDATION.md](../VALIDATION.md).
