# Fronteira de privilégios — etapa Qt6 Mainuan

## Fluxo e operações administrativas

A GUI recusa EUID 0 antes de criar QApplication. Só chama o executável fixo
`/usr/lib/mainuan-install-appimage/privileged-install` por pkexec após a ação
Instalar/Reinstalar/Substituir. A ação PolicyKit aponta exclusivamente para
esse helper, sem autorização retida (`auth_admin`, sem `*_keep`). Os únicos
argumentos aceitos são `--install`, caminho privado de payload e SHA-256.
Não se aceitam `.deb`, diretório de destino, comandos ou opções de dpkg.

| Operação | Identidade efetiva | Conteúdo interpretado |
| --- | --- | --- |
| Cópia e inspeção inicial | usuário da sessão | ELF, superbloco/listagem SquashFS, `.desktop`, ícone PNG para exibição |
| Autenticação | agente PolicyKit do sistema | ação fixa e autorização administrativa |
| Abertura e cópia administrativa | root | nomes restritos, fstat, bytes opacos e SHA-256; não interpreta ELF/SquashFS/PNG |
| Nova inspeção independente | processo `nobody`, sem grupos suplementares | ELF, SquashFS e `.desktop` do snapshot administrativo; não usa resultados da GUI |
| Leitura seletiva do SquashFS | `unsquashfs`, descendente do processo sem privilégios | descompressão/listagem; `-cat` envia apenas metadados selecionados a stdout, sem extrair árvore em disco |
| Decodificação/conversão de ícones | Qt no processo `nobody` | PNG não confiável; gera PNGs de 64 e 128 pixels |
| Validação da resposta | root | JSON limitado a 256 KiB; esquema fechado, textos, identidade, versão, arquitetura, tamanho/hash e base64; não decodifica imagens |
| Construção Debian | root e `dpkg-deb` | texto gerado por código fixo e dados opacos; ícones já preparados, AppImage copiado sem execução |
| Validação do pacote gerado | root, `dpkg-deb` e tarfile em streaming | controle canônico completo, manifesto fechado de cinco arquivos/diretórios previstos, tipos/modos/UID/GID e SHA-256 do AppImage, sem extração |
| Transação | root e dpkg | pacote construído em área exclusiva de root; scripts/triggers já instalados no sistema podem ser acionados pelo dpkg |
| Abrir aplicativo | usuário da GUI | executável instalado, após clique; sem pkexec |

O backend importa classes Qt em root, mas o caminho administrativo não chama
os decodificadores, pintores nem conversores. `_png_icon` agora também recusa
EUID 0 explicitamente, prevenindo uso acidental em um build sem ícones preparados. Os ícones recebidos são bytes
opacos com limite de tamanho/assinatura PNG, sem renderização em root.

## Redução efetiva de privilégios

`boundary.py` lança `/usr/bin/python3 -I -m mainuan_install_appimage.reduced`
com UID/GID da conta `nobody`, `extra_groups=[]`, stdin fechado, cwd `/`,
ambiente explícito e somente um descritor extra de entrada, aberto para leitura.
Não há fallback para executar o parser como root se essa operação falhar.
O processo reduzido verifica UIDs/GIDs reais, efetivos e salvos não zero,
ausência de grupos suplementares e de capabilities efetivas/permitidas/ambiente.
Antes de importar parsers, ativa `no_new_privs`, proíbe core dumps e limita
CPU (120 s), espaço de endereçamento (1 GiB), arquivo (8 GiB) e descritores (64).
Os filhos unsquashfs herdam as restrições. O supervisor impõe 180 s de parede,
256 KiB de saída combinada e encerra o grupo de processos ao finalizar/falhar.

O snapshot permanece em diretório 0700 de root, com arquivo 0600. O parser
recebe apenas seu FD de leitura e copia os bytes para scratch 0700 de `nobody`,
sob diretório-âncora de root 0711. O supervisor remove o scratch após terminar
o grupo, inclusive em timeout. Não reabre arquivos produzidos pelo parser:
recebe sua resposta pelos pipes. A saída é validada mesmo sendo gerada por
código instalado pelo pacote; ela continua sendo considerada não confiável.

