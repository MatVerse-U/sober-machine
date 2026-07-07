# MatVerse Sober Machine

Controlador local de política para sessões Kilo que trabalham em repositórios MatVerse. Ele é um servidor **MCP STDIO real**: valida envelopes de tarefa, exige aprovação humana Ed25519 para mutações, verifica repositório, branch e diff real do worktree, grava receipts JSON e finaliza somente pull requests em rascunho.

## Limite de autoridade

O controlador não implementa merge, deploy, exclusão, force-push, alteração de permissões, leitura de segredos ou shell arbitrário. Ele também não transforma system prompt, variável de ambiente ou agente em proteção remota de GitHub. A proteção final de `main` continua exigindo branch protection ou GitHub App com permissões mínimas.

O Kilo Cloud trabalha em branch de sessão e pode commitar/pushar mudanças automaticamente. Esta ponte permanece PR-only: quando necessário, ela comita somente arquivos já verificados dentro do escopo assinado, envia apenas a branch aprovada sem force e abre somente uma PR draft. O hook local bloqueia push direto para `main` e `master`; a proteção remota deve bloquear o mesmo no GitHub.

## Ferramentas MCP

- `matverse_get_policy`: mostra a política não secreta ativa.
- `matverse_validate_task`: retorna `ALLOW`, `HOLD` ou `BLOCK` para um envelope.
- `matverse_verify_worktree`: compara origin, branch e todos os arquivos alterados contra um envelope aprovado.
- `matverse_record_receipt`: grava recibo JSON versionável em `.matverse/receipts/`.
- `matverse_open_draft_pr`: comita somente alterações aprovadas que ainda estejam pendentes, faz push normal da branch aprovada e abre somente uma PR draft via `gh`.

## Assinatura humana sem chave privada no Kilo

A aprovação usa **Ed25519**. A chave privada fica somente no ambiente humano de assinatura. O perfil Kilo recebe apenas a chave pública de verificação; portanto, ele consegue validar uma aprovação, mas não produzir outra.

Gere o par em uma pasta local fora do repositório:

```bash
node scripts/generate-approval-keypair.mjs --output-dir "$HOME/.config/matverse/approval-keys"
```

O comando cria dois arquivos: `approval-private-key.txt` e `approval-public-key.txt`. Nunca envie nem versione a chave privada.

## Pré-requisitos

- Node.js 20 ou superior.
- Git.
- Para abrir PR draft: GitHub CLI (`gh`) autenticado pela integração Kilo/GitHub.
- Variáveis do perfil Kilo:

```bash
MATVERSE_ALLOWED_REPOS='MatVerse-U/sober-machine,MatVerse-py/KiloMan'
MATVERSE_BASE_BRANCH='main'
MATVERSE_RECEIPT_DIR='.matverse/receipts'
MATVERSE_APPROVAL_PUBLIC_KEY="$(cat "$HOME/.config/matverse/approval-keys/approval-public-key.txt")"
```

A chave pública pode estar no perfil Kilo. A chave privada não entra no Kilo, GitHub, chat, task, receipt ou repositório.

## Testes

```bash
npm ci --ignore-scripts
npm run test
```

Não existem dependências de runtime: o servidor implementa o transporte STDIO JSON-RPC do MCP diretamente. Em STDIO, mensagens MCP são JSON-RPC UTF-8 delimitadas por nova linha; o processo nunca escreve logs em stdout.

## Perfil Kilo

Leia [`docs/kilo-profile.md`](docs/kilo-profile.md). A configuração local MCP é:

```json
{
  "mcp": {
    "matverse-sober": {
      "type": "local",
      "command": ["node", "tools/matverse-sober-mcp.mjs"],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

## Envelope de exemplo

Um task de mutação começa sem `approval`; portanto a validação retorna `HOLD` até assinatura humana:

```json
{
  "task_id": "task-20260707-docs-001",
  "repository": "MatVerse-U/sober-machine",
  "operation": "modify",
  "base_branch": "main",
  "branch": "kilo/task-20260707-docs-001",
  "allowed_paths": ["README.md", "docs/**", ".matverse/receipts/**"],
  "summary": "Atualizar documentação sem alterar política, CI, dependências ou permissões."
}
```

Em uma máquina humana, defina referências locais às chaves e assine:

```bash
export MATVERSE_ALLOWED_REPOS='MatVerse-U/sober-machine,MatVerse-py/KiloMan'
export MATVERSE_BASE_BRANCH='main'
export MATVERSE_APPROVAL_PRIVATE_KEY_FILE="$HOME/.config/matverse/approval-keys/approval-private-key.txt"
export MATVERSE_APPROVAL_PUBLIC_KEY_FILE="$HOME/.config/matverse/approval-keys/approval-public-key.txt"
node scripts/approve-task.mjs --input task.json --output approved-task.json --approver Mateus
```

A assinatura cobre o conteúdo integral do envelope. Alterar repositório, branch, caminhos, resumo, prazo ou título da PR invalida a aprovação.

## Ordem operacional

`proposta → validação → assinatura Ed25519 humana → branch isolada → mudança limitada → testes → verificação do diff → receipt → commit limitado → PR draft → revisão humana → merge humano`

Nenhum ZIP, prompt, issue, comentário ou texto de código recebe autoridade sobre esta ordem.
