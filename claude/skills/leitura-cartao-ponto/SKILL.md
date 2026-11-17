---
name: leitura-cartao-ponto
description: >
  Extrai marcações de um cartão/espelho de ponto (PDF ou imagem escaneada) via
  docling, normaliza para CSV e calcula horas trabalhadas, horas extras
  (critério diário e semanal), adicional noturno e violações de intervalo
  intrajornada (art. 71 CLT) e interjornada (art. 66 CLT). O resultado
  alimenta o `--media-he` da skill calculo-trabalhista. Use quando o usuário
  anexar um cartão de ponto, espelho de ponto, folha de frequência, ou pedir
  "calcula as horas extras desse ponto", "analisa esse cartão de ponto",
  "quantas horas extras teve esse mês".
argument-hint: "[arquivo do cartão de ponto]"
---

# /leitura-cartao-ponto

## Divisão de trabalho — por que não é tudo automático

Cartão de ponto tem formato livre (papel, sistema eletrônico, REP, planilha) —
não existe um parser universal confiável. O fluxo divide o trabalho onde cada
parte é boa:

1. **docling** extrai o conteúdo bruto do PDF/imagem (OCR incluso quando
   necessário) para markdown/texto.
2. **Você (Claude), lendo o extraído**, mapeia isso para o CSV canônico —
   isso é compreensão de documento, não aritmética, então é sua parte do
   trabalho, feita com cuidado e conferida linha a linha contra o extraído.
3. **`calculo_jornada.py`** (script determinístico, mesma pasta deste
   SKILL.md) faz a aritmética de horas, extras, noturno e violações — nunca
   calcule esses números de cabeça.
4. Opcionalmente, os totais de HE alimentam
   `~/.claude/skills/calculo-trabalhista/calculo_trabalhista.py` (skill
   irmã) para chegar no valor em R$.

**Python:** use `python` (no Windows, `py -3.13` se `python` não estiver no PATH).
**docling CLI:** se `docling` não estiver no PATH, use `python -m docling.cli.main`.

Rode `--selftest` uma vez por sessão para confirmar que o script está íntegro:
```
python calculo_jornada.py --selftest
```

## Fluxo

### 1. Extrair com docling

```
docling convert "<arquivo>" --to md --output <pasta_saida>
```

Se o arquivo for uma foto/imagem solta (jpg/png) e o docling recusar o
formato, avise o usuário e sugira converter para PDF antes (ou tente mesmo
assim — versões recentes do docling aceitam imagem direto).

Leia o markdown gerado. Se a extração vier ilegível ou incompleta (comum em
foto de baixa qualidade), diga isso ao usuário ANTES de inventar valores —
peça uma digitalização melhor ou os dados manualmente.

### 2. Normalizar para o CSV canônico

Rode `python calculo_jornada.py gerar-modelo` para ver o formato exato.
Colunas: `data` (YYYY-MM-DD), `marcacoes` (horários HH:MM separados por `;`,
em ordem cronológica — 2, 4 ou 6+ marcações por dia, o que o cartão trouxer),
`observacao` (folga, feriado, atestado, férias, falta, ponto não registrado
etc.).

Regras ao mapear:
- Preserve a ordem cronológica das marcações do dia.
- Dia sem nenhuma marcação → `marcacoes` vazio + `observacao` explicando por quê.
- Marcação que você não consegue ler com confiança → **não invente o horário**;
  deixe uma nota em `observacao` tipo "marcação ilegível às ~14h, confirmar" e
  omita esse par das marcações (o script sinaliza dias com número ímpar de
  marcações para revisão manual).
- Turno que atravessa a meia-noite: registre normalmente (o script já trata
  saída com hora-relógio menor que a entrada como virada de dia).

Salve o CSV (ex.: em `dados/tratado/` do workspace jurídico) e mostre as
primeiras linhas para o usuário confirmar antes de calcular.

### 3. Calcular

```
python calculo_jornada.py analisar --csv <arquivo.csv> \
  --jornada-diaria 8 --jornada-semanal 44
```

Ajuste `--jornada-diaria`/`--jornada-semanal` se o contrato do cliente for
diferente (ex.: 6h/dia, escala 12x36 — para 12x36 o critério diário de 8h não
se aplica; pergunte a jornada contratual antes de rodar).

### 4. Apresentar

- Tabela dia a dia: horas trabalhadas, maior pausa, HE do dia, observação.
- Resumo do mês: total de horas, HE por critério diário **e** semanal (mostre
  os dois — divergência entre eles costuma indicar banco de horas/acordo de
  compensação, que é uma questão jurídica para o advogado decidir, não para
  o script).
- Lista de violações de intervalo intra/interjornada, cada uma com o artigo
  da CLT.
- Dias com número ímpar de marcações → flag explícita para conferência manual.
- Sempre repita os avisos que o script devolve.

### 5. Alimentar o cálculo trabalhista (opcional)

Se o usuário quiser o valor em R$ das horas extras ou usar a média para a
rescisão:
- Horas extras avulsas → `calculo_trabalhista.py hora-extra --salario X --horas <total_horas_extras>`
- Média mensal para reflexo em 13º/férias na rescisão → rode este fluxo em
  cada um dos últimos 12 meses (Súmula 347/TST), tire a média das HE mensais
  e passe em `calculo_trabalhista.py rescisao --media-he <média>`. **Não**
  estime essa média a partir de 1 mês só — avise o usuário se ele só tiver um
  mês de cartão de ponto disponível.

## O que esta skill não faz

- Não decide se a jornada registrada bate com a realidade (isso é prova, não
  aritmética) — se o usuário disser que o cartão é "britânico"
  (pré-assinado/fraudado), essa é uma alegação a provar por outros meios
  (testemunhas, e-mails, etc.), o script só soma o que está escrito.
- Não aplica o adicional noturno em R$ — devolve `horas_noturnas_reduzidas`;
  use `calculo_trabalhista.py hora-extra` ou uma chamada dedicada para converter em valor.
- Não decide qual critério de HE (diário ou semanal) prevalece quando há
  banco de horas — reporta os dois e sinaliza a divergência.