**Isso não é uma sandbox de filesystem, rede ou syscalls.** Não há namespaces,
seccomp, AppArmor próprio ou quota de disco. O parser pode ler arquivos públicos
e acessar rede como `nobody`. Outros processos com esse UID compartilham a
identidade; isolamento entre eles não é garantido. Limites de recursos não
substituem quota e não garantem disponibilidade em disco cheio. Atualizações de
segurança de Qt, Python, squashfs-tools e dpkg continuam necessárias. Um processo
comprometido pode mudar de grupo/sessão e escapar do encerramento por killpg;
não há cgroup de contenção. Uma falha
em parser fica limitada à conta reduzida, mas não se promete contenção completa.

## Regras que root aplica independentemente

- O runtime é exatamente `/run/user/UID/mainuan-install-appimage`; diretórios
  são abertos com `O_DIRECTORY|O_NOFOLLOW`, e os próximos componentes via dir_fd.
  Propriedade e modos são conferidos com fstat dos diretórios efetivamente abertos.
  O payload deve ser regular, privado, do usuário autorizado e ter nome restrito.
- Root copia e calcula SHA-256 antes de interpretar dados. A cópia imutável para
  o usuário é usada em todas as etapas seguintes. Alterações no payload original
  não alteram o snapshot. Python usa `-I`; o helper limpa o ambiente e fixa umask
  077, PATH, locale, HOME e TMPDIR. Nenhuma chamada usa shell, eval ou executável
  localizado no AppImage.
- O protocolo rejeita chaves JSON duplicadas e excesso de profundidade;
  só permite os campos conhecidos; rejeita campos de caminho, textos
  com controles, nomes excessivos, arquiteturas e versões inválidas. Recalcula o
  identificador Debian a partir da identidade; nunca usa um destino do parser.
- Root cria uma árvore nova, com exatamente os cinco arquivos definidos pelo
  código: AppImage em `/opt/mainuan-appimages/PACOTE/AppImage`, `.desktop`, dois
  ícones e marcador gerenciado. O lançador é escrito do zero, sem preservar
  Exec/TryExec/ações/scripts fornecidos pelo aplicativo. Não há maintainer scripts.
- `dpkg-deb` constrói o pacote nessa árvore; root valida controle, identidade e
  ausência de outros arquivos de controle. O texto de controle deve corresponder
  integralmente ao gerado (não admite Depends/Replaces/Conflicts injetados).
  O data.tar é lido em streaming, sem extração, com conjunto fechado de caminhos,
  diretórios, cinco arquivos regulares, modos 0755/0644, UID/GID 0 e hash/tamanho
  exatos do snapshot. Links, arquivos extras/duplicados, especiais, sparse e bits
  especiais são recusados. Um watchdog de 300 s só protege essa preparação;
  não se aplica à transação dpkg. Só esse pacote interno é instalado.
  A raiz interna do arquivo recebe 0755 explicitamente, inclusive sob umask 077;
  seu diretório temporário pai permanece 0700. O diretório de build e o `.deb`
  não são graváveis pelo parser/usuário.
- O lock de frontend é obtido sem espera e mantido desde a inspeção administrativa
  até a transação terminar. Outra instância/apt/dpkg recebe ou provoca erro de
  ocupação; nenhum lock é apagado. `DPKG_FRONTEND_LOCKED=1` é definido pelo helper
  só após adquirir o lock; dpkg ainda obtém seu próprio lock interno.
- Estados parciais no dpkg bloqueiam instalação. Pacote já instalado exige marcador
  regular de root, não gravável por grupo/outros, pertencente ao próprio pacote,
  com identidade compatível. Colisões são recusadas. Destinos existentes exigem
  instalação gerenciada válida e propriedade pelo pacote; diretórios ancestrais
  devem ser de root e não graváveis por grupo/outros, sem symlinks. Arquivos soltos
  ou conffiles de uma identidade não gerenciada são preservados por recusa.

Essas verificações não resistem a um invasor que já controla root ou modifica a
base/arquivos do dpkg como administrador. Identidade e hash não verificam autoria:
aplicativos de produtores diferentes que declarem a mesma identidade/nome podem
ser indistinguíveis. O AppImage pode ser malicioso quando executado pelo usuário.

## Falhas, cancelamento e recuperação

