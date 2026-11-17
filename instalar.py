"""Instala o harness jurídico do Claude Code numa máquina nova (ou atualiza uma existente).

Uso:
  python instalar.py                         # tudo, workspace em ~/juridico
  python instalar.py --workspace D:/juridico
  python instalar.py --pular-pip --pular-plugins

O que faz (idempotente — pode rodar de novo para atualizar):
  1. Bibliotecas Python (requirements.txt) e modelo spaCy em português
  2. dbt + adaptador DuckDB como ferramenta isolada do uv
  3. Workspace: pastas de dados, CLAUDE.md, scripts de anonimização, projeto dbt
  4. Skills próprias em ~/.claude/skills
  5. ~/.claude/settings.json: plugins, conectores de nuvem desligados, hook de anonimização
     (mescla com o que já existe; faz backup antes)
  6. Plugins oficiais (Anthropic e dbt Labs) e servidores MCP
  7. Autotestes

Arquivos existentes que mudariam ganham backup <arquivo>.bak-AAAAMMDD-HHMMSS.
Pré-requisitos: Python 3.12+, Claude Code (claude), uv (uvx). No Windows, rode antes
prerequisitos-windows.ps1.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
CARIMBO = datetime.now().strftime("%Y%m%d-%H%M%S")
ENV = {**os.environ, "UV_NATIVE_TLS": "1", "PYTHONIOENCODING": "utf-8"}

DUCKDB = "1.5.6"
DBT_CORE = "1.12.7"
DBT_DUCKDB = "1.11.1"

MARKETPLACES = {
    "anthropic-agent-skills": "anthropics/skills",
    "knowledge-work-plugins": "anthropics/knowledge-work-plugins",
    "dbt-agent-marketplace": "dbt-labs/dbt-agent-skills",
}
PLUGINS = [
    "document-skills@anthropic-agent-skills",
    "legal@knowledge-work-plugins",
    "data@knowledge-work-plugins",
    "dbt@dbt-agent-marketplace",
]
# Conectores de nuvem que vêm nos plugins legal/data e o escritório não usa.
CONECTORES_DESLIGADOS = [
    "plugin:legal:slack", "plugin:legal:box", "plugin:legal:egnyte", "plugin:legal:atlassian",
    "plugin:legal:docusign", "plugin:legal:google calendar", "plugin:legal:gmail",
    "plugin:data:snowflake", "plugin:data:databricks", "plugin:data:bigquery", "plugin:data:hex",
    "plugin:data:amplitude", "plugin:data:amplitude-eu", "plugin:data:atlassian", "plugin:data:definite",
]

passos_ok: list[str] = []
pendencias: list[str] = []


def titulo(t: str) -> None:
    print(f"\n=== {t} ===", flush=True)


def rodar(cmd: list[str], cwd: Path | None = None, checar: bool = True, silencioso: bool = False) -> int:
    print("  $", " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env=ENV,
                       stdout=subprocess.DEVNULL if silencioso else None,
                       stderr=subprocess.DEVNULL if silencioso else None)
    if checar and r.returncode != 0:
        raise SystemExit(f"Falhou (código {r.returncode}): {' '.join(cmd)}")
    return r.returncode


def exe(nome: str) -> str | None:
    return shutil.which(nome)


def copiar(origem: Path, destino: Path) -> str:
    """Copia arquivo; se o destino existe e é diferente, faz backup. Retorna o que fez."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        if filecmp.cmp(origem, destino, shallow=False):
            return "igual"
        shutil.copy2(destino, destino.with_name(f"{destino.name}.bak-{CARIMBO}"))
        shutil.copy2(origem, destino)
        return "atualizado (backup feito)"
    shutil.copy2(origem, destino)
    return "criado"


