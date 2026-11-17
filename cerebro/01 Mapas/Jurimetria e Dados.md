---
tipo: mapa
area: dados
---
# Jurimetria e Dados

O cérebro também é uma base de dados. `python scripts/cerebro.py indexar` grava em `dados/tratado/`:

- `cerebro_notas.parquet`: uma linha por nota, com tipo, área, status, resultado e órgão
- `cerebro_links.parquet`: uma linha por ligação (origem → destino)

Consultas pelo MCP `duckdb-juridico` (somente leitura) ou em notebook:

```sql
-- Êxito por tese em casos encerrados (cada par caso→tese conta uma vez)
with l as (select distinct origem, destino from 'dados/tratado/cerebro_links.parquet'),
     n as (select * from 'dados/tratado/cerebro_notas.parquet')
select l.destino as tese,
       count(*) filter (where c.resultado in ('procedente','parcialmente-procedente')) as vitorias,
       count(*) filter (where c.resultado = 'improcedente') as derrotas
from l
join n c on c.titulo = l.origem  and c.tipo = 'caso' and c.status = 'encerrado'
join n t on t.titulo = l.destino and t.tipo = 'tese'
group by 1 order by vitorias desc;

-- Êxito por tese e por órgão
with l as (select distinct origem, destino from 'dados/tratado/cerebro_links.parquet'),
     n as (select * from 'dados/tratado/cerebro_notas.parquet')
select c.orgao, l.destino as tese, count(*) as casos,
       count(*) filter (where c.resultado in ('procedente','parcialmente-procedente')) as vitorias
from l
join n c on c.titulo = l.origem  and c.tipo = 'caso' and c.status = 'encerrado'
join n t on t.titulo = l.destino and t.tipo = 'tese'
group by 1, 2 order by 1, vitorias desc;

-- Notas mais conectadas (centros do grafo)
select destino, count(distinct origem) as citada_por
from 'dados/tratado/cerebro_links.parquet'
where resolvido and destino not like '%.base'
group by 1 order by 2 desc limit 15;
```

- Dados processuais ao vivo: MCP `juridico-brasil` (DataJud).
- Jurisprudência em lote: biblioteca `juscraper`.
