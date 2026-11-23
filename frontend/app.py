"""Interface Streamlit du projet P30 : recommandation de parcours de formation.

Lancement :  streamlit run frontend/app.py
L'interface ne parle jamais à Neo4j directement : tout passe par l'API FastAPI.
"""
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
TIMEOUT = 15

NIVEAUX = ["Débutant", "Intermédiaire", "Avancé"]
MODALITES = ["En ligne", "Présentiel", "Hybride"]
COULEURS = {"Metier": "#f4a261", "Competence": "#8ecae6", "Formation": "#90be6d", "Parcours": "#cdb4db"}

st.set_page_config(page_title="P30 - Parcours de formation", page_icon="🎓", layout="wide")


# ---------------------------------------------------------------------------
# Client de l'API
# ---------------------------------------------------------------------------
class ErreurAPI(Exception):
    """Erreur lisible renvoyée à l'utilisateur."""


def appeler(methode: str, chemin: str, *, json=None, params=None, ecriture: bool = False):
    headers = {"X-API-Key": API_KEY} if ecriture else {}
    try:
        rep = requests.request(methode, f"{API_URL}{chemin}", json=json, params=params,
                               headers=headers, timeout=TIMEOUT)
    except requests.ConnectionError:
        raise ErreurAPI(f"API injoignable sur {API_URL}. Lancez : uvicorn backend.main:app --port 8000") from None
    except requests.Timeout:
        raise ErreurAPI("Délai dépassé : l'API ne répond pas.") from None
    if rep.status_code == 204:
        return None
    if rep.status_code >= 400:
        try:
            detail = rep.json().get("detail", rep.text)
        except ValueError:
            detail = rep.text
        if isinstance(detail, list):  # erreurs de validation Pydantic (422)
            detail = " ; ".join(
                f"{'.'.join(str(x) for x in d.get('loc', [])[1:])} : {d.get('msg')}" for d in detail)
        raise ErreurAPI(f"[{rep.status_code}] {detail}")
    return rep.json()


@st.cache_data(ttl=30, show_spinner=False)
def _charger(ressource: str) -> list[dict]:
    return appeler("GET", f"/{ressource}", params={"limit": 500})


def liste(ressource: str) -> list[dict]:
    try:
        return _charger(ressource)
    except ErreurAPI as exc:
        st.error(str(exc))
        st.stop()


def lire(chemin: str, **params):
    """GET avec affichage de l'erreur ; retourne None en cas d'échec."""
    try:
        return appeler("GET", chemin, params=params or None)
    except ErreurAPI as exc:
        st.error(str(exc))
        return None


def ecrire(methode: str, chemin: str, json=None, succes: str = "Opération réussie") -> bool:
    try:
        appeler(methode, chemin, json=json, ecriture=True)
    except ErreurAPI as exc:
        st.error(str(exc))
        return False
    st.cache_data.clear()
    st.session_state["flash"] = succes
    return True


def libelles(elements: list[dict]) -> dict[str, str]:
    return {e["id"]: f"{e['id']} - {e['nom']}" for e in elements}


# ---------------------------------------------------------------------------
# Graphes (Graphviz)
# ---------------------------------------------------------------------------
def _q(texte) -> str:
    return '"' + str(texte).replace("\\", "\\\\").replace('"', '\\"') + '"'


def dot_graphe(noeuds: list[dict], aretes: list[dict]) -> str:
    lignes = ["digraph G {", "rankdir=LR;",
              'node [shape=box style="filled,rounded" fontname="Helvetica" fontsize=10];',
              'edge [fontname="Helvetica" fontsize=8];']
    for n in noeuds:
        lignes.append(f'{_q(n["id"])} [label={_q(n["nom"])} fillcolor="{COULEURS.get(n["label"], "#dddddd")}"];')
    for a in aretes:
        etiquette = a["type"]
        if a.get("importance") is not None:
            etiquette += f" ({a['importance']})"
        if a.get("niveau_acquis") is not None:
            etiquette += f" (niv. {a['niveau_acquis']})"
        style = ' style="dashed"' if a["type"] == "PREREQUIS" else ""
        lignes.append(f'{_q(a["source"])} -> {_q(a["cible"])} [label={_q(etiquette)}{style}];')
    lignes.append("}")
    return "\n".join(lignes)


