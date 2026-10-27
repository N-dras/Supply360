"""Assemble app/ en un fichier HTML unique : dist/supply360.html (Streamlit via stlite / Pyodide).

Usage : python build.py
Sans dépendance externe (bibliothèque standard uniquement).
"""

import json
import re
import sys
import tomllib
from pathlib import Path

# Version épinglée : toute montée de version doit être testée avant livraison (CLAUDE.md §4).
# @stlite/browser 1.9.2 embarque Streamlit 1.62.0 et Pyodide 0.29.3 (cf. requirements-dev.txt).
STLITE_VERSION = "1.9.2"
STLITE_CDN = f"https://cdn.jsdelivr.net/npm/@stlite/browser@{STLITE_VERSION}/build"

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
ASSETS = ROOT / "assets"
CONFIG = ROOT / ".streamlit" / "config.toml"
OUT = ROOT / "dist" / "supply360.html"

sys.path.insert(0, str(APP))
from core.style import css_complet  # noqa: E402  (module sans dépendance : bibliothèque standard)


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
/* Écran de chargement (les variables et images viennent du thème, en fin de page) */
#s360-loading {
  position: fixed; inset: 0; z-index: 1000000; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 1.2rem; padding: 1rem; text-align: center; font-family: var(--font); overflow: hidden;
  background: linear-gradient(180deg, rgba(11, 26, 51, .55), rgba(11, 26, 51, .8)), var(--img-fond) center / cover;
  transition: opacity .4s ease;
}
#s360-loading.fini { opacity: 0; pointer-events: none; }
#s360-loading .carte {
  display: flex; flex-direction: column; align-items: center; gap: 1rem; padding: 1.8rem 2.4rem; border-radius: 16px;
  background: rgba(255, 255, 255, .96); box-shadow: 0 20px 60px rgba(0, 0, 0, .35); max-width: 30rem;
}
/* Logo sur fond transparent, texte bleu marine : toujours sur la carte blanche. */
#s360-loading .s360-logo { width: 16rem; height: 3.8rem; background-position: center; }
#s360-loading .titre { color: var(--navy); font-size: 1.9rem; font-weight: 800; }
#s360-loading .titre span { color: var(--accent); }
#s360-loading .texte { color: var(--muted); font-size: 1rem; }
#s360-loading .barre { width: 16rem; height: 4px; border-radius: 4px; overflow: hidden; background: #E3E9F1; }
#s360-loading .barre::after {
  content: ""; display: block; width: 40%; height: 100%; border-radius: 4px;
  background: linear-gradient(90deg, var(--navy), var(--accent)); animation: s360-glisse 1.3s ease-in-out infinite;
}
#s360-loading .avion {
  position: absolute; left: -45%; bottom: 12%; width: min(42rem, 70vw); aspect-ratio: 4 / 1;
  background: var(--img-avion) center / contain no-repeat; filter: drop-shadow(0 18px 18px rgba(0, 0, 0, .4));
  animation: s360-vol 18s linear infinite;  /* vitesse réduite de moitié */
}
@keyframes s360-glisse { 0% { transform: translateX(-100%); } 100% { transform: translateX(250%); } }
@keyframes s360-vol { from { transform: translateX(0); } to { transform: translateX(260vw); } }
#s360-loading .lent { display: none; color: var(--muted); font-size: .9375rem; }
#s360-loading .etape { color: var(--navy); font-size: .9375rem; font-weight: 700; min-height: 1.4em; }
#s360-loading .erreur { display: none; max-width: 26rem; padding: .6rem .8rem; border-radius: 8px; background: #FDECEC;
  color: var(--ko); font-size: .875rem; text-align: left; white-space: pre-wrap; word-break: break-word; }