Recusar/cancelar PolicyKit não inicia o helper. Cancelar inspeção descarta a cópia;
um subprocesso de inspeção iniciado pode concluir até seu timeout. Preparação
administrativa falha antes da transação sem remover o aplicativo existente.

Depois que dpkg começa, não há rollback automático: desempacotamento parcial,
triggers com erro, disco cheio ou desligamento podem deixar arquivos/estado
parciais. A GUI só declara sucesso com saída normal e código 0 do helper/dpkg.
Falha e crash nunca oferecem Abrir aplicativo. Logs ficam recolhidos no erro.

Fechar fica desabilitado e o evento de fechamento é recusado enquanto o helper
está ativo. O timeout que antes poderia matar dpkg após uma hora foi removido;
aguarda-se o resultado real. Se dpkg travar, intervenção administrativa é feita
fora da GUI, avaliando a transação. SIGKILL, encerramento da sessão ou desligamento
não são protegidos por essa regra da janela. Recuperação deve usar o gerenciador
normal ou snapshot da VM, nunca edição manual automática de status/info.

## Transição do instalador e aplicativos legados

O pacote novo declara Provides, Conflicts e Replaces para `appimage-installer`
em qualquer versão. O limite anterior `<< 2.0.0` deixava versões locais
maiores do pacote antigo sem conflito declarado, permitindo dois instaladores/
lançadores. A troca é delegada ao dpkg, sem remoção manual de launchers. Uma transação Debian remove os arquivos **registrados** do antigo
pacote, inclusive `AppImage-Installer.desktop`, e instala o lançador novo com
`Exec=/usr/bin/mainuan-install-appimage %f`. Não há varredura nem remoção genérica
de launchers, mimeapps.list ou associações de outros aplicativos. Sobras não
registradas de instalações antigas exigem diagnóstico manual, sem exclusão cega.

Isso é separado dos aplicativos que o Bash registrava artificialmente no dpkg.
Esses registros não são migrados nem reparados. O detector bloqueia registros
legados reconhecíveis pelo nome/maintainer; registros alterados ou nomes divergentes
podem não ser reconhecidos. Destinos antigos não são reutilizados. Use VM
restaurável para avaliar casos legados e preserve as instalações existentes.


## Revisão adicional — 30/10/2026

A inspeção reduzida já existia antes desta consolidação e foi preservada, não
reapresentada como implementação nova. Problemas concretos corrigidos agora:
validação parcial do controle/data.tar; caminho de conversão de PNG sem recusa
explícita de root; respostas JSON ambíguas ou profundas; versões declaradas
malformadas mostradas após limpeza; conflito de transição limitado à versão do
instalador antigo. Os testes hostis validam os pacotes, **não os instalam**.

A proteção de caminhos depende de diretórios administrativos não graváveis pelo
usuário. O lock evita concorrência cooperativa com APT/dpkg; não protege contra
outro root alterando arquivos à margem do gerenciador. O snapshot administrativo,
.deb e árvore de build são privados de root, portanto um processo do usuário não
consegue trocar o pacote entre validação e uso. Não se aceita um .deb da GUI.

O validador tar usa biblioteca Python e descompressor dpkg-deb como root sobre
arquivo construído pelo próprio helper na área privada, nunca sobre um arquivo
.deb indicado pelo usuário. Ainda interpreta esses formatos e o JSON limitado,
assim como metadados locais do dpkg e marcador gerenciado. Não se afirma ausência
completa de parsing em root. A interpretação de metadados ELF/SquashFS/.desktop e a decodificação dos
ícones fornecidos pelo AppImage ficam no processo reduzido, fora de root.
O AppImage nunca é executado para inspeção.

Os triggers/scripts **preexistentes** do sistema continuam executando como root
na transação; ferramentas de cache do sistema podem interpretar arquivos
instalados, inclusive ícones. A separação do parser próprio não isola esses
componentes nem demonstra ausência de vulnerabilidades neles. O conteúdo de um
AppImage também não tem autenticidade comprovada por nome/hash. Comprometer o
parser permite mentir dentro do protocolo e do namespace gerenciado; a identidade
não substitui assinatura/procedência. O processo reduzido não tem isolamento de
rede/filesystem, quota ou limite específico de número de processos. Não é sandbox.


