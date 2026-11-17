#!/usr/bin/env python3
"""Biblioteca e CLI de cálculos trabalhistas (CLT) — verbas rescisórias, horas
extras e reflexos. Uso: python calculo_trabalhista.py <comando> --help
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

TWO_PLACES = Decimal("0.01")
DIVISOR_PADRAO = 220  # jornada 44h/semana (Súmula 431/TST usa 220 como divisor mensal)


def d(value) -> Decimal:
    return Decimal(str(value))


def money(value) -> Decimal:
    return d(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class Motivo(str, Enum):
    SEM_JUSTA_CAUSA = "sem_justa_causa"
    RESCISAO_INDIRETA = "rescisao_indireta"  # art. 483 CLT — mesmos efeitos de sem justa causa
    PEDIDO_DEMISSAO = "pedido_demissao"
    JUSTA_CAUSA = "justa_causa"
    ACORDO = "acordo"  # art. 484-A CLT (Lei 13.467/2017)


# ---------------------------------------------------------------------------
# Datas / contagem de meses e anos (Lei 4.090/62 art. 1º §único; CLT art. 146 §ún.:
# fração igual ou superior a 15 dias no mês conta como mês completo)
# ---------------------------------------------------------------------------

def _add_months(dt: date, n: int) -> date:
    total = dt.month - 1 + n
    ano = dt.year + total // 12
    mes = total % 12 + 1
    dia = min(dt.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def meses_completos(inicio: date, fim: date) -> int:
    """Meses completos entre duas datas. Fração >=15 dias corridos no mês
    incompleto conta como mês cheio (Lei 4.090/62, art. 1º, §único)."""
    if fim < inicio:
        raise ValueError("data final anterior à data inicial")
    meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    if fim.day < inicio.day:
        meses -= 1
    ultimo_mes_completo = _add_months(inicio, meses)
    dias_fracao = (fim - ultimo_mes_completo).days
    if dias_fracao >= 15:
        meses += 1
    return max(meses, 0)


def anos_completos(inicio: date, fim: date) -> int:
    """Anos completos por aniversário exato (não usa a regra de arredondamento
    de 15 dias — essa regra vale só para o mês incompleto dentro de um período,
    não para fechar um ano inteiro antes da hora)."""
    anos = fim.year - inicio.year
    try:
        aniversario = inicio.replace(year=inicio.year + anos)
    except ValueError:
        aniversario = date(inicio.year + anos, inicio.month, 28)  # 29/fev em ano não bissexto
    if aniversario > fim:
        anos -= 1
    return max(anos, 0)


# ---------------------------------------------------------------------------
# Jornada: hora extra, adicional noturno, DSR sobre variáveis habituais
# ---------------------------------------------------------------------------

def salario_hora(salario: Decimal, divisor: int = DIVISOR_PADRAO) -> Decimal:
    return d(salario) / d(divisor)


def valor_hora_extra(
    salario: Decimal,
    horas: Decimal,
    percentual: Decimal = Decimal("50"),
    divisor: int = DIVISOR_PADRAO,
) -> Decimal:
    """Adicional mínimo 50% em dia útil (art. 7º, XVI, CF/88); 100% em domingo/
    feriado não compensado (Súmula 146/TST) — informe `percentual` conforme o caso."""
    hora = salario_hora(salario, divisor)
    return money(hora * (1 + d(percentual) / 100) * d(horas))


def valor_adicional_noturno(
    salario: Decimal,
    horas_noturnas_reduzidas: Decimal,
    percentual: Decimal = Decimal("20"),
    divisor: int = DIVISOR_PADRAO,
) -> Decimal:
    """Art. 73 CLT: mínimo 20% sobre a hora diurna, para trabalho entre 22h-5h.
    `horas_noturnas_reduzidas` já deve estar na hora noturna reduzida
    (60min = 52min30s: multiplique horas-relógio por 60/52.5 antes de chamar)."""
    hora = salario_hora(salario, divisor)
    return money(hora * (d(percentual) / 100) * d(horas_noturnas_reduzidas))


def dsr_sobre_variavel(
    valor_variavel_mes: Decimal, dias_uteis_mes: int, dias_repouso_mes: int
) -> Decimal:
    """Reflexo de horas extras/comissões habituais no DSR (Lei 605/49 art. 7º;
    Súmula 172/TST). dias_repouso_mes = domingos + feriados no mês."""
    if dias_uteis_mes <= 0:
        raise ValueError("dias_uteis_mes deve ser > 0")
    return money((d(valor_variavel_mes) / d(dias_uteis_mes)) * d(dias_repouso_mes))


# ---------------------------------------------------------------------------
# Verbas rescisórias
# ---------------------------------------------------------------------------

def saldo_salario(salario: Decimal, dias_trabalhados_mes: int, dias_no_mes: int = 30) -> Decimal:
    return money(d(salario) / d(dias_no_mes) * d(dias_trabalhados_mes))


def decimo_terceiro_proporcional(salario_base: Decimal, meses: int) -> Decimal:
    return money(d(salario_base) / 12 * meses)


def ferias_proporcionais(salario_base: Decimal, meses: int) -> Decimal:
    """Férias proporcionais + 1/3 constitucional (art. 7º, XVII, CF/88)."""
    base = d(salario_base) / 12 * meses
    return money(base * d("1.3333333333"))


def ferias_vencidas(salario_base: Decimal, periodos: int = 1) -> Decimal:
    """Períodos aquisitivos completos, vencidos e não gozados/pagos, + 1/3."""
    return money(d(salario_base) * d("1.3333333333") * periodos)


def aviso_previo_dias(anos_de_servico_completos: int) -> int:
    """Lei 12.506/2011: 30 dias + 3 por ano completo de serviço, limite 90."""
    return min(30 + 3 * max(anos_de_servico_completos, 0), 90)


def aviso_previo_valor(salario: Decimal, dias: int) -> Decimal:
    return money(d(salario) / 30 * dias)


def fgts_mensal(salario: Decimal) -> Decimal:
    return money(d(salario) * Decimal("0.08"))


def multa_fgts(saldo_fgts_total: Decimal, motivo: Motivo) -> Decimal:
    """40% em dispensa sem justa causa/rescisão indireta (art. 18 §1º Lei
    8.036/90); 20% em acordo (art. 484-A CLT); 0% em pedido de demissão/justa causa."""
    if motivo in (Motivo.SEM_JUSTA_CAUSA, Motivo.RESCISAO_INDIRETA):
        return money(d(saldo_fgts_total) * Decimal("0.40"))
    if motivo == Motivo.ACORDO:
        return money(d(saldo_fgts_total) * Decimal("0.20"))
    return money(0)


# ---------------------------------------------------------------------------
# Agregador — rescisão completa
# ---------------------------------------------------------------------------

@dataclass
class RescisaoInput:
    salario: Decimal
    data_admissao: date
    data_demissao: date
    motivo: Motivo
    dias_trabalhados_mes_rescisao: int
    saldo_fgts_atual: Decimal = d(0)  # saldo informado pelo extrato do FGTS (obrigatório p/ multa)
    periodos_ferias_vencidas: int = 0
    aviso_previo_tipo: str = "indenizado"  # "indenizado" | "trabalhado" | "nao_se_aplica"
    media_he_habituais_mensal: Decimal = d(0)  # média de HE (já com DSR) para reflexo em 13º/férias
    inicio_periodo_aquisitivo_ferias: Optional[date] = None


def calcular_rescisao(inp: RescisaoInput) -> dict:
    meses_ano_corrente_13 = meses_completos(
        max(inp.data_admissao, date(inp.data_demissao.year, 1, 1)), inp.data_demissao
    )
    anos_de_casa = anos_completos(inp.data_admissao, inp.data_demissao)
    inicio_periodo_ferias = inp.inicio_periodo_aquisitivo_ferias or _add_months(
        inp.data_admissao, anos_de_casa * 12
    )  # início do período aquisitivo ATUAL (último aniversário contratual completo)
    meses_periodo_ferias = meses_completos(inicio_periodo_ferias, inp.data_demissao)

    salario_base_13_ferias = d(inp.salario) + d(inp.media_he_habituais_mensal)

    itens: dict[str, Decimal] = {}
    itens["saldo_de_salario"] = saldo_salario(inp.salario, inp.dias_trabalhados_mes_rescisao)

    dias_aviso = aviso_previo_dias(anos_de_casa)
    if inp.motivo in (Motivo.SEM_JUSTA_CAUSA, Motivo.RESCISAO_INDIRETA) and inp.aviso_previo_tipo == "indenizado":
        itens["aviso_previo_indenizado"] = aviso_previo_valor(inp.salario, dias_aviso)
    elif inp.motivo == Motivo.ACORDO and inp.aviso_previo_tipo == "indenizado":
        # art. 484-A CLT: aviso prévio indenizado pago pela metade no acordo
        itens["aviso_previo_indenizado_50pct"] = money(aviso_previo_valor(inp.salario, dias_aviso) / 2)

    if inp.motivo != Motivo.JUSTA_CAUSA:
        itens["decimo_terceiro_proporcional"] = decimo_terceiro_proporcional(
            salario_base_13_ferias, meses_ano_corrente_13
        )
        itens["ferias_proporcionais_mais_1_3"] = ferias_proporcionais(
            salario_base_13_ferias, meses_periodo_ferias
        )
    if inp.periodos_ferias_vencidas:
        itens["ferias_vencidas_mais_1_3"] = ferias_vencidas(
            salario_base_13_ferias, inp.periodos_ferias_vencidas
        )

    if inp.motivo == Motivo.ACORDO:
        itens["multa_fgts_20pct"] = multa_fgts(inp.saldo_fgts_atual, inp.motivo)
        nota_saque = "até 80% do saldo do FGTS pode ser sacado (art. 484-A, II, CLT); sem direito a seguro-desemprego"
    elif inp.motivo in (Motivo.SEM_JUSTA_CAUSA, Motivo.RESCISAO_INDIRETA):
        itens["multa_fgts_40pct"] = multa_fgts(inp.saldo_fgts_atual, inp.motivo)
        nota_saque = "saque integral do FGTS + seguro-desemprego (se preenchidos os requisitos)"
    else:
        nota_saque = "sem multa de FGTS; saque do FGTS não se aplica (exceto hipóteses legais específicas)"

    total = sum(itens.values(), money(0))

    return {
        "motivo": inp.motivo.value,
        "meses_13_ano_corrente": meses_ano_corrente_13,
        "meses_periodo_aquisitivo_ferias": meses_periodo_ferias,
        "dias_aviso_previo_proporcional": dias_aviso,
        "itens": {k: str(v) for k, v in itens.items()},
        "total_bruto": str(money(total)),
        "nota_fgts": nota_saque,
        "avisos": [
            "Valores BRUTOS — não incluem descontos de INSS/IRRF nem consignados.",
            "Confirme saldo do FGTS pelo extrato oficial (FGTS Digital / app Caixa) antes de usar para a multa.",
            "Se houve horas extras habituais, a média informada deve refletir os últimos 12 meses (Súmula 347/TST) — confira com folhas de pagamento reais.",
            "Minuta para revisão do advogado responsável — não substitui conferência com a CTPS, ficha financeira e o TRCT.",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _print_result(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_rescisao(args: argparse.Namespace) -> None:
    inp = RescisaoInput(
        salario=d(args.salario),
        data_admissao=_parse_date(args.admissao),
        data_demissao=_parse_date(args.demissao),
        motivo=Motivo(args.motivo),
        dias_trabalhados_mes_rescisao=args.dias_trabalhados_mes,
        saldo_fgts_atual=d(args.saldo_fgts or 0),
        periodos_ferias_vencidas=args.ferias_vencidas,
        aviso_previo_tipo=args.aviso_previo,
        media_he_habituais_mensal=d(args.media_he or 0),
        inicio_periodo_aquisitivo_ferias=_parse_date(args.inicio_periodo_ferias)
        if args.inicio_periodo_ferias
        else None,
    )
    _print_result(calcular_rescisao(inp))


def cmd_hora_extra(args: argparse.Namespace) -> None:
    valor = valor_hora_extra(d(args.salario), d(args.horas), d(args.percentual), args.divisor)
    _print_result({"valor_hora_extra_total": str(valor)})


def cmd_aviso_previo(args: argparse.Namespace) -> None:
    anos = anos_completos(_parse_date(args.admissao), _parse_date(args.demissao))
    dias = aviso_previo_dias(anos)
    valor = aviso_previo_valor(d(args.salario), dias)
    _print_result({"anos_completos": anos, "dias_aviso_previo": dias, "valor": str(valor)})


def _selftest() -> None:
    assert salario_hora(d("3000")) == d("3000") / 220
    assert valor_hora_extra(d("2200"), d("10"), d("50")) == money(d("10") * d("10") * d("1.5"))
    assert aviso_previo_dias(0) == 30
    assert aviso_previo_dias(1) == 33
    assert aviso_previo_dias(20) == 90
    assert aviso_previo_dias(25) == 90  # limite de 90 dias
    assert meses_completos(date(2023, 1, 10), date(2026, 8, 27)) == 44  # aniversário dia 10; sobram 17 dias (>=15) -> arredonda
    assert meses_completos(date(2023, 1, 20), date(2026, 8, 27)) == 43  # aniversário dia 20; sobram 7 dias (<15) -> não arredonda
    assert meses_completos(date(2023, 1, 20), date(2026, 8, 10)) == 43  # aniversário dia 20; mês incompleto tem 21 dias (>=15) -> arredonda
    assert anos_completos(date(2023, 1, 10), date(2026, 8, 27)) == 3  # 3 anos completos; o 4º só fecha em 2027-01-10
    assert anos_completos(date(2023, 1, 10), date(2023, 1, 9)) == 0
    assert anos_completos(date(2023, 1, 10), date(2023, 1, 10)) == 0
    assert anos_completos(date(2023, 1, 10), date(2024, 1, 10)) == 1
    assert multa_fgts(d("10000"), Motivo.SEM_JUSTA_CAUSA) == d("4000.00")
    assert multa_fgts(d("10000"), Motivo.ACORDO) == d("2000.00")
    assert multa_fgts(d("10000"), Motivo.PEDIDO_DEMISSAO) == d("0")
    print("selftest OK")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cálculos trabalhistas (CLT)")
    sub = p.add_subparsers(dest="comando", required=True)

    p_rescisao = sub.add_parser("rescisao", help="Verbas rescisórias completas")
    p_rescisao.add_argument("--salario", required=True)
    p_rescisao.add_argument("--admissao", required=True, help="YYYY-MM-DD")
    p_rescisao.add_argument("--demissao", required=True, help="YYYY-MM-DD")
    p_rescisao.add_argument("--motivo", required=True, choices=[m.value for m in Motivo])
    p_rescisao.add_argument("--dias-trabalhados-mes", type=int, required=True)
    p_rescisao.add_argument("--saldo-fgts", default="0")
    p_rescisao.add_argument("--ferias-vencidas", type=int, default=0, help="nº de períodos vencidos não gozados")
    p_rescisao.add_argument("--aviso-previo", choices=["indenizado", "trabalhado", "nao_se_aplica"], default="indenizado")
    p_rescisao.add_argument("--media-he", default="0", help="média mensal de HE habituais (já com DSR) p/ reflexo em 13º/férias")
    p_rescisao.add_argument("--inicio-periodo-ferias", default=None, help="YYYY-MM-DD, se != data de admissão")
    p_rescisao.set_defaults(func=cmd_rescisao)

    p_he = sub.add_parser("hora-extra", help="Valor de horas extras")
    p_he.add_argument("--salario", required=True)
    p_he.add_argument("--horas", required=True)
    p_he.add_argument("--percentual", default="50")
    p_he.add_argument("--divisor", type=int, default=DIVISOR_PADRAO)
    p_he.set_defaults(func=cmd_hora_extra)

    p_av = sub.add_parser("aviso-previo", help="Dias e valor do aviso prévio proporcional")
    p_av.add_argument("--salario", required=True)
    p_av.add_argument("--admissao", required=True)
    p_av.add_argument("--demissao", required=True)
    p_av.set_defaults(func=cmd_aviso_previo)

    p.add_argument("--selftest", action="store_true", help="roda verificações internas e sai")
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
