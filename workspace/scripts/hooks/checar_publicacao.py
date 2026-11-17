"""Hook PreToolUse: antes de publicar (Artifact, ArtifactData, Claude Docs), procura dados
pessoais (CPF, CNPJ, número CNJ, OAB, e-mail). Se achar, pede confirmação ao usuário.

Usa só regex + dígito verificador (pii_br) para ser instantâneo. Nomes de pessoas não são
checados aqui: rode anonimizar.py antes de publicar material de cliente.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEXTO_EXT = {".html", ".htm", ".md", ".txt", ".json", ".csv", ".js", ".css", ".svg", ".xml", ".tsv"}
LIMITE = 5_000_000  # caracteres por arquivo


def _ler(caminho: str, base: Path) -> str:
    p = Path(caminho)
    if not p.is_absolute():
        p = base / p
    try:
        if p.suffix.lower() in TEXTO_EXT and p.is_file():
            return p.read_text(encoding="utf-8", errors="ignore")[:LIMITE]
    except OSError:
        pass
    return ""


def coletar(evento: dict) -> list[tuple[str, str]]:
    """[(origem, texto)] de tudo o que a chamada vai publicar."""
    nome = evento.get("tool_name", "")
    ent = evento.get("tool_input") or {}
    base = Path(evento.get("cwd") or ".")
    out = []
    if nome == "Artifact":
        if ent.get("action", "publish") != "publish":
            return []
        for chave in ("file_path",):
            if ent.get(chave):
                out.append((ent[chave], _ler(ent[chave], base)))
        for c in ent.get("file_paths") or []:
            out.append((c, _ler(c, base)))
        for ed in ent.get("edits") or []:
            out.append(("edits", ed.get("new_str", "")))
        arquivos = ent.get("files") or {}
        if isinstance(arquivos, dict):
            for destino, origem in arquivos.items():
                src = origem.get("from") if isinstance(origem, dict) else origem
                if isinstance(src, str):
                    out.append((destino, _ler(src, base)))
        elif isinstance(arquivos, list):
            for item in arquivos:
                if isinstance(item, dict) and item.get("path"):
                    out.append((item["path"], _ler(item["path"], base)))
        out.append(("parâmetros", json.dumps({k: ent.get(k) for k in ("title", "description")},
                                             ensure_ascii=False)))
    else:  # ArtifactData / Claude Docs: o conteúdo vem nos próprios parâmetros
        if ent.get("file_path"):
            out.append((ent["file_path"], _ler(ent["file_path"], base)))
        out.append(("parâmetros", json.dumps(ent, ensure_ascii=False)))
    return out


def responder(decisao: str, motivo: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decisao,
        "permissionDecisionReason": motivo,
    }}, ensure_ascii=False))


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import pii_br

        evento = json.load(sys.stdin)
        if evento.get("tool_name") == "ArtifactData" and \
                (evento.get("tool_input") or {}).get("action") in ("get", "list", "query"):
            return  # leitura não publica nada
        achados = []
        for origem, texto in coletar(evento):
            for a in pii_br.detectar(texto):
                achados.append((origem, a))
        if not achados:
            return
        por_tipo = {}
        for _, a in achados:
            por_tipo[a.tipo] = por_tipo.get(a.tipo, 0) + 1
        exemplos = "; ".join(f"{a.tipo} {pii_br.mascarar_parcial(a.valor)} em {Path(o).name}"
                             for o, a in achados[:4])
        resumo = ", ".join(f"{k}: {v}" for k, v in sorted(por_tipo.items()))
        responder("ask",
                  f"LGPD — o conteúdo a publicar contém dados pessoais ({resumo}). Ex.: {exemplos}. "
                  "Confirme só se a publicação desses dados é intencional; senão, recuse e anonimize "
                  "com scripts/anonimizar.py.")
    except Exception as e:  # falha fechada: na dúvida, pergunta
        responder("ask", f"LGPD — a verificação de dados pessoais falhou ({type(e).__name__}: {e}). "
                         "Confirme manualmente que não há dados de cliente.")


if __name__ == "__main__":
    main()