#s360-loading.echec .erreur, #s360-loading.echec .lent { display: block; }
#s360-loading.echec .barre, #s360-loading.echec .avion { display: none; }
/* Étapes de stlite (en anglais) : reprises en français sur l'écran de chargement, jamais affichées en bas de page. */
.Toastify__toast:not(.Toastify__toast--error) { display: none !important; }
.Toastify { position: relative; z-index: 1000001; }
#s360-loading.lent .lent { display: block; }
#s360-loading button {
  font: inherit; font-weight: 700; color: #fff; border: 0; border-radius: 99px; padding: .5rem 1.1rem; cursor: pointer;
  background: var(--navy);
}
</style>
</head>
<body>
<div id="s360-loading" role="status" aria-live="polite">
  <div class="avion"></div>
  <div class="carte">
    <div class="s360-logo" role="img" aria-label="Air France Industries KLM Engineering &amp; Maintenance"></div>
    <div class="titre">Supply<span>360</span></div>
    <div class="barre"></div>
    <div class="texte">Chargement de Supply360… le premier lancement peut prendre jusqu'à une minute.</div>
    <div class="etape" id="s360-etape">Téléchargement du moteur (stlite)…</div>
    <div class="erreur" id="s360-erreur"></div>
    <div class="lent"><span id="s360-lent">Le chargement est plus long que prévu : le navigateur doit pouvoir accéder à
      cdn.jsdelivr.net et pypi.org (proxy).</span><br><br>
      <button type="button" onclick="location.reload()">Recharger</button>
      <button type="button" onclick="document.getElementById('s360-loading').classList.add('fini')">Afficher la page</button>
    </div>
  </div>
