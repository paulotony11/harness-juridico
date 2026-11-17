#!/usr/bin/env python3
"""Biblioteca e CLI para análise de jornada a partir de um CSV normalizado de
marcações de ponto — horas trabalhadas, horas extras, adicional noturno,
violações de intervalo intra/interjornada. Uso:
    python calculo_jornada.py gerar-modelo
    python calculo_jornada.py analisar --csv marcacoes.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

TWO_PLACES = Decimal("0.01")
JANELA_NOTURNA_INICIO = time(22, 0)  # art. 73 CLT
JANELA_NOTURNA_FIM = time(5, 0)
FATOR_HORA_NOTURNA_REDUZIDA = Decimal("8") / Decimal("7")  # 60min / 52min30s


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def horas(td: timedelta) -> Decimal:
    return Decimal(td.total_seconds()) / Decimal(3600)


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------

@dataclass
class DiaPonto:
    data: date
    marcacoes: list[time]
    observacao: str = ""


@dataclass
class ResultadoDia:
    data: date
    horas_trabalhadas: Decimal
    pausas: list[Decimal]
    horas_noturnas_reduzidas: Decimal
    marcacoes_impares: bool
    violacao_intrajornada: Optional[str]
    violacao_interjornada: Optional[str]
    observacao: str


# ---------------------------------------------------------------------------
# CSV de entrada
# ---------------------------------------------------------------------------

def ler_csv(caminho: str) -> list[DiaPonto]:
    dias: list[DiaPonto] = []
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        campos_esperados = {"data", "marcacoes", "observacao"}
        if not campos_esperados.issubset({c.strip() for c in (reader.fieldnames or [])}):
            raise ValueError(
                f"CSV precisa das colunas {sorted(campos_esperados)}; encontrado {reader.fieldnames}"
            )
        for row in reader:
            data_str = (row.get("data") or "").strip()
            if not data_str:
                continue
            dt = date.fromisoformat(data_str)
            marcacoes_str = (row.get("marcacoes") or "").strip()
            marcacoes = []
            if marcacoes_str:
                for token in marcacoes_str.split(";"):
                    token = token.strip()
                    if token:
                        marcacoes.append(datetime.strptime(token, "%H:%M").time())
            obs = (row.get("observacao") or "").strip()
            dias.append(DiaPonto(data=dt, marcacoes=marcacoes, observacao=obs))
    dias.sort(key=lambda x: x.data)
    return dias


# ---------------------------------------------------------------------------
# Cálculo por dia
# ---------------------------------------------------------------------------

def _pares_trabalho(dia: DiaPonto) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Casa marcações em pares (entrada, saída). Se a 'saída' tem hora-relógio
    menor ou igual à 'entrada', assume virada de turno (soma 1 dia)."""
    marcacoes_impares = len(dia.marcacoes) % 2 != 0
    pares = []
    for i in range(0, len(dia.marcacoes) - 1, 2):
        entrada_t, saida_t = dia.marcacoes[i], dia.marcacoes[i + 1]
        entrada_dt = datetime.combine(dia.data, entrada_t)
        saida_dt = datetime.combine(dia.data, saida_t)
        if saida_t <= entrada_t:
            saida_dt += timedelta(days=1)
        pares.append((entrada_dt, saida_dt))
    return pares, marcacoes_impares


def _overlap(a_ini: datetime, a_fim: datetime, b_ini: datetime, b_fim: datetime) -> timedelta:
    ini = max(a_ini, b_ini)
    fim = min(a_fim, b_fim)
    return max(fim - ini, timedelta(0))


def _horas_noturnas_no_intervalo(entrada: datetime, saida: datetime) -> Decimal:
    """Soma o tempo real do intervalo (entrada,saida) dentro de qualquer
    janela 22h-5h que ele toque, depois converte pela hora noturna reduzida."""
    total_real = timedelta(0)
    dia_cursor = entrada.date() - timedelta(days=1)
    while datetime.combine(dia_cursor, JANELA_NOTURNA_INICIO) < saida:
        janela_ini = datetime.combine(dia_cursor, JANELA_NOTURNA_INICIO)
        janela_fim = datetime.combine(dia_cursor + timedelta(days=1), JANELA_NOTURNA_FIM)
        total_real += _overlap(entrada, saida, janela_ini, janela_fim)
        dia_cursor += timedelta(days=1)
    return horas(total_real) * FATOR_HORA_NOTURNA_REDUZIDA


def _checar_intrajornada(horas_trabalhadas: Decimal, maior_pausa: Decimal) -> Optional[str]:
    """Art. 71 CLT: jornada > 6h exige intervalo mínimo de 1h; entre 4h e 6h,
    mínimo 15min. Intervalo suprimido/reduzido é só o período faltante,
    natureza indenizatória, com pelo menos 50% de acréscimo (art. 71 §4º,
    Lei 13.467/2017) — a MEDIDA do que falta fica no relatório para o
    calculo_trabalhista.valor_hora_extra aplicar o valor."""
    if horas_trabalhadas > 6 and maior_pausa < 1:
        faltante = money(Decimal(1) - maior_pausa)
        return f"intervalo intrajornada de {maior_pausa}h < 1h mínima (art. 71 CLT) — faltam {faltante}h"
    if 4 < horas_trabalhadas <= 6 and maior_pausa < Decimal("0.25"):
        faltante = money(Decimal("0.25") - maior_pausa)
        return f"intervalo intrajornada de {maior_pausa}h < 15min mínimos (art. 71 CLT) — faltam {faltante}h"
    return None


