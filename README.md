# Harness Jurídico

Configuração da nossa stack de IA para advocacia em volta do **Claude Code**: regras do escritório,
skills, ferramentas conectadas (MCP), bibliotecas de engenharia e análise de dados e a anonimização LGPD
automática. Com este repositório, qualquer máquina nova fica igual à de referência com dois comandos.

> **Este repositório guarda só configuração.** Dados de clientes, minutas e o banco `juridico.duckdb`
> nunca entram aqui (veja `.gitignore`).

## Documento da equipe

**[`docs/harness-juridico.pdf`](docs/harness-juridico.pdf)** abre direto aqui no GitHub: chatbot × agente
com harness, camadas da stack, segundo cérebro, como ele melhora com o uso, fluxo de dados, LGPD,
curadoria e regras de uso. A mesma página em versão web está em
[`docs/harness-juridico.html`](docs/harness-juridico.html): baixe e abra no navegador (os diagramas se
ajustam à tela). Autor: Paulo Tony.

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
| Segundo cérebro | cofre Obsidian (`cerebro/`) com leis, precedentes, teses, estratégias, casos e órgãos ligados em grafo; painéis nativos (Bases), mapa visual (Canvas), skill `segundo-cerebro` e `scripts/cerebro.py` |
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

## Segundo cérebro (Obsidian)

O cofre-modelo em `cerebro/` é copiado para `~/juridico/cerebro` **só onde ainda não existe arquivo**:
reinstalar nunca sobrescreve as notas do escritório. Abra essa pasta no Obsidian ("Abrir pasta como
cofre"). Só recursos nativos: grafo com cores por tipo de nota, painéis Bases, Canvas, modelos e
favoritos. Nenhum plugin da comunidade.

```
01 Mapas            índice por área + Guia do cérebro (tipos, regras de ligação, LGPD)
02 Legislação       um artigo por nota          03 Precedentes   súmulas, temas, OJs, julgados
04 Teses            argumentos com placar        05 Estratégias   playbooks + mapa visual
06 Casos            casos (cliente por código)   07 Órgãos e pessoas  varas, tribunais, peritos
08 Modelos de peças · 09 Doutrina e estudos · 10 Diário · _painéis (Bases) · _modelos
```

As notas-semente (CLT arts. 66, 71, 74, 775 e 818, CPC art. 219, Súmulas 338 e 437 e OJ 355 do TST)
vêm com `verificado: false`: confira na fonte oficial antes de usar. Caso e vara de exemplo são fictícios.

```
python scripts/cerebro.py novo tese "Título"   # cria pelo modelo, nunca sobrescreve
python scripts/cerebro.py verificar            # links quebrados, órfãs, CPF/e-mail no cofre
python scripts/cerebro.py indexar              # grafo -> parquet para consultas DuckDB
python scripts/cerebro.py grafo                # centros e ilhas de conhecimento
```

**O cofre real não entra neste repositório** (tem dados de casos). Só o modelo entra.

### Backup no OneDrive (configuração do escritório)

O cofre fica em `OneDrive\HYASMIN - ADVOCACIA\Cerebro Juridico`, e `~/juridico/cerebro` é um atalho
(junção) para lá, então Claude, scripts e regras não mudam de caminho. Numa máquina nova, espere o
OneDrive baixar a pasta e rode:

```powershell
python instalar.py --cerebro-em "$env:OneDrive\HYASMIN - ADVOCACIA\Cerebro Juridico"
```

Se a pasta já tem o cofre, o instalador só cria o atalho e acrescenta modelos ou painéis que faltem;
notas nunca são sobrescritas nem recriadas. Cuidados:
- marque a pasta como **"Sempre manter neste dispositivo"** (arquivos só na nuvem somem da busca e do grafo);
- use o cofre em **uma máquina por vez**; `cerebro.py verificar` aponta cópias de conflito do OneDrive;
- ative a **verificação em duas etapas** na conta Microsoft;
- o banco `juridico.duckdb` **não** vai para o OneDrive (sincronizar banco aberto corrompe; ele é regerado pelo dbt).

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