def dot_parcours(etapes: list[dict]) -> str:
    lignes = ["digraph G {", "rankdir=LR;",
              'node [shape=box style="filled,rounded" fillcolor="#90be6d" fontname="Helvetica" fontsize=10];']
    for e in etapes:
        lignes.append(f'{_q(e["formation_id"])} [label={_q(str(e["ordre"]) + ". " + e["formation"])}];')
    for a, b in zip(etapes, etapes[1:]):
        lignes.append(f'{_q(a["formation_id"])} -> {_q(b["formation_id"])};')
    lignes.append("}")
    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Page : recommandation
# ---------------------------------------------------------------------------
def page_recommandation():
    st.header("🎯 Recommandation de parcours")
    metiers, competences = liste("metiers"), liste("competences")
    nom_metier = libelles(metiers)
    nom_comp = {c["id"]: f"{c['nom']} ({c['categorie']})" for c in competences}

    col1, col2 = st.columns([1, 2])
    with col1:
        metier_id = st.selectbox("Métier visé", list(nom_metier), format_func=nom_metier.get)
        max_formations = st.slider("Nombre maximum de formations", 1, 15, 8)
    with col2:
        acquises = st.multiselect("Compétences déjà acquises", list(nom_comp), format_func=nom_comp.get,
                                  help="Les prérequis de ces compétences sont considérés comme acquis.")

    if st.button("Générer ma recommandation", type="primary"):
        try:
            with st.spinner("Interrogation du graphe…"):
                st.session_state["reco"] = appeler("POST", "/recommandation", json={
                    "metier_id": metier_id, "competences_acquises": acquises, "max_formations": max_formations})
        except ErreurAPI as exc:
            st.session_state.pop("reco", None)
            st.error(str(exc))

    res = st.session_state.get("reco")
    if not res:
        st.info("Choisissez un métier et vos compétences, puis lancez la recommandation.")
        return

    parcours = res["parcours_propose"]
    st.subheader(f"Objectif : {res['metier']['nom']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Couverture du métier", f"{res['couverture_pct']} %")
    c2.metric("Compétences manquantes", len(res["competences_manquantes"]))
    c3.metric("Formations du parcours", parcours["nb_formations"])
    c4.metric("Durée totale", f"{parcours['duree_totale_heures']} h")
    st.progress(min(max(res["couverture_pct"] / 100, 0.0), 1.0))
    st.caption(f"{len(res['competences_acquises'])} compétences prises en compte (acquis + prérequis implicites).")

    if not res["competences_manquantes"]:
        st.success("Vous couvrez déjà toutes les compétences requises pour ce métier.")

    onglets = st.tabs(["Parcours proposé", "Compétences manquantes", "Formations classées", "Graphe du métier"])

    with onglets[0]:
        if not parcours["etapes"]:
            st.info("Aucune formation nécessaire.")
        for e in parcours["etapes"]:
            with st.container(border=True):
                st.markdown(f"**Étape {e['ordre']} - {e['formation']}**  \n"
                            f"{e['niveau']} · {e['duree_heures']} h")
                st.caption("Compétences visées : " + ", ".join(c["nom"] for c in e["competences"]))
        if parcours["etapes"]:
            st.graphviz_chart(dot_parcours(parcours["etapes"]))
        if parcours["competences_non_couvertes"]:
            st.warning("Aucune formation disponible (ou limite atteinte) pour : "
                       + ", ".join(c["nom"] for c in parcours["competences_non_couvertes"]))

    with onglets[1]:
        st.markdown("**Compétences requises par le métier et non acquises**")
        st.dataframe(pd.DataFrame(res["competences_manquantes"]).rename(columns={
            "id": "ID", "nom": "Compétence", "categorie": "Catégorie", "importance": "Importance (1-5)"}),
            hide_index=True)
        if res["prerequis_manquants"]:
            st.markdown("**Prérequis indirects à acquérir d'abord** (parcours de graphe `PREREQUIS*0..4`)")
            df = pd.DataFrame(res["prerequis_manquants"])[["id", "nom", "categorie", "profondeur"]]
            st.dataframe(df.rename(columns={"id": "ID", "nom": "Compétence", "categorie": "Catégorie",
                                            "profondeur": "Profondeur"}), hide_index=True)

    with onglets[2]:
        if res["formations_recommandees"]:
            df = pd.DataFrame(res["formations_recommandees"])
            df["competences_couvertes"] = df["competences_couvertes"].apply(", ".join)
            st.dataframe(df.rename(columns={
                "id": "ID", "nom": "Formation", "niveau": "Niveau", "duree_heures": "Heures",
                "nb_competences": "Nb compétences", "competences_couvertes": "Compétences couvertes",
                "score": "Score", "efficacite_pour_10h": "Score / 10 h"}), hide_index=True)
            st.caption("Score = somme (importance de la compétence × niveau acquis en formation).")

    with onglets[3]:
        graphe = lire(f"/graphe/metier/{res['metier']['id']}")
        if graphe:
            st.graphviz_chart(dot_graphe(graphe["noeuds"], graphe["aretes"]))
            st.caption("Orange : métier · Bleu : compétences · Vert : formations · pointillés : PREREQUIS")


