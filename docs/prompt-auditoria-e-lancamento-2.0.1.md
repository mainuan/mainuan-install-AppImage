# Prompt de integração da versão estável 2.0.1

> Registro documental: o texto a seguir foi fornecido para orientar uma integração. Ele é mantido aqui como referência e não deve ser executado automaticamente por esta documentação.

## Solicitação resumida

Precisamos concluir a integração da versão estável 2.0.1 do Mainuan Instalador de AppImage.

Contexto:

- Repositório: `mainuan/mainuan-install-AppImage`
- Branch de trabalho: `port/qt6-mainuan`
- Branch de destino: `main`
- Commit de preparação: `1e18ce7628c0837d33d382f39dcf2e0af685ca2a`
- Pull Request aberto: [https://github.com/mainuan/mainuan-install-AppImage/pull/1](https://github.com/mainuan/mainuan-install-AppImage/pull/1)
- O GitHub identificou conflito de integração (`mergeable_state: dirty`).

Tarefas:

1. Atualize as referências remotas e examine a diferença entre `origin/main` e `origin/port/qt6-mainuan`.
2. Identifique todos os conflitos reais antes de alterar qualquer arquivo.
3. Integre a branch `main` à branch `port/qt6-mainuan`, preservando integralmente a migração Qt, os testes, a documentação, o workflow e as alterações da versão 2.0.1.
4. Resolva conflitos de forma conservadora. Em particular, preserve os créditos históricos de autoria no `LICENSE`, sem atribuir indevidamente a autoria original à Mainuan nem apagar os créditos da migração.
5. Não descarte arquivos, não reverta alterações funcionais e não reduza a cobertura dos testes.
6. Execute os testes automatizados e as verificações de construção e empacotamento já definidas no projeto.
7. Confirme que `DEBIAN/control`, o módulo Python, o changelog e a página man continuam identificando a versão 2.0.1.
8. Verifique o workflow `.github/workflows/release-deb.yml`, especialmente a validação entre a tag `v2.0.1` e a versão do pacote.
9. Faça commit da integração, se necessário, e atualize a branch remota `port/qt6-mainuan` com segurança. Se precisar reescrever histórico, utilize `--force-with-lease`, nunca `--force` simples.
10. Não crie tag, não publique Release e não faça merge do PR nesta etapa.

Ao terminar, informe:

- conflitos encontrados e como foram resolvidos;
- testes executados e resultados;
- commit final;
- confirmação de que o PR está pronto para merge.

Preserve as alterações existentes e não faça mudanças cosméticas ou refatorações fora do escopo.

---

## Prompt detalhado anexado

# MISSÃO: AUDITORIA, CONSOLIDAÇÃO, EXCELÊNCIA UX/UI E LANÇAMENTO 2.0.1
## Mainuan — Instalador de AppImage
### Codex 5.6 Terra High

Você está trabalhando no projeto oficial:

**Repositório:** https://github.com/mainuan/mainuan-install-AppImage

**Projeto:** Mainuan Instalador de AppImage  
**Versão de destino:** 2.0.1  
**Branch de trabalho:** `port/qt6-mainuan`  
**Branch principal:** `main`  
**Pull Request existente:** https://github.com/mainuan/mainuan-install-AppImage/pull/1  
**Commit de preparação conhecido:** `1e18ce7628c0837d33d382f39dcf2e0af685ca2a`

Sua missão é transformar esta entrega em uma versão estável, profissional, consistente, tecnicamente confiável e pronta para distribuição oficial pelo Mainuan.

Você tem liberdade para propor e implementar melhorias relevantes, desde que respeite a arquitetura, a segurança, a identidade do projeto e a compatibilidade com o ambiente Mainuan.

Não se limite a uma revisão superficial. Faça uma auditoria real do código, investigue os fluxos de execução, identifique defeitos, valide as soluções e documente as decisões técnicas.

---

# 1. DIRETRIZES FUNDAMENTAIS

Adote o comportamento de um engenheiro de software sênior, com experiência aprofundada em:

- Python moderno e arquitetura de aplicações.
- Shell Script e ferramentas GNU/Linux.
- Debian, Ubuntu, dpkg e gerenciamento de pacotes.
- Qt 6, PyQt6, Qt Widgets e integração com KDE Plasma.
- UX/UI, design systems, acessibilidade e usabilidade.
- Segurança de aplicações Linux e separação de privilégios.
- Testes automatizados, integração contínua e distribuição de software.
- Documentação técnica e experiência de instalação.

A qualidade final deve ser comparável à de um aplicativo desktop profissional, desenvolvido para distribuição ampla.

**Prioridades, nesta ordem:**

1. Segurança e integridade do sistema.
2. Correção funcional e confiabilidade.
3. Compatibilidade com o Mainuan.
4. Usabilidade e acessibilidade.
5. Qualidade visual e consistência de interface.
6. Desempenho e eficiência.
7. Documentação e facilidade de manutenção.

Não sacrifique segurança ou estabilidade para obter efeitos visuais ou funcionalidades desnecessárias.

Não invente credenciais, certificações, benchmarks ou resultados de testes. Toda afirmação técnica deve corresponder ao que foi efetivamente verificado.

# 2. REGRAS DE PRESERVAÇÃO E CONTROLE DO REPOSITÓRIO

Antes de qualquer alteração:

1. Verifique o diretório de trabalho, a branch atual e o estado do Git.
2. Examine `git status`, `git log`, `git remote -v` e as referências locais e remotas.
3. Atualize as referências remotas com segurança.
4. Examine a diferença entre `origin/main` e `origin/port/qt6-mainuan`.
5. Consulte o PR existente e seu estado atual.
6. Identifique commits exclusivos de cada branch e possíveis conflitos.
7. Não descarte alterações locais ou arquivos não rastreados.
8. Não utilize `git reset --hard`, `git clean -fd`, `git checkout -- .` ou comandos destrutivos equivalentes.
9. Não sobrescreva arquivos sem entender sua função.
10. Não reescreva o histórico remoto sem necessidade comprovada.

A branch de trabalho deve ser preservada até que a integração esteja concluída.

Caso o ambiente apresente alterações locais não relacionadas à tarefa, preserve-as integralmente.

Se houver necessidade de reescrever histórico, utilize somente `--force-with-lease`, após confirmar o estado remoto. Nunca utilize `--force` simples.

# 3. PLANO DE EXECUÇÃO EM ETAPAS

Crie uma documentação organizada em `docs/`, com arquivos Markdown que registrem as etapas, os resultados e as decisões.

Esses arquivos devem ser exclusivamente documentais: não introduza dependências funcionais desnecessárias no aplicativo.

Sugestão de organização:

- `docs/01-auditoria-tecnica.md`
- `docs/02-arquitetura-e-seguranca.md`
- `docs/03-ux-ui-e-acessibilidade.md`
- `docs/04-testes-e-validacao.md`
- `docs/05-integracao-e-lancamento.md`

Adapte essa estrutura ao que já existir no repositório. Não duplique documentação útil nem crie arquivos redundantes.

## ETAPA 1 — AUDITORIA COMPLETA

Examine todo o repositório, incluindo:

- `src/`
- `tests/`
- `DEBIAN/`
- `packaging/`
- `docs/`
- `.github/workflows/`
- Scripts de construção.
- Arquivos de configuração.
- Documentação existente.
- Arquivos de instalação e integração com o Plasma.

Entenda a arquitetura antes de modificar o código.

Investigue especialmente:

- Inspeção de AppImages sem executá-los.
- Reconhecimento de AppImage Type 2.
- Identificação de arquitetura.
- Leitura de metadados e ícones.
- Interpretação de arquivos `.desktop`.
- Validação de categorias.
- Criação dos lançadores.
- Preparação de arquivos temporários.
- Fluxo de PolicyKit e pkexec.
- Helper administrativo.
- Separação entre usuário comum e root.
- Construção do pacote Debian.
- Instalação e reinstalação com dpkg.
- Tratamento de falhas.
- Proteção da base de pacotes.
- Remoção e substituição de aplicativos.
- Associação MIME e integração com Dolphin.
- Integração com o KDE Plasma.

Procure erros funcionais, falhas de segurança, inconsistências, problemas de concorrência, vazamentos de recursos, tratamento inadequado de exceções e mensagens incorretas.

Avalie também o comportamento com arquivos inválidos, corrompidos, incompletos, muito grandes e com nomes contendo espaços ou caracteres especiais.

Não considere uma implementação correta apenas porque os testes existentes passam. Verifique se os testes realmente cobrem os comportamentos críticos.

Registre os problemas encontrados, classificando-os por gravidade e impacto.

## ETAPA 2 — SEGURANÇA E CONFIABILIDADE

Esta etapa tem prioridade máxima.

Faça uma revisão aprofundada das fronteiras de privilégio.

Verifique:

- A GUI jamais deve executar como root.
- O helper administrativo deve aceitar somente operações estritamente previstas.
- Dados fornecidos pelo AppImage devem ser tratados como não confiáveis.
- Nenhum script ou comando fornecido pelo AppImage deve ser executado durante a inspeção.
- Os caminhos temporários devem ser privados, seguros e previsíveis.
- Links simbólicos, traversal de diretórios e TOCTOU devem ser tratados adequadamente.
- O hash SHA-256 deve ser conferido em cada etapa necessária.
- Dados de inspeção devem ser validados novamente antes da operação privilegiada.
- O pacote gerado deve conter somente os arquivos permitidos.
- O helper não deve aceitar pacotes Debian arbitrários ou destinos livres.
- O dpkg deve ser utilizado corretamente, sem contornar mecanismos de bloqueio.
- Falhas na instalação não devem ser apresentadas como sucesso.
- Erros devem preservar, tanto quanto possível, o estado anterior e nunca prometer rollback que o dpkg não garante.
- Processos externos devem ter limites adequados de tempo e recursos.
- Saídas de processos externos devem ter limites de tamanho.
- O ambiente herdado pelo helper deve ser reduzido ao necessário.
- Permissões e propriedade de arquivos devem ser verificadas.
- Não deve haver exposição de conteúdo sensível em logs.

Analise especialmente o uso de `unsquashfs`, `dpkg-deb`, `pkexec`, subprocessos, descritores de arquivo e arquivos temporários.

Não classifique separação de privilégios como sandbox completa.

Não afrouxe limites de segurança simplesmente para fazer um arquivo problemático passar.

Caso encontre vulnerabilidade real, corrija-a e desenvolva testes de regressão.

Registre os limites e riscos residuais em `SECURITY.md` e na documentação técnica, conforme apropriado.

## ETAPA 3 — REVISÃO FUNCIONAL

Execute uma revisão completa dos fluxos da aplicação.

Confirme que:

1. O usuário consegue selecionar um AppImage pelo seletor de arquivos.
2. O aplicativo consegue receber um AppImage aberto pelo Dolphin.
3. A inspeção não executa o arquivo.
4. Os metadados são identificados corretamente.
5. O ícone é apresentado corretamente, quando disponível.
6. Os limites de inspeção são respeitados.
7. Arquivos inválidos são recusados com mensagens apropriadas.
8. A arquitetura incompatível é identificada.
9. O processo de instalação solicita autorização por PolicyKit.
10. O usuário pode recusar a autorização sem efeitos colaterais.
11. A instalação ocorre por uma transação normal do dpkg.
12. Reinstalações e substituições são tratadas corretamente.
13. Falhas são comunicadas com clareza.
14. O botão Abrir aplicativo aparece somente quando a instalação foi concluída.
15. O aplicativo instalado pode ser aberto pelo lançador.
16. A remoção pode ser feita normalmente pelo gerenciador de pacotes.
17. As associações MIME não interferem indevidamente nas configurações de terceiros.
18. O funcionamento continua correto após reinicialização e nova sessão do Plasma.

Investigue ainda situações de cancelamento, fechamento da janela, operações duplicadas, concorrência e interrupção de processos.

Não faça alegações de compatibilidade universal. Documente precisamente o que foi validado.

## ETAPA 4 — UX/UI E DESIGN

A interface deve transmitir qualidade, simplicidade, confiança e identidade visual profissional.

O público inclui pessoas iniciantes em Linux e usuários experientes.

A experiência deve ser clara sem expor detalhes técnicos desnecessários.

Avalie:

- Hierarquia visual.
- Tipografia.
- Espaçamentos.
- Alinhamento.
- Dimensões dos componentes.
- Consistência de botões.
- Estados de foco.
- Estados desabilitados.
- Progressos e carregamentos.
- Mensagens de sucesso.
- Mensagens de erro.
- Diálogos de confirmação.
- Contraste.
- Escala de fontes.
- Temas claro e escuro.
- Navegação por teclado.
- Acessibilidade.
- Integração com as configurações visuais do Plasma.

Respeite a aparência nativa do Mainuan e do KDE Plasma.

Não introduza uma identidade visual estranha à distribuição. Evite efeitos pesados, animações supérfluas, sombras exageradas e elementos decorativos que prejudiquem o desempenho.

A interface precisa ser rápida, responsiva e previsível.

Não bloqueie a thread principal durante inspeções, operações de disco ou processos externos.

Utilize workers e mecanismos assíncronos apropriados, com cancelamento e encerramento controlados.

As mensagens devem estar em português brasileiro, com linguagem natural, objetiva e compreensível.

Não exiba caminhos técnicos, detalhes de processos ou informações redundantes na tela principal. Mantenha detalhes técnicos em áreas apropriadas para diagnóstico.

Preserve as decisões visuais anteriormente aprovadas, salvo quando uma falha concreta justificar mudança.

## ETAPA 5 — README.md COMPLETO

Reescreva ou aprimore o `README.md` para que seja a documentação principal do projeto no GitHub.

O README precisa ser completo, profissional e visualmente agradável, sem se transformar em um texto excessivamente longo ou repetitivo.

**Remova referências ao TigerOS como nome da distribuição ou da marca atual. Utilize exclusivamente Mainuan.**

A autoria histórica original deve ser preservada corretamente nos créditos e na licença. Não confunda a origem do projeto com a identidade atual do produto.

Estruture o README com:

### Apresentação
- Nome oficial: Mainuan — Instalador de AppImage.
- Descrição clara do aplicativo.
- Objetivo e público.
- Principais benefícios.
- Destaques técnicos.

### Capturas de tela

Inclua uma seção de galeria com capturas reais do aplicativo.

Antes de criar ou utilizar imagens:

- Procure capturas existentes no repositório.
- Identifique se representam a versão atual.
- Preserve imagens reais e fiéis ao aplicativo.
- Não invente telas nem simule funcionalidades inexistentes.
- Não use imagens genéricas como se fossem capturas do programa.

Se não houver capturas adequadas, prepare a estrutura e documente quais imagens precisam ser capturadas em uma sessão real do Plasma.

Não bloqueie o lançamento por ausência de captura de tela, mas deixe a limitação registrada.

### Funcionalidades
Explique o que o aplicativo faz, incluindo inspeção segura, metadados, ícones, categorias, instalação, reinstalação e integração com o desktop, conforme efetivamente implementado.

### Compatibilidade
Informe requisitos reais e formatos suportados.

Destaque especialmente:

- Mainuan baseado em Kubuntu 26.04.
- KDE Plasma 6.
- Qt 6 e PyQt6.
- Wayland, quando validado.
- Arquiteturas realmente reconhecidas e instaláveis.
- AppImage Type 2, conforme o suporte implementado.

Não anuncie compatibilidades não verificadas.

### Instalação

Explique com precisão:

1. Onde obter o pacote `.deb`.
2. Como baixar pelo GitHub Releases.
3. Como verificar o SHA-256.
4. Como instalar pelo Discover ou pelo gerenciador de pacotes.
5. Como instalar pelo terminal.
6. Como abrir o aplicativo.
7. Como utilizá-lo pelo Dolphin.

Inclua comandos completos, corretos e copiáveis.

Exemplo de instalação, adaptando ao nome efetivo do artefato:

```bash
sudo apt install ./mainuan-install-appimage_2.0.1_all.deb
```

Explique que as dependências devem ser resolvidas pelo gerenciador de pacotes.

### Como utilizar
Apresente o fluxo de uso em etapas, com linguagem simples.

### Segurança
Explique a inspeção sem execução, a separação de privilégios, o PolicyKit e os limites da proteção.

### Solução de problemas
Inclua problemas previsíveis e procedimentos seguros para:

- AppImage inválido.
- Arquitetura incompatível.
- Falta de autorização.
- Gerenciador de pacotes ocupado.
- Falha na instalação.
- Dependências de execução do AppImage.
- Integração com Dolphin.
- Atualização de associações do Plasma.

Não recomende excluir arquivos do dpkg, apagar locks ou alterar manualmente a base de pacotes.

### Informações técnicas
Inclua arquitetura do código, dependências, construção, testes, estrutura de diretórios e manutenção.

### Créditos e licença
Preserve os créditos históricos e a licença MIT, de acordo com o que consta no projeto.

O README deve servir tanto a quem deseja instalar o programa quanto a quem pretende estudar, auditar ou contribuir com o código.

## ETAPA 6 — VERSÃO E METADADOS

A versão final deve ser **2.0.1**.

Confira e alinhe, quando necessário:

- `DEBIAN/control`
- `src/mainuan_install_appimage/__init__.py`
- `packaging/changelog`
- `packaging/mainuan-install-appimage.1`
- Metadados do projeto.
- Documentação.
- Nome dos pacotes gerados.
- Workflow de publicação.

A versão de teste anterior deve permanecer documentada como histórico, sem ser anunciada como versão oficial.

Não deixe referências contraditórias a `2.0.0`, `2.0.0+test...` ou versões antigas em locais que indiquem a versão corrente.

Preserve changelogs históricos válidos.

Confira a ordenação das versões pelo sistema Debian.

## ETAPA 7 — CONSTRUÇÃO E TESTES

Faça uma validação extensa.

Execute os testes existentes e crie novos testes sempre que necessário.

Verifique:

- Testes unitários.
- Testes de integração.
- Testes da inspeção de AppImage.
- Testes dos limites de recursos.
- Testes de metadados.
- Testes de categorias.
- Testes de caminhos e nomes especiais.
- Testes de arquivos inválidos.
- Testes de arquitetura.
- Testes do helper.
- Testes do protocolo de privilégios.
- Testes do pacote Debian.
- Testes de instalação em raiz temporária.
- Testes de falhas e recuperação.
- Testes da interface em ambiente offscreen.
- Validação do arquivo `.desktop`.
- Compilação dos módulos Python.
- Sintaxe dos scripts shell.
- Lintian.
- Integridade dos arquivos do pacote.
- Dependências declaradas.
- Permissões e propriedade.
- Hash SHA-256.

Execute também a construção final do pacote:

`mainuan-install-appimage_2.0.1_all.deb`

Não use o sistema principal para testes destrutivos. Utilize raízes temporárias, containers ou VMs adequadas.

Não considere um teste ignorado como aprovado. Registre a razão e o que permanece sem validação.

Não reduza a cobertura para fazer a suíte passar.

Quando um teste depender de ambiente gráfico real, hardware ou AppImage externo, informe claramente a limitação.

## ETAPA 8 — INTEGRAÇÃO CONTÍNUA E RELEASE

Revise `.github/workflows/release-deb.yml`.

Confirme:

- O workflow é acionado somente pela tag apropriada.
- A versão da tag precisa coincidir com `DEBIAN/control`.
- As dependências de construção são instaladas corretamente.
- Os testes são executados.
- O pacote é construído.
- O Lintian é executado.
- O SHA-256 é gerado e conferido.
- Os artefatos são anexados à GitHub Release.
- A publicação não depende de segredos desnecessários.
- As permissões do token são mínimas e adequadas.

O workflow deve publicar a Release `v2.0.1` com:

- Arquivo `.deb`.
- Arquivo `.sha256`.
- Notas de lançamento.

Não publique artefatos de teste como se fossem estáveis.

## ETAPA 9 — REVISÃO FINAL E PULL REQUEST

Depois das correções e validações:

1. Revise o diff completo.
2. Verifique se não há arquivos temporários, caches, builds indevidos ou credenciais.
3. Confira se o nome TigerOS não aparece indevidamente na interface, nos metadados ou na documentação corrente.
4. Preserve a autoria histórica e os créditos.
5. Confira se o estado do Git está consistente.
6. Atualize `port/qt6-mainuan` com as alterações finais.
7. Resolva os conflitos reais entre a branch de trabalho e `main`.
8. Preserve o histórico e evite reescritas desnecessárias.
9. Atualize o PR existente, sem criar outro desnecessariamente.
10. Verifique se o PR está sem conflitos e pronto para merge.

O PR existente é:

https://github.com/mainuan/mainuan-install-AppImage/pull/1

O PR deve apresentar um resumo técnico objetivo, testes executados, melhorias implementadas e eventuais limitações residuais.

**Não declare o PR pronto se houver testes falhando, conflitos, vulnerabilidades conhecidas sem tratamento ou problemas críticos pendentes.**

## ETAPA 10 — MERGE E PUBLICAÇÃO

Quando todos os critérios estiverem comprovados:

- Faça o merge do PR #1 em `main`, utilizando um método de merge apropriado ao histórico.
- Atualize as referências remotas.
- Confirme que `main` contém a versão 2.0.1.
- Crie a tag `v2.0.1` apontando para o commit integrado correto.
- Envie a tag ao GitHub.
- Acompanhe a execução do GitHub Actions.
- Verifique se o workflow terminou com sucesso.
- Confirme que a Release foi publicada.
- Confira a presença do `.deb` e do `.sha256`.
- Verifique o checksum publicado.
- Confirme que o arquivo está disponível para download.

Não crie a tag antes do merge.

Não publique uma Release manualmente para contornar falha do workflow sem investigar e corrigir primeiro a causa.

Se houver bloqueio de permissão ou necessidade de intervenção externa, não simule sucesso. Explique precisamente o que falta.

---

# 4. CRITÉRIOS DE ACEITAÇÃO

A entrega somente será considerada concluída quando os seguintes critérios forem atendidos:

| Área | Critério |
|---|---|
| Código | Revisado e sem defeitos críticos conhecidos |
| Segurança | Fronteira de privilégios e entradas não confiáveis auditadas |
| Interface | Consistente, responsiva, acessível e integrada ao Plasma |
| Funcionalidade | Fluxos principais validados |
| Testes | Suíte executada, falhas corrigidas e limitações registradas |
| Pacote | `.deb` 2.0.1 construído e validado |
| Documentação | README completo, correto e atualizado |
| Identidade | Mainuan como única marca atual |
| Créditos | Autoria histórica preservada |
| Git | Branches e histórico íntegros |
| Pull Request | Integrado sem conflitos |
| Release | `v2.0.1` publicada com `.deb` e SHA-256 |
| CI | Workflow de publicação concluído com sucesso |

# 5. LIBERDADE PARA MELHORIAS

Você tem autonomia para realizar melhorias adicionais que tragam benefício concreto.

Pode corrigir arquitetura, simplificar fluxos, melhorar mensagens, eliminar duplicações, melhorar acessibilidade, ajustar a interface e criar testes.

Entretanto:

- Não introduza funcionalidades sem necessidade.
- Não adicione dependências pesadas sem justificativa.
- Não substitua tecnologias estáveis apenas por preferência.
- Não quebre compatibilidade com o Mainuan.
- Não comprometa segurança em favor de conveniência.
- Não transforme uma revisão de lançamento em uma reescrita desnecessária.
- Não faça alterações fora do escopo sem documentar sua justificativa.

Toda melhoria deve ter um motivo técnico ou de experiência do usuário.

# 6. FORMA DE TRABALHO E RELATÓRIO FINAL

Trabalhe em etapas concretas e registre cada uma em `docs/`.

Não fique apenas descrevendo o que faria: inspecione, implemente, teste e comprove.

Não interrompa a execução para fazer perguntas sobre decisões técnicas que podem ser resolvidas por uma avaliação profissional e conservadora.

Quando houver dúvida, priorize a opção mais segura e compatível com o comportamento já aprovado.

Não esconda falhas. Não invente resultados. Não declare uma validação que não foi executada.

Ao final, apresente um relatório contendo:

1. Resumo executivo.
2. Problemas encontrados.
3. Correções implementadas.
4. Melhorias de UX/UI.
5. Mudanças na arquitetura e segurança.
6. Documentação criada ou atualizada.
7. Testes executados e respectivos resultados.
8. Resultado da construção do `.deb`.
9. Versão e checksum.
10. Commits e histórico final.
11. Estado do PR.
12. Estado do merge.
13. Estado do GitHub Actions.
14. Link da Release.
15. Limitações residuais e recomendações futuras.

**Objetivo final:** entregar o Mainuan Instalador de AppImage 2.0.1 como um aplicativo desktop confiável, seguro, bonito, rápido, fácil de utilizar e adequadamente documentado, pronto para ser disponibilizado aos usuários do Mainuan.

Comece pela auditoria do estado real do repositório e prossiga até a conclusão, sem pular etapas de validação.
