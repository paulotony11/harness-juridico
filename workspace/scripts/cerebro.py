"""Ferramentas do segundo cérebro jurídico (cofre Obsidian em <workspace>/cerebro).

  python scripts/cerebro.py novo tese "Título da tese" [--area trabalhista]
  python scripts/cerebro.py verificar        # links quebrados, órfãs, propriedades, CPF/e-mail no cofre
  python scripts/cerebro.py indexar          # grafo -> dados/tratado/cerebro_{notas,links}.parquet
  python scripts/cerebro.py grafo            # centros, órfãs e resumo por tipo
  python scripts/cerebro.py --selftest

Nada aqui bloqueia trabalho: os comandos só leem o cofre (exceto `novo`, que cria uma nota nova
e nunca sobrescreve) e sempre terminam com código 0, exceto erro de uso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
COFRE = WORKSPACE / "cerebro"
IGNORAR = {"_modelos", "_painéis", "_anexos", ".obsidian", ".trash"}

PASTA_DO_TIPO = {
    "dispositivo": "02 Legislação", "precedente": "03 Precedentes", "tese": "04 Teses",
    "estrategia": "05 Estratégias", "caso": "06 Casos", "orgao": "07 Órgãos e pessoas",
    "pessoa": "07 Órgãos e pessoas", "modelo-peca": "08 Modelos de peças",
    "doutrina": "09 Doutrina e estudos", "diario": "10 Diário", "mapa": "01 Mapas",
}
OBRIGATORIAS = {
    "dispositivo": ["norma", "artigo", "fonte"],
    "precedente": ["tribunal", "especie", "fonte"],
    "tese": ["area", "status"],
    "caso": ["codigo", "status", "area"],
}
WIKILINK = re.compile(r"(!?)\[\[([^\[\]|#^]+)(?:[#^][^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")


@dataclass
class Nota:
    caminho: Path
    titulo: str
    props: dict
    corpo: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (destino, via)


def _frontmatter(texto: str) -> tuple[dict, str]:
    if not texto.startswith("---"):
        return {}, texto
    partes = texto.split("---", 2)
    if len(partes) < 3:
        return {}, texto
    import yaml
    try:
        props = yaml.safe_load(partes[1]) or {}
    except yaml.YAMLError:
        props = {"_erro_yaml": True}
    return (props if isinstance(props, dict) else {}), partes[2]


def _links_em(valor) -> list[str]:
    if isinstance(valor, str):
        return [m.group(2).strip() for m in WIKILINK.finditer(valor)]
    if isinstance(valor, list):
        return [x for v in valor for x in _links_em(v)]
    if isinstance(valor, dict):
        return [x for v in valor.values() for x in _links_em(v)]
    return []


def carregar(cofre: Path = COFRE) -> list[Nota]:
    notas = []
    for p in sorted(cofre.rglob("*.md")):
        rel = p.relative_to(cofre)
        if rel.parts and rel.parts[0] in IGNORAR:
            continue
        props, corpo = _frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        n = Nota(p, p.stem, props, corpo)
        n.links = [(m.group(2).strip(), "embed" if m.group(1) else "corpo") for m in WIKILINK.finditer(corpo)]
        n.links += [(d, "propriedade") for d in _links_em(props)]
        notas.append(n)
    return notas


def _resolvedor(cofre: Path, notas: list[Nota]):
    """nome/alias/caminho (minúsculas) -> título; arquivos não-md existentes também resolvem."""
    idx = {}
    for n in notas:
        idx[n.titulo.lower()] = n.titulo
        idx[n.caminho.relative_to(cofre).with_suffix("").as_posix().lower()] = n.titulo
        for a in n.props.get("aliases") or []:
            if isinstance(a, str):
                idx[a.lower()] = n.titulo
    outros = {p.name.lower() for p in cofre.rglob("*") if p.is_file() and p.suffix != ".md"}

    def resolver(destino: str) -> str | None:
        d = destino.strip().lower()
        if d in idx:
            return idx[d]
        if d in outros or Path(d).name in outros:
            return destino
        return idx.get(d.removesuffix(".md"))

    return resolver


# ---------------------------------------------------------------- comandos
def cmd_novo(tipo: str, titulo: str, area: str | None, cofre: Path = COFRE) -> Path:
    if tipo not in PASTA_DO_TIPO:
        raise SystemExit(f"tipo inválido: {tipo}. Use: {', '.join(PASTA_DO_TIPO)}")
    if re.search(r'[\\/:*?"<>|#^\[\]]', titulo):
        raise SystemExit('o título não pode ter \\ / : * ? " < > | # ^ [ ]')
    modelo = cofre / "_modelos" / f"{tipo}.md"
    texto = modelo.read_text(encoding="utf-8") if modelo.exists() else f"---\ntipo: {tipo}\n---\n# {{{{title}}}}\n"
    hoje = date.today().isoformat()
    texto = (texto.replace("{{title}}", titulo).replace("{{date}}", hoje)
             .replace("{{date:YYYY-MM-DD}}", hoje).replace("{{time}}", ""))
    if area:
        texto = re.sub(r"^area:.*$", f"area: {area}", texto, count=1, flags=re.M)
    destino = cofre / PASTA_DO_TIPO[tipo] / f"{titulo}.md"
    if destino.exists():
        raise SystemExit(f"já existe: {destino.relative_to(cofre)} (abra e atualize em vez de duplicar)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(f"criada: {destino.relative_to(cofre).as_posix()}")
    return destino


def cmd_verificar(cofre: Path = COFRE) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import pii_br

    notas = carregar(cofre)
    resolver = _resolvedor(cofre, notas)
    quebrados, sem_tipo, faltando, a_verificar, pii, erros_yaml = [], [], [], [], [], []
    entrada = Counter()
    for n in notas:
        rel = n.caminho.relative_to(cofre).as_posix()
        if n.props.get("_erro_yaml"):
            erros_yaml.append(rel)
        tipo = n.props.get("tipo")
        if not tipo:
            sem_tipo.append(rel)
        for campo in OBRIGATORIAS.get(tipo, []):
            if not n.props.get(campo):
                faltando.append(f"{rel}: falta `{campo}`")
        if tipo in ("dispositivo", "precedente", "tese") and n.props.get("verificado") is not True:
            a_verificar.append(rel)
        for destino, _ in n.links:
            alvo = resolver(destino)
            if alvo is None:
                quebrados.append(f"{rel} → [[{destino}]]")
            else:
                entrada[alvo] += 1
        achados = [a for a in pii_br.detectar(n.corpo + json.dumps(n.props, ensure_ascii=False, default=str))
                   if a.tipo in ("BR_CPF", "BR_CNPJ", "EMAIL")]
        if achados:
            pii.append(f"{rel}: " + ", ".join(f"{a.tipo} {pii_br.mascarar_parcial(a.valor)}" for a in achados[:3]))
    orfas = [n.caminho.relative_to(cofre).as_posix() for n in notas
             if not n.links and entrada[n.titulo] == 0 and n.props.get("tipo") != "diario"]
    conflitos = conflitos_sincronizacao(cofre)

    def bloco(titulo, itens, dica=""):
        print(f"\n{titulo}: {len(itens)}" + (f"  ({dica})" if dica and itens else ""))
        for i in itens[:30]:
            print(f"  - {i}")
        if len(itens) > 30:
            print(f"  … e mais {len(itens) - 30}")

    print(f"Cofre: {cofre}  ·  {len(notas)} notas")
    bloco("Links quebrados", quebrados, "crie a nota ou corrija o nome")
    bloco("Notas sem `tipo`", sem_tipo)
    bloco("Propriedades obrigatórias faltando", faltando)
    bloco("Órfãs (sem ligação nenhuma)", orfas, "ligue a um mapa ou a uma tese")
    bloco("Lei/precedente/tese ainda não conferidos (verificado != true)", a_verificar,
          "confira na fonte oficial e marque verificado: true")
    bloco("LGPD: CPF, CNPJ ou e-mail dentro do cofre", pii, "troque por código do cliente")
    bloco("Cópias de conflito do OneDrive", conflitos,
          "compare com a original, junte o conteúdo e apague a cópia")
    if erros_yaml:
        bloco("YAML inválido no cabeçalho", erros_yaml)
    return {"quebrados": quebrados, "orfas": orfas, "pii": pii, "a_verificar": a_verificar,
            "sem_tipo": sem_tipo, "faltando": faltando, "conflitos": conflitos}


_NOME_PC = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,14}(?:-\d+)?$")  # nome NetBIOS do PC (+ -2, -3…)


def conflitos_sincronizacao(cofre: Path = COFRE) -> list[str]:
    """OneDrive salva edições simultâneas como 'Nota-NOMEDOPC.md' ao lado de 'Nota.md'.

    O nome do PC pode ter hífen (DESKTOP-AB12CD), então testa cada hífen como ponto de corte e
    só aponta quando a original existe ao lado.
    """
    achados = []
    for p in sorted(cofre.rglob("*")):
        if not p.is_file() or ".trash" in p.parts:
            continue
        stem = p.stem
        for i, ch in enumerate(stem):
            if ch == "-" and i > 0 and _NOME_PC.match(stem[i + 1:]):
                original = p.with_name(stem[:i] + p.suffix)
                if original.exists():
                    achados.append(f"{p.relative_to(cofre).as_posix()}  (original: {original.name})")
                    break
    return achados


def cmd_indexar(cofre: Path = COFRE, saida: Path | None = None) -> tuple[Path, Path]:
    import polars as pl

    saida = saida or WORKSPACE / "dados" / "tratado"
    saida.mkdir(parents=True, exist_ok=True)
    notas = carregar(cofre)
    resolver = _resolvedor(cofre, notas)

    def texto(v):
        if v is None:
            return None
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

    linhas = []
    for n in notas:
        p = n.props
        orgao = _links_em(p.get("orgao"))
        linhas.append({
            "titulo": n.titulo,
            "caminho": n.caminho.relative_to(cofre).as_posix(),
            "pasta": n.caminho.parent.relative_to(cofre).as_posix(),
            "tipo": texto(p.get("tipo")), "area": texto(p.get("area")), "status": texto(p.get("status")),
            "resultado": texto(p.get("resultado")), "orgao": orgao[0] if orgao else texto(p.get("orgao")),
            "tribunal": texto(p.get("tribunal")), "situacao": texto(p.get("situacao")),
            "verificado": bool(p.get("verificado")) if "verificado" in p else None,
            "vitorias": p.get("vitorias") if isinstance(p.get("vitorias"), int) else None,
            "derrotas": p.get("derrotas") if isinstance(p.get("derrotas"), int) else None,
            "proximo_prazo": texto(p.get("proximo_prazo")),
            "atualizado_em": texto(p.get("atualizado_em")),
            "palavras": len(n.corpo.split()),
            "propriedades_json": json.dumps(p, ensure_ascii=False, default=str),
        })
    links = []
    for n in notas:
        for destino, via in n.links:
            alvo = resolver(destino)
            links.append({"origem": n.titulo, "destino": alvo or destino.strip(), "via": via,
                          "resolvido": alvo is not None})
    f_notas, f_links = saida / "cerebro_notas.parquet", saida / "cerebro_links.parquet"
    pl.DataFrame(linhas, infer_schema_length=None).write_parquet(f_notas)
    pl.DataFrame(links, schema={"origem": pl.Utf8, "destino": pl.Utf8, "via": pl.Utf8,
                                "resolvido": pl.Boolean}).write_parquet(f_links)
    print(f"{len(linhas)} notas -> {f_notas}")
    print(f"{len(links)} ligações -> {f_links}")
    print("Consulte com DuckDB (ou pelo MCP duckdb-juridico):")
    print(f"  select * from '{f_links.as_posix()}' limit 10;")
    return f_notas, f_links


def cmd_grafo(cofre: Path = COFRE) -> None:
    notas = carregar(cofre)
    resolver = _resolvedor(cofre, notas)
    entrada, saida_, vizinhos = Counter(), Counter(), defaultdict(set)
    for n in notas:
        for destino, _ in n.links:
            alvo = resolver(destino)
            if alvo and alvo != n.titulo and not alvo.lower().endswith((".base", ".canvas")):
                entrada[alvo] += 1
                saida_[n.titulo] += 1
                vizinhos[n.titulo].add(alvo)
                vizinhos[alvo].add(n.titulo)
    por_tipo = Counter(n.props.get("tipo") or "(sem tipo)" for n in notas)
    print(f"{len(notas)} notas, {sum(saida_.values())} ligações")
    print("Por tipo: " + ", ".join(f"{t}={q}" for t, q in por_tipo.most_common()))
    print("\nCentros do grafo (mais citadas):")
    for t, q in entrada.most_common(10):
        print(f"  {q:3d}  {t}")
    # componentes conexos
    vistos, comps = set(), []
    for n in (x.titulo for x in notas):
        if n in vistos:
            continue
        pilha, comp = [n], set()
        while pilha:
            a = pilha.pop()
            if a in comp:
                continue
            comp.add(a)
            pilha.extend(vizinhos[a] - comp)
        vistos |= comp
        comps.append(comp)
    ilhas = [c for c in comps if len(c) > 1]
    soltas = [next(iter(c)) for c in comps if len(c) == 1]
    print(f"\nIlhas de conhecimento: {len(ilhas)} (maior com {max((len(c) for c in ilhas), default=0)} notas)")
    if soltas:
        print(f"Notas soltas: {len(soltas)}: " + ", ".join(sorted(soltas)[:10]))


def _selftest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        c = Path(d) / "cerebro"
        (c / "_modelos").mkdir(parents=True)
        (c / "_modelos" / "tese.md").write_text("---\ntipo: tese\narea:\nstatus: em-teste\n---\n# {{title}}\n"
                                               "Base: [[CLT art. 71]] e [[Inexistente]]\n", encoding="utf-8")
        (c / "02 Legislação").mkdir()
        (c / "02 Legislação" / "CLT art. 71.md").write_text(
            "---\ntipo: dispositivo\nnorma: CLT\nartigo: '71'\nfonte: x\nverificado: true\naliases: [Intervalo]\n---\n"
            "# CLT art. 71\n", encoding="utf-8")
        (c / "06 Casos").mkdir()
        (c / "06 Casos" / "CASO-1.md").write_text(
            '---\ntipo: caso\ncodigo: CASO-1\nstatus: ativo\narea: trabalhista\norgao: "[[Vara X]]"\n'
            'teses: ["[[Tese A]]"]\n---\nCliente CPF 529.982.247-25 [[Intervalo|ver]]\n', encoding="utf-8")
        cmd_novo("tese", "Tese A", "trabalhista", c)
        try:
            cmd_novo("tese", "Tese A", None, c)
            raise AssertionError("deveria recusar duplicata")
        except SystemExit:
            pass
        assert "area: trabalhista" in (c / "04 Teses" / "Tese A.md").read_text(encoding="utf-8")
        (c / "04 Teses" / "Tese A-DESKTOP-AB12CD.md").write_text("cópia", encoding="utf-8")
        r = cmd_verificar(c)
        assert any("Tese A-DESKTOP-AB12CD" in q for q in r["conflitos"]), r["conflitos"]
        assert not any("CASO-1" in q for q in r["conflitos"]), "nome com hífen sem original não é conflito"
        (c / "04 Teses" / "Tese A-DESKTOP-AB12CD.md").unlink()
        assert any("Inexistente" in q for q in r["quebrados"]), r["quebrados"]
        assert any("Vara X" in q for q in r["quebrados"]), "link em propriedade deve ser lido"
        assert not any("Intervalo" in q for q in r["quebrados"]), "alias deve resolver"
        assert r["pii"], "CPF no cofre deve ser apontado"
        fn, fl = cmd_indexar(c, Path(d) / "out")
        import polars as pl
        links = pl.read_parquet(fl)
        assert links.filter((pl.col("origem") == "CASO-1") & (pl.col("destino") == "Tese A")).height == 1
        assert pl.read_parquet(fn).filter(pl.col("titulo") == "CASO-1")["orgao"][0] == "Vara X"
        cmd_grafo(c)
    print("selftest OK")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cofre", type=Path, default=COFRE)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("novo", help="cria nota a partir do modelo")
    n.add_argument("tipo", choices=sorted(PASTA_DO_TIPO))
    n.add_argument("titulo")
    n.add_argument("--area")
    sub.add_parser("verificar")
    sub.add_parser("indexar")
    sub.add_parser("grafo")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.cmd == "novo":
        cmd_novo(a.tipo, a.titulo, a.area, a.cofre)
    elif a.cmd == "verificar":
        cmd_verificar(a.cofre)
    elif a.cmd == "indexar":
        cmd_indexar(a.cofre)
    elif a.cmd == "grafo":
        cmd_grafo(a.cofre)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
