# Supply360 · Air France Industries

Plateforme de pilotage de la supply chain des équipements cabine, livrée sous forme d'**un seul
fichier HTML** : `dist/supply360.html`.

## Utilisation

1. Ouvrir `supply360.html` par **double-clic** (Edge ou Chrome). Aucun serveur, aucune installation.
2. Au premier lancement, le navigateur télécharge son moteur Python (environ 15 s) depuis
   `cdn.jsdelivr.net`, plus un petit paquet depuis `pypi.org` / `files.pythonhosted.org`. Ces adresses
   doivent être accessibles via le proxy. Les lancements suivants profitent du cache du navigateur.
3. Importer les fichiers dans l'onglet voulu. Ils sont **traités localement dans le navigateur** et
   ne sont envoyés nulle part.
4. Le fichier **Commandes (SAP)** est commun : importé une fois, il sert à tous les onglets. L'**État du
   stock** est propre à chaque onglet. Changer d'onglet conserve fichiers, filtres et paramètres.
5. Rafraîchir la page **réinitialise tout** : il faut alors réimporter les fichiers.

Pendant un calcul, la barre sous le header s'anime et la pastille « Calcul en cours… » s'affiche.

**Design** : chaque onglet a sa couleur (en-tête de page, onglet actif). En haut de chaque onglet, l'encadré de droite
rappelle le contexte (chantier et date de début, date des données…). Les tableaux d'actions affichent le statut en
badge coloré et se filtrent d'un clic sur les pastilles au-dessus ; le bouton **Exporter (Excel)** de chaque bloc
produit un fichier avec les mêmes colonnes, dans le même ordre, et les mêmes couleurs de statut.

## Organisation des dossiers et import

Version en ligne : **https://n-dras.github.io/Supply360/** (republiée automatiquement à chaque mise à
jour). Les fichiers importés restent dans le navigateur : rien n'est envoyé, ni à GitHub ni ailleurs.

```
SharePoint (canal Teams MS-LGT1-Analystes, bibliothèque Documents)
├── COMMANDE/          fichier Commandes (SAP) à jour (le plus récent est pris) — c'est lui qui fait foi
├── Textile/           « Résultat … ALL TEXTILE » (État du stock de Textile cabine), « Résultat … PE » (État du
│                      stock de PE mousses), « textile_master_export » (Références textile),
│                      « textile_all_parts » (Pièces par avion)
│                      « PE_MOUSSE_JJMMAAAA » (âge des mousses, fichier mensuel tel quel)
│                      « Besoin_Prod… » (objectif PE mousses de l'année : avions et CCN par type d'avion)
└── R2/                un dossier par chantier : <IMMAT> - <JJMMAA>
    ├── F-XKAA - 151126/   Besoins LOGOPS (ou étude ASREQ), État du stock
    └── F-XKBB - 030227/
```

**Première utilisation (une fois par poste)** : aide « 🔗 Première utilisation » de l'onglet → ouvrir le dossier
sur SharePoint → « Ajouter un raccourci à Mon OneDrive » (idéalement la bibliothèque Documents entière). Les
dossiers apparaissent dans l'Explorateur et restent à jour ; rien n'est copié, chacun le fait avec son compte.

