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
# Morceaux de l'interface que stlite ne télécharge qu'à la première utilisation d'un composant (tableau, liste
# déroulante, téléchargement…). Ils sont préchargés juste après le démarrage : sinon, après une période
# d'inactivité (connexion proxy expirée), leur téléchargement peut échouer et figer la page jusqu'au rechargement.
# Liste relevée sur un parcours complet de l'app avec stlite {STLITE_VERSION} : À REFAIRE à chaque montée de version.
PRECHARGEMENT = [
    "Checkbox-E_kqAaSQ-XDNDyBvK.js",
    "Close.esm-53Kdm0pn-BTjbStjM.js",
    "DataFrame-D3ov19Re-DgV6QYb0.js",
    "DataFrame-D3ov19Re-DiVf96O7.js",
    "Delete.esm-eQnZPoP6-BmgQoQ39.js",
    "DownloadButton-BCKLqfXu-CxjBVa7P.js",
    "FileDownload.esm-iHteBN-O-B2zuyOVq.js",
    "InputInstructions-kdC8ngsh-DtoZPH3K.js",
    "NumberInput-DB8CmU_F-CTAxqc36.js",
    "Selectbox-CPd6VRVc-CEBySJwc.js",
    "Slider-DZ2YwD_e-BCLslQhV.js",
    "TextField-DMz8flDd-BYc8lIbh.js",
    "TextInput-5lGdvVSD-jkOP18uQ.js",
    "_baseAssignValue-IQwDL8b1-wSPyEqHN.js",
    "assets/1b1a876c211e4f13.wasm",
    "assets/512f7db3dabc21be.woff2",
    "assets/a804e71d97445f8d.woff2",
    "colors-BD7LS4qt-BehGd4Ls.js",
    "createDownloadLinkElement-QSfNRYy1-k2qjp4Ep.js",
    "cubic-Dir1Ko---Ccey17jF.js",
    "defaultLocale-2bEbhetO-QGFVckfi.js",
    "formatMoment-DEtsTHwA-Cy3S6Sp4.js",
    "formatNumber-xp1Ep0f5-DHq-Xx7V.js",
    "iconPosition-DY1kTtFE-C8pN-O4s.js",
    "index-Bh_NXBPX-BZVlUpTI.js",
    "index-CVld_lKx-DBjTNNj_.js",
    "index-CsubvKbq-FbSnpms7.js",
    "index-CtOUUcfI-DNqIEPU5.js",
    "index-DVjwAKiP-zTZQenW8.js",
    "index-Df-1Z3LJ-BbKzDPIK.js",
    "index-DgYQCen1-Bimy2-LT.js",
    "init-5BClRdiB-LyILMlTE.js",
    "inputUtils-DCYiajnz-DpM8zsby.js",
    "linear-CJvvCWKw-rrRTERsA.js",
    "moment-C29_LcvN-QgIIpCw9.js",
    "numbro-CDdPhOTG-vF1UvoJy.js",
    "ordinal-DkyryJlW-DURmPlUH.js",
    "pandasStylerUtils--IM_7ZsY-CD0uJ7uR.js",
    "range-C0hfWAYi-cb33LuVx.js",
    "range-DdOGybNB-Ba7Spj1J.js",
    "reactJsonViewCompat-BquGJEzn-BKjUVnQo.js",
    "resolveDefaultExport-Cy5TTESD-CcwO08HL.js",
    "serialization-BSMBF8e2-CqZaT18J.js",
    "sprintfjs-lt-CVrXF-__7wvrub.js",
    "string-BvOnLx8K-BsWpS-s0.js",
    "styled-components-BNQOantF-DPuk6Rjb.js",
    "threshold-je-9V4hw-qdwK0deF.js",
    "time-p2i1Qn9v-RYMFf5JC.js",
    "useUpdateUiValue-Dpx7InB9-BtZthHVv.js",
    "value-Fb9HFOxE-BHCNJ526.js",
    "withCalculatedWidth-qkUd4en1-CpQUhavR.js",
    "withFullScreenWrapper-D-Ly5q5J-Cy5NDgpz.js",
    "zoom-C9yGXsgU-cg-4X7cE.js",
]

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