</div>
<div id="root"></div>
<script>
// Surveillance du chargement (script classique : elle fonctionne même si stlite ne se télécharge pas).
(function () {
  const ecran = document.getElementById("s360-loading");
  const etape = document.getElementById("s360-etape");
  const erreur = document.getElementById("s360-erreur");
  const lent = document.getElementById("s360-lent");
  const debut = Date.now();
  const ETAPES = [
    [/Loading Pyodide/i, "Téléchargement du moteur Python (cdn.jsdelivr.net)…", "cdn.jsdelivr.net"],
    [/Mounting files|Unpacking archives/i, "Préparation des fichiers de l'application…", ""],
    [/Installing packages/i, "Installation de pandas, numpy… (cdn.jsdelivr.net, pypi.org)", "cdn.jsdelivr.net et pypi.org"],
    [/Loading streamlit/i, "Chargement de Streamlit…", "cdn.jsdelivr.net"],
    [/loggers|Mocking|Booting/i, "Démarrage de l'application…", ""],
  ];
  let libelle = etape.textContent, hote = "cdn.jsdelivr.net";
  const pret = () => document.querySelector(".s360-header, .stException, [data-testid='stException']");
  window.s360Echec = (message) => {
    if (ecran.classList.contains("echec")) return;
    erreur.textContent = "Le chargement a échoué : " + message;
    lent.textContent = "Vérifiez l'accès à cdn.jsdelivr.net et pypi.org (proxy), puis rechargez la page.";
    ecran.classList.add("echec");
  };
  const suivre = () => {
    if (pret()) { ecran.classList.add("fini"); clearInterval(minuteur); obs.disconnect(); return; }
    const toasts = document.querySelectorAll(".Toastify__toast");
    const err = document.querySelector(".Toastify__toast--error");
    if (err) window.s360Echec(err.innerText.trim().slice(0, 400));
    if (toasts.length) {
      const t = toasts[toasts.length - 1].innerText;
      for (const [motif, texte, h] of ETAPES) if (motif.test(t)) { libelle = texte; if (h) hote = h; }
    }
    const sec = Math.round((Date.now() - debut) / 1000);
    const texte = libelle + "  " + sec + " s";
    if (etape.textContent !== texte) etape.textContent = texte;  // n'écrit que si besoin (pas de boucle)
    if (sec >= 60 && !ecran.classList.contains("echec") && !ecran.classList.contains("lent")) {
      lent.textContent = "Le chargement est plus long que prévu (étape : " + libelle.replace(/….*$/, "") +
        "). Le navigateur doit pouvoir accéder à " + hote + " ; le premier lancement sur un nouveau poste ou une nouvelle adresse est le plus long.";
      if (!ecran.classList.contains("lent")) ecran.classList.add("lent");
    }
  };
  // Observe uniquement l'app (#root, où stlite affiche ses étapes), jamais l'écran de chargement lui-même.
  const obs = new MutationObserver(suivre);
  obs.observe(document.getElementById("root"), { childList: true, subtree: true });
  const minuteur = setInterval(suivre, 1000);
})();
</script>
<script>
// Dossiers mémorisés (Edge / Chrome, API File System Access) : le dossier R2 ou Textile, choisi une fois,
// est retenu dans le navigateur (IndexedDB). Ensuite « Ouvrir R2 » + « Autoriser » liste les chantiers ; les
// fichiers du chantier choisi sont déposés dans la zone d'import de l'app, comme un « Parcourir ». Rien ne
// sort du poste : les fichiers sont lus localement, dans le dossier OneDrive synchronisé.
window.s360Chemins = new Map();  // « nom|taille|date » → chemin relatif (« R2/F-HRBA - 151126/x.xlsx »)
(function () {
  const EXT = /\\.(xlsx|xlsm|csv)$/i;
  const CHANTIER = /([A-Z]{1,2}-?[A-Z0-9]{3,5})\\s*-\\s*(\\d{2})(\\d{2})(\\d{2})(?!\\d)/i;
  const base = () => new Promise((ok, ko) => {
    const r = indexedDB.open("supply360", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("dossiers");
    r.onsuccess = () => ok(r.result); r.onerror = () => ko(r.error);
  });
  const lire = async (cle) => { const db = await base(); return new Promise((ok, ko) => {
    const t = db.transaction("dossiers").objectStore("dossiers").get(cle); t.onsuccess = () => ok(t.result); t.onerror = () => ko(t.error); }); };
  const ecrire = async (cle, v) => { const db = await base(); return new Promise((ok, ko) => {
    const t = db.transaction("dossiers", "readwrite"); t.objectStore("dossiers").put(v, cle); t.oncomplete = ok; t.onerror = () => ko(t.error); }); };
  const autoriser = async (h) => {
    if (!h.queryPermission || (await h.queryPermission({ mode: "read" })) === "granted") return true;
    return (await h.requestPermission({ mode: "read" })) === "granted";
  };
  async function fichiers(dir, chemin, profondeur) {
    const out = [];
    for await (const [nom, e] of dir.entries()) {
      if (e.kind === "file" && EXT.test(nom) && !nom.startsWith("~$")) {
        const f = await e.getFile();
        window.s360Chemins.set(`${f.name}|${f.size}|${f.lastModified}`, `${chemin}/${nom}`);
        out.push(f);
      } else if (e.kind === "directory" && profondeur > 0) {
        out.push(...await fichiers(e, `${chemin}/${nom}`, profondeur - 1));
      }
    }
    return out;
  }
  function deposer(cible, liste) {
    const input = document.querySelector(`.st-key-${cible} input[type=file]`);
    if (!input) throw new Error("zone d'import introuvable sur la page");
    const dt = new DataTransfer();
    liste.forEach((f) => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function fenetre(html) {
    fermer();
    const f = document.createElement("div");
    f.id = "s360-fenetre";
    f.innerHTML = `<div class="boite" role="dialog" aria-modal="true"><button type="button" class="fermer" aria-label="Fermer">✕</button>${html}</div>`;
    f.addEventListener("click", (e) => { if (e.target === f || e.target.closest(".fermer")) fermer(); });
    document.body.append(f);
    return f;
  }
  const fermer = () => document.getElementById("s360-fenetre")?.remove();
  const message = (texte) => fenetre(`<p class="msg">${texte}</p>`);
  async function listeChantiers(h, cible) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const items = [];
    for await (const [nom, e] of h.entries()) {
      const m = e.kind === "directory" && nom.match(CHANTIER);
      if (!m) continue;
      const d = new Date(2000 + +m[4], +m[3] - 1, +m[2]);
      if (!isNaN(d)) items.push({ nom, e, immat: m[1].toUpperCase(), d, j: Math.round((d - today) / 864e5) });
    }
    if (!items.length) {
      message(`Aucun dossier « IMMAT - JJMMAA » dans « ${h.name} ». Vérifiez le dossier choisi (bouton « Changer de dossier »).`);
      return;
    }
    const avenir = items.filter((x) => x.j >= 0).sort((a, b) => a.d - b.d);
    const passes = items.filter((x) => x.j < 0).sort((a, b) => b.d - a.d);
    const dernier = localStorage.getItem("s360-dernier-chantier");
    const ligne = (x, i) => `<button type="button" class="ch${x.nom === dernier ? " dernier" : ""}" data-i="${i}">
      <b>${x.immat}</b><span>début ${x.d.toLocaleDateString("fr-FR")}</span>
      <em>${x.j > 0 ? "À venir · J-" + x.j : x.j === 0 ? "Aujourd'hui" : "Démarré il y a " + -x.j + " j"}</em></button>`;
    const tous = [...avenir, ...passes];
    const f = fenetre(`<h3>Chantier à analyser</h3><p class="sous">Dossier « ${h.name} » · ${tous.length} chantiers</p>
      <input type="search" placeholder="🔎 Immatriculation…" class="filtre">
      <div class="liste">${avenir.map((x) => ligne(x, tous.indexOf(x))).join("")}
      ${passes.length ? `<div class="sep">Chantiers démarrés</div>${passes.map((x) => ligne(x, tous.indexOf(x))).join("")}` : ""}</div>`);
    const filtre = f.querySelector(".filtre");
    filtre.focus();
    filtre.addEventListener("input", () => f.querySelectorAll(".ch").forEach((b) => {
      b.style.display = b.textContent.toUpperCase().includes(filtre.value.trim().toUpperCase()) ? "" : "none"; }));
    f.querySelectorAll(".ch").forEach((b) => b.addEventListener("click", async () => {
      const x = tous[+b.dataset.i];
      localStorage.setItem("s360-dernier-chantier", x.nom);
      message(`Lecture du dossier ${x.nom}…`);
      try {
        const liste = await fichiers(x.e, `${h.name}/${x.nom}`, 2);
        if (!liste.length) { message(`Aucun fichier Excel dans « ${x.nom} ».`); return; }
        deposer(cible, liste); fermer();
      } catch (err) { message("Lecture impossible : " + err.message); }
    }));
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest(".s360-dossier-btn");
    if (!b) return;
    ev.preventDefault();
    const { dossier, cible, mode } = b.dataset;
    if (!window.showDirectoryPicker) {
      message("Le dossier mémorisé fonctionne avec Edge ou Chrome. Utilisez « Parcourir » ci-dessous.");
      return;
    }
    try {
      let h = b.dataset.changer ? null : await lire(dossier);
      if (h && !(await autoriser(h))) return;
      if (!h) {
        h = await window.showDirectoryPicker({ id: `s360-${dossier}`, mode: "read" });
        await ecrire(dossier, h);
      }
      if (mode === "chantier") await listeChantiers(h, cible);
      else if (mode === "dernier") {  // dossier COMMANDE : le fichier le plus récemment modifié
        const liste = await fichiers(h, h.name, 0);
        if (!liste.length) { message(`Aucun fichier Excel dans « ${h.name} ».`); return; }
        deposer(cible, [liste.reduce((a, b) => (b.lastModified > a.lastModified ? b : a))]);
      } else {
        message(`Lecture du dossier ${h.name}…`);
        const liste = await fichiers(h, h.name, 0);
        if (!liste.length) { message(`Aucun fichier Excel ou CSV dans « ${h.name} ».`); return; }
        deposer(cible, liste); fermer();
      }
    } catch (err) {
      if (err.name !== "AbortError") message("Accès au dossier impossible : " + err.message);
    }
  });
})();
</script>
<script type="module">
// Import d'un dossier : stlite n'envoie que le nom du fichier. On transmet son chemin relatif
// (« R2/F-HRBA - 151126/extraction.xlsx ») pour que l'app regroupe les fichiers par dossier chantier.
const ajouterFormData = FormData.prototype.append;
FormData.prototype.append = function (nom, valeur, fichier) {
  if (valeur instanceof File && fichier === undefined) {
    const chemin = window.s360Chemins.get(`${valeur.name}|${valeur.size}|${valeur.lastModified}`) || valeur.webkitRelativePath;
    if (chemin) return ajouterFormData.call(this, nom, valeur, chemin);
  }
  return ajouterFormData.apply(this, arguments);
};

// Import dynamique : un échec de téléchargement de stlite est affiché au lieu de bloquer l'écran de chargement.
import("__CDN__/stlite.js")
  .then(({ mount }) => mount(
    {
      entrypoint: "app/main.py",
      requirements: __REQUIREMENTS__,
      files: __FILES__,
      streamlitConfig: __CONFIG__,
    },
    document.getElementById("root"),
  ))
  .catch((e) => window.s360Echec("impossible de télécharger stlite depuis cdn.jsdelivr.net (" + e + ")"));
</script>
<!-- Thème Supply360 (app/core/theme.css), images incluses : chargé une seule fois.
     Placé en fin de <body> pour passer après les styles que Streamlit ajoute au <head>. -->
<style>
__THEME__
</style>
</body>
</html>
"""


def main() -> None:
    fichiers = lire_fichiers()
    reqs = lire_requirements()
    html = (TEMPLATE
            .replace("__CDN__", STLITE_CDN)
            .replace("__THEME__", css_complet(ASSETS))
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