**Ensuite (Edge ou Chrome)** : boutons **Ouvrir R2**, **Ouvrir Textile**, **Ouvrir COMMANDE**. La première
fois, choisissez le dossier ; le navigateur le retient (« dossier mémorisé »). Les fois suivantes, même après
actualisation : clic sur le bouton → **Autoriser** →
- **R2** : liste des chantiers (à venir d'abord, avec J-x), recherche par immatriculation ; seuls les fichiers du
  chantier choisi sont lus. Le fichier « Résultat… » est toujours l'État du stock ; les autres sont reconnus par
  leurs en-têtes (30 premières lignes), à défaut par leur nom (« LOGOPS » = Besoins chantier). Un fichier écarté est
  signalé avec la raison (« non reconnu » ou « reconnu comme … ») ;
- **Textile** : tous les fichiers du dossier ;
- **COMMANDE** : le fichier le plus récemment modifié, commun à tous les onglets.

« Changer de dossier » pour en choisir un autre. Sans Edge/Chrome : « Parcourir » (import manuel), toujours disponible.

**Commandes (SAP)** : seul le fichier du dossier COMMANDE fait foi ; un fichier de commandes trouvé dans un dossier
R2 ou Textile est ignoré (c'est signalé).

**Textile** : le nom fait foi — « textile_master_export », « textile_all_parts », et pour l'État du stock :
- l'onglet **Textile cabine** prend le **« Résultat … ALL TEXTILE » le plus récent** ;
- l'onglet **PE mousses** prend le **« Résultat … PE » le plus récent** ;
- chaque onglet laisse de côté le Résultat de l'autre, sans le signaler. S'il n'y a ni « ALL TEXTILE » ni « PE » dans
  les noms, tout « Résultat » est accepté. Si aucun fichier ne porte ces noms, la reconnaissance par le contenu prend
  le relais.

« Le plus récent » : la date écrite dans le nom si elle existe, sinon la **date de modification** du fichier.

Sinon, les fichiers sont reconnus par leur **contenu** (en-têtes de colonnes), quel que soit leur nom ; à défaut
par un mot du nom (`logops`, `asreq`, `stock`, `commande`/`sap`, `reference`, `piece`). Si un dossier
contient plusieurs fichiers du même type, le plus récent (date dans le nom, ex. `20261020`) est retenu et
peut être changé dans la liste. Les fichiers non reconnus sont ignorés et signalés. Tout est lu localement :
rien n'est envoyé.

## Onglets

### 🛠️ Stock par chantier (GEAV)

Pièces à **commander** et fournisseurs à **relancer** avant le début d'un chantier.

**Paramètres** (bouton « Paramètres » du bloc d'import) : type d'étude (Classique ou ASREQ/NOREQ), date de début du chantier, codes Gestion du
périmètre (par défaut 245, 246, 247, 400, 401, 230).

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| Besoins chantier (LOGOPS) — étude Classique | `MPN Prime`, `Qty` | `Task TRFX` / `Task Name` / `Task WP Line`, `Requestid` (→ RRS), `Description` |
| Étude ASREQ/NOREQ — `.xlsm`, feuille `Ordered`, en-tête en ligne 6 | `PN + infos pièce sortie`, `Qty` | `ID BARECODE` |
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `QTE SAR` (→ SAR), `Purchase Req.` (→ PR), `GESTION`, `CODE AGT APPRO` (→ Code agent), `CODE FOURNISSEUR`, `DERNIER FOURNISSEUR`, `CCN`, `CLASS CODE`, `TRACKING LEVEL` |
| Commandes (SAP) — feuille « Toutes les commandes » de préférence | `PN` | `Commande`, `Gestion`, `Code fournisseur`, `Fournisseur`, `Date de livraison promise`, `Date de livraison demandée`, `Class code`, `CCN` |

**En-tête** : immatriculation, **type d'avion** (reconnu par la série d'immatriculation : F-HTY… / F-HUV… = A350, F-GZC… = A330,
F-HZU… / F-HPN… / F-HOZ… = A220, famille A320, B777-200 / -300, B787) et son image, début du chantier (J-x), type d'étude.

**Résultat** : synthèse, actions à lancer (classe 8/9 en tête, avec
un drapeau), tableau filtrable, toutes les références, export `Supply360_stock_chantier_AAAAMMJJ.xlsx` (un seul bouton
**Exporter (Excel)**, en haut de la synthèse).

Colonnes des tableaux (et de l'export), dans cet ordre : Statut, PN, CCN, **RRS**, À commander, Besoin, Stock,
En cmd, **SAR**, **PR**, N° commande, PSD, Fournisseur, Code fournisseur, Action, **Code agent**, Gestion, TL,
Date chantier (puis TRFX et Class code).

- **Besoin** = somme de toutes les lignes LOGOPS du PN : un même PN demandé par plusieurs TRFX / RRS forme un
  seul besoin, additionné (TRFX et RRS listés « A | B ») ; **À commander** = max(0, besoin − stock − en commande).
- **Code agent** = `CODE AGT APPRO` de l'État du stock : c'est le contact indiqué dans les actions (le code
  acheteur des commandes n'est plus utilisé).
- **TL** (tracking level, `TRACKING LEVEL`) : 0 = consommable, 1 = réparable.

### 🧵 Textile cabine

Stock, consommation, commandes et retards fournisseurs des ceintures, housses, mousses et rideaux.

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `DESCRIPTION`, `QTE CONSO 12M / 18M / 24M`, `QTE CONSO <année>`, `Dernier PU (achat) Euros`, `DATE DERNIERE CONSO`, `B/O`, `RP`, `EOQ`, `TDD` |
| Commandes (SAP) | `PN`, `Commande` | `Fournisseur`, `Code fournisseur`, `Date d'émission de la commande`, `Date de livraison demandée / promise`, `Quantité restant à livrer` |
| Références textile — feuille « PN Catalog » | `pn`, `equipment` | `description`, `ccn` |
| Pièces par avion (textile_all_parts) — CSV ou Excel | `equipment`, `aircraft_type`, `group`, `registration`, `area`, `ccn`, `pn`, `description`, `qty_per_ac` | |

Seul l'État du stock est indispensable ; les autres fichiers complètent l'analyse. La Prévision
fonctionne avec le seul État du stock (consommation) ; Pièces par avion y ajoute le stock minimum par flotte et le filtre Flotte.

**Croisement par CCN** : une même pièce peut avoir un PN différent d'un fichier à l'autre. Elle est reconnue par son PN,
à défaut par son **CCN** : une ligne de commande écrite avec un autre PN est rattachée au PN du stock de même CCN (le PN
de la commande reste visible dans « PN commandé »). Le CCN est affiché à côté du PN dans les tableaux.

**Barre « Flotte · Équipement »** sous les sous-onglets : Flotte (types d'avion du fichier Pièces par avion : pièces
montées sur ces avions, par PN ou CCN) et Équipement (Ceinture, Housse, Mousse, Rideaux). « Toutes » par défaut, un
clic choisit une valeur, plusieurs choix possibles. S'applique à tous les sous-onglets et à l'export.

**Sous-onglets** : Synthèse (relances fournisseurs, valeur et activité du stock par catégorie),
**Stock** (état des stocks, voir ci-dessous), Commandes (statuts, livraisons, profondeur des retards, toutes les lignes),
Fournisseurs (lignes en cours, retards, délais promis, BFE, vue par fournisseur),
**Consommation** (sorties sur 12 mois avec la période écrite, valeur sortie, tendance par rapport aux 12 mois d'avant,
sorties par année et par équipement, les 10 PN qui sortent le plus, sorties par année d'un PN),
**Prévision** (période écrite en clair ; à commander maintenant, plus tard, total ; tableau des commandes à passer ;
par fournisseur). Export `Supply360_textiles_AAAAMMJJ.xlsx` (avec les feuilles de prévision si elle est calculée).

**Stock** : pour chaque PN, la **couverture** = stock sur étagère ÷ consommation mensuelle (12 derniers mois).
Statuts, par ordre de priorité : **Obsolète / supprimé** (CLASS CODE de l'État du stock = 3 obsolète, 8 en cours de
suppression ou 9 supprimé : compté à part, jamais en surstock ni en rupture, jamais proposé à la commande), **Jamais
consommé** (dernière conso en 2001, date fictive : compté à part, pas en surstock), **Surstock (dormant)** (du stock
mais aucune consommation depuis 3 ans, sur 24 mois glissants et les 3 dernières années civiles, même avec une commande
en cours), **Sans conso** (aucune consommation sur 12 mois mais consommé dans les 3 ans, ou ni stock ni conso),
**Rupture** (consommé sur 12 mois, stock à 0), **Critique** (moins de 1 mois de stock, seuil réglable), **Bas** (moins de
3 mois), **Correct** (jusqu'à 24 mois), **Couverture élevée** (au-delà : le PN est consommé, ce n'est pas du surstock).
On y trouve : les tuiles (répartition, ruptures, critiques, valeur du surstock dormant, valeur obsolète / supprimée),
le niveau de stock par catégorie et la valeur du stock par statut côte à côte, puis le tableau de tous les PN avec CCN
et classe code. Règles et seuil dans le popover « Règles de calcul et seuil ». Feuille « État des stocks » dans l'export.

**Règles** : retard = date promise − date demandée au-delà de 10 jours de tolérance ; date promise 2001,
2030 ou plus (ou vide) = sans date promise ; 2049 = en attente de BFE. PN **dormant** = du stock mais
aucune consommation sur 3 ans ; **inactif** = ni stock, ni consommation, ni commande.

**Prévision de commandes** (détail dans « Comment c'est calculé ») — fondée sur la **consommation**, pas sur la PE
(elle n'existe pas pour tous les équipements textile) ni sur les sorties de flotte :

- **consommation prévue** d'un PN par mois = moyenne des rythmes `QTE CONSO 12M`, `18M` et `24M` du Résultat, le plus
  récent pesant le plus (50 / 30 / 20 %) ; **tendance** = 12 derniers mois comparés aux 12 mois d'avant (24M − 12M) :
  en hausse (> +20 %), stable, en baisse (< −20 %), nouveau, sans conso ;
- **stock à tenir** = le plus grand de : **stock minimum par flotte** (quantité par avion × 10 % des avions du groupe,
  au moins 1, additionné sur les groupes qui utilisent le PN ; nécessite « Pièces par avion ») et **stock de sécurité**
  statistique (irrégularité de la consommation d'une année civile sur l'autre × racine du délai fournisseur × coefficient
  du taux de service visé, 95 % par défaut) ;
- **commande** pour que le stock reste au-dessus du stock à tenir malgré la consommation prévue, délai compris ;
  si le délai est trop long, la commande part maintenant ;
- **délai** d'un PN : le sien (`LT observé moyen sur 2 ans`, ou délais promis de ses commandes selon Paramètres),
  à défaut la moyenne des PN de son fournisseur (CODE FOURNISSEUR du Résultat, 3 PN au moins), à défaut 60 jours ;
  arrondi au mois supérieur (colonnes « Délai (mois) » et « Source délai ») ;
- les PN dormants, inactifs, obsolètes ou supprimés (classe code 3, 8 ou 9) ne sont jamais recommandés ;
- chiffres donnés pour les **12, 24 et 36 prochains mois** (cumuls, commandes de ce mois comprises, période écrite en
  clair) : tuiles en tête, tableau **Prévision par PN** (conso 12 derniers mois, évolution, conso prévue sur les 12
  prochains mois, à commander maintenant, 12, 24, 36 mois, valeur) ;
- **évolution de la consommation** par PN, en % dans les tableaux : ▲ +67 % (hausse), ▼ −30 % (baisse), = (stable) ;
- **flottes** : un PN monté sur plusieurs flottes apparaît sous chacune ; avec un filtre Flotte, « Part des flottes
  choisies » donne la part des pièces installées sur ces flottes (la quantité à commander reste celle du PN) ;
- **forecast par fournisseur** : quantité et valeur à commander sur 12, 24 et 36 mois, année par année, PN en hausse /
  en baisse ; **forecast d'un fournisseur** : chiffres 12 / 24 / 36 mois, ses PN, et bouton
  **Exporter le forecast du fournisseur (Excel)** à lui envoyer (Synthèse 12/24/36 mois, Par PN, Par mois, Commandes
  en cours) — fichier `Supply360_forecast_<code>_AAAAMMJJ.xlsx`.
  Fournisseur d'un PN : le **CODE FOURNISSEUR du Résultat**, à défaut le code des commandes.

Les paramètres (avions d'avance, taux de service, délai par défaut…) sont dans « Paramètres » › Prévision.
Le planning des PE mousses est dans l'onglet **PE mousses**.

### 🛠️ PE mousses

Politique d'entretien des mousses de sièges : ce que l'on peut faire cette année avec le stock, ce qu'il faut commander,
l'avancement avion par avion et le forecast des années suivantes. Tous les fichiers sont lus dans le dossier **Textile**
(Ouvrir Textile) ; les commandes dans le dossier COMMANDE.

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| Besoin Prod mousses (« Besoin_Prod… », annuel) — feuille « QUOTE en euro » | `A/C` (type d'avion), `Area` (classe), `CCN`, `Qty per A/C`, `NB_AC` | `Flotte`, `NB_AC PE RESTANT`, `P/N OEM Seat Supplier`, `Seat Supplier`, `Description`, `P.U forecast PE` |
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE`, `CCN` | `QTE EN CDE`, `Dernier PU (achat) Euros` |
| Commandes (SAP) | `PN`, `Commande` | `CCN` (sinon retrouvé par le PN), `Quantité restant à livrer`, `Date de livraison promise` |
| PE mousses (PE_MOUSSE_JJMMAAAA, mensuel) | feuilles « … BOTTOM FOAM … » et « … BACKREST FOAM … » : FLEET, AIRCRAFT, AGE (month) par classe, PAST / NEXT EXECUTION | |
| Pièces par avion (textile_all_parts) | `equipment`, `registration`, `area`, `ccn`, `pn`, `description`, `qty_per_ac` | |

**Sous-onglets** :

- **Synthèse** : objectif de l'année, avions complets maintenant / à réception / à approvisionner, valeurs (stock,
  en commande, à commander, besoin), CCN à coter, CCN par action, avancement par type × classe, **actions à lancer**
  (PR à émettre), export Excel complet et contrôles des données.
- **Avions faisables** : par type d'avion × classe, avions complets avec le stock, à réception des commandes, à
  approvisionner, CCN limitant, CCN communs ; détail d'un type d'avion : avions couvrables par chaque CCN (stock, + commandes,
  trait = objectif de la classe). **Code couleur commun à tous les graphes** : 🟢 couvert par le stock, 🔵 couvert à
  réception des commandes en cours, 🟠 à coter (CCN sans prix), 🔴 à approvisionner (à commander), gris : au-delà de
  l'objectif. Jamais de rouge sur ce que le stock couvre : 26 avions couverts sur un objectif de 28 = 26 en vert + 2 en
  rouge. Un CCN commun à plusieurs types est partagé selon la répartition des avions complets (le détail par CCN
  concorde avec l'avancement par classe).
- **CCN et commandes** : une barre par CCN = 100 % de son besoin de l'année, découpée en part couverte par le stock,
  par les commandes en cours et manque à commander (les moins couverts en haut) ; recherche, filtre par action, CCN à coter.
- **Avancement PE** et **Forecast** : voir ci-dessous (ex-sous-onglet « Planning PE » du Textile).

Règles de l'année (reprises du Streamlit « Pilotage Politique d'entretien Mousse ») :

- **avions restants** (objectif) : par défaut la colonne **`NB_AC PE RESTANT`** du Besoin Prod, à défaut `NB_AC`.
  Autre choix dans « Paramètres » › Année : **recalculés** = NB_AC − avions du type dont la mousse (même classe,
  assise ou dossier) a été remplacée depuis le 1er janvier d'après le fichier PE mousses. Le type de chaque avion
  (A350 AFR01, B777-300 14J…) est retrouvé par ses CCN de mousses dans textile_all_parts (type qui en partage le plus) ;
  sans ces fichiers, ou pour une classe non reconnue : colonne `NB_AC PE RESTANT`. Comparaison fichier / calcul dans
  « ℹ️ Règles de calcul et avions restants » ;
- NB_AC compté une fois par type d'avion × classe (pas une fois par ligne) ; l'objectif et les avions faisables sont
  comptés **par classe** (un avion à traiter en J, W et Y compte 3 fois), l'équivalent en avions est indiqué sous l'objectif ;
- besoin d'un CCN = qté par avion × avions restants, additionné sur les types d'avion ;
- stock d'un CCN = QTE SUR ÉTAGÈRE de l'État du stock (maximum des lignes du CCN) ; en commande = reste à livrer des
  commandes SAP du CCN (sans fichier Commandes : QTE EN CDE) ;
- à demander (PR) = besoin − stock − en commande (si positif). Action : PR à émettre (aucune commande), PR
  complémentaire (commandes insuffisantes), à réceptionner (couvert avec les commandes), couvert par le stock ;
- prix = Dernier PU de l'État du stock, à défaut le prix du devis ; sans prix : CCN « à coter » ;
- **avions faisables** : un avion d'une classe est complet si tous ses CCN sont disponibles. Le stock d'un CCN commun
  à plusieurs types d'avion est **réparti** (l'avion suivant va au type le moins avancé) : le total ne compte jamais
  deux fois le même stock. Les colonnes MRI, PSD et capa du Besoin Prod ne sont pas utilisées.

**Avancement PE et Prévision** — à partir du fichier mensuel PE_MOUSSE déposé tel quel dans le dossier Textile (date des
âges lue dans son nom) et de textile_all_parts. Une **classe** = les mousses d'une classe (J, W ou Y) d'un avion,
assise ou dossier (survolez le « ? » à côté du titre).

- **Avancement** : conformité PE, classes en retard, dans le délai toléré, à faire sous 3 mois, visites à venir ;
  statut par flotte et classe ; classes à remplacer mois par mois.
- **Calendrier** : une ligne par avion, le nombre de classes à remplacer par mois (24 mois) ; détail par avion.
- **Prévision** (période choisie dans la barre « Périmètre » : 12 / 24 / 36 mois, écrite en clair, ex.
  « 24 mois · nov. 2026 → oct. 2028 ») : mousses à remplacer (dont retard), à commander, valeur,
  déjà disponibles ; « mois par mois » (à remplacer / à recevoir) ; tableau par PN avec CCN.
- **Par fournisseur** : commande globale et livraisons mois par mois par PN, export Excel à lui envoyer.
  Fournisseur d'une mousse : code fournisseur des commandes, à défaut le **CODE FOURNISSEUR** du Résultat (par PN,
  puis par CCN) ; les références sont comparées sans espaces, tirets ni points.
- **Filtres** (barre « Flotte · Classe · Assise / dossier ») : « Toutes » par défaut ; un clic choisit une valeur,
  plusieurs choix possibles ; « Toutes » remet à zéro. **Exports** : planning complet ; **contrôles** des données.

Règles (paramètres dans « Paramètres » › Planning PE ; stock de sécurité réglable de 0 à 50 %) :
- cycles : J / W / Y assise 36 mois, J dossier 72 mois, dossiers W / Y jamais ;
- échéance = date des âges − âge + cycle (âge « > 60 » : 60 pris comme minimum, échéance au plus tôt) ;
- statut : En retard (échéance + délai toléré dépassés, 3 mois par défaut), Délai toléré, À faire < 3 mois,
  À faire < 12 mois, OK ;
- date prévue : la prochaine visite datée (PAST / NEXT EXECUTION), sinon l'échéance ; un retard est à rattraper
  le mois en cours ; une visite postérieure à l'échéance est signalée ;
- mousses : lignes `equipment` = MOUSSE de textile_all_parts, classe = `area`, assise = « FOAM BOTTOM / BOTT… »,
  dossier = « FOAM BACKREST / BACK… » ;
- stock de sécurité par PN : pour chaque flotte, 10 % des avions qui l'utilisent (arrondi au-dessus, au moins 1)
  × quantité par avion ;
- à commander, par PN = besoin + stock de sécurité − stock − commandes en cours (déjà passées : toujours déduites,
  quelle que soit leur date promise), livré le mois où il en faut ; une commande en cours promise après le mois où elle
  est nécessaire est signalée « à avancer » (relance fournisseur) au lieu d'être commandée deux fois. Le fichier étant
  régénéré chaque mois, un remplacement fait remet l'âge à zéro : rien à saisir.

### Graphiques

Chaque graphe a deux boutons en haut à droite (visibles au survol) : **⛶ Agrandir** ouvre le graphe en grand, en
entier, sans barre de défilement (un très grand graphe est affiché à la largeur de l'écran et défile verticalement) ;
**⤓** (ou **Enregistrer en PNG** dans la vue agrandie) télécharge une image identique au graphe du site (police,
couleurs, graphe complet même s'il défile à l'écran), à partager par mail ou dans une présentation.

Survol d'une colonne, d'une barre ou d'une case : infobulle avec toutes ses valeurs.

### Fournisseur = code fournisseur (Textile cabine, PE mousses)

Un même fournisseur peut être écrit de plusieurs façons (« ALPHA SAS », « Alpha ») ou n'avoir qu'un code sur
certaines lignes : il est donc désigné par son **code fournisseur** dans toutes les listes, graphes et tableaux
(choix d'un fournisseur, regroupements, filtres de colonne). Lignes de commande : code de la ligne, sinon code des autres
commandes du même PN. Fournisseur d'un PN (prévision, PE mousses) : `CODE FOURNISSEUR` de l'État du stock (Résultat),
sinon code des commandes ; le nom n'est utilisé que si aucun code n'existe. Dans le détail d'un fournisseur, son nom tel qu'écrit dans les commandes est rappelé sous la liste.

Stock par chantier garde ses deux colonnes `Fournisseur` et `Code fournisseur`. Quand la colonne `Fournisseur` est
vide dans les Commandes (SAP), le nom est retrouvé grâce au `Code fournisseur` (autres lignes du même code), puis
grâce aux autres lignes du même PN ; à défaut, le code lui-même est affiché (« Code F123 »).

### 🏭 Fournisseurs · 🔔 Alertes

En cours de développement. Chaque onglet présente déjà ce qu'il contiendra :

- **Fournisseurs** (source : Commandes (SAP), fournisseur désigné par son code) : **score fournisseur pondéré** sur 100
  (ponctualité OTD 30 %, livraison complète OTIF 20 %, promesses tenues 15 %, retards en cours 15 %, confirmation 10 %,
  délai d'approvisionnement 10 % ; classes A ≥ 80, B 60–79, C < 60 ; poids réglables), indicateurs (OTD, OTIF, retard
  moyen / maximal, lignes sans date promise ou en attente BFE, délai promis, valeur en commande), fiche fournisseur,
  relances prêtes à envoyer, comparaisons par famille, risques (mono-source, délais qui s'allongent).
  À valider : l'OTD / OTIF réels demandent la date de réception effective dans l'extraction SAP.
- **Alertes** (aucun nouvel import : fichiers des autres onglets) : alertes **par gestionnaire** (code agent appro,
  code Gestion ou acheteur, seuils personnels), infos urgentes du jour, **actions à lancer** (qui, quoi, avant quand ;
  suivi à faire / en cours / fait), ruptures, chantiers à risque, retards fournisseurs, PE mousses, qualité des données ;
  quatre niveaux : Urgent, À traiter, À surveiller, Info.

## Développement

```bash
pip install -r requirements-dev.txt     # dev local
streamlit run app/main.py               # tester en local (serveur)
pytest                                  # tests des lectures, croisements, exports
python build.py                         # générer dist/supply360.html
python tests/fixtures/generer_fixtures.py   # régénérer les fichiers fictifs de test
```

Les fichiers de `tests/fixtures/` sont **fictifs** : ils permettent d'essayer l'application sans
données réelles. Voir `CLAUDE.md` pour l'architecture et les règles du projet.

### Imports et page qui ne répond plus

- **Version** : la date de génération de la page s'affiche sur l'écran de chargement (« Version du … »). Si elle
  est ancienne, rechargez avec **Ctrl+F5** (ou retéléchargez le fichier HTML).

- **Plus de redémarrage toutes les 10 minutes** : le moteur Python (Pyodide) plantait 10 minutes après l'ouverture de
  la page, même sans rien faire, à cause d'une fonction récente de Chrome / Edge (JSPI). Elle est désactivée pour
  Supply360 : le moteur reste stable (testé 40 minutes, mise en veille de l'onglet comprise).
- **Onglet jamais mis en veille** : Supply360 empêche Edge / Chrome d'endormir puis de décharger l'onglet (ce qui
  rechargeait toute la page et faisait perdre les fichiers). L'état s'affiche dans le journal (« mise en veille :
  bloquée »).
- **Ouvrir** : une barre de progression suit la lecture des fichiers, leur envoi puis l'analyse.
- Pendant un calcul (y compris le traitement d'un import), la pastille « Calcul en cours… » s'affiche aussitôt, avec
  sa durée au-delà de 10 s. **Un long calcul n'est jamais interrompu** : la page attend qu'il se termine (au-delà de
  3 minutes, un bandeau propose de relancer, à votre choix).
- **Relance en arrière-plan** : pendant la remise en route, votre page reste affichée (figée, consultable) avec un bandeau d'avancement en haut ; à la fin, vous retrouvez l'onglet et le sous-onglet où vous étiez, fichiers réimportés.
- **Journal du moteur** : cliquez sur **Prêt** (en haut à droite) pour voir les relances et leur cause, les erreurs et les rechargements de page, conservés dans le navigateur même après un rechargement. **Copier le journal** pour le transmettre à l'auteur si les relances se répètent.
- **Relance automatique du moteur, seulement sur une panne constatée** : la page interroge le moteur (Python libre ?
  session ouverte ? clics bien reçus ? réponses bien envoyées ?) et ne le relance que si la panne est confirmée deux
  fois de suite (détection en 5 à 15 s, immédiate si Python signale une erreur fatale). Un écran Supply360 (logo, barre d'avancement) suit la relance, puis **tous
  les fichiers sont réimportés**, onglet par onglet (relus dans le dossier mémorisé quand ils en viennent ; gardés en
  mémoire de la page, jamais écrits sur le disque). Une seconde panne en moins de 2 minutes : bandeau **Relancer en
  gardant mes fichiers** / **Recharger la page** ;
  **Détails techniques › Copier** donne le diagnostic à transmettre à l'auteur.
- **Tableaux** : tous les tableaux fonctionnent de la même façon. **Cliquez sur un titre de colonne** pour trier ou
  filtrer (cases à cocher pour un texte, « au moins / au plus » pour un nombre, « du / au » pour une date) ; champ
  **Rechercher dans le tableau** ; pastilles par statut ; le compteur indique « x lignes sur y » et **Effacer les
  filtres** remet tout à zéro. Les grands tableaux s'affichent par 200 lignes (**Afficher plus**) ; filtres, recherche
  et tri portent toujours sur toutes les lignes.
- **Règles de calcul** : chaque sous-onglet a un bouton « Règles de calcul » qui explique, avec un exemple, ce que
  veut dire chaque statut et que faire. Les précisions secondaires sont dans un petit « ? » : survolez-le.
- **Exporter (Excel)** : un seul bouton par sous-onglet, en haut à droite du premier bloc.
- **Exports Excel** : bouton **Exporter** → le fichier est fabriqué à ce moment-là, puis téléchargé automatiquement
  (il n'est plus fabriqué à chaque affichage d'onglet, ce qui ralentissait et chargeait la mémoire).
- Mémoire : les gros fichiers (État du stock, Commandes) sont lus en ne gardant que les colonnes utiles ; les fichiers
  sont reconnus en ne lisant que leurs en-têtes ; chaque fichier n'est gardé qu'une fois (format Excel compressé).
Sécurité supplémentaire (facultative) dans Edge : *Paramètres › Système et performances › Ne jamais mettre en veille ces sites* → ajouter l'adresse de Supply360.
