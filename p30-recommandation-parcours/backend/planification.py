"""Construction du parcours de formation (logique pure, sans accès à Neo4j).

Entrées fournies par les requêtes Cypher du moteur (voir recommender.py) :
  * besoins      : {id_competence: {"nom", "poids", "profondeur", ...}}
                   compétences à acquérir (cibles du métier + prérequis manquants)
  * candidats    : formations qui développent au moins un besoin
                   [{"id", "nom", "niveau", "duree_heures", "couvre": [{"id", "niveau"}]}]
  * dependances  : couples (competence, prerequis) entre besoins

Algorithme :
  1. sélection gloutonne : à chaque tour, on prend la formation qui rapporte le
     plus de points par heure sur les besoins encore non couverts
     (points = poids de la compétence x niveau acquis en formation) ;
  2. ordonnancement : tri topologique des formations selon les prérequis des
     compétences (une formation qui apporte un prérequis passe avant celle qui
     en dépend) ; à égalité, les fondations (profondeur élevée) passent d'abord.
"""


def selectionner_formations(besoins: dict, candidats: list[dict], max_formations: int):
    """Retourne (formations_choisies, ids_competences_non_couvertes)."""
    non_couverts = set(besoins)
    restants = sorted(candidats, key=lambda f: f["id"])
    choisies: list[dict] = []

    while non_couverts and restants and len(choisies) < max_formations:
        meilleur, meilleur_cle = None, (0.0, 0)
        for f in restants:
            gain = sum(besoins[c["id"]]["poids"] * (c["niveau"] or 1) for c in f["couvre"] if c["id"] in non_couverts)
            if gain <= 0:
                continue
            cle = (gain / (f["duree_heures"] or 10), gain)
            if cle > meilleur_cle:  # strict : à égalité, la plus petite id (liste triée) gagne
                meilleur, meilleur_cle = f, cle
        if meilleur is None:
            break
        apportees = sorted(c["id"] for c in meilleur["couvre"] if c["id"] in non_couverts)
        choisies.append({**meilleur, "competences_apportees": apportees, "gain": round(meilleur_cle[1], 2)})
        non_couverts -= set(apportees)
        restants = [f for f in restants if f["id"] != meilleur["id"]]

    return choisies, sorted(non_couverts)


def ordonner_formations(choisies: list[dict], besoins: dict, dependances: list[tuple[str, str]]) -> list[dict]:
    """Tri topologique des formations choisies (fondations d'abord)."""
    fournisseur = {c: f["id"] for f in choisies for c in f["competences_apportees"]}
    avant: dict[str, set[str]] = {f["id"]: set() for f in choisies}
    for competence, prerequis in dependances:
        fc, fp = fournisseur.get(competence), fournisseur.get(prerequis)
        if fc and fp and fc != fp:
            avant[fc].add(fp)

    fondation = {f["id"]: max(besoins[c]["profondeur"] for c in f["competences_apportees"]) for f in choisies}
    restantes = {f["id"]: f for f in choisies}
    ordre: list[dict] = []
    while restantes:
        pretes = [fid for fid in restantes if not (avant[fid] & restantes.keys())]
        if not pretes:  # cycle entre formations (cas rare) : on retombe sur la profondeur
            pretes = list(restantes)
        pretes.sort(key=lambda fid: (-fondation[fid], restantes[fid]["duree_heures"], fid))
        ordre.append(restantes.pop(pretes[0]))
    return ordre


def construire_parcours(besoins: dict, candidats: list[dict], dependances: list[tuple[str, str]],
                        max_formations: int) -> dict:
    choisies, non_couverts = selectionner_formations(besoins, candidats, max_formations)
    ordre = ordonner_formations(choisies, besoins, dependances)
    etapes = []
    for i, f in enumerate(ordre, start=1):
        etapes.append({
            "ordre": i,
            "formation_id": f["id"],
            "formation": f["nom"],
            "niveau": f["niveau"],
            "duree_heures": f["duree_heures"],
            "competences": [{"id": c, "nom": besoins[c]["nom"]} for c in f["competences_apportees"]],
        })
    return {
        "etapes": etapes,
        "nb_formations": len(etapes),
        "duree_totale_heures": sum((e["duree_heures"] or 10) for e in etapes),
        "competences_non_couvertes": [{"id": c, "nom": besoins[c]["nom"]} for c in non_couverts],
    }
