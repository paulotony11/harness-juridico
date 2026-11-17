-- Modelo de exemplo: confirma que o dbt grava no juridico.duckdb.
select * from (values
  (date '2026-01-01', 'Confraternização Universal'),
  (date '2026-04-21', 'Tiradentes'),
  (date '2026-09-07', 'Independência'),
  (date '2026-11-15', 'Proclamação da República')
) as t(data, feriado)