def copiar_arvore(origem: Path, destino: Path) -> None:
    for f in sorted(origem.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            r = copiar(f, destino / f.relative_to(origem))
            if r != "igual":
                print(f"  {destino / f.relative_to(origem)}: {r}")


# ---------------------------------------------------------------- passos
def checar_prerequisitos() -> None:
    titulo("Pré-requisitos")
    if sys.version_info < (3, 12):
        raise SystemExit(f"Python 3.12+ necessário (este é {sys.version.split()[0]}).")
    print(f"  Python {sys.version.split()[0]} ok")
    for nome in ("claude", "uvx", "uv"):
        print(f"  {nome}: {exe(nome) or 'NÃO ENCONTRADO'}")
    if not exe("claude"):
        pendencias.append("Instale o Claude Code e rode o instalador de novo para plugins e MCP.")
    if not exe("uvx"):
        pendencias.append("Instale o uv (winget install astral-sh.uv) para dbt e servidores MCP.")
    if not exe("tesseract"):
        pendencias.append("Tesseract não está no PATH (opcional; OCR alternativo ao docling).")


def instalar_python() -> None:
    titulo("Bibliotecas Python")
    rodar([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")])
    try:
        import spacy.util  # noqa: F401
        tem_modelo = spacy.util.is_package("pt_core_news_lg")
    except Exception:
        tem_modelo = False
    if not tem_modelo:
        rodar([sys.executable, "-m", "spacy", "download", "pt_core_news_lg"])
    passos_ok.append("bibliotecas Python + spaCy pt")


def instalar_dbt() -> None:
    titulo("dbt (ferramenta isolada do uv)")
    if not exe("uv"):
        pendencias.append("dbt não instalado: falta o uv.")
        return
    rodar(["uv", "tool", "install", "--force", f"dbt-core=={DBT_CORE}",
           "--with", f"dbt-duckdb=={DBT_DUCKDB}", "--with", f"duckdb=={DUCKDB}"])
    passos_ok.append(f"dbt {DBT_CORE} + duckdb {DUCKDB}")


def instalar_workspace(ws: Path) -> None:
    titulo(f"Workspace em {ws}")
    for pasta in ("dados/bruto", "dados/tratado", "dados/exportacoes", "pipelines", "notebooks"):
        (ws / pasta).mkdir(parents=True, exist_ok=True)
    copiar_arvore(REPO / "workspace", ws)
    passos_ok.append(f"workspace {ws}")


def _criar_atalho_pasta(link: Path, alvo: Path) -> None:
    """Junção no Windows (não precisa de admin); link simbólico nos outros sistemas."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"Não consegui criar a junção {link} -> {alvo}: {r.stdout}{r.stderr}")
    else:
        link.symlink_to(alvo, target_is_directory=True)


def instalar_cerebro(ws: Path, cerebro_em: Path | None) -> None:
    """Cofre Obsidian. Nunca sobrescreve notas.

    Cofre novo (sem .obsidian): recebe o modelo completo, com notas-semente.
    Cofre existente: só ganha o que faltar em _modelos/, _painéis/ e .obsidian/ — notas que o
    escritório apagou de propósito não voltam.
    Com --cerebro-em (ex.: pasta do OneDrive), o cofre fica lá e <workspace>/cerebro vira um atalho.
    """
    origem, atalho = REPO / "cerebro", ws / "cerebro"
    destino = cerebro_em or atalho
    titulo(f"Segundo cérebro em {destino}")
    if cerebro_em:
        if atalho.exists() and atalho.resolve() != cerebro_em.resolve():
            pendencias.append(f"{atalho} já existe e não aponta para {cerebro_em}: mova o conteúdo "
                              "para lá e apague a pasta antiga para eu criar o atalho.")
            return
        cerebro_em.mkdir(parents=True, exist_ok=True)
    novo = not (destino / ".obsidian").exists()
    sistema = ("_modelos", "_painéis", ".obsidian")
    novos = 0
    for f in sorted(origem.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        rel = f.relative_to(origem)
        if not novo and rel.parts[0] not in sistema:
            continue
        alvo = destino / rel
        if alvo.exists():
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, alvo)
        novos += 1
    for pasta in (p for p in origem.iterdir() if p.is_dir()):
        (destino / pasta.name).mkdir(exist_ok=True)
    if cerebro_em and not atalho.exists():
        _criar_atalho_pasta(atalho, cerebro_em)
        print(f"  atalho {atalho} -> {cerebro_em}")
    print(f"  {'cofre novo' if novo else 'cofre existente'}: {novos} arquivo(s) adicionado(s); notas mantidas")
    passos_ok.append(f"segundo cérebro em {destino} ({novos} arquivos novos)")
    if "onedrive" in str(destino).lower():
        pendencias.append("No Explorador, clique com o botão direito na pasta do cofre → "
                          "'Sempre manter neste dispositivo' (ou rode: attrib +P -U \"<pasta>\\*\" /S /D).")
    if not exe("obsidian") and not (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Obsidian").exists():
        pendencias.append("Obsidian não encontrado: instale (winget install Obsidian.Obsidian) e abra "
                          f"a pasta {destino} como cofre.")


def instalar_skills() -> None:
    titulo("Skills próprias")
    copiar_arvore(REPO / "claude" / "skills", CLAUDE_DIR / "skills")
    passos_ok.append("skills: " + ", ".join(p.name for p in (REPO / "claude" / "skills").iterdir()))


def configurar_settings(ws: Path) -> None:
    titulo("~/.claude/settings.json")
    arq = CLAUDE_DIR / "settings.json"
    CLAUDE_DIR.mkdir(exist_ok=True)
    s = {}
    if arq.exists():
        s = json.loads(arq.read_text(encoding="utf-8") or "{}")
        shutil.copy2(arq, arq.with_name(f"settings.json.bak-{CARIMBO}"))

    s.setdefault("enabledPlugins", {}).update({p: True for p in PLUGINS})
    mk = s.setdefault("extraKnownMarketplaces", {})
    for nome, repo in MARKETPLACES.items():
        mk.setdefault(nome, {"source": {"source": "github", "repo": repo}})

    negados = s.setdefault("deniedMcpServers", [])
    ja = {d.get("serverName") for d in negados if isinstance(d, dict)}
    negados += [{"serverName": n} for n in CONECTORES_DESLIGADOS if n not in ja]

    script = (ws / "scripts" / "hooks" / "anonimizar_exportacoes.py").as_posix()
    py = Path(sys.executable).as_posix()
    comando = f'"{py}" "{script}"'
    post = s.setdefault("hooks", {}).setdefault("PostToolUse", [])
    existente = [h for grupo in post for h in grupo.get("hooks", [])
                 if "anonimizar_exportacoes.py" in h.get("command", "")]
    if existente:
        for h in existente:
            h["command"] = comando
    else:
        post.append({"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell",
                     "hooks": [{"type": "command", "command": comando, "timeout": 300,
                                "statusMessage": "LGPD: anonimizando exportações..."}]})

    arq.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.loads(arq.read_text(encoding="utf-8"))  # valida
    passos_ok.append("settings.json (plugins, conectores desligados, hook LGPD)")


def instalar_plugins() -> None:
    titulo("Plugins do Claude Code")
    claude = exe("claude")
    if not claude:
        return
    for nome, repo in MARKETPLACES.items():
        rodar([claude, "plugin", "marketplace", "add", repo], checar=False)
    for p in PLUGINS:
        rodar([claude, "plugin", "install", p], checar=False)
    passos_ok.append("plugins: " + ", ".join(p.split("@")[0] for p in PLUGINS))


def configurar_mcp(ws: Path) -> None:
    titulo("Servidores MCP")
    claude, uvx = exe("claude"), exe("uvx")
    if not (claude and uvx):
        return
    banco = (ws / "juridico.duckdb").as_posix()
    servidores = {
        "juridico-brasil": [uvx, "--system-certs", "mcp-juridico-brasil"],
        "mcp-brasil": [uvx, "--system-certs", "--from", "mcp-brasil", "python", "-m", "mcp_brasil.server"],
        "duckdb-juridico": [uvx, "--system-certs", "--with", f"duckdb=={DUCKDB}", "mcp-server-motherduck",
                            "--db-path", banco, "--max-rows", "2000"],
    }
    for nome, cmd in servidores.items():
        if rodar([claude, "mcp", "get", nome], checar=False, silencioso=True) == 0:
            print(f"  {nome}: já configurado (mantido)")
            continue
        rodar([claude, "mcp", "add", nome, "--scope", "user", "--", *cmd], checar=False)
    passos_ok.append("MCP: " + ", ".join(servidores))


def criar_banco(ws: Path) -> None:
    titulo("Banco analítico")
    banco = ws / "juridico.duckdb"
    if banco.exists():
        print("  juridico.duckdb já existe (mantido)")
        return
    if not exe("dbt"):
        pendencias.append("Banco não criado: rode `dbt run` em workspace/dbt depois de instalar o dbt.")
        return
    env_dbt = {**ENV, "DBT_PROFILES_DIR": "."}
    r = subprocess.run(["dbt", "run"], cwd=ws / "dbt", env=env_dbt)
    if r.returncode == 0:
        passos_ok.append("juridico.duckdb criado (modelo de exemplo)")
    else:
        pendencias.append("dbt run falhou: veja a saída acima.")


def autotestes(ws: Path) -> None:
    titulo("Autotestes")
    testes = [
        ("calculo-trabalhista", [sys.executable, str(CLAUDE_DIR / "skills/calculo-trabalhista/calculo_trabalhista.py"), "--selftest"]),
        ("leitura-cartao-ponto", [sys.executable, str(CLAUDE_DIR / "skills/leitura-cartao-ponto/calculo_jornada.py"), "--selftest"]),
        ("anonimizar", [sys.executable, str(ws / "scripts/anonimizar.py"), "--selftest"]),
        ("cerebro", [sys.executable, str(ws / "scripts/cerebro.py"), "--selftest"]),
    ]
    for nome, cmd in testes:
        r = subprocess.run(cmd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = r.returncode == 0 and "selftest OK" in r.stdout
        print(f"  {nome}: {'OK' if ok else 'FALHOU'}")
        if not ok:
            pendencias.append(f"autoteste {nome} falhou:\n{(r.stdout + r.stderr)[-800:]}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", type=Path, default=HOME / "juridico")
    ap.add_argument("--cerebro-em", type=Path, default=None,
                    help="pasta do cofre fora do workspace (ex.: no OneDrive); cria atalho em <workspace>/cerebro")
    ap.add_argument("--pular-pip", action="store_true")
    ap.add_argument("--pular-dbt", action="store_true")
    ap.add_argument("--pular-plugins", action="store_true")
    ap.add_argument("--pular-mcp", action="store_true")
    a = ap.parse_args()
    ws = a.workspace.expanduser().resolve()
    cerebro_em = Path(os.path.expandvars(str(a.cerebro_em))).expanduser().resolve() if a.cerebro_em else None

    checar_prerequisitos()
    if not a.pular_pip:
        instalar_python()
    if not a.pular_dbt:
        instalar_dbt()
    instalar_workspace(ws)
    instalar_cerebro(ws, cerebro_em)
    instalar_skills()
    configurar_settings(ws)
    if not a.pular_plugins:
        instalar_plugins()
    if not a.pular_mcp:
        configurar_mcp(ws)
    if not a.pular_dbt:
        criar_banco(ws)
    autotestes(ws)

    titulo("Resumo")
    for p in passos_ok:
        print(f"  ✓ {p}")
    for p in pendencias:
        print(f"  ! {p}")
    print("\nReinicie o Claude Code e abra-o na pasta do workspace para carregar tudo.")


if __name__ == "__main__":
    main()
