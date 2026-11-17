"""Hook PostToolUse: todo arquivo novo ou alterado em dados/exportacoes/ ganha uma cópia
anonimizada <nome>_anon.<ext> ao lado (docx, pdf, txt, md).

Roda depois de Write/Edit/Bash/PowerShell. A checagem de pendências é só uma listagem de
pasta (rápida); o spaCy só é carregado quando há algo para processar.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent  # .../juridico
PASTA = RAIZ / "dados" / "exportacoes"
sys.path.insert(0, str(RAIZ / "scripts"))


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8", errors="ignore")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.stdin.read()  # o evento não importa: varremos a pasta
    except Exception:
        pass
    if not PASTA.is_dir():
        return
    from anonimizar import Anonimizador, pendentes

    fila = pendentes(PASTA)
    if not fila:
        return
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)
    feitos, problemas = [], []
    for f in fila:
        try:
            an = Anonimizador()
            saida, avisos = an.arquivo(f)
            total = sum(an.contagem.values())
            feitos.append(f"{f.relative_to(PASTA)} -> {saida.name} ({total} dado(s) mascarado(s))")
            problemas += [f"{f.name}: {a}" for a in avisos]
        except PermissionError:
            problemas.append(f"{f.name}: arquivo aberto em outro programa (Word?) — feche e salve de novo.")
        except Exception as e:
            problemas.append(f"{f.name}: falhou ({type(e).__name__}: {e})")
    linhas = ["LGPD — cópias anonimizadas geradas em dados/exportacoes:"] + [f"  • {x}" for x in feitos]
    if problemas:
        linhas += ["Atenção:"] + [f"  ! {x}" for x in problemas]
    linhas.append("Revise as cópias _anon antes de enviar: a detecção automática não é infalível.")
    msg = "\n".join(linhas)
    print(json.dumps({"systemMessage": msg,
                      "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