def _checar_interjornada(saida_anterior: Optional[datetime], entrada_atual: Optional[datetime]) -> Optional[str]:
    """Art. 66 CLT: mínimo 11h consecutivas entre duas jornadas."""
    if saida_anterior is None or entrada_atual is None:
        return None
    gap = horas(entrada_atual - saida_anterior)
    if gap < 11:
        return f"intervalo interjornada de {money(gap)}h < 11h mínimas (art. 66 CLT)"
    return None


def processar_dias(dias: list[DiaPonto]) -> list[ResultadoDia]:
    resultados: list[ResultadoDia] = []
    ultima_saida: Optional[datetime] = None
    for dia in dias:
        if not dia.marcacoes:
            resultados.append(
                ResultadoDia(
                    data=dia.data,
                    horas_trabalhadas=money(0),
                    pausas=[],
                    horas_noturnas_reduzidas=money(0),
                    marcacoes_impares=False,
                    violacao_intrajornada=None,
                    violacao_interjornada=None,
                    observacao=dia.observacao or "sem marcação",
                )
            )
            ultima_saida = None
            continue

        pares, impares = _pares_trabalho(dia)
        horas_trabalhadas = sum((horas(fim - ini) for ini, fim in pares), Decimal(0))
        pausas = [
            money(horas(pares[i + 1][0] - pares[i][1]))
            for i in range(len(pares) - 1)
            if pares[i + 1][0] > pares[i][1]
        ]
        horas_noturnas = sum((_horas_noturnas_no_intervalo(ini, fim) for ini, fim in pares), Decimal(0))
        maior_pausa = max(pausas) if pausas else money(0)

        primeira_entrada = pares[0][0] if pares else None
        resultados.append(
            ResultadoDia(
                data=dia.data,
                horas_trabalhadas=money(horas_trabalhadas),
                pausas=pausas,
                horas_noturnas_reduzidas=money(horas_noturnas),
                marcacoes_impares=impares,
                violacao_intrajornada=_checar_intrajornada(money(horas_trabalhadas), maior_pausa),
                violacao_interjornada=_checar_interjornada(ultima_saida, primeira_entrada),
                observacao=dia.observacao,
            )
        )
        ultima_saida = pares[-1][1] if pares else ultima_saida


    return resultados


# ---------------------------------------------------------------------------
# Resumo mensal
# ---------------------------------------------------------------------------

