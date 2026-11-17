"""Detecção rápida (só regex + dígito verificador) de identificadores brasileiros.

Sem spaCy: roda em milissegundos, por isso é a base dos hooks. Não detecta nomes —
para isso use anonimizar.py (Presidio + spaCy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from validate_docbr import CNPJ, CPF

_CPF, _CNPJ = CPF(), CNPJ()


def cnj_valido(numero: str) -> bool:
    """Dígito verificador do número único CNJ (Res. CNJ 65/2008, módulo 97)."""
    d = re.sub(r"\D", "", numero)
    if len(d) != 20:
        return False
    return 98 - (int(d[:7] + d[9:] + "00") % 97) == int(d[7:9])


@dataclass(frozen=True)
class Achado:
    tipo: str
    inicio: int
    fim: int
    valor: str


# (tipo, regex, validador ou None)
PADROES = [
    ("BR_PROCESSO_CNJ", re.compile(r"(?<!\d)\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}(?!\d)"), cnj_valido),
    ("BR_CNPJ", re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"),
     lambda s: _CNPJ.validate(re.sub(r"\D", "", s))),
    ("BR_CPF", re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
     lambda s: _CPF.validate(re.sub(r"\D", "", s))),
    ("BR_OAB", re.compile(r"\bOAB\s*/?\s*[A-Z]{2}\s*(?:n[º°.]?\s*)?\d{1,3}(?:\.?\d{3})?(?:-?[A-Z])?\b"), None),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), None),
]


def detectar(texto: str, tipos: set[str] | None = None) -> list[Achado]:
    """Achados sem sobreposição, em ordem de posição."""
    brutos = []
    for tipo, rx, valida in PADROES:
        if tipos and tipo not in tipos:
            continue
        for m in rx.finditer(texto):
            if valida is None or valida(m.group()):
                brutos.append(Achado(tipo, m.start(), m.end(), m.group()))
    brutos.sort(key=lambda a: (a.inicio, -(a.fim - a.inicio)))
    out, fim = [], -1
    for a in brutos:
        if a.inicio >= fim:
            out.append(a)
            fim = a.fim
    return out


def mascarar_parcial(valor: str) -> str:
    """Mostra só o começo e o fim (para mensagens sem expor o dado inteiro)."""
    if "@" in valor:
        u, d = valor.split("@", 1)
        return f"{u[:1]}***@{d}"
    return valor[:3] + "***" + valor[-2:] if len(valor) > 6 else "***"