# ---------------------------------------------------------------------------
# Page : exploration du graphe
# ---------------------------------------------------------------------------
def page_exploration():
    st.header("🗺️ Explorer le graphe")
    metiers, competences, formations = liste("metiers"), liste("competences"), liste("formations")
    onglets = st.tabs(["Prérequis (*1..4)", "Plus court chemin", "Graphe d'un métier", "Parcours prédéfinis"])

    with onglets[0]:
        nom_comp = libelles(competences)
        cid = st.selectbox("Compétence", list(nom_comp), format_func=nom_comp.get, key="expl_comp")
        prof = st.slider("Profondeur maximale", 1, 4, 4)
        res = lire(f"/competences/{cid}/prerequis", profondeur=prof)
        if res is not None:
            if res["prerequis"]:
                st.dataframe(pd.DataFrame(res["prerequis"]).rename(columns={
                    "id": "ID", "nom": "Prérequis", "categorie": "Catégorie", "distance": "Distance"}),
                    hide_index=True)
                noeuds = [{"id": cid, "nom": nom_comp[cid].split(" - ", 1)[1], "label": "Competence"}]
                noeuds += [{"id": p["id"], "nom": p["nom"], "label": "Competence"} for p in res["prerequis"]]
                aretes = [{"source": cid, "cible": p["id"], "type": f"niveau {p['distance']}"}
                          for p in res["prerequis"]]
                st.graphviz_chart(dot_graphe(noeuds, aretes))
            else:
                st.info("Cette compétence n'a aucun prérequis.")

    with onglets[1]:
        tous = {**libelles(metiers), **libelles(competences), **libelles(formations)}
        c1, c2 = st.columns(2)
        source = c1.selectbox("Départ", list(tous), format_func=tous.get, key="chemin_a")
        cible = c2.selectbox("Arrivée", list(tous), index=min(len(tous) - 1, 70), format_func=tous.get,
                             key="chemin_b")
        if st.button("Chercher le plus court chemin"):
            if source == cible:
                st.warning("Choisissez deux nœuds différents.")
            else:
                res = lire("/chemin", source=source, cible=cible)
                if res and not res["chemin"]:
                    st.info(res.get("message", "Aucun chemin."))
                elif res:
                    ch = res["chemin"]
                    morceaux = [ch["noeuds"][0]["nom"]]
                    for i, rel in enumerate(ch["relations"]):
                        suivant = ch["noeuds"][i + 1]["nom"]
                        sens = f"—{rel['type']}→" if rel["de"] == ch["noeuds"][i]["id"] else f"←{rel['type']}—"
                        morceaux += [sens, suivant]
                    st.success(f"Longueur : {ch['longueur']}")
                    st.markdown(" ".join(f"**{m}**" if not m.startswith(("—", "←")) else f"`{m}`" for m in morceaux))
                    noeuds = [{"id": n["id"], "nom": n["nom"], "label": n["type"]} for n in ch["noeuds"]]
                    aretes = [{"source": r["de"], "cible": r["vers"], "type": r["type"]} for r in ch["relations"]]
                    st.graphviz_chart(dot_graphe(noeuds, aretes))

    with onglets[2]:
        nom_metier = libelles(metiers)
        mid = st.selectbox("Métier", list(nom_metier), format_func=nom_metier.get, key="expl_metier")
        graphe = lire(f"/graphe/metier/{mid}")
        if graphe:
            st.graphviz_chart(dot_graphe(graphe["noeuds"], graphe["aretes"]))

    with onglets[3]:
        parcours = lire("/parcours") or []
        for p in parcours:
            with st.expander(f"{p['nom']} → {p['metier']} ({p['heures_totales']} h · {p['duree_mois']} mois)"):
                st.write(p["description"])
                st.dataframe(pd.DataFrame(p["formations"]).rename(columns={
                    "ordre": "Ordre", "id": "ID", "nom": "Formation", "duree_heures": "Heures"}), hide_index=True)


