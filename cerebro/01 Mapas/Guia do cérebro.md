---
tipo: mapa
---
# Guia do cérebro

## Tipos de nota
| Tipo | Pasta | Uma nota por… | Exemplo de nome |
|---|---|---|---|
| dispositivo | 02 Legislação | artigo (com parágrafos) | `CLT art. 71` |
| precedente | 03 Precedentes | súmula, tema, OJ ou julgado | `Súmula 338 TST` |
| tese | 04 Teses | argumento reutilizável | `Cartão de ponto britânico inverte o ônus da prova` |
| estrategia | 05 Estratégias | tipo de ação ou situação | `Reclamação trabalhista — horas extras` |
| caso | 06 Casos | processo ou consulta | `CASO-2026-001` |
| orgao / pessoa | 07 Órgãos e pessoas | vara, tribunal, perito, parte litigante | `1ª Vara do Trabalho de Exemplo` |
| modelo-peca | 08 Modelos de peças | modelo de peça | `Petição inicial trabalhista` |
| doutrina | 09 Doutrina e estudos | obra ou artigo | — |
| diario | 10 Diário | dia | `2026-11-17` |

## Regras de ligação (é isso que forma o grafo)
1. Toda tese liga aos **dispositivos** e **precedentes** que a sustentam.
2. Todo caso lista as **teses** usadas (propriedade `teses`) e o **órgão** (propriedade `orgao`).
3. Todo precedente liga aos dispositivos que interpreta.
4. Toda nota permanente liga a pelo menos um **mapa** de área.
5. Encerrou um caso? Atualize `resultado` e some 1 em `vitorias` ou `derrotas` de cada tese usada.

## Regras de qualidade
- Texto de lei e de precedente vem **copiado da fonte oficial**, com o link em `fonte`. Depois de conferir, marque `verificado: true`.
- Sem fonte, escreva `[VERIFICAR]`. Nunca invente número de súmula, tema ou julgado.
- Precedente superado não se apaga: mude `situacao` e explique em Observações.

## LGPD
- Cliente só por código (`CLI-0001`). Nada de CPF, endereço, saúde ou dados de terceiros.
- O cofre fica só neste computador. Não sincronize com nuvem sem criptografia.

## Com o Claude
Peça em linguagem natural, por exemplo:
- "Registre no cérebro a Súmula 85 do TST e ligue às teses de compensação de jornada."
- "Atualize o CASO-2026-001 com a sentença de hoje e some o resultado nas teses."
- "O que o cérebro sabe sobre intervalo intrajornada? Aponte lacunas."
- "Quais teses têm melhor êxito na 1ª Vara do Trabalho de Exemplo?"

Ferramentas: `python scripts/cerebro.py novo|verificar|indexar|grafo` (na pasta do workspace).
