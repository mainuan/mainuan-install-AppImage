# Categorias do lançador — build test20261031.2 — 31/10/2026

Branch `port/qt6-mainuan`, alterações locais preservadas. Sem commit, push, tag ou
publicação. Nenhuma instalação foi feita no dpkg real deste host.

## Resultado da VM informado pelo usuário

O usuário confirmou instalação bem-sucedida do Kdenlive e funcionamento do botão
Abrir aplicativo. A entrada apareceu em Utilitários. Esses resultados pertencem
ao teste real do usuário na VM, não a uma instalação executada por este agente.

## Causa e correção

O `.desktop` original de kdenlive-26.08.2-x86_64.AppImage contém:
`Categories=Qt;KDE;AudioVideo;AudioVideoEditing;`.
A inspeção anterior descartava o campo; o protocolo não o transportava e
`installer._write_package` escrevia invariavelmente `Categories=Utility;`.
A constante foi conferida também no código dentro do .deb test20261031.1.
Não foi lido diretamente o arquivo instalado na VM, indisponível neste host.

Agora `Inspection.categories` carrega uma lista canônica. O processo reduzido a
serializa como array JSON; o helper exige/valida esse campo independentemente e
o gerador valida de novo antes de escrever o único campo Categories. A whitelist
é genérica, baseada no registro freedesktop, sem exceção por nome de aplicativo.
Quebras de linha/injeção e sintaxe inválida não são copiadas. Categorias desconhecidas
ou incompatíveis são filtradas; sem classificação útil há fallback Utility.
Não se copiam o desktop inteiro, Exec nem ações arbitrárias.

O arquivo gerado para Kdenlive preserva exatamente
`Qt;KDE;AudioVideo;AudioVideoEditing;`. O menu padrão Plasma usa AudioVideo em
Multimedia (nome pt_BR: Multimídia). O teste real de geração KDE em XDG temporário
mudou a mesma entrada de `Utilities/` para `Multimedia/`, com uma única ocorrência.
A cópia privada de teste usou TryExec=/usr/bin/true porque o AppImage não está
instalado no host; o desktop gerado real não foi alterado por essa adaptação.
Isso não é confirmação visual no menu da sessão/VM; ela permanece pendente.

## Validação e entrega

**59 testes passaram:** os 51 existentes e oito regressões de categorias. Cobrem
multimídia real, outro aplicativo Office/Spreadsheet de ponta a ponta, dados
malformados/ausentes, injeção, protocolo hostil e reinstalação de pacote com a
mesma identidade/versão/hash. O dpkg isolado substituiu Utility pelo novo campo
no mesmo arquivo, sem duplicá-lo. desktop-file-validate passou para os desktops
gerados; lintian do novo instalador sem apontamentos. gui.py é byte a byte igual
ao do build anterior: título `Instalador de AppImage` e visual preservados.

Pacote novo: `dist/mainuan-install-appimage_2.0.0+test20261031.2_all.deb`.
SHA-256: `ef32ad9bc916b5ad3c653c137dc13a287e87e464cc70041e3e86d67dababa48f`.
Arquivo de checksum ao lado, com sufixo `.deb.sha256`.
Logs/evidências: `dist/categories-20261031.2/`. O build anterior não foi sobrescrito.

Atualizar o instalador na VM, reabrir o mesmo AppImage e clicar Reinstalar. Não
remover o aplicativo previamente. O desktop é substituído no mesmo caminho; o
KService/kded monitora a mudança. Se o menu mantiver informação antiga, executar
`kbuildsycoca6` como usuário da sessão e reabrir o menu, sem apagar caches ou
configurações. Roteiro com diagnósticos em [VALIDATION.md](VALIDATION.md).

Referências: [registro de categorias](https://specifications.freedesktop.org/menu/latest/category-registry.html),
[categorias adicionais](https://specifications.freedesktop.org/menu/latest/additional-category-registry.html),
[monitoramento de desktop files pelo KService](https://api.kde.org/ksycoca.html).
