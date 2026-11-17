---
name: segundo-cerebro
description: >
  Segundo cérebro jurídico do escritório: cofre Obsidian em <workspace>/cerebro com leis,
  precedentes, teses, estratégias, casos e órgãos ligados num grafo de conhecimento. Use quando o
  usuário pedir para registrar, salvar, anotar ou "guardar no cérebro" uma lei, súmula, tema,
  julgado, tese, estratégia, caso, aprendizado ou perfil de vara/juiz; quando perguntar "o que
  sabemos sobre X", "quais teses funcionam em Y", "que precedentes temos sobre Z"; ou ao encerrar
  um caso (atualizar resultado e placar das teses).
---

# Segundo cérebro jurídico

O cofre fica em `cerebro/` dentro do workspace jurídico (ao lado de `dados/` e `scripts/`).
São arquivos Markdown: leia e edite direto com as ferramentas de arquivo. O Obsidian mostra o
grafo e os painéis; você não precisa dele aberto.

Antes de tudo, leia `cerebro/01 Mapas/Guia do cérebro.md`: ele define os tipos, as pastas e as
regras de ligação. Esta skill resume o que importa para você.

## Ferramenta

```
python scripts/cerebro.py novo <tipo> "<Título>" [--area trabalhista]   # cria a partir do modelo
python scripts/cerebro.py verificar                                    # rode depois de editar
python scripts/cerebro.py grafo                                        # centros e ilhas
python scripts/cerebro.py indexar                                      # grafo -> parquet p/ DuckDB
```
Tipos: dispositivo, precedente, tese, estrategia, caso, orgao, pessoa, modelo-peca, doutrina,
diario, mapa. `novo` nunca sobrescreve: se a nota existe, atualize-a.

## Fluxo para registrar conhecimento

1. **Procure antes de criar.** Busque por título e por `aliases` (Grep em `cerebro/`). Duplicata
   quebra o grafo: prefira atualizar a nota existente.
2. **Crie com `cerebro.py novo`**, depois preencha as seções do modelo.
3. **Texto de lei e de precedente só da fonte oficial consultada agora** (planalto.gov.br, sites
   dos tribunais, DataJud, juscraper). Copie o texto, ponha o link em `fonte` e deixe
   `verificado: false`: quem marca `true` é o advogado, depois de conferir. Sem fonte, escreva
   `[VERIFICAR]`. Nunca reconstrua ementa ou número de súmula de memória.
4. **Ligue a nota** (é isso que forma o grafo), seguindo o Guia:
   - tese → dispositivos e precedentes que a sustentam, estratégia e mapa da área;
   - precedente → dispositivos que interpreta;
   - caso → `orgao` e lista `teses` nas propriedades (entre aspas: `"[[Nome]]"`), mais estratégia;
   - toda nota permanente → pelo menos um mapa em `01 Mapas/`.
   Use o nome exato do arquivo no `[[link]]` (ou um alias que a nota declara).
5. **Rode `cerebro.py verificar`** e corrija links quebrados e órfãs que você criou.

## Encerramento de caso

Quando o usuário informar a decisão final:
- no caso: `status: encerrado`, `resultado:` procedente | parcialmente-procedente | improcedente |
  acordo | extinto, e preencha "Aprendizados";
- em cada tese da lista `teses`: some 1 em `vitorias` (procedente/parcial) ou `derrotas`
  (improcedente), e atualize `atualizado_em`. Acordo e extinção não contam no placar;
- no órgão: acrescente em "Perfil decisório" o que esse resultado ensinou (fatos, não opinião
  sobre a pessoa do magistrado).

## Respondendo perguntas com o cérebro

- Leia a nota central e siga os links (e os backlinks: Grep por `[[Título`).
- Diga de onde veio cada afirmação (nota e fonte). Aponte o que está `verificado: false`.
- Aponte lacunas: tese sem precedente, precedente superado, caso sem tese ligada.
- Para números (êxito por tese, por vara), rode `cerebro.py indexar` e consulte os parquet com
  DuckDB (exemplos em `01 Mapas/Jurimetria e Dados.md`). Não conte de cabeça.

## LGPD — obrigatório

- Cliente só por código (`CLI-0001`). Nunca CPF, RG, endereço, dados de saúde ou de terceiros.
- Número CNJ do processo pode entrar no caso (é público), salvo segredo de justiça: aí não.
- `cerebro.py verificar` aponta CPF, CNPJ e e-mail no cofre. Se aparecer, remova.

## O que esta skill não faz

- Não substitui a conferência do advogado: `verificado: true` é decisão humana.
- Não calcula prazos nem verbas: use o MCP `juridico-brasil` e as skills de cálculo e registre o
  resultado no caso.
