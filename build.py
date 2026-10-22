"""Assemble app/ en un fichier HTML unique : dist/supply360.html (Streamlit via stlite / Pyodide).

Usage : python build.py
Sans dépendance externe (bibliothèque standard uniquement).
"""

import base64
import json
import re
import tomllib
from pathlib import Path

# Version épinglée : toute montée de version doit être testée avant livraison (CLAUDE.md §4).
# @stlite/browser 1.9.2 embarque Streamlit 1.62.0 (cf. requirements-dev.txt).
STLITE_VERSION = "1.9.2"
STLITE_CDN = f"https://cdn.jsdelivr.net/npm/@stlite/browser@{STLITE_VERSION}/build"

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
LOGO = ROOT / "assets" / "logo_afi.png"
LOGO_PY = APP / "core" / "_logo.py"
CONFIG = ROOT / ".streamlit" / "config.toml"
OUT = ROOT / "dist" / "supply360.html"


def generer_logo() -> str:
    b64 = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    LOGO_PY.write_text(
        '"""GÉNÉRÉ par build.py à partir de assets/logo_afi.png — ne pas éditer à la main."""\n\n'
        f'LOGO_B64 = "{b64}"\n',
        encoding="utf-8",
    )
    return b64


def lire_requirements() -> list[str]:
    reqs = []
    for ligne in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if ligne:
            reqs.append(ligne)
    return reqs


def lire_fichiers() -> dict[str, str]:
    fichiers = {}
    for p in sorted(APP.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        fichiers[p.relative_to(ROOT).as_posix()] = p.read_text(encoding="utf-8")
    fichiers[".streamlit/config.toml"] = CONFIG.read_text(encoding="utf-8")
    return fichiers


def config_streamlit() -> dict:
    """Options [theme] et [client] de config.toml, au format attendu par stlite (« section.cle »)."""
    conf = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return {f"{section}.{cle}": val
            for section in ("theme", "client")
            for cle, val in conf.get(section, {}).items()}


def js(obj) -> str:
    """Littéral JSON sûr à l'intérieur d'une balise <script>."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "\\u003c!--")


def modules_embarques(fichiers: dict[str, str]) -> list[str]:
    noms = []
    for chemin, code in fichiers.items():
        if chemin.startswith("app/modules/") and not chemin.endswith("__init__.py"):
            label = re.search(r'^TAB_LABEL\s*=\s*"([^"]+)"', code, re.M)
            noms.append(f"{Path(chemin).stem} ({label.group(1) if label else '?'})")
    return noms


TEMPLATE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
<title>Supply360 · Air France Industries</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✈️</text></svg>">
<link rel="stylesheet" href="__CDN__/stlite.css">
<style>
  :root { --navy:#002157; --navy-2:#1F4E9C; --bg:#F4F6FA; --muted:#5B6478; }
  html, body { margin:0; background:var(--bg); }
  #s360-loading {
    position:fixed; inset:0; z-index:1000000; display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:1.25rem; padding:1rem;
    background:#FFFFFF; font-family:"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif;
    text-align:center; transition:opacity .35s ease;
  }
  #s360-loading.fini { opacity:0; pointer-events:none; }
  /* Logo sur fond transparent, texte bleu marine : toujours sur fond blanc. */
  #s360-loading img { width:min(22rem, 80vw); height:auto; }
  #s360-loading .titre { color:var(--navy); font-size:1.75rem; font-weight:700; }
  #s360-loading .texte { color:var(--muted); font-size:1rem; max-width:32rem; }
  #s360-loading .barre { width:min(18rem, 70vw); height:4px; border-radius:4px; overflow:hidden; background:#E3E8F1; }
  #s360-loading .barre::after {
    content:""; display:block; width:40%; height:100%; border-radius:4px;
    background:linear-gradient(90deg, var(--navy), var(--navy-2)); animation:s360-glisse 1.3s ease-in-out infinite;
  }
  @keyframes s360-glisse { 0% { transform:translateX(-100%); } 100% { transform:translateX(250%); } }
  #s360-loading .lent { display:none; color:var(--muted); font-size:.9375rem; max-width:34rem; }
  #s360-loading.lent .lent { display:block; }
  #s360-loading button {
    font:inherit; font-weight:600; color:#fff; border:0; border-radius:8px; padding:.5rem 1rem; cursor:pointer;
    background:linear-gradient(90deg, var(--navy), var(--navy-2));
  }
</style>
</head>
<body>
<div id="s360-loading" role="status" aria-live="polite">
  <img src="data:image/png;base64,__LOGO__" alt="Air France Industries KLM Engineering &amp; Maintenance">
  <div class="titre">Supply360</div>
  <div class="barre"></div>
  <div class="texte">Chargement de Supply360… le premier lancement peut prendre jusqu'à une minute.</div>
  <div class="lent">Le chargement est plus long que prévu. Le navigateur doit pouvoir accéder à
    cdn.jsdelivr.net et pypi.org (proxy, réseau). <br><br>
    <button type="button" onclick="document.getElementById('s360-loading').classList.add('fini')">Afficher la page</button>
  </div>
</div>
<div id="root"></div>
<script type="module">
import { mount } from "__CDN__/stlite.js";

mount(
  {
    entrypoint: "app/main.py",
    requirements: __REQUIREMENTS__,
    files: __FILES__,
    streamlitConfig: __CONFIG__,
    disableProgressToasts: true,
  },
  document.getElementById("root"),
);

// Masque l'écran de chargement dès que l'app (ou une erreur) est affichée.
const ecran = document.getElementById("s360-loading");
const pret = () => document.querySelector(".s360-header, .stException, [data-testid='stException']");
const obs = new MutationObserver(() => {
  if (pret()) { ecran.classList.add("fini"); obs.disconnect(); }
});
obs.observe(document.body, { childList: true, subtree: true });
setTimeout(() => { if (!pret()) ecran.classList.add("lent"); }, 120000);
</script>
</body>
</html>
"""


def main() -> None:
    logo_b64 = generer_logo()
    fichiers = lire_fichiers()
    reqs = lire_requirements()
    html = (TEMPLATE
            .replace("__CDN__", STLITE_CDN)
            .replace("__LOGO__", logo_b64)
            .replace("__REQUIREMENTS__", js(reqs))
            .replace("__CONFIG__", js(config_streamlit()))
            .replace("__FILES__", js(fichiers)))  # en dernier : le code peut contenir des « __X__ »
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    taille = OUT.stat().st_size
    print(f"✅ {OUT.relative_to(ROOT)} généré — {taille / 1024:.0f} Ko")
    print(f"   stlite {STLITE_VERSION} · requirements : {', '.join(reqs)}")
    print(f"   {len(fichiers)} fichiers embarqués")
    for nom in modules_embarques(fichiers):
        print(f"   • module {nom}")


if __name__ == "__main__":
    main()