def resumo(
    resultados: list[ResultadoDia],
    jornada_diaria: Decimal = Decimal(8),
    jornada_semanal: Decimal = Decimal(44),
) -> dict:
    total_horas = sum((r.horas_trabalhadas for r in resultados), Decimal(0))
    total_noturnas = sum((r.horas_noturnas_reduzidas for r in resultados), Decimal(0))
    dias_com_marcacao = [r for r in resultados if r.horas_trabalhadas > 0]

    he_diaria_total = sum(
        (max(r.horas_trabalhadas - jornada_diaria, Decimal(0)) for r in dias_com_marcacao),
        Decimal(0),
    )

    semanas: dict[str, Decimal] = {}
    for r in dias_com_marcacao:
        chave = f"{r.data.isocalendar().year}-W{r.data.isocalendar().week:02d}"
        semanas[chave] = semanas.get(chave, Decimal(0)) + r.horas_trabalhadas
    he_semanal_total = sum((max(v - jornada_semanal, Decimal(0)) for v in semanas.values()), Decimal(0))

    violacoes_intra = [
        {"data": r.data.isoformat(), "detalhe": r.violacao_intrajornada}
        for r in resultados
        if r.violacao_intrajornada
    ]
    violacoes_inter = [
        {"data": r.data.isoformat(), "detalhe": r.violacao_interjornada}
        for r in resultados
        if r.violacao_interjornada
    ]
    dias_marcacao_impar = [r.data.isoformat() for r in resultados if r.marcacoes_impares]

    # total de HE do período coberto por este CSV — se o CSV cobre um mês
    # cheio, este número já é a "média mensal" para `rescisao --media-he`;
    # se cobre vários meses, divida por conta própria pelo nº de meses.
    media_he_mensal = money(he_diaria_total)

    return {
        "periodo": {
            "inicio": resultados[0].data.isoformat() if resultados else None,
            "fim": resultados[-1].data.isoformat() if resultados else None,
        },
        "total_horas_trabalhadas": str(money(total_horas)),
        "total_horas_extras_criterio_diario": str(money(he_diaria_total)),
        "total_horas_extras_criterio_semanal": str(money(he_semanal_total)),
        "total_horas_noturnas_reduzidas": str(money(total_noturnas)),
        "media_he_mensal_para_media_he": str(media_he_mensal),
        "violacoes_intervalo_intrajornada": violacoes_intra,
        "violacoes_intervalo_interjornada": violacoes_inter,
        "dias_com_numero_impar_de_marcacoes": dias_marcacao_impar,
        "avisos": [
            "HE por critério diário e semanal podem divergir por causa de banco de horas/acordo de compensação — reporte os dois e deixe o advogado decidir qual se aplica ao caso.",
            "Semana usada = ISO (segunda a domingo); se a escala da empresa usa outra semana de referência, ajuste antes de confiar no total semanal.",
            "Marcação ímpar em um dia indica falta de batida (esquecimento, ponto não registrado) — o dia foi computado só com os pares completos; confira manualmente.",
            "Este resumo não aplica valor em R$ — use `total_horas_extras_criterio_diario` (ou semanal) e `total_horas_noturnas_reduzidas` como entrada do calculo_trabalhista.py (hora-extra / --media-he).",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

MODELO_CSV = """data,marcacoes,observacao
2026-08-03,08:02;12:01;13:05;18:10,
2026-08-04,08:00;12:00;13:00;18:00;19:00;21:00,hora extra noturna autorizada
2026-08-05,,folga
2026-08-06,08:05;18:12,intervalo não registrado — confirmar com o cliente
"""


def cmd_gerar_modelo(_args: argparse.Namespace) -> None:
    print(MODELO_CSV)


def cmd_analisar(args: argparse.Namespace) -> None:
    dias = ler_csv(args.csv)
    if not dias:
        print(json.dumps({"erro": "CSV sem linhas de data válidas"}, ensure_ascii=False, indent=2))
        return
    resultados = processar_dias(dias)
    payload = {
        "dias": [
            {
                "data": r.data.isoformat(),
                "horas_trabalhadas": str(r.horas_trabalhadas),
                "pausas_horas": [str(p) for p in r.pausas],
                "horas_noturnas_reduzidas": str(r.horas_noturnas_reduzidas),
                "marcacoes_impares": r.marcacoes_impares,
                "violacao_intrajornada": r.violacao_intrajornada,
                "violacao_interjornada": r.violacao_interjornada,
                "observacao": r.observacao,
            }
            for r in resultados
        ],
        "resumo": resumo(resultados, Decimal(str(args.jornada_diaria)), Decimal(str(args.jornada_semanal))),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _selftest() -> None:
    dias = [
        DiaPonto(date(2026, 8, 3), [time(8, 2), time(12, 1), time(13, 5), time(18, 10)]),
        DiaPonto(date(2026, 8, 4), [time(22, 0), time(23, 0)]),  # 1h cheia dentro da janela noturna
        DiaPonto(date(2026, 8, 5), [], "folga"),
    ]
    resultados = processar_dias(dias)
    # 08:02-12:01 (3h59m) + 13:05-18:10 (5h05m) = 9h04m = 9.0667h -> 9.07
    assert resultados[0].horas_trabalhadas == money(Decimal("9.0667")), resultados[0].horas_trabalhadas
    assert resultados[1].horas_noturnas_reduzidas == money(FATOR_HORA_NOTURNA_REDUZIDA), resultados[1].horas_noturnas_reduzidas
    assert resultados[2].observacao == "folga"

    # intervalo intrajornada insuficiente: 8h trabalhadas com só 30min de pausa
    dia_intervalo_curto = DiaPonto(date(2026, 8, 6), [time(8, 0), time(12, 0), time(12, 30), time(16, 30)])
    r = processar_dias([dia_intervalo_curto])[0]
    assert r.violacao_intrajornada is not None

    # interjornada insuficiente: sai 23h, entra 8h do dia seguinte (9h de intervalo, <11h)
    dias_inter = [
        DiaPonto(date(2026, 8, 7), [time(14, 0), time(23, 0)]),
        DiaPonto(date(2026, 8, 8), [time(8, 0), time(12, 0)]),
    ]
    r2 = processar_dias(dias_inter)
    assert r2[1].violacao_interjornada is not None

    print("selftest OK")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Análise de jornada a partir de marcações de ponto")
    sub = p.add_subparsers(dest="comando", required=True)

    p_modelo = sub.add_parser("gerar-modelo", help="Imprime o CSV modelo de entrada")
    p_modelo.set_defaults(func=cmd_gerar_modelo)

    p_analisar = sub.add_parser("analisar", help="Analisa um CSV de marcações")
    p_analisar.add_argument("--csv", required=True)
    p_analisar.add_argument("--jornada-diaria", default="8")
    p_analisar.add_argument("--jornada-semanal", default="44")
    p_analisar.set_defaults(func=cmd_analisar)

    p.add_argument("--selftest", action="store_true")
    return p


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    if "--selftest" in argv:
        _selftest()
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