def onglets(fichiers: dict[str, str]) -> dict[str, str]:
    """{TAB_ID: TAB_LABEL} des onglets du registre (relance du moteur : retrouver l'onglet de chaque import)."""
    out = {}
    for chemin, code in fichiers.items():
        if chemin.startswith("app/modules/") and not Path(chemin).name.startswith("_"):
            tab_id = re.search(r'^TAB_ID\s*=\s*"([^"]+)"', code, re.M)
            label = re.search(r'^TAB_LABEL\s*=\s*"([^"]+)"', code, re.M)
            if tab_id and label:
                out[tab_id.group(1)] = label.group(1)
    return out


def modules_embarques(fichiers: dict[str, str]) -> list[str]:
    noms = []
    for chemin, code in fichiers.items():
        if chemin.startswith("app/modules/") and not chemin.endswith("__init__.py") and not Path(chemin).name.startswith("_"):
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
#s360-bloque { display: none; position: fixed; z-index: 1000001; left: 50%; bottom: 1.2rem; transform: translateX(-50%);
  width: min(46rem, calc(100vw - 2rem)); padding: .8rem 1.1rem; border-radius: 12px; background: #fff; color: var(--text);
  font-family: var(--font); font-size: .9375rem; box-shadow: 0 10px 30px rgba(0, 0, 0, .25); border-left: 4px solid var(--warn); }
#s360-bloque.visible { display: block; }
#s360-bloque button { font: inherit; font-weight: 700; color: #fff; background: var(--navy); border: 0; border-radius: 99px;
  padding: .3rem .9rem; cursor: pointer; margin-left: .3rem; }
#s360-bloque .actions { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .5rem; }
#s360-bloque .actions button { margin: 0; }
#s360-bloque .recharger { background: #fff; color: var(--navy); border: 1px solid #CFD8E5; }
#s360-bloque details { margin-top: .4rem; color: var(--muted); font-size: .8125rem; }
#s360-bloque pre { max-height: 10rem; overflow: auto; white-space: pre-wrap; margin: .3rem 0; font-size: .75rem; }
#s360-bloque .copier { background: #fff; color: var(--navy); border: 1px solid #CFD8E5; margin: 0; }
#s360-progres { display: none; position: fixed; z-index: 1000001; left: 50%; top: 4.6rem; transform: translateX(-50%);
  width: min(26rem, calc(100vw - 2rem)); padding: .7rem 1rem .8rem; border-radius: 12px; background: #fff;
  font-family: var(--font); box-shadow: 0 10px 30px rgba(0, 20, 60, .22); border-left: 4px solid var(--navy-2); }
#s360-progres.visible { display: block; }
#s360-progres .l { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: .45rem; font-size: .9375rem; color: var(--text); }
#s360-progres .l span { color: var(--muted); font-weight: 700; }
#s360-progres .piste { height: 6px; border-radius: 6px; overflow: hidden; background: #E3E9F1; }
#s360-progres i { display: block; height: 100%; border-radius: 6px; background: linear-gradient(90deg, var(--navy), var(--navy-2));
  transition: width .25s ease; }
#s360-progres.indet i { width: 35%; animation: s360-glisse 1.2s ease-in-out infinite; }
#s360-progres.ok { border-left-color: var(--ok); }
#s360-progres.ok i { background: var(--ok); }
#s360-loading.lent .lent { display: block; }
#s360-loading .avancement { display: none; width: 18rem; height: 8px; border-radius: 8px; overflow: hidden; background: #E3E9F1; }
#s360-loading .avancement i { display: block; height: 100%; width: 3%; border-radius: 8px; transition: width .4s ease;
  background: linear-gradient(90deg, var(--navy), var(--navy-2)); }