# ---------------------------------------------------------------------------
# Page : analyses
# ---------------------------------------------------------------------------
def page_analyses():
    st.header("📊 Analyses du graphe")
    metiers, competences = liste("metiers"), liste("competences")
    onglets = st.tabs(["Compétences pivot", "Couverture par métier", "Métiers proches", "Intégrité & statistiques"])

    with onglets[0]:
        limite = st.slider("Nombre de compétences", 5, 25, 10)
        rows = lire("/analyses/competences-pivot", limite=limite)
        if rows:
            df = pd.DataFrame(rows)
            st.bar_chart(df.set_index("nom")["nb_metiers"])
            st.dataframe(df.rename(columns={
                "id": "ID", "nom": "Compétence", "categorie": "Catégorie", "nb_metiers": "Nb métiers",
                "importance_moyenne": "Importance moyenne", "nb_formations": "Nb formations"}), hide_index=True)

    with onglets[1]:
        nom_comp = {c["id"]: c["nom"] for c in competences}
        acquises = st.multiselect("Vos compétences acquises", list(nom_comp), format_func=nom_comp.get)
        try:
            rows = appeler("POST", "/analyses/couverture", json={"competences_acquises": acquises})
        except ErreurAPI as exc:
            rows = None
            st.error(str(exc))
        if rows:
            df = pd.DataFrame(rows)
            st.bar_chart(df.set_index("nom")["couverture_pct"])
            st.dataframe(df.rename(columns={
                "id": "ID", "nom": "Métier", "secteur": "Secteur", "nb_acquises": "Acquises",
                "nb_requises": "Requises", "couverture_pct": "Couverture (%)"}), hide_index=True)

    with onglets[2]:
        nom_metier = libelles(metiers)
        mid = st.selectbox("Métier de référence", list(nom_metier), format_func=nom_metier.get, key="sim_metier")
        rows = lire(f"/analyses/metiers-similaires/{mid}", limite=5)
        if rows:
            df = pd.DataFrame(rows)
            df["communes"] = df["communes"].apply(", ".join)
            st.dataframe(df.rename(columns={
                "id": "ID", "nom": "Métier", "nb_communes": "Compétences communes",
                "jaccard": "Similarité (Jaccard)", "communes": "Détail"}), hide_index=True)

    with onglets[3]:
        integrite = lire("/analyses/integrite")
        if integrite:
            if integrite["integre"]:
                st.success("Aucun cycle dans le graphe des prérequis.")
            else:
                st.error(f"Cycle(s) détecté(s) : {integrite['cycles']}")
        stats = lire("/stats")
        if stats:
            c1, c2 = st.columns(2)
            c1.markdown("**Nœuds**")
            c1.dataframe(pd.DataFrame(stats["noeuds"].items(), columns=["Label", "Nombre"]), hide_index=True)
            c2.markdown("**Relations**")
            c2.dataframe(pd.DataFrame(stats["relations"].items(), columns=["Type", "Nombre"]), hide_index=True)


