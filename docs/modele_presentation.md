# Modèle de présentation Supply360

Modèle validé par l'auteur (novembre 2026). Présentation vierge prête à dupliquer : « Modèle Supply360 »
(https://claude.ai/artifact/FEELjfeVnWNGuaNKts5ZYF : couverture, transition, texte, schéma, fonctionnalité, tableau,
chiffres clés, étapes, fin). Format : slides 1920 × 1080, styles en ligne, une `<section>` par slide.

## Règles

- **Schématique et à l'essentiel** : une idée par slide, un schéma plutôt qu'une liste, et sous chaque titre une
  phrase d'explication en clair (28 px, gris).
- **Pas de capture d'écran du site** : illustrer par des schémas dessinés (chronologie, courbe, pictogrammes) sur un
  exemple fictif, signalé « exemple fictif ».
- **Avion A350 sur la couverture uniquement.**
- **Aucune donnée réelle**, jamais le nom de l'outil d'optimisation du stock (« État du stock »).
- Notes orateur dans chaque slide (`<aside>`).

## Identité

- **Police** : Manrope (Google Fonts, `family=Manrope:wght@400..800`), comme l'application. Titres en 800.
- **Logo Supply360** (texte) : « Supply » bleu marine `#002157` + « 360 » rouge `#E4002B`, graisse 800, lettres
  resserrées. Sur fond marine : « Supply » `#F4F7FC` + « 360 » `#FF5468`. En grand sur la couverture (160 px) et la
  fin (120 px), dans le bloc central des schémas, et dans chaque pied de page.
- **Logo AFI** : `assets/logo_afi.png` (fond transparent, texte foncé : toujours sur fond clair).
- **Avion** : `assets/avion_a350.webp`, couverture seulement, avec une traînée blanche en dégradé.
- **Accent Air France** : parallélogramme rouge avant les surtitres
  (`width:12–14px; height:30–44px; background:#E4002B; transform:skewX(-24deg)`).

## Couleurs

| Rôle | Valeur |
|---|---|
| Bleu marine (titres, blocs « Supply360 ») | `#002157` (dégradé vers `#0F3C80`) |
| Bleu (surtitres, flèches) | `#1F5FA8` |
| Fond des slides de contenu | `#F4F7FC` |
| Fond ciel (couverture, fin) | `linear-gradient(180deg, #F4F7FC 0%, #D6E3F3 100%)` |
| Fond de transition | `linear-gradient(135deg, #002157 0%, #0F3C80 100%)` |
| Cartes | `#FBFCFE`, filet `#D3DDEB`, coins 14–20 px |
| Bandeau clair, pastilles | `#DCE6F4` |
| Décision (encadré orange) | fond `#FFF1E6`, filet `#F2C9A8`, texte `#8A3E0B` |
| Texte / secondaire | `#1A1F36` / `#4F5A70` ; sur marine `#F4F7FC` / `#C9D7EE` |
| Domaines | Production `#1F4E9C`, Supply Chain `#1E7A6F` (onglet `#2A9D8F`), PE `#5B45A8`, Fournisseurs `#B35A16` (onglet `#E8833A`), Alertes `#9A2F3C` |
| Statuts | OK `#1E8E5A`, à temps `#2B6CB0`, à relancer `#E8590C`, à commander `#A61B1B` |

## Échelle typographique

160 / 120 (logo Supply360) · 96 (titre de transition) · 64 (titre de couverture) · 56 (titre de slide) · 36 (chiffres,
formules) · 28 (texte, phrase d'explication) · 24 (surtitres, détails, pied de page).

## Gabarits

- **Couverture** : fond ciel ; logo AFI (300 × 70) ; logo Supply360 160 px ; titre 64 px avec l'accent rouge ;
  sous-titre 36 px ; A350 en bas à droite (≈ 1200 × 300) ; pied « équipe · mois année ».
- **Transition** : fond marine en dégradé, surtitre bleu clair, titre 96 px, une phrase, bandeau facultatif
  avant → après (deux encadrés et une flèche orange).
- **Contenu** : fond `#F4F7FC`, `padding:128px 128px 160px` ; surtitre + titre 56 px + phrase d'explication ;
  pied épinglé à `bottom:56px` : logo Supply360 + « titre court · n° » à gauche, logo AFI 172 × 40 à droite.
- **Schéma** données → calcul → décision : cartes à gauche, bloc marine « Supply360 » au centre, décisions orange à
  droite, flèches `x-shape arrow-right`.
- **Fonctionnalité** : à gauche données croisées (2 × 2), bloc « Supply360 croise », encadré « Décision » ; à droite un
  schéma d'exemple fictif et la source des données.
- **Tableau**, **chiffres clés** (4 tuiles, la principale en marine), **étapes** (4 colonnes numérotées, pastille d'état).
- **Fin** : fond ciel, logo Supply360 120 px, trois messages (le principal en marine), « Merci. Des questions ? »,
  logo AFI.