#s360-loading.relance .avancement { display: block; }
#s360-loading.relance .barre, #s360-loading.relance .lent, #s360-loading.relance .erreur { display: none; }
#s360-loading.relance .texte { max-width: 26rem; text-align: center; color: var(--text); }
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
// Surveillance du moteur Python (Pyodide, dans un « worker » du navigateur). On note les messages envoyés à
// l'application (clics) et reçus en retour, les erreurs, et on peut sonder le moteur (message « heartbeat » de
// Streamlit, sans effet sur l'app). Si le moteur ne répond plus, un bandeau le signale au lieu d'une page figée.
window.s360Moteur = (function () {
  const journal = [];
  const noter = (m) => {
    journal.push(new Date().toLocaleTimeString("fr-FR") + "  " + String(m).replace(/\\s+/g, " ").slice(0, 600));
    if (journal.length > 30) journal.shift();
  };
  window.addEventListener("error", (e) => noter("Erreur : " + (e.message || e.error)));
  window.addEventListener("unhandledrejection", (e) => noter("Erreur : " + ((e.reason && e.reason.message) || e.reason)));
  const consoleErreur = console.error;
  console.error = function (...a) { try { noter(a.map((x) => (x && x.message) || x).join(" ")); } catch (_) {} return consoleErreur.apply(this, a); };
  const etat = { worker: null, envoi: 0, recu: Date.now(), mort: "" };
  const W = window.Worker;
  window.Worker = function (...args) {
    const w = new W(...args);
    etat.worker = w;
    w.addEventListener("message", (e) => {
      etat.recu = Date.now();
      const d = e.data;
      if (d && d.type === "s360:journal") {  // erreur Python transmise par core/journal.py
        noter("Python " + d.texte);
        if (/report this bug|RuntimeStoppedError/.test(d.texte)) etat.mort = "erreur interne de Streamlit";
        if (d.evenement === "session_fermee") etat.mort = "session du moteur fermée";
      }
    });
    w.addEventListener("error", (e) => { etat.mort = e.message || "erreur du moteur"; noter("Moteur arrêté : " + etat.mort); });
    const envoyer = w.postMessage.bind(w);
    w.postMessage = function (m, t) {
      if (m && m.type === "websocket:send") etat.envoi = Date.now();
      if (m && m.type === "http:request") window.s360Moteur.ecouteurs.forEach((f) => f(m));  // suivi des imports
      return envoyer(m, t);
    };
    return w;
  };
  window.Worker.prototype = W.prototype;
  // BackMsg { appHeartbeat: true } (champ 17, booléen ; étiquette varint 0x88 0x01, valeur 1) : Streamlit répond par un « heartbeat_ack ».
  const sonder = () => {
    if (!etat.worker) return;
    const canal = new MessageChannel();
    canal.port1.onmessage = () => canal.port1.close();
    etat.worker.postMessage({ type: "websocket:send", data: { payload: new Uint8Array([136, 1, 1]) } }, [canal.port2]);
  };
  // Python lui-même répond-il ? (commande interne de stlite, hors session Streamlit) : s'il répond alors que la
  // session ne répond plus, la session est bloquée (pas un long calcul) → relance immédiate.
  const pingPython = (delai = 3000) => new Promise((ok) => {
    if (!etat.worker) return ok(false);
    const canal = new MessageChannel();
    const t = setTimeout(() => ok(false), delai);
    canal.port1.onmessage = () => { clearTimeout(t); canal.port1.close(); ok(true); };
    etat.worker.postMessage({ type: "run_python", data: { code: "1" } }, [canal.port2]);
  });
  return { etat, journal, noter, sonder, pingPython, ecouteurs: new Set() };
})();
</script>
<script>
// Le bouton de téléchargement de Streamlit « vérifie » son adresse interne (https://stlite.invalid/…) par une vraie
// requête réseau, qui part vers le proxy et échoue. On y répond localement : aucune requête inutile.
const fetchOrigine = window.fetch;
window.fetch = function (ressource, options) {
  const url = typeof ressource === "string" ? ressource : ressource && ressource.url;
  if (url && url.startsWith("https://stlite.invalid/")) return Promise.resolve(new Response(null, { status: 204 }));
  return fetchOrigine.apply(this, arguments);
};
</script>
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
  // Après le démarrage : bandeau si le moteur s'arrête, ne répond plus (aucune réponse 20 s après un clic ou une
  // sonde) ou si un calcul dure anormalement (plus de 90 s). La sonde part toutes les 30 s d'inactivité, et dès
  // que l'on revient sur l'onglet : un blocage est signalé avant même le prochain clic.
  const surveiller = () => {
    const M = window.s360Moteur;
    let depuis = null, affiche = "";
    const bandeau = document.createElement("div");
    bandeau.id = "s360-bloque";
    document.body.append(bandeau);
    const afficher = (titre, texte) => {
      const cle = titre + texte;
      if (cle === affiche) return;
      affiche = cle;
      if (!titre) { bandeau.classList.remove("visible"); return; }
      bandeau.innerHTML = "<b></b> <span></span><div class='actions'><button type='button' class='relancer'>Relancer en gardant mes " +
        "fichiers</button><button type='button' class='recharger'>Recharger la page</button></div>" +
        "<details><summary>Détails techniques</summary><pre></pre><button type='button' class='copier'>Copier</button></details>";
      bandeau.querySelector("b").textContent = titre;
      bandeau.querySelector("span").textContent = texte;
      bandeau.querySelector("pre").textContent = M.journal.join("\\n") || "Aucune erreur enregistrée.";
      bandeau.querySelector(".recharger").onclick = () => location.reload();
      bandeau.querySelector(".relancer").onclick = () => { bandeau.classList.remove("visible"); affiche = ""; window.s360Relancer(); };
      bandeau.querySelector(".copier").onclick = () => navigator.clipboard && navigator.clipboard.writeText(
        titre + "\\n" + navigator.userAgent + "\\n" + M.journal.join("\\n"));
      bandeau.classList.add("visible");
    };
    // Attente d'une réponse du moteur : « Calcul en cours » affiché tout de suite (même pendant un traitement d'import,
    // avant que Streamlit ne signale le calcul). Sans réponse pendant 60 s (onglet visible, sonde comprise), le moteur
    // est relancé AUTOMATIQUEMENT en gardant les fichiers ; une seconde fois en moins de 5 min : bandeau.
    let attente = null, derniereRelance = 0, sondeEnvoyee = false, ping = "";
    const relancerAuto = (raison) => {
      if (Date.now() - derniereRelance < 300000) return false;
      derniereRelance = Date.now();
      M.noter("Relance automatique : " + raison);
      window.s360Relancer(raison);
      return true;
    };
    const bloque = () => afficher("⚠️ L'application ne répond plus.", "Relancez le moteur : vos fichiers sont réimportés automatiquement.");
    const verifier = () => {
      const e = M.etat, now = Date.now();
      const enCours = !!document.querySelector(".stApp[data-test-script-state='running']");
      depuis = enCours ? depuis || now : null;
      attente = e.envoi > e.recu && !enCours ? attente || e.envoi : null;
      if (!attente) { sondeEnvoyee = false; ping = ""; }
      document.body.classList.toggle("s360-attente", !!attente && now - attente > 500 && !window.s360EnRelance);
      const visible = document.visibilityState === "visible";
      if (window.s360EnRelance) { afficher("", ""); return; }
      if (e.mort) {
        if (!relancerAuto(e.mort)) afficher("⛔ Le moteur de calcul s'est arrêté.", "Relancez-le : vos fichiers sont réimportés automatiquement.");
        return;
      }
      // 6 s sans réponse : Python répond-il en direct ? Oui → session bloquée : relance tout de suite.
      // Non → Python calcule ou est arrêté : relance au bout de 30 s sans aucune réponse.
      if (attente && visible && now - attente > 6000 && !ping) {
        ping = "en cours";
        M.pingPython().then((repond) => {
          if (!attente) return;
          ping = repond ? "session bloquée" : "occupé";
          if (repond && !relancerAuto("session bloquée (le moteur répond, mais plus aux clics)")) bloque();
        });
      }
      if (attente && visible && now - attente > 20000 && !sondeEnvoyee) { sondeEnvoyee = true; M.sonder(); }
      // Python muet lui aussi (moteur arrêté, ou calcul bloquant hors calcul Streamlit) : relance au bout de 30 s.
      if (attente && visible && now - attente > 30000 && ping === "occupé") {
        if (!relancerAuto("aucune réponse depuis " + Math.round((now - attente) / 1000) + " s")) bloque();
      } else if (depuis && now - depuis > 90000)
        afficher("⏳ Le calcul dure plus longtemps que prévu.", "Si la page ne répond plus, relancez le moteur (fichiers conservés).");
      else if (ping !== "session bloquée") afficher("", "");
      if (!enCours && visible && e.envoi <= e.recu && now - e.recu > 30000) { e.envoi = now; M.sonder(); }
    };
    setInterval(verifier, 1000);
    // Export Excel préparé à la demande (components.telecharger) : le bouton de téléchargement apparaît, on le clique.
    setInterval(() => {
      document.querySelectorAll('[class*="__auto"] [data-testid="stDownloadButton"] button:not([data-s360-clique])').forEach((b) => {
        b.setAttribute("data-s360-clique", "1");
        b.click();
      });
    }, 400);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") return;
      if (attente) attente = Date.now();  // onglet en arrière-plan : le moteur a pu être ralenti, on lui laisse 60 s
      else { M.etat.envoi = Date.now(); M.sonder(); }
    });
  };
  // Préchargement (voir PRECHARGEMENT dans build.py) : un fichier à la fois, quand le navigateur est libre ;
  // les échecs sont retentés une minute plus tard. Ensuite, l'app n'a plus besoin du réseau.
  const precharger = (liste = __PRECHARGEMENT__) => {
    const echecs = [];
    const suivant = (i) => {
      if (i >= liste.length) { if (echecs.length) setTimeout(() => precharger(echecs), 60000); return; }
      const url = "__CDN__/" + liste[i];
      const p = url.endsWith(".js") ? import(url) : fetch(url, { cache: "force-cache" }).then((r) => r.arrayBuffer());
      p.catch(() => echecs.push(liste[i])).finally(() => (window.requestIdleCallback || setTimeout)(() => suivant(i + 1)));
    };
    suivant(0);
  };
  window.s360Echec = (message) => {
    if (ecran.classList.contains("echec")) return;
    erreur.textContent = "Le chargement a échoué : " + message;
    lent.textContent = "Vérifiez l'accès à cdn.jsdelivr.net et pypi.org (proxy), puis rechargez la page.";
    ecran.classList.add("echec");
  };
  const suivre = () => {
    if (pret()) { ecran.classList.add("fini"); clearInterval(minuteur); obs.disconnect(); precharger(); surveiller(); return; }
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
window.s360Chemins = new Map();  // « nom|taille|date » → chemin relatif (« R2/F-XKAA - 151126/x.xlsx »)
window.s360Poignees = new WeakMap();  // fichier → poignée du dossier mémorisé
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
  // Barre de progression des imports : lecture des fichiers (i / n), envoi au moteur Python (i / n : un fichier
  // OneDrive « en ligne seulement » est téléchargé à ce moment-là), puis analyse (jusqu'à la fin du calcul).
  const progres = (() => {
    let el = null, fin = null;
    const montrer = (titre, i, n) => {
      if (!el) {
        el = document.createElement("div");
        el.id = "s360-progres";
        el.innerHTML = "<div class='l'><b></b><span></span></div><div class='piste'><i></i></div>";
        document.body.append(el);
      }
      clearTimeout(fin);
      el.className = "visible" + (n ? "" : " indet");
      el.querySelector("b").textContent = titre;
      el.querySelector("span").textContent = n ? `${i} / ${n}` : "";
      el.querySelector("i").style.width = n ? `${Math.max(4, Math.round(i / n * 100))}%` : "";
    };
    const cacher = (texte) => {
      if (!el) return;
      if (texte) { montrer(texte, 1, 1); el.classList.add("ok"); el.querySelector("span").textContent = ""; }
      fin = setTimeout(() => el.classList.remove("visible"), texte ? 1800 : 0);
    };
    const suivre = (n) => {
      const M = window.s360Moteur, debut = Date.now();
      let envoyes = 0, dernier = Date.now(), vu = false;
      const ecoute = (m) => {
        const r = (m.data && m.data.request) || {};
        if (/upload_file/.test(String(r.path || r.url || ""))) { envoyes++; dernier = Date.now(); }
      };
      M.ecouteurs.add(ecoute);
      montrer("Envoi des fichiers à Supply360…", 0, n);
      const tic = setInterval(() => {
        const enCours = !!document.querySelector(".stApp[data-test-script-state='running']");
        vu = vu || enCours;
        if (!vu && envoyes < n) montrer("Envoi des fichiers à Supply360…", envoyes, n);
        else if (enCours || !vu) montrer("Analyse des fichiers…", 0, 0);
        const fini = (vu && !enCours) || (envoyes >= n && !vu && Date.now() - dernier > 6000);
        if (fini || Date.now() - debut > 300000) {
          clearInterval(tic);
          M.ecouteurs.delete(ecoute);
          cacher(fini ? `✓ ${n} fichier${n > 1 ? "s" : ""} importé${n > 1 ? "s" : ""}` : "");
        }
      }, 250);
    };
    return { montrer, cacher, suivre };
  })();
  window.s360Progres = progres;
  async function fichiers(dir, chemin, profondeur) {
    const poignees = [];
    const parcourir = async (d, ch, p) => {
      for await (const [nom, e] of d.entries()) {
        if (e.kind === "file" && EXT.test(nom) && !nom.startsWith("~$")) poignees.push([e, `${ch}/${nom}`]);
        else if (e.kind === "directory" && p > 0) await parcourir(e, `${ch}/${nom}`, p - 1);
      }
    };
    await parcourir(dir, chemin, profondeur);
    const out = [];
    for (const [i, [e, ch]] of poignees.entries()) {
      progres.montrer("Lecture des fichiers…", i, poignees.length);
      const f = await e.getFile();
      window.s360Chemins.set(`${f.name}|${f.size}|${f.lastModified}`, ch);
      window.s360Poignees.set(f, e);  // relance du moteur : fichier relu sur le disque (OneDrive a pu le mettre à jour)
      out.push(f);
    }
    return out;
  }
  function deposer(cible, liste) {
    const input = document.querySelector(`[class*="st-key-${cible}"] input[type=file]`);  // clé versionnée (…upload3)
    if (!input) throw new Error("zone d'import introuvable sur la page");
    const dt = new DataTransfer();
    liste.forEach((f) => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    progres.suivre(liste.length);
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
      fermer();
      try {
        const liste = await fichiers(x.e, `${h.name}/${x.nom}`, 2);
        if (!liste.length) { progres.cacher(); message(`Aucun fichier Excel dans « ${x.nom} ».`); return; }
        deposer(cible, liste);
      } catch (err) { progres.cacher(); message("Lecture impossible : " + err.message); }
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
        if (!liste.length) { progres.cacher(); message(`Aucun fichier Excel dans « ${h.name} ».`); return; }
        deposer(cible, [liste.reduce((a, b) => (b.lastModified > a.lastModified ? b : a))]);
      } else {
        const liste = await fichiers(h, h.name, 0);
        if (!liste.length) { progres.cacher(); message(`Aucun fichier Excel ou CSV dans « ${h.name} ».`); return; }
        deposer(cible, liste);
      }
    } catch (err) {
      progres.cacher();
      if (err.name !== "AbortError") message("Accès au dossier impossible : " + err.message);
    }
  });
})();
</script>
<script>
// Relance du moteur sans perdre les fichiers. Chaque import (📂 Ouvrir ou Parcourir) est retenu EN MÉMOIRE de la
// page (rien n'est écrit sur le disque) : clé de la zone d'import + fichiers. Si le moteur Python s'arrête ou ne
// répond plus, « Relancer » redémarre stlite (sans recharger la page) puis redépose chaque import dans sa zone,
// onglet par onglet, dans l'ordre d'origine.
(function () {
  const ONGLETS = __ONGLETS__;  // TAB_ID → libellé de l'onglet
  const imports = [];
  window.s360Imports = imports;  // (lecture seule : diagnostic)
  let rejeu = false;
  const cleDe = (el) => {
    const c = el.closest('[class*="st-key-"]');
    const m = c && [...c.classList].map((x) => x.match(/^st-key-(.+)$/)).find(Boolean);
    return m ? m[1].replace(/(__upload)\\d*$/, "$1") : null;
  };
  const ongletActif = () => {
    const b = document.querySelector('.st-key-s360_nav button[aria-checked="true"], .st-key-s360_nav button[data-selected="true"]');
    const lib = b ? b.textContent : "";
    return Object.keys(ONGLETS).find((id) => lib.includes(ONGLETS[id])) || Object.keys(ONGLETS)[0];
  };
  document.addEventListener("change", (e) => {
    const inp = e.target;
    if (rejeu || !(inp instanceof HTMLInputElement) || inp.type !== "file" || !inp.files || !inp.files.length) return;
    const cle = cleDe(inp);
    if (!cle) return;
    const onglet = cle.startsWith("commun__") ? ongletActif() : cle.split("__")[0];
    for (let i = imports.length - 1; i >= 0; i--) if (imports[i].cle === cle) imports.splice(i, 1);  // une sélection remplace l'autre
    imports.push({ cle, onglet, fichiers: [...inp.files] });
  }, true);
  const pause = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const M = () => window.s360Moteur;
  const occupe = () => !document.querySelector(".s360-header") || !!document.querySelector(".stApp[data-test-script-state='running']")
    || M().etat.envoi > M().etat.recu;
  const libre = async (max = 180000) => {  // attend la fin du calcul Streamlit (et des réponses du moteur)
    const debut = Date.now();
    await pause(400);
    let calme = 0;
    while (Date.now() - debut < max) {
      calme = occupe() ? 0 : calme + 1;
      if (calme >= 6) return;
      await pause(250);
    }
  };
  // Dépôt de fichiers dans une zone d'import, puis attente : envoi de TOUS les fichiers au moteur, puis fin du calcul.
  const deposerEtAttendre = (input, fichiers) => new Promise((ok) => {
    let envoyes = 0, dernier = Date.now(), vu = false;
    const debut = Date.now();
    const ecoute = (m) => {
      const r = (m.data && m.data.request) || {};
      if (/upload_file/.test(String(r.path || ""))) { envoyes++; dernier = Date.now(); }
    };
    M().ecouteurs.add(ecoute);
    const dt = new DataTransfer();
    fichiers.forEach((f) => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const tic = setInterval(() => {
      const o = occupe();
      if (envoyes >= fichiers.length && o) vu = true;
      const fini = envoyes >= fichiers.length && !o && Date.now() - dernier > 1200 && (vu || Date.now() - dernier > 6000);
      if (fini || Date.now() - debut > 240000) { clearInterval(tic); M().ecouteurs.delete(ecoute); ok(fini); }
    }, 150);
  });
  const ouvrirOnglet = async (id) => {
    const b = [...document.querySelectorAll(".st-key-s360_nav button")].find((x) => x.textContent.includes(ONGLETS[id]));
    if (b && !b.matches('[aria-checked="true"], [data-selected="true"]')) { b.click(); await libre(); }
  };
  // Écran de relance : celui du chargement (logo, Supply360, avion) avec une barre d'avancement.
  const ecran = (() => {
    const el = document.getElementById("s360-loading");
    let barre = el.querySelector(".avancement");
    if (!barre) {
      barre = document.createElement("div");
      barre.className = "avancement";
      barre.innerHTML = "<i></i>";
      el.querySelector(".barre").after(barre);
    }
    return {
      montrer(texte, etape, pct) {
        el.classList.remove("fini", "lent", "echec");
        el.classList.add("relance");
        el.querySelector(".texte").textContent = texte;
        el.querySelector(".etape").textContent = etape;
        barre.querySelector("i").style.width = Math.max(3, Math.min(100, pct)) + "%";
      },
      cacher() { el.classList.add("fini"); setTimeout(() => el.classList.remove("relance"), 600); },
    };
  })();
  window.s360Relancer = async (raison) => {
    const Mo = M(), retour = ongletActif();
    if (window.s360EnRelance) return;
    window.s360EnRelance = true;
    const titre = raison ? "Le moteur de calcul ne répondait plus : relance automatique, vos fichiers sont conservés."
      : "Relance du moteur de calcul, vos fichiers sont conservés.";
    let pct = 2;
    const montee = setInterval(() => { pct += (55 - pct) * 0.06; ecran.montrer(titre, "Redémarrage du moteur Python…", pct); }, 400);
    const echecs = [];
    try {
      ecran.montrer(titre, "Redémarrage du moteur Python…", pct);
      try { window.s360App && window.s360App.unmount(); } catch (_) { /* moteur déjà arrêté */ }
      Mo.etat.mort = ""; Mo.etat.envoi = 0; Mo.etat.recu = Date.now();
      await window.s360Monter();
      await libre(300000);
      clearInterval(montee);
      rejeu = true;
      const ordre = [...new Set(imports.map((x) => x.onglet))];
      let n = 0;
      for (const id of ordre) {
        await ouvrirOnglet(id);
        for (const imp of imports.filter((x) => x.onglet === id)) {
          n++;
          ecran.montrer(titre, `Réimport de vos fichiers (${n} / ${imports.length}) : ${ONGLETS[id] || ""}…`, 55 + 45 * (n - 1) / imports.length);
          // fichiers relus sur le disque quand ils viennent d'un dossier mémorisé (version à jour, lisible)
          const fichiers = [];
          for (const f of imp.fichiers) {
            const h = window.s360Poignees.get(f);
            try { fichiers.push(h ? await h.getFile() : f); } catch (_) { fichiers.push(f); }
          }
          // zone d'origine ; à défaut (zone absente, ex. type d'étude différent) l'import du dossier de l'onglet,
          // qui reconnaît chaque fichier par son contenu
          const input = document.querySelector(`[class*="st-key-${imp.cle}"] input[type=file]`)
            || document.querySelector(`[class*="st-key-${id}__dossier__upload"] input[type=file]`);
          if (!input || !(await deposerEtAttendre(input, fichiers))) echecs.push(imp.fichiers.map((f) => f.name).join(", "));
        }
      }
      await ouvrirOnglet(retour);
      ecran.montrer(titre, echecs.length ? "Terminé, sauf : " + echecs.join(" ; ") : "✓ Moteur relancé, fichiers réimportés", 100);
      if (echecs.length) Mo.noter("Réimport incomplet : " + echecs.join(" ; "));
      await pause(echecs.length ? 4000 : 900);
      ecran.cacher();
    } catch (err) {
      Mo.noter("Relance impossible : " + err);
      location.reload();
    } finally {
      clearInterval(montee);
      rejeu = false;
      window.s360EnRelance = false;
    }
  };
})();
</script>
<script type="module">
// Import d'un dossier : stlite n'envoie que le nom du fichier. On transmet son chemin relatif
// (« R2/F-XKAA - 151126/extraction.xlsx ») pour que l'app regroupe les fichiers par dossier chantier.
const ajouterFormData = FormData.prototype.append;
FormData.prototype.append = function (nom, valeur, fichier) {
  if (valeur instanceof File && fichier === undefined) {
    const chemin = window.s360Chemins.get(`${valeur.name}|${valeur.size}|${valeur.lastModified}`) || valeur.webkitRelativePath;
    if (chemin) return ajouterFormData.call(this, nom, valeur, chemin);
  }
  return ajouterFormData.apply(this, arguments);
};

// Import dynamique : un échec de téléchargement de stlite est affiché au lieu de bloquer l'écran de chargement.
// s360Monter est réutilisé par la relance du moteur (bandeau « L'application ne répond plus »).
const OPTIONS = {
  entrypoint: "app/main.py",
  requirements: __REQUIREMENTS__,
  files: __FILES__,
  streamlitConfig: __CONFIG__,
};
window.s360Monter = () => import("__CDN__/stlite.js").then(({ mount }) => {
  window.s360App = mount(OPTIONS, document.getElementById("root"));
});
window.s360Monter().catch((e) => window.s360Echec("impossible de télécharger stlite depuis cdn.jsdelivr.net (" + e + ")"));
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
            .replace("__PRECHARGEMENT__", js(PRECHARGEMENT))
            .replace("__ONGLETS__", js(onglets(fichiers)))
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
