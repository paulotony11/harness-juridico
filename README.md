# Harness Jurídico

Configuração da nossa stack de IA para advocacia em volta do **Claude Code**: regras do escritório,
skills, ferramentas conectadas (MCP), bibliotecas de engenharia e análise de dados e a anonimização LGPD
automática. Com este repositório, qualquer máquina nova fica igual à de referência com dois comandos.

> **Este repositório guarda só configuração.** Dados de clientes, minutas e o banco `juridico.duckdb`
> nunca entram aqui (veja `.gitignore`).

A explicação visual (chatbot × harness, camadas, fluxo de dados) está em
[`docs/harness-juridico.html`](docs/harness-juridico.html). Baixe e abra no navegador.

## Instalar numa máquina nova (Windows)

```powershell
git clone https://github.com/<conta>/harness-juridico.git
cd harness-juridico
powershell -ExecutionPolicy Bypass -File .\prerequisitos-windows.ps1   # Python, uv, Git, Tesseract (sem admin)
# feche e abra o terminal
python instalar.py                                                      # todo o resto
```

Em macOS/Linux: instale Python 3.13, `uv`, Tesseract (com o idioma `por`) e o Claude Code, e rode
`python3 instalar.py`.

Opções: `--workspace D:/juridico` (padrão `~/juridico`), `--pular-pip`, `--pular-dbt`,
`--pular-plugins`, `--pular-mcp`. O instalador é **idempotente**: rodar de novo atualiza, e todo arquivo
que mudaria ganha backup `.bak-AAAAMMDD-HHMMSS`.

## O que é instalado

| Camada | Itens |
|---|---|
| Regras | `workspace/CLAUDE.md`: cinco regras do escritório, estrutura de pastas, convenções de dados |
| Skills próprias | `calculo-trabalhista`, `leitura-cartao-ponto`, `lgpd-sentinel` (revisada) |
| Plugins oficiais | `legal`, `data` (Anthropic knowledge-work-plugins), `document-skills` (Anthropic skills), `dbt` (dbt Labs) |
| MCP | `juridico-brasil` (DataJud, prazos CPC, DJe), `mcp-brasil` (dados públicos), `duckdb-juridico` (consulta somente leitura) |
| Python | `requirements.txt`: docling, DuckDB 1.5.6, polars, dlt, pandera, statsmodels, scikit-learn, lifelines, juscraper, validate-docbr, holidays, Presidio + spaCy pt etc. |
| dbt | `dbt-core` + `dbt-duckdb` como ferramenta isolada do `uv` |
| Automação | hook que gera cópia `_anon` de tudo em `dados/exportacoes/` |
| Desligado | 15 conectores de nuvem dos plugins (Slack, Box, Snowflake…) que o escritório não usa |

## Estrutura

```
claude/skills/            skills copiadas para ~/.claude/skills
workspace/                copiado para ~/juridico
  CLAUDE.md               regras do workspace
  scripts/anonimizar.py   anonimização LGPD (.docx, .pdf, .txt, .md)
  scripts/pii_br.py       detecção rápida de CPF, CNPJ, CNJ, OAB, e-mail
  scripts/hooks/          anonimizar_exportacoes.py (ativo) e checar_publicacao.py (desligado)
  dbt/                    projeto dbt "jurimetria"
docs/harness-juridico.html  página de apresentação para a equipe
instalar.py               instalador multiplataforma
prerequisitos-windows.ps1 pré-requisitos no Windows
requirements.txt          versões testadas juntas
```

## Atualizar a stack

1. Altere os arquivos aqui (não direto em `~/.claude` ou `~/juridico`).
2. Rode `python instalar.py --pular-pip --pular-dbt` para aplicar na sua máquina e conferir os autotestes.
3. Faça commit e push. Nas outras máquinas: `git pull` e `python instalar.py`.

## Cuidados

- **DuckDB fixado em 1.5.6** em Python, dbt e MCP. O 2.0 grava arquivos que o 1.5 não lê; atualize todos juntos.
- **Anonimização reduz o risco, não garante nada.** Revise as cópias `_anon` antes de enviar.
- O plugin `legal` segue a prática norte-americana; adapte ao direito brasileiro.
- Toda saída é apoio ao advogado (Recomendação CFOAB nº 001/2024; Resolução CNJ nº 615/2025).
- `lgpd-sentinel` é AGPL-3.0 (veja `claude/skills/lgpd-sentinel/NOTICE.md`).
