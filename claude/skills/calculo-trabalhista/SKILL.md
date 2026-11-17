---
name: calculo-trabalhista
description: >
  Cálculo de verbas rescisórias, horas extras, aviso prévio e reflexos sob a
  CLT. Usa uma biblioteca Python determinística (calculo_trabalhista.py) para
  a aritmética — não calcula valores trabalhistas de cabeça. Use quando o
  usuário pedir "calcula a rescisão", "quanto fica de verbas rescisórias",
  "cálculo de horas extras", "aviso prévio proporcional", "quanto tenho que
  pagar/receber nessa demissão", ou informar dados de admissão/demissão/salário
  pedindo o valor.
argument-hint: "[dados da rescisão ou pergunta de cálculo]"
---

# /calculo-trabalhista

## Por que um script e não conta de cabeça

Cálculo trabalhista tem regra legal específica para cada parcela (Lei
12.506/2011, Lei 4.090/62, art. 484-A CLT, Lei 8.036/90 etc.) e depende de
contagem de datas (meses/anos completos, período aquisitivo de férias) onde
erro de um dia muda o resultado. Não estime esses números por conta própria —
sempre rode o script em `calculo_trabalhista.py` (mesma pasta deste SKILL.md)
e reporte exatamente o que ele devolve.

**Python:** use `python` (no Windows, `py -3.13` se `python` não estiver no PATH).

Antes do primeiro uso na sessão, rode `--selftest` uma vez para confirmar que
o script está íntegro:
```
python calculo_trabalhista.py --selftest
```

## Fluxo

### 1. Identifique o tipo de cálculo
- Rescisão completa → subcomando `rescisao`
- Só valor de hora extra → subcomando `hora-extra`
- Só aviso prévio proporcional → subcomando `aviso-previo`

### 2. Colete os dados — pergunte o que faltar, não presuma

Para `rescisao`, obrigatórios:
- Salário base (sem adicionais, salvo se o usuário já quiser incluir médias)
- Data de admissão e data de demissão (YYYY-MM-DD)
- Motivo: `sem_justa_causa` | `rescisao_indireta` | `pedido_demissao` | `justa_causa` | `acordo` (art. 484-A)
- Dias trabalhados no mês da rescisão (para saldo de salário)
- Saldo atual do FGTS **conforme extrato oficial** (FGTS Digital / app Caixa) — sem isso a multa de 40%/20% não pode ser calculada; se o usuário não tiver o número agora, calcule o resto e deixe essa linha em aberto, não invente o saldo.

Opcionais (pergunte só se parecer relevante ao caso):
- `--ferias-vencidas N` — períodos vencidos e não gozados/pagos
- `--aviso-previo indenizado|trabalhado|nao_se_aplica`
- `--media-he VALOR` — média mensal de horas extras **habituais** dos últimos 12 meses (Súmula 347/TST), para refletir em 13º e férias. Se o usuário mencionar horas extras habituais mas não tiver a média, ofereça calcular primeiro com o subcomando `hora-extra` mês a mês e depois tirar a média — não estime a média de cabeça.
- `--inicio-periodo-ferias YYYY-MM-DD` — só se o período aquisitivo de férias não seguir a admissão (ex.: já houve gozo intermediário com nova contagem)

### 3. Rode o script

```
python calculo_trabalhista.py rescisao \
  --salario 3000 --admissao 2023-01-10 --demissao 2026-08-27 \
  --motivo sem_justa_causa --dias-trabalhados-mes 27 --saldo-fgts 12000
```

O script devolve JSON com cada verba, o total bruto, uma nota sobre saque do
FGTS/seguro-desemprego, e uma lista de avisos — inclua os avisos na resposta,
não os omita.

### 4. Apresente o resultado

Formato: tabela com cada verba e valor, total em negrito, e logo abaixo os
avisos do script (sem reescrevê-los de forma que percam o sentido). Sempre
deixe explícito:

- **Valores são BRUTOS** — não incluem INSS/IRRF (a tabela muda todo ano por
  portaria; se o usuário pedir o líquido, pergunte se ele tem a tabela vigente
  ou pesquise a tabela oficial do ano corrente antes de aplicar — não use uma
  tabela de memória sem confirmar a vigência).
- O cálculo é uma **minuta para conferência do advogado responsável**, cruzando
  com CTPS, ficha financeira e o TRCT real.
- Se `--media-he` não foi informado mas o caso claramente tem horas extras
  habituais, avise que os reflexos em 13º/férias/FGTS **não foram** aplicados
  e ficaram subestimados.

## O que esta skill não faz

- Não calcula INSS/IRRF (tabelas mudam anualmente — peça a tabela vigente ou
  pesquise antes de aplicar; nunca aplique de memória sem confirmar a data).
- Não decide o motivo da rescisão nem qualifica fatos como justa causa —
  isso é análise jurídica, não aritmética. Pergunte ao usuário qual motivo
  aplicar, ou analise os fatos separadamente antes de rodar o cálculo.
- Não substitui a leitura da CTPS/ficha financeira real do caso.
