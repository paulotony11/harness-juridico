"""Anonimização/pseudonimização LGPD de minutas e documentos jurídicos.

Formatos: .docx (preserva a formatação), .pdf (tarja de verdade: o texto é removido do
arquivo, não só coberto), .txt e .md.

Detecta: CPF e CNPJ (com dígito verificador), número CNJ (com dígito verificador), OAB,
e-mail, telefone, CEP e nomes de pessoas (spaCy pt_core_news_lg, inclusive em CAIXA ALTA).

Uso:
  python anonimizar.py minuta.docx                 -> grava minuta_anon.docx ao lado
  python anonimizar.py peticao.pdf -o saida.pdf
  python anonimizar.py notas.txt --stdout
  python anonimizar.py --pasta dados/exportacoes   -> processa o que estiver pendente
  python anonimizar.py --selftest

Rótulos: por padrão o mesmo valor recebe sempre o mesmo rótulo no documento (<BR_CPF_1>);
--generico usa só <BR_CPF>. --manter-processo não mascara números CNJ.

LIMITAÇÃO: detecção automática não garante anonimização completa (nomes raros,
apelidos, endereços por extenso, dados em imagens). Revise antes de enviar.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SUFIXO = "_anon"
FORMATOS = {".docx", ".pdf", ".txt", ".md"}
LANG = "pt"

# Palavras que o spaCy confunde com nomes em peças processuais.
_TRATAMENTO = {
    "excelentíssimo", "excelentíssima", "exmo", "exma", "meritíssimo", "meritíssima", "senhor", "senhora",
    "sr", "sra", "doutor", "doutora", "dr", "dra", "juiz", "juíza", "juízo", "desembargador",
    "desembargadora", "ministro", "ministra", "relator", "relatora", "presidente", "réu", "ré", "autor",
    "autora", "reclamante", "reclamado", "reclamada", "requerente", "requerido", "requerida", "exequente",
    "executado", "executada", "agravante", "agravado", "apelante", "apelado", "impetrante", "impetrado",
    "embargante", "embargado", "recorrente", "recorrido", "advogado", "advogada", "procurador",
    "procuradora", "promotor", "promotora", "defensor", "defensora", "de", "da", "do", "das", "dos", "e",
    "vossa", "v", "ex", "ª", "º", "excelência", "nobre", "ilustre", "colenda", "egrégio", "egrégia",
}


def _so_tratamento(trecho: str) -> bool:
    palavras = [p for p in re.split(r"[\s.,;:]+", trecho.lower()) if p]
    return bool(palavras) and all(p in _TRATAMENTO for p in palavras)


def _aparar(texto: str, ini: int, fim: int) -> tuple[int, int]:
    """Tira palavras de tratamento/papel das bordas: 'Réu João Souza' -> 'João Souza'."""
    while True:
        m = re.match(r"[\s.,;:]*([^\s.,;:]+)[\s.,;:]*", texto[ini:fim])
        if not m or m.group(1).lower() not in _TRATAMENTO or m.end() >= fim - ini:
            break
        ini += m.end()
    while True:
        m = re.search(r"[\s.,;:]*([^\s.,;:]+)[\s.,;:]*$", texto[ini:fim])
        if not m or m.group(1).lower() not in _TRATAMENTO or m.start() == 0:
            break
        fim = ini + m.start()
    return ini, fim


def _titulo(texto: str) -> str:
    """MARIA DA SILVA -> Maria Da Silva (mesmo comprimento) para o NER achar nomes em caixa alta."""
    out = re.sub(r"\b[A-ZÀ-Ý]{2,}\b", lambda m: m.group().capitalize(), texto)
    return out if len(out) == len(texto) else texto


@dataclass
class Anonimizador:
    pseudonimo: bool = True
    manter_processo: bool = False
    _an: object = field(default=None, repr=False)
    _mapa: dict = field(default_factory=dict, repr=False)
    _cont: dict = field(default_factory=dict, repr=False)
    contagem: dict = field(default_factory=dict)

    # ---------- detecção ----------
    def _analisador(self):
        if self._an is None:
            self._an = _montar_analisador()
        return self._an

    def achados(self, texto: str) -> list[tuple[int, int, str, str]]:
        """[(inicio, fim, tipo, valor)] sem sobreposição."""
        if not texto.strip():
            return []
        ents = [e for e in ENTIDADES if not (self.manter_processo and e == "BR_PROCESSO_CNJ")]
        an = self._analisador()
        brutos = an.analyze(text=texto, language=LANG, entities=ents, score_threshold=0.5)
        titulo = _titulo(texto)
        if titulo != texto:  # nomes em caixa alta
            brutos += an.analyze(text=titulo, language=LANG, entities=["PERSON"], score_threshold=0.5)
        bons = []  # (ini, fim, tipo, score)
        for r in brutos:
            ini, fim = r.start, r.end
            if r.entity_type == "PERSON":
                if _so_tratamento(texto[ini:fim]):
                    continue
                ini, fim = _aparar(texto, ini, fim)
                trecho = texto[ini:fim].strip()
                if len(trecho) < 3 or (" " not in trecho and trecho.isupper() and len(trecho) <= 5):
                    continue  # siglas: CPF, OAB, STJ
            bons.append((ini, fim, r.entity_type, r.score))
        bons.sort(key=lambda b: (b[0], -(b[1] - b[0]), -b[3]))
        out, ultimo = [], -1
        for ini, fim, tipo, _ in bons:
            if ini >= ultimo:
                out.append((ini, fim, tipo, texto[ini:fim]))
                ultimo = fim
        return out

    def rotulo(self, tipo: str, valor: str) -> str:
        self.contagem[tipo] = self.contagem.get(tipo, 0) + 1
        if not self.pseudonimo:
            return f"<{tipo}>"
        chave = (tipo, re.sub(r"\W", "", valor).lower())
        if chave not in self._mapa:
            self._cont[tipo] = self._cont.get(tipo, 0) + 1
            self._mapa[chave] = f"<{tipo}_{self._cont[tipo]}>"
        return self._mapa[chave]

    def texto(self, texto: str) -> str:
        partes, pos = [], 0
        for ini, fim, tipo, valor in self.achados(texto):
            partes += [texto[pos:ini], self.rotulo(tipo, valor)]
            pos = fim
        partes.append(texto[pos:])
        return "".join(partes)

    # ---------- formatos ----------
    def txt(self, entrada: Path, saida: Path) -> list[str]:
        saida.write_text(self.texto(entrada.read_text(encoding="utf-8")), encoding="utf-8")
        return []

    def docx(self, entrada: Path, saida: Path) -> list[str]:
        from docx import Document
        from lxml import etree

        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
        avisos: list[str] = []
        doc = Document(str(entrada))

        def tratar_raiz(raiz) -> None:
            for p in raiz.iter(f"{{{W}}}p"):
                # w:t (texto) e w:delText (revisão excluída também vaza dados), em ordem
                nos = [n for n in p.iter(f"{{{W}}}t", f"{{{W}}}delText")
                       if n.getparent() is not None and _paragrafo_de(n, W) is p]
                if not nos:
                    continue
                textos = [n.text or "" for n in nos]
                completo = "".join(textos)
                subs = self.achados(completo)
                if not subs:
                    continue
                limites, pos = [], 0
                for t in textos:
                    limites.append((pos, pos + len(t)))
                    pos += len(t)
                novos = list(textos)
                for ini, fim, tipo, valor in reversed(subs):
                    rot = self.rotulo(tipo, valor)
                    primeiro = True
                    for i, (a, b) in enumerate(limites):
                        if b <= ini or a >= fim or a == b:
                            continue
                        s, e = max(ini, a) - a, min(fim, b) - a
                        if primeiro and a <= ini < b:
                            novos[i] = novos[i][:s] + rot + novos[i][e:]
                            primeiro = False
                        else:
                            novos[i] = novos[i][:s] + novos[i][e:]
                for n, novo, velho in zip(nos, novos, textos):
                    if novo != velho:
                        n.text = novo
                        n.set(XML_SPACE, "preserve")
            # códigos de campo (ex.: HYPERLINK "mailto:...")
            for n in raiz.iter(f"{{{W}}}instrText"):
                if n.text:
                    n.text = self.texto(n.text)

        partes_xml = ("document.main", "header", "footer", "footnotes", "endnotes", "comments")
        for parte in doc.part.package.iter_parts():
            ct = parte.content_type
            if "wordprocessingml" not in ct or not any(k in ct for k in partes_xml):
                continue
            if hasattr(parte, "_element"):
                tratar_raiz(parte._element)
            else:
                raiz = etree.fromstring(parte.blob)
                tratar_raiz(raiz)
                parte._blob = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)
            # destinos de hiperlink (mailto:, links com CPF etc.)
            for rel in parte.rels.values():
                if rel.is_external and "hyperlink" in rel.reltype:
                    alvo = rel.target_ref
                    if "mailto:" in alvo.lower() or self.achados(alvo):
                        rel._target = "#"
        cp = doc.core_properties
        for campo in ("author", "last_modified_by", "comments", "title", "subject", "keywords"):
            setattr(cp, campo, "")
        if doc.inline_shapes:
            avisos.append(f"{len(doc.inline_shapes)} imagem(ns) no documento não foram verificadas "
                          "(prints, assinaturas e documentos escaneados podem conter dados pessoais).")
        doc.save(str(saida))
        return avisos

    def pdf(self, entrada: Path, saida: Path) -> list[str]:
        import pymupdf as fitz

        avisos: list[str] = []
        doc = fitz.open(str(entrada))
        sem_texto, nao_localizados = [], 0
        for pagina in doc:
            texto = pagina.get_text()
            if len(texto.strip()) < 20:
                sem_texto.append(pagina.number + 1)
                continue
            for _, _, tipo, valor in self.achados(texto):
                rot = self.rotulo(tipo, valor)
                # o valor pode ter quebrado linha no PDF: procura também por partes
                retangulos = pagina.search_for(valor) or [
                    r for linha in valor.splitlines() if linha.strip() for r in pagina.search_for(linha.strip())]
                if not retangulos:
                    nao_localizados += 1
                    continue
                for ret in retangulos:
                    pagina.add_redact_annot(ret, text=rot, fontsize=7, fill=(0.85, 0.85, 0.85))
            pagina.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        doc.set_metadata({})
        doc.del_xml_metadata()
        doc.save(str(saida), garbage=4, deflate=True)
        if sem_texto:
            avisos.append(f"Páginas sem camada de texto (escaneadas?) NÃO foram anonimizadas: {sem_texto}. "
                          "Faça OCR antes (docling/Tesseract) ou tarje manualmente.")
        if nao_localizados:
            avisos.append(f"{nao_localizados} dado(s) detectado(s) não foram localizados na página para tarjar "
                          "(texto quebrado/hifenizado). Revise o PDF.")
        return avisos

    def arquivo(self, entrada: Path, saida: Path | None = None) -> tuple[Path, list[str]]:
        ext = entrada.suffix.lower()
        if ext not in FORMATOS:
            raise ValueError(f"formato não suportado: {ext} (aceitos: {sorted(FORMATOS)})")
        saida = saida or entrada.with_name(entrada.stem + SUFIXO + entrada.suffix)
        if ext == ".docx":
            avisos = self.docx(entrada, saida)
        elif ext == ".pdf":
            avisos = self.pdf(entrada, saida)
        else:
            avisos = self.txt(entrada, saida)
        return saida, avisos


def _paragrafo_de(no, W):
    """Parágrafo mais próximo (evita contar texto de caixas de texto aninhadas duas vezes)."""
    p = no.getparent()
    while p is not None and p.tag != f"{{{W}}}p":
        p = p.getparent()
    return p


# ---------- Presidio ----------
ENTIDADES = ["PERSON", "BR_CPF", "BR_CNPJ", "BR_PROCESSO_CNJ", "BR_OAB", "BR_TELEFONE", "BR_CEP", "EMAIL"]


def _montar_analisador():
    import logging

    logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    sys.path.insert(0, str(Path(__file__).parent))
    import pii_br

    class _Validado(PatternRecognizer):
        def __init__(self, entidade, regex, contexto, validador, score=0.6):
            super().__init__(supported_entity=entidade, patterns=[Pattern(entidade, regex, score)],
                             context=contexto, supported_language=LANG)
            self._v = validador

        def validate_result(self, pattern_text):
            return self._v(pattern_text)

    padroes = {tipo: (rx.pattern, v) for tipo, rx, v in pii_br.PADROES}
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": LANG, "model_name": "pt_core_news_lg"}],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": {"PER": "PERSON", "LOC": "LOCATION", "ORG": "ORGANIZATION"},
            "labels_to_ignore": ["MISC", "LOC", "ORG"],
        },
    }).create_engine()
    an = AnalyzerEngine(nlp_engine=nlp, supported_languages=[LANG])
    reg = an.registry
    for tipo, contexto in [("BR_CPF", ["cpf"]), ("BR_CNPJ", ["cnpj"]),
                           ("BR_PROCESSO_CNJ", ["processo", "autos"])]:
        rx, v = padroes[tipo]
        reg.add_recognizer(_Validado(tipo, rx, contexto, v))
    reg.add_recognizer(PatternRecognizer("BR_OAB", supported_language=LANG,
                                         patterns=[Pattern("oab", padroes["BR_OAB"][0], 0.85)]))
    reg.add_recognizer(PatternRecognizer("EMAIL", supported_language=LANG,
                                         patterns=[Pattern("email", padroes["EMAIL"][0], 0.9)]))
    reg.add_recognizer(PatternRecognizer(
        "BR_TELEFONE", supported_language=LANG, context=["telefone", "tel", "celular", "whatsapp", "fone"],
        patterns=[Pattern("tel", r"(?:\+55\s?)?\(\d{2}\)\s?9?\d{4}-?\d{4}\b", 0.6),
                  Pattern("tel2", r"(?<![\d.])\d{2}\s9\d{4}-\d{4}\b", 0.5)]))
    reg.add_recognizer(PatternRecognizer("BR_CEP", supported_language=LANG, context=["cep"],
                                         patterns=[Pattern("cep", r"\b\d{5}-\d{3}\b", 0.5)]))
    return an


# ---------- pasta (usado pelo hook) ----------
def pendentes(pasta: Path) -> list[Path]:
    """Arquivos sem versão _anon atualizada."""
    out = []
    for f in sorted(pasta.rglob("*")):
        if (not f.is_file() or f.suffix.lower() not in FORMATOS or f.stem.endswith(SUFIXO)
                or f.name.startswith(("~$", "."))):
            continue
        anon = f.with_name(f.stem + SUFIXO + f.suffix)
        if not anon.exists() or anon.stat().st_mtime < f.stat().st_mtime:
            out.append(f)
    return out


# ---------- teste ----------
def _selftest() -> None:
    import tempfile

    from docx import Document

    txt = ("MARIA DA SILVA PEREIRA, brasileira, CPF 529.982.247-25, empregada da Acme Ltda, "
           "CNPJ 11.222.333/0001-81, nos autos do processo nº 0001234-95.2024.5.02.0001. "
           "Excelentíssimo Senhor Doutor Juiz, o Réu João Souza, OAB/SP 123456, "
           "e-mail maria@exemplo.com.br, tel (11) 98765-4321, CEP 01310-100. CPF falso 111.222.333-44.")
    a = Anonimizador()
    s = a.texto(txt)
    for dado in ["MARIA DA SILVA", "529.982.247-25", "11.222.333/0001-81", "0001234-95.2024.5.02.0001",
                 "João Souza", "123456", "maria@exemplo", "98765-4321", "01310-100"]:
        assert dado not in s, f"vazou {dado!r}: {s}"
    assert "111.222.333-44" in s, "CPF com DV inválido não deveria ser marcado"
    assert "Excelentíssimo Senhor Doutor Juiz" in s and "Réu" in s, f"tratamento mascarado: {s}"
    print("texto :", s)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        doc = Document()
        doc.add_heading("RECLAMAÇÃO TRABALHISTA", 1)
        p = doc.add_paragraph()
        p.add_run("JOANA RIBEIRO").bold = True
        p.add_run(", inscrita no CPF sob o nº 529.982.")
        p.add_run("247-25, residente na cidade de Campinas.")  # CPF quebrado entre runs
        t = doc.add_table(rows=1, cols=1)
        t.cell(0, 0).text = "Contato: joana@exemplo.com.br"
        doc.sections[0].header.paragraphs[0].text = "Processo 0001234-95.2024.5.02.0001"
        doc.core_properties.author = "Fulano Advogado"
        doc.save(d / "m.docx")
        saida, _ = Anonimizador().arquivo(d / "m.docx")
        r = Document(str(saida))
        corpo = "\n".join(x.text for x in r.paragraphs) + r.tables[0].cell(0, 0).text
        cab = r.sections[0].header.paragraphs[0].text
        assert "JOANA" not in corpo and "529.982" not in corpo and "247-25" not in corpo, corpo
        assert "joana@" not in corpo and "0001234" not in cab, (corpo, cab)
        assert r.paragraphs[1].runs[0].bold, "formatação do 1º run perdida"
        assert r.core_properties.author == ""
        print("docx  :", r.paragraphs[1].text, "|", cab)

        import pymupdf as fitz
        pdf = fitz.open()
        pg = pdf.new_page()
        pg.insert_text((50, 80), "Autora: Joana Ribeiro, CPF 529.982.247-25", fontsize=11)
        pg.insert_text((50, 100), "Processo 0001234-95.2024.5.02.0001", fontsize=11)
        pdf.save(str(d / "p.pdf"))
        saida, avisos = Anonimizador().arquivo(d / "p.pdf")
        texto_pdf = fitz.open(str(saida))[0].get_text(sort=True)
        assert "529.982" not in texto_pdf and "Joana" not in texto_pdf and "0001234" not in texto_pdf, texto_pdf
        print("pdf   :", " | ".join(texto_pdf.split("\n")[:3]))

        (d / "x.docx").write_bytes((d / "m.docx").read_bytes())
        assert d / "x.docx" in pendentes(d) and d / "m.docx" not in pendentes(d)
    print("selftest OK")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arquivo", nargs="?", type=Path)
    ap.add_argument("-o", "--saida", type=Path)
    ap.add_argument("--pasta", type=Path, help="processa os arquivos pendentes da pasta (recursivo)")
    ap.add_argument("--stdout", action="store_true", help="(.txt/.md) imprime em vez de gravar")
    ap.add_argument("--generico", action="store_true", help="rótulo único por tipo (<BR_CPF>)")
    ap.add_argument("--manter-processo", action="store_true", help="não mascara números CNJ")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    an = Anonimizador(pseudonimo=not a.generico, manter_processo=a.manter_processo)
    if a.pasta:
        for f in pendentes(a.pasta):
            saida, avisos = Anonimizador(pseudonimo=not a.generico, manter_processo=a.manter_processo).arquivo(f)
            print(f"{f} -> {saida}")
            for av in avisos:
                print(f"  AVISO: {av}")
        return
    if not a.arquivo:
        ap.error("informe o arquivo ou --pasta")
    if a.stdout:
        print(an.texto(a.arquivo.read_text(encoding="utf-8")))
        return
    saida, avisos = an.arquivo(a.arquivo, a.saida)
    print(f"gravado: {saida}")
    print("encontrados:", ", ".join(f"{k}={v}" for k, v in sorted(an.contagem.items())) or "nada")
    for av in avisos:
        print(f"AVISO: {av}")


if __name__ == "__main__":
    main()