## Correção da inspeção seletiva — 31/10/2026

Não se exige mais uma listagem recursiva até profundidade 12 de toda a imagem
antes dos metadados. O leitor enumera a raiz e resolve cada componente dos links
por consultas exatas com `-no-wildcards`, sem seguir links automaticamente.
Consultas de diretórios encerram na profundidade do próprio diretório, sem listar
seus filhos. O `-cat` só recebe caminhos regulares resolvidos na árvore selecionada.
Os ancestrais retornados devem ser diretórios reais. Links externos/cíclicos não
abrem arquivos do host. O restante do aplicativo é copiado como dado opaco.

A listagem é consumida por linhas; duplicações na mesma resposta, saída fora da
seleção e campos incompatíveis são recusados. O orçamento de 10.000 registros
acumula também ancestrais repetidos entre consultas, e não conta arquivos de
subárvores não consultadas. Há cache positivo/negativo, 4 MiB acumulados de
listagens, 4 KiB por linha e no máximo 64 consultas, profundidade 12. Não há
fallback permissivo após erro de limite ou de ferramenta. Diretórios raiz com
mais de 10.000 entradas ainda podem ser recusados por limite operacional.

`_run_bounded` inicia um Python isolado e novo para definir RLIMIT_AS=1 GiB,
RLIMIT_CPU=30 s e core=0 antes de exec do unsquashfs. Esse wrapper recusa EUID 0;
não usa preexec_fn na thread Qt. Vale também para a inspeção inicial como usuário.
O cache do unsquashfs continua em 64 MiB; isso não é seu limite total de memória.
Na revalidação, esses limites se somam aos do processo nobody já existente.
A saída stdout é limitada conforme operação, stderr a 16 KiB, com timeout por
comando e deadline de 120 s para inspeção. Uso de memória não tem quota agregada
entre processos; o parser reduzido e seu leitor têm limites individuais.

Inspeção de metadados não certifica cada arquivo interno do aplicativo, autoria,
assinaturas ou segurança de execução. Tampouco se promete que unsquashfs não leia
suas tabelas internas completas; CPU/memória/tempo continuam limitados. A GUI e o
helper usam a mesma estratégia, com inspeção independente do snapshot pelo helper.
Falhas de formato, orçamento operacional e processo leitor têm classes distintas;
a mensagem inclui valores/código/stderr limitados quando disponíveis. Não se
confunde excesso de orçamento com formato inválido. SIGKILL sem diagnóstico não
permite afirmar que houve falta de memória; limites configurados são informados.


## Categorias do lançador — build test20261031.2

`Inspection.categories` contém uma tupla canônica de identificadores registrados.
A inspeção não privilegiada interpreta o campo opcional Categories após decodificar
escapes desktop; a lista é serializada como array JSON pelo processo reduzido.
`boundary.validate_response` exige o campo, tipo lista, 1–32 strings limitadas e
canonicalização exata pelo registro estático em categories.py. A geração do desktop
valida novamente antes de escrever `Categories=...;`. Categorias não alteram caminhos,
identidade do pacote, Exec, permissões, autorização ou comandos administrativos.

Campo original ausente, sintaticamente inválido ou sem classificação utilizável
usa Utility; um token desconhecido é descartado sem transportar texto arbitrário.
Somente identificadores registrados pertinentes à classificação são preservados;
frameworks conhecidos (Qt/KDE/GTK etc.) podem acompanhar a principal. Não há exceção
por nome de aplicativo. O registro é código instalado, não baixado em runtime.
Limites: 1.024 caracteres e 32 itens, inclusive no protocolo. Não se preservam
categorias reservadas/customizadas, nem ConsoleOnly em um lançador Terminal=false.
A informação não comprova a atividade ou autoria real do aplicativo: os metadados
continuam declarativos. Um parser comprometido pode sugerir categorias permitidas,
mas não inserir campos extras/comandos através da lista.

KService monitora as pastas de desktop na sessão KDE; a transação dpkg normal
substitui o arquivo no mesmo destino. O helper não altera caches/configurações da
sessão nem executa ferramentas de menu como root. Uma atualização manual de sycoca,
se necessária, deve ocorrer como usuário da sessão, sem remoção de cache em massa.