# ---------------------------------------------------------------------------
# Page : gestion (CRUD)
# ---------------------------------------------------------------------------
CHAMPS = {
    "metiers": [("nom", "text", None), ("secteur", "text", None), ("description", "area", None)],
    "competences": [("nom", "text", None), ("categorie", "text", None), ("description", "area", None)],
    "formations": [("nom", "text", None), ("organisme", "text", None), ("duree_heures", "int", None),
                   ("niveau", "select", NIVEAUX), ("modalite", "select", MODALITES),
                   ("description", "area", None)],
}
TITRES = {"metiers": "métier", "competences": "compétence", "formations": "formation"}


def _widget(nom, type_, options, valeur, cle):
    etiquette = nom.replace("_", " ").capitalize()
    if type_ == "text":
        return st.text_input(etiquette, value=valeur or "", key=cle)
    if type_ == "area":
        return st.text_area(etiquette, value=valeur or "", key=cle)
    if type_ == "int":
        return st.number_input(etiquette, min_value=1, max_value=500, value=int(valeur or 20), step=1, key=cle)
    return st.selectbox(etiquette, options, index=options.index(valeur) if valeur in options else 0, key=cle)


def crud_entite(ressource: str):
    elements = liste(ressource)
    titre = TITRES[ressource]
    st.dataframe(pd.DataFrame(elements), hide_index=True)

    with st.expander(f"➕ Créer un(e) {titre}"):
        with st.form(f"creer_{ressource}", clear_on_submit=True):
            valeurs = {n: _widget(n, t, o, None, f"c_{ressource}_{n}") for n, t, o in CHAMPS[ressource]}
            envoye = st.form_submit_button("Créer")
        if envoye and ecrire("POST", f"/{ressource}", json=valeurs, succes=f"{titre.capitalize()} créé(e)."):
            st.rerun()

    with st.expander(f"✏️ Modifier ou supprimer un(e) {titre}"):
        noms = libelles(elements)
        choix = st.selectbox("Élément", list(noms), format_func=noms.get, key=f"sel_{ressource}")
        courant = next(e for e in elements if e["id"] == choix)
        with st.form(f"modifier_{ressource}_{choix}"):
            valeurs = {n: _widget(n, t, o, courant.get(n), f"m_{ressource}_{choix}_{n}")
                       for n, t, o in CHAMPS[ressource]}
            envoye = st.form_submit_button("Enregistrer les modifications")
        if envoye and ecrire("PUT", f"/{ressource}/{choix}", json=valeurs, succes="Modifications enregistrées."):
            st.rerun()

        st.divider()
        force = st.checkbox("Supprimer aussi ses relations (force)", key=f"force_{ressource}")
        confirme = st.checkbox(f"Je confirme la suppression de {choix}", key=f"conf_{ressource}")
        if st.button("🗑️ Supprimer", key=f"del_{ressource}", disabled=not confirme):
            chemin = f"/{ressource}/{choix}" + ("?force=true" if force else "")
            if ecrire("DELETE", chemin, succes=f"{choix} supprimé(e)."):
                st.rerun()


