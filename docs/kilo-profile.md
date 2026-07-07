# Perfil Kilo: AGENTE GPT-KILO

## Objetivo

Executar somente tarefas MatVerse com escopo explícito, assinatura Ed25519 humana para mutações, branch isolada, receipt versionado e pull request em rascunho. O perfil não recebe poder de merge, deploy, exclusão, force-push ou leitura de segredos.

## Campos do perfil

**Nome:** `AGENTE GPT-KILO`  
**Descrição:** `Executor PR-only de tarefas MatVerse: valida escopo e assinatura humana no Sober Machine, altera apenas a branch de sessão, registra receipt e abre somente PR draft.`

Cole como **System prompt** o conteúdo de `.kilo/agents/gpt-kilo-sober.md` abaixo do frontmatter YAML.

## Variables

| Chave | Valor |
| --- | --- |
| `MATVERSE_ALLOWED_REPOS` | `MatVerse-U/sober-machine,MatVerse-py/KiloMan` |
| `MATVERSE_BASE_BRANCH` | `main` |
| `MATVERSE_RECEIPT_DIR` | `.matverse/receipts` |
| `MATVERSE_APPROVAL_PUBLIC_KEY` | conteúdo de `approval-public-key.txt` gerado fora do repositório |

A chave pública pode ser incluída no Environment JSON do perfil. A chave privada não é configurada no Kilo sob nenhuma forma.

## Setup

Use este comando de startup no repositório `MatVerse-U/sober-machine`:

```bash
bash scripts/kilo-setup.sh
```

## MCP local

Na aba **MCP**, escolha **Local** e adicione:

| Campo | Valor |
| --- | --- |
| Name | `matverse-sober` |
| Command | `node tools/matverse-sober-mcp.mjs` |
| Enabled | ligado |

O processo MCP herda a chave pública do perfil. Não forneça chave privada, token pessoal, segredo de API ou arquivo de credencial ao servidor.

## Skills

O skill canônico está em `.kilo/skills/matverse-sober-pr/SKILL.md`. Uma cópia de compatibilidade está em `.kilocode/skills/matverse-sober-pr/SKILL.md` para o fluxo Cloud que reconhece esse diretório. As duas cópias devem permanecer idênticas; não crie uma segunda política.

## Assinatura humana de uma mutação

1. Gere o par Ed25519 localmente:

```bash
node scripts/generate-approval-keypair.mjs --output-dir "$HOME/.config/matverse/approval-keys"
```

2. Coloque somente o conteúdo de `approval-public-key.txt` em `MATVERSE_APPROVAL_PUBLIC_KEY` no perfil Kilo.
3. Gere um `task.json` sem campo `approval`.
4. Revise repositório, branch, `allowed_paths`, resumo e, quando houver PR, `pr_title`.
5. Em ambiente humano local, assine:

```bash
export MATVERSE_ALLOWED_REPOS='MatVerse-U/sober-machine,MatVerse-py/KiloMan'
export MATVERSE_BASE_BRANCH='main'
export MATVERSE_APPROVAL_PRIVATE_KEY_FILE="$HOME/.config/matverse/approval-keys/approval-private-key.txt"
export MATVERSE_APPROVAL_PUBLIC_KEY_FILE="$HOME/.config/matverse/approval-keys/approval-public-key.txt"
node scripts/approve-task.mjs --input task.json --output approved-task.json --approver Mateus
```

6. Entregue ao agente somente `approved-task.json`; a chave privada não acompanha o arquivo.
7. O agente valida, trabalha no escopo, testa, grava receipt e abre apenas uma PR em rascunho.

## Limite atual para KiloMan

Este servidor MCP é local ao repositório em que a sessão Kilo foi iniciada. Portanto, nesta primeira implantação ele controla diretamente `MatVerse-U/sober-machine`. Para usar o mesmo controlador em sessões Kilo do `MatVerse-py/KiloMan`, primeiro promova este PR e então instale o controlador como dependência versionada e pinada no KiloMan; não copie a implementação sem uma referência de versão e linhagem.