def crud_relations():
    metiers, competences, formations = liste("metiers"), liste("competences"), liste("formations")
    nom_comp = libelles(competences)
    type_rel = st.radio("Relation", ["REQUIERT (Métier → Compétence)", "DEVELOPPE (Formation → Compétence)",
                                     "PREREQUIS (Compétence → Compétence)"], horizontal=True)

    if type_rel.startswith("REQUIERT"):
        nom_metier = libelles(metiers)
        mid = st.selectbox("Métier", list(nom_metier), format_func=nom_metier.get, key="rq_metier")
        actuelles = lire(f"/metiers/{mid}/competences") or []
        st.dataframe(pd.DataFrame(actuelles), hide_index=True)
        c1, c2, c3 = st.columns([3, 2, 1])
        cid = c1.selectbox("Compétence", list(nom_comp), format_func=nom_comp.get, key="rq_comp")
        imp = c2.slider("Importance", 1, 5, 3, key="rq_imp")
        if c3.button("Ajouter / mettre à jour", key="rq_add") and ecrire(
                "PUT", f"/metiers/{mid}/competences/{cid}", json={"importance": imp}, succes="Relation enregistrée."):
            st.rerun()
        if actuelles:
            retirer = st.selectbox("Retirer", [a["id"] for a in actuelles], format_func=nom_comp.get, key="rq_del")
            if st.button("Retirer cette compétence", key="rq_del_btn") and ecrire(
                    "DELETE", f"/metiers/{mid}/competences/{retirer}", succes="Relation supprimée."):
                st.rerun()

    elif type_rel.startswith("DEVELOPPE"):
        nom_form = libelles(formations)
        fid = st.selectbox("Formation", list(nom_form), format_func=nom_form.get, key="dv_form")
        actuelles = lire(f"/formations/{fid}/competences") or []
        st.dataframe(pd.DataFrame(actuelles), hide_index=True)
        c1, c2, c3 = st.columns([3, 2, 1])
        cid = c1.selectbox("Compétence", list(nom_comp), format_func=nom_comp.get, key="dv_comp")
        niv = c2.slider("Niveau acquis", 1, 3, 2, key="dv_niv")
        if c3.button("Ajouter / mettre à jour", key="dv_add") and ecrire(
                "PUT", f"/formations/{fid}/competences/{cid}", json={"niveau_acquis": niv},
                succes="Relation enregistrée."):
            st.rerun()
        if actuelles:
            retirer = st.selectbox("Retirer", [a["id"] for a in actuelles], format_func=nom_comp.get, key="dv_del")
            if st.button("Retirer cette compétence", key="dv_del_btn") and ecrire(
                    "DELETE", f"/formations/{fid}/competences/{retirer}", succes="Relation supprimée."):
                st.rerun()

    else:
        cid = st.selectbox("Compétence", list(nom_comp), format_func=nom_comp.get, key="pr_comp")
        directs = (lire(f"/competences/{cid}/prerequis", profondeur=1) or {}).get("prerequis", [])
        st.write("Prérequis directs :", ", ".join(p["nom"] for p in directs) or "aucun")
        autres = [c for c in nom_comp if c != cid]
        pid = st.selectbox("Nouveau prérequis", autres, format_func=nom_comp.get, key="pr_new")
        if st.button("Ajouter le prérequis", key="pr_add") and ecrire(
                "PUT", f"/competences/{cid}/prerequis/{pid}", succes="Prérequis ajouté."):
            st.rerun()
        if directs:
            retirer = st.selectbox("Retirer", [p["id"] for p in directs], format_func=nom_comp.get, key="pr_del")
            if st.button("Retirer ce prérequis", key="pr_del_btn") and ecrire(
                    "DELETE", f"/competences/{cid}/prerequis/{retirer}", succes="Prérequis supprimé."):
                st.rerun()


def page_gestion():
    st.header("🛠️ Gestion des données")
    if not API_KEY:
        st.warning("API_KEY n'est pas définie dans .env : les écritures seront refusées par l'API.")
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)
    onglets = st.tabs(["Métiers", "Compétences", "Formations", "Relations"])
    with onglets[0]:
        crud_entite("metiers")
    with onglets[1]:
        crud_entite("competences")
    with onglets[2]:
        crud_entite("formations")
    with onglets[3]:
        crud_relations()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
PAGES = {
    "🎯 Recommandation": page_recommandation,
    "🗺️ Explorer le graphe": page_exploration,
    "📊 Analyses": page_analyses,
    "🛠️ Gestion des données": page_gestion,
}


def main():
    st.sidebar.title("🎓 P30")
    st.sidebar.caption("Recommandation de parcours de formation par compétences (Neo4j)")
    choix = st.sidebar.radio("Navigation", list(PAGES))
    try:
        sante = appeler("GET", "/health")
        st.sidebar.success(f"API : {sante['api']} · Neo4j : {sante['neo4j']}")
    except ErreurAPI as exc:
        st.sidebar.error(str(exc))
    st.sidebar.caption(f"API : {API_URL}")
    PAGES[choix]()


main()
