#!/usr/bin/env python3
"""
lint_vault.py — Contrôle du frontmatter et des tâches d'un second cerveau Obsidian.

Raison d'être : un référentiel qui classe par properties n'a aucun signal
naturel quand les properties se dégradent. Une note mal renseignée n'est pas
cassée, elle est juste invisible : aucune vue ne la remonte, et personne ne
s'en aperçoit. Sur le référentiel d'origine, le système de classement a déjà
été débranché une fois de cette façon (environ un quart des notes seulement
portaient un frontmatter exploitable). Ce lint est ce signal.

Doctrine :
  - LECTURE SEULE. Ce script ne modifie jamais une note.
  - Le moteur ne connaît aucune valeur métier : vocabulaires et paramètres
    sont lus dans `regles/referentiel.yaml`.
  - Le vocabulaire `sujet:` est lu DEPUIS le dossier des sujets du vault (une
    note par sujet), jamais dupliqué : une seule source de vérité.
    La règle est « la cible est DANS le dossier », jamais « la cible existe » :
    Obsidian ne contraint pas la cible d'un lien, la fermeture du vocabulaire
    tient entièrement à ce contrôle.
  - Trois sévérités. ERROR = la note ment (valeur hors vocabulaire, graphe
    cassé). WARN = la note est incomplète. INFO = signal, pas dette.
  - Chaque règle est binaire et applicable sans jugement (« test de
    l'agent ») : c'est ce qui permet à un modèle léger d'écrire dans le
    référentiel sans le corrompre. L'erreur est attrapée ici, elle n'est pas
    prévenue par la subtilité des instructions.
  - Rejouable, sans effet de bord, utilisable en hook pre-commit (--staged).

Usage :
    python controles/lint_vault.py --vault exemples/vault-exemple
    python controles/lint_vault.py --vault <vault> --strict      # exit 1 si ERROR
    python controles/lint_vault.py --vault <vault> --staged      # hook pre-commit
    python controles/lint_vault.py --vault <vault> --summary     # résumé seul
    python controles/lint_vault.py --vault <vault> --seuil INFO --limite 0
    python controles/lint_vault.py --vault <vault> --regles autre_referentiel.yaml
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install pyyaml")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------
# 1. RÉFÉRENTIEL — chargé depuis regles/referentiel.yaml
# --------------------------------------------------------------------------

REFERENTIEL_DEFAUT = Path(__file__).resolve().parent.parent / "regles" / "referentiel.yaml"


def charger_referentiel(chemin: Path = REFERENTIEL_DEFAUT) -> SimpleNamespace:
    """Charge le référentiel et convertit les listes en ensembles."""
    brut = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
    r = SimpleNamespace(**brut)
    for clef in ("types", "types_sans_sujet", "types_journal", "types_hub",
                 "statuses", "statuses_endormis", "sources", "recurrences",
                 "tags_energie", "tags_ligne_autorises", "familles_miroir",
                 "tags_fonctionnels", "dirs_ignores", "fichiers_ignores",
                 "dirs_templates"):
        setattr(r, clef, set(getattr(r, clef) or []))
    r.dossiers_autorises = frozenset(r.dossiers_autorises or [])
    r.perimetre_orphelines = tuple(r.perimetre_orphelines or [])
    r.dossiers_basse_priorite = tuple(r.dossiers_basse_priorite or [])
    r.dossiers_ref_externe = tuple(r.dossiers_ref_externe or [])
    r.profondeur_frontiere = dict(r.profondeur_frontiere or {})
    r.cles_en_attente_arbitrage = dict(r.cles_en_attente_arbitrage or {})
    return r


R = charger_referentiel()

SEVERITES = ("ERROR", "WARN", "INFO")

RE_CLEF_FM = re.compile(r"^[A-Za-z_][\w-]*:")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
RE_PEREMPTION = re.compile(r"^(\d{4}|\d{4}-\d{2}|permanent)$")
# Le lookbehind écarte : un `#` collé à un mot (URL, ancre), un `##` de titre,
# un backtick (code inline) et un guillemet (tag cité dans du code).
RE_TAG_LIGNE = re.compile(r"""(?<![\w&#`"'])#([A-Za-zÀ-ÿ][\wÀ-ſ/-]*)""")
RE_TITRE_MD = re.compile(r"^#{1,6}\s")
# Zones où un `#` n'est pas un tag : code inline, ancre de wikilink, lien markdown.
RE_ZONES_NEUTRES = re.compile(r"`[^`]*`|\[\[[^\]]*\]\]|\]\([^)]*\)")
# Statuts de tâches du plugin Tasks : ` ` à faire, `x` fait, `/` en cours,
# `-` annulé, `w` en attente/délégué, `?` idée, `J` jalon.
RE_LIGNE_TACHE = re.compile(r"^\s*[-*]\s+\[([ xX/\-w?J])\]")
# `🆔` identifiant unique au vault, `⛔` = « dépend de » (fin → début).
# Les deux emojis sont RÉSERVÉS aux lignes de tâches.
RE_ID_TACHE = re.compile(r"🆔\s*([A-Za-z0-9_-]+)")
RE_DEPENDS = re.compile(r"⛔\s*([A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)*)")
PREFIXE_JALON = "🏁 JALON — "
STATUTS_FAITS = {"x", "X", "-"}
STATUTS_OUVERTS_DOUBLON = {" ", "/", "w"}


def neutraliser(ligne: str) -> str:
    return RE_ZONES_NEUTRES.sub(lambda m: " " * len(m.group(0)), ligne)


# --------------------------------------------------------------------------
# 2. VOCABULAIRE SUJET — lu depuis le dossier, jamais dupliqué
# --------------------------------------------------------------------------

def charger_vocabulaire_sujet(vault: Path) -> set[str]:
    """Un sujet EST une note du dossier des sujets. Le dossier fait office de
    frontière d'habilitation : le référentiel peut contenir bien d'autres
    `moc`, aucune ne devient un sujet valide par accident."""
    dossier = vault / R.dossier_sujets
    if not dossier.is_dir():
        return set()
    return {p.stem for p in dossier.glob("*.md")}


# --------------------------------------------------------------------------
# 3. PARSING
# --------------------------------------------------------------------------

def ouvre_un_frontmatter(texte: str) -> bool:
    """Un `---` en tête n'est pas forcément un frontmatter : certaines notes
    commencent par une ligne horizontale markdown. Un vrai frontmatter
    enchaîne sur une ligne `clef:`."""
    if not texte.startswith("---"):
        return False
    for ligne in texte[3:].split("\n")[1:]:
        if not ligne.strip():
            continue
        return bool(RE_CLEF_FM.match(ligne))
    return False


def lire_frontmatter(texte: str) -> tuple[dict | None, str, str | None]:
    """Retourne (frontmatter, corps, erreur_yaml)."""
    if not ouvre_un_frontmatter(texte):
        return None, texte, None
    fin = texte.find("\n---", 3)
    if fin == -1:
        return None, texte, "délimiteur de fermeture `---` absent"
    brut = texte[3:fin]
    corps = texte[fin + 4:]
    try:
        fm = yaml.safe_load(brut)
    except yaml.YAMLError as e:
        return None, corps, f"YAML invalide : {str(e).splitlines()[0]}"
    if fm is None:
        return {}, corps, None
    if not isinstance(fm, dict):
        return None, corps, "le frontmatter n'est pas un dictionnaire"
    return fm, corps, None


def en_liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, list):
        return [v for v in valeur if v is not None and str(v).strip() != ""]
    if str(valeur).strip() == "":
        return []
    return [valeur]


def vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip()) \
        or (isinstance(valeur, list) and not valeur)


# --------------------------------------------------------------------------
# 4. INDEX GLOBAUX — certains invariants portent sur le VAULT, pas sur une note
# --------------------------------------------------------------------------

class Constat:
    __slots__ = ("severite", "regle", "note", "detail", "froid")

    def __init__(self, severite: str, regle: str, note: str, detail: str = ""):
        self.severite = severite
        self.regle = regle
        self.note = note
        self.detail = detail
        # Dette FROIDE : constat porté par une note endormie. Compté à part.
        self.froid = False

    def __repr__(self) -> str:
        return f"Constat({self.severite}, {self.regle}, {self.note})"


def notes_du_vault(vault: Path, avec_templates: bool = False):
    """Itère (chemin, chemin relatif posix) sur les notes du périmètre."""
    for p in sorted(vault.rglob("*.md")):
        parts = p.relative_to(vault).parts
        if any(part in R.dirs_ignores for part in parts):
            continue
        if not avec_templates and parts[0] in R.dirs_templates:
            continue
        rel = p.relative_to(vault).as_posix()
        if rel in R.fichiers_ignores or p.name in R.fichiers_ignores:
            continue
        yield p, rel


def lire(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return None


def indexer_types(vault: Path) -> dict[str, str]:
    """basename -> valeur de `type:`. Sert à vérifier la cible de `projet:`."""
    index: dict[str, str] = {}
    for p, _ in notes_du_vault(vault, avec_templates=True):
        texte = lire(p)
        if texte is None:
            continue
        fm, _, _ = lire_frontmatter(texte)
        t = fm.get("type") if isinstance(fm, dict) else None
        index[p.stem] = str(t).strip() if t and not isinstance(t, list) else ""
    return index


def lignes_hors_code(texte: str):
    """Itère (numéro, ligne) hors des blocs de code (y compris en callout)."""
    dans_code = False
    for i, ligne in enumerate(texte.splitlines(), 1):
        if ligne.strip().lstrip("> ").startswith("```"):
            dans_code = not dans_code
            continue
        if not dans_code:
            yield i, ligne


def indexer_taches(vault: Path) -> list[dict]:
    """Toutes les lignes de tâches portant `🆔` ou `⛔`. Un identifiant est
    unique au VAULT et une dépendance traverse les notes : l'index se
    construit toujours sur tout le vault, même quand on n'en scanne qu'une
    partie."""
    taches: list[dict] = []
    for p, rel in notes_du_vault(vault):
        texte = lire(p)
        if texte is None:
            continue
        for i, ligne in lignes_hors_code(texte):
            m = RE_LIGNE_TACHE.match(ligne)
            if not m:
                continue
            ids = RE_ID_TACHE.findall(ligne)
            m_dep = RE_DEPENDS.search(ligne)
            deps = [d.strip() for d in m_dep.group(1).split(",")] if m_dep else []
            if ids or deps:
                taches.append({"note": rel, "ligne": i, "statut": m.group(1),
                               "ids": ids, "deps": deps,
                               "jalon": m.group(1) == "J"})
    return taches


def indexer_focus(vault: Path) -> list[str]:
    """Notes portant `focus: true` (le plafond est un invariant du vault)."""
    focalisees: list[str] = []
    for p, rel in notes_du_vault(vault):
        texte = lire(p)
        if texte is None:
            continue
        fm, _, _ = lire_frontmatter(texte)
        if isinstance(fm, dict) and fm.get("focus") is True:
            focalisees.append(rel)
    return focalisees


def controler_focus(focalisees: list[str]) -> list[Constat]:
    """Plafond de `focus`. Le constat est posé sur CHACUNE des notes
    focalisées : dépasser le plafond n'est pas la faute d'une note, c'est un
    arbitrage qui n'a pas été rendu, et il faut voir toute la liste pour
    choisir laquelle sort."""
    if len(focalisees) <= R.focus_plafond:
        return []
    liste = ", ".join(Path(r).stem for r in focalisees)
    return [Constat("ERROR", "focus-hors-plafond", rel,
                    f"{len(focalisees)} hubs portent `focus: true` (plafond "
                    f"{R.focus_plafond}) — {liste}")
            for rel in focalisees]


# -- Doublons probables de tâches ------------------------------------------
# Constat d'origine : un audit de la file de tâches a trouvé une vingtaine de
# groupes de doublons, presque tous au patron « journal du jour → hub ». La
# parade est un contrôle, pas une consigne. Similarité de Jaccard sur les mots
# significatifs, entre lignes OUVERTES de fichiers DIFFÉRENTS. Exclus : tâches
# récurrentes (`🔁`), idées, jalons, notes endormies, itérations d'un même hub
# récurrent ; deux lignes aux [[liens]] disjoints ne sont pas comparées.
RE_DOUBLON_BRUIT = re.compile(
    r"#\w+|[🆔⛔]\s*[\w-]+(?:\s*,\s*[\w-]+)*|[⏱📅⏳🛫✅❌➕]\s*[\w:.\-]*|[⏫🔼🔽⏬🔺]|"
    r"\*\*|`|\[\[|\]\]")
MOTS_VIDES_DOUBLON = {
    "les", "des", "une", "pour", "dans", "avec", "sur", "que", "qui", "par",
    "aux", "est", "son", "ses", "the", "and", "pas", "puis", "sans", "cet",
    "cette", "plus", "fait", "faire", "tout", "tous",
}
RE_PERIODE_NOM = re.compile(r"\d{4}-\d{2}")


def mots_doublon(ligne: str) -> frozenset[str]:
    """Mots significatifs d'une ligne de tâche (accents et casse neutralisés)."""
    corps = RE_LIGNE_TACHE.sub("", ligne, count=1)
    corps = RE_DOUBLON_BRUIT.sub(" ", corps)
    corps = unicodedata.normalize("NFD", corps.lower())
    corps = "".join(ch for ch in corps if not unicodedata.combining(ch))
    return frozenset(m for m in re.findall(r"[a-z0-9]{3,}", corps)
                     if m not in MOTS_VIDES_DOUBLON)


def indexer_taches_ouvertes(vault: Path) -> list[dict]:
    out: list[dict] = []
    hubs_recurrents: set[str] = set()
    for p, rel in notes_du_vault(vault):
        texte = lire(p)
        if texte is None:
            continue
        fm, _, _ = lire_frontmatter(texte)
        projet_note = None
        if isinstance(fm, dict):
            if fm.get("recurrence"):
                hubs_recurrents.add(p.stem)
            cibles = RE_WIKILINK.findall(str(fm.get("projet") or ""))
            projet_note = cibles[0] if cibles else None
            if str(fm.get("status") or "").strip() in R.statuses_endormis:
                continue
        for i, ligne in lignes_hors_code(texte):
            m = RE_LIGNE_TACHE.match(ligne)
            if not m or m.group(1) not in STATUTS_OUVERTS_DOUBLON \
                    or "#task" not in ligne or "🔁" in ligne:
                continue
            mots = mots_doublon(ligne)
            if len(mots) >= R.doublon_min_mots:
                liens = frozenset(x for x in RE_WIKILINK.findall(ligne)
                                  if x != R.nom_agent)
                out.append({"note": rel, "ligne": i, "mots": mots,
                            "liens": liens, "projet": projet_note})
    for t in out:
        t["hub_recurrent"] = t["projet"] if t["projet"] in hubs_recurrents else None
    return out


def _iterations_du_meme_hub(a: dict, b: dict) -> bool:
    """Deux itérations d'un même hub récurrent réinstancient la même tâche
    par construction : ce n'est jamais un doublon."""
    if a["hub_recurrent"] and a["hub_recurrent"] == b["hub_recurrent"]:
        return True
    na, nb = Path(a["note"]).stem, Path(b["note"]).stem
    return na != nb and RE_PERIODE_NOM.search(na) is not None \
        and RE_PERIODE_NOM.sub("", na) == RE_PERIODE_NOM.sub("", nb)


def controler_doublons(taches: list[dict]) -> list[Constat]:
    """WARN `tache-doublon-probable` : un constat par note."""
    meilleur: dict[str, tuple[float, dict, dict]] = {}
    nb: dict[str, int] = {}
    for a_i, a in enumerate(taches):
        for b in taches[a_i + 1:]:
            if a["note"] == b["note"] or _iterations_du_meme_hub(a, b):
                continue
            inter = len(a["mots"] & b["mots"])
            if not inter:
                continue
            if a["liens"] and b["liens"] and not (a["liens"] & b["liens"]):
                continue
            score = inter / len(a["mots"] | b["mots"])
            if score < R.doublon_seuil:
                continue
            for x, y in ((a, b), (b, a)):
                nb[x["note"]] = nb.get(x["note"], 0) + 1
                if x["note"] not in meilleur or score > meilleur[x["note"]][0]:
                    meilleur[x["note"]] = (score, x, y)
    return [Constat("WARN", "tache-doublon-probable", note,
                    f"{nb[note]} paire(s) — ex. ligne {x['ligne']} proche de "
                    f"`{y['note']}` ligne {y['ligne']} (similarité {score:.2f}) : "
                    "traiter l'une des deux, ou annuler le doublon")
            for note, (score, x, y) in sorted(meilleur.items())]


def controler_graphe(taches: list[dict]) -> list[Constat]:
    """Contrôles globaux du graphe `🆔`/`⛔` : identifiants en double,
    dépendances mortes, cycles, jalons franchissables."""
    constats: list[Constat] = []
    par_id: dict[str, list[dict]] = defaultdict(list)
    for t in taches:
        for ident in t["ids"]:
            par_id[ident].append(t)

    # Collision d'identifiants : chaque 🆔 est unique au vault.
    for ident, porteurs in par_id.items():
        if len(porteurs) > 1:
            lieux = ", ".join(f"`{t['note']}:{t['ligne']}`" for t in porteurs)
            for t in porteurs:
                constats.append(Constat("ERROR", "id-en-double", t["note"],
                                        f"`🆔 {ident}` porté par plusieurs lignes : {lieux}"))

    # Dépendance morte : ⛔ vers un 🆔 qui n'existe pas.
    for t in taches:
        for d in t["deps"]:
            if d not in par_id:
                constats.append(Constat("ERROR", "dependance-morte", t["note"],
                                        f"ligne {t['ligne']} : `⛔ {d}` ne correspond "
                                        "à aucun `🆔` du vault"))

    # Cycle : A bloque B qui bloque A (parcours en profondeur).
    graphe = {}
    for t in taches:
        for ident in t["ids"]:
            graphe[ident] = [d for d in t["deps"] if d in par_id]
    etat: dict[str, int] = {}  # 0 = vierge, 1 = en cours, 2 = fini
    cycles_vus: set[frozenset] = set()

    def visite(n: str, pile: list[str]) -> None:
        etat[n] = 1
        for v in graphe.get(n, []):
            if etat.get(v) == 1:
                cycle = pile[pile.index(v):] if v in pile else [n, v]
                clef = frozenset(cycle)
                if clef not in cycles_vus:
                    cycles_vus.add(clef)
                    porteur = par_id[cycle[0]][0]
                    constats.append(Constat("ERROR", "cycle-dependances", porteur["note"],
                                            "cycle : " + " → ".join(cycle + [cycle[0]])))
            elif etat.get(v, 0) == 0:
                visite(v, pile + [v])
        etat[n] = 2

    for n in graphe:
        if etat.get(n, 0) == 0:
            visite(n, [n])

    # Jalon franchissable : toutes ses dépendances sont faites. INFO : c'est
    # le signal « un jalon attend ta validation » — le cocher reste un geste
    # humain, jamais un automatisme.
    fait = {ident: t["statut"] in STATUTS_FAITS for t in taches for ident in t["ids"]}
    for t in taches:
        if t["jalon"] and t["statut"] not in STATUTS_FAITS and t["deps"] \
                and all(fait.get(d, False) for d in t["deps"]):
            constats.append(Constat("INFO", "jalon-franchissable", t["note"],
                                    f"ligne {t['ligne']} : toutes les dépendances sont "
                                    "faites — le jalon attend sa validation"))
    return constats


# --------------------------------------------------------------------------
# 5. RÈGLES PAR NOTE
# --------------------------------------------------------------------------

def controler_template(rel: str, texte: str) -> list[Constat]:
    """Un template contient des placeholders (`created: {{date}}`) qui ne sont
    pas du YAML valide : on contrôle seulement la PRÉSENCE des clefs."""
    c: list[Constat] = []
    if not texte.startswith("---"):
        return [Constat("WARN", "template-sans-frontmatter", rel,
                        "un template doit porter le schéma")]
    fin = texte.find("\n---", 3)
    entete = texte[3:fin] if fin != -1 else texte
    clefs = set(re.findall(r"^([A-Za-z_][\w-]*):", entete, re.MULTILINE))
    for ancienne, nouvelle in R.cles_obsoletes.items():
        if ancienne in clefs:
            c.append(Constat("WARN", "cle-obsolete", rel, f"`{ancienne}` → `{nouvelle}`"))
    for attendue in ("type", "summary", "created"):
        if attendue not in clefs:
            c.append(Constat("WARN", "template-clef-manquante", rel,
                             f"`{attendue}` absente du schéma du template"))
    return c


def controler(rel: str, texte: str, sujets_valides: set[str],
              index_types: dict[str, str] | None = None) -> list[Constat]:
    """Toutes les règles qui se jugent sur une note seule."""
    texte = texte.replace("\r\n", "\n")
    if rel.split("/")[0] in R.dirs_templates:
        return controler_template(rel, texte)

    c: list[Constat] = []

    def add(s: str, r: str, d: str = "") -> None:
        c.append(Constat(s, r, rel, d))

    # -- Aucune note orpheline : au moins un wikilink sortant ----------------
    if rel.startswith(R.perimetre_orphelines) and "[[" not in texte:
        add("WARN", "note-orpheline",
            "aucun wikilink sortant — ajouter `##### Refs` vers la note-tête du dossier")

    fm, corps, err_yaml = lire_frontmatter(texte)
    if err_yaml:
        add("ERROR", "frontmatter-illisible", err_yaml)
        return c
    if fm is None:
        add("ERROR", "frontmatter-absent", "aucun bloc `---` en tête")
        return c

    # -- clefs obsolètes ----------------------------------------------------
    for ancienne, nouvelle in R.cles_obsoletes.items():
        if ancienne in fm:
            add("WARN", "cle-obsolete", f"`{ancienne}` → `{nouvelle}`")
    for clef, motif in R.cles_en_attente_arbitrage.items():
        if clef in fm:
            add("INFO", "cle-en-attente-arbitrage", f"`{clef}` — {motif}")

    type_ = fm.get("type")
    type_str = str(type_).strip() if not vide(type_) else None

    # -- type ---------------------------------------------------------------
    if type_str is None:
        add("WARN", "type-absent")
    elif type_str in R.types_a_remapper:
        add("WARN", "type-a-remapper", f"`{type_str}` → `{R.types_a_remapper[type_str]}`")
    elif type_str in R.types_supprimes:
        add("ERROR", "type-supprime",
            f"`{type_str}` a été supprimé du référentiel → `{R.types_supprimes[type_str]}`")
    elif type_str not in R.types:
        add("ERROR", "type-invalide", f"`{type_str}`")

    # -- summary ------------------------------------------------------------
    summary = fm.get("summary")
    if vide(summary):
        add("WARN", "summary-absent")
    else:
        s = str(summary)
        if len(s) < R.summary_caracteres_min:
            add("INFO", "summary-trop-court", f"{len(s)} caractères")
        nb_mots = len(s.split())
        if nb_mots > R.summary_mots_max:
            add("WARN", "summary-trop-long",
                f"{nb_mots} mots (max {R.summary_mots_max}) — le summary alimente "
                "toutes les vues, il doit se lire d'un coup d'œil")

    # -- sujet --------------------------------------------------------------
    # Une note DU dossier des sujets est le sujet : elle n'en porte pas.
    est_note_sujet = rel.startswith(R.dossier_sujets + "/")
    sujets = en_liste(fm.get("sujet"))
    if not sujets:
        if type_str not in R.types_sans_sujet and not est_note_sujet:
            add("WARN", "sujet-absent")
    elif est_note_sujet:
        add("ERROR", "sujet-sur-note-sujet",
            "une note de sujet ne porte pas `sujet:` — elle EST le sujet")
    else:
        if len(sujets) > R.sujets_max:
            add("WARN", "sujet-trop-nombreux", f"{len(sujets)} valeurs (max {R.sujets_max})")
        for s in sujets:
            # Piège YAML : `- [[compta]]` NON quoté parse en liste imbriquée
            # (`[[a]]` == `[ [ a ] ]`). Obsidian écrit toujours quoté ; un
            # modèle léger qui rédige le frontmatter à la main, non.
            if isinstance(s, (list, dict)):
                add("ERROR", "sujet-yaml-imbrique",
                    '`- [[x]]` non quoté parse en liste imbriquée — écrire `- "[[x]]"`')
                continue
            brut = str(s).strip()
            m = RE_WIKILINK.fullmatch(brut)
            if not m:
                add("ERROR", "sujet-pas-un-wikilink",
                    f'`{brut[:40]}` — attendu : "[[nom_du_sujet]]"')
                continue
            cible = m.group(1).strip().split("/")[-1]
            if cible not in sujets_valides:
                add("ERROR", "sujet-hors-vocabulaire",
                    f"`{cible}` n'est pas une note de `{R.dossier_sujets}/`")

    # -- projet : la cible est TOUJOURS un hub `projet-chantier` -------------
    # Le rattachement à un client ou un rôle passe par l'emplacement et par
    # `lien:`, jamais par `projet:`. Règle binaire.
    if index_types is not None:
        for val in en_liste(fm.get("projet")):
            m = RE_WIKILINK.search(str(val))
            if not m:
                add("ERROR", "projet-pas-un-wikilink",
                    f'`{str(val)[:40]}` — attendu : "[[Nom du hub]]"')
                continue
            cible = m.group(1).strip()
            if cible not in index_types:
                add("ERROR", "projet-cible-introuvable", f"[[{cible}]] n'existe pas")
            elif index_types[cible] not in R.types_hub:
                add("ERROR", "projet-cible-non-projet",
                    f"[[{cible}]] est `type: {index_types[cible] or '?'}` — la cible de "
                    "`projet:` doit être un hub `projet-chantier` ; rattachement "
                    "client/rôle : emplacement + `lien:`")

    # -- status -------------------------------------------------------------
    st = fm.get("status")
    if not vide(st) and str(st).strip() not in R.statuses:
        add("ERROR", "status-invalide",
            f"`{st}` (attendu : {' | '.join(sorted(R.statuses))})")

    # -- recurrence : hubs récurrents seulement -----------------------------
    rec = fm.get("recurrence")
    if not vide(rec):
        if type_str not in R.types_hub:
            add("ERROR", "recurrence-hors-hub",
                f"`recurrence:` sur `type: {type_str or '?'}` — réservée aux hubs")
        if str(rec).strip() not in R.recurrences:
            add("ERROR", "recurrence-invalide",
                f"`{rec}` (attendu : {' | '.join(sorted(R.recurrences))})")

    # -- focus : deux règles binaires (le plafond est un contrôle global) ---
    if "focus" in fm:
        foc = fm.get("focus")
        if not vide(foc):
            if type_str not in R.types_hub:
                add("ERROR", "focus-hors-hub",
                    f"`focus:` sur `type: {type_str or '?'}` — réservée aux hubs")
            if not isinstance(foc, bool):
                add("ERROR", "focus-invalide",
                    f"`{foc}` — `focus:` est booléenne (`true` ou absente) ; "
                    "une chaîne ne serait comptée par aucun contrôle")

    # -- ref_externe : rattachement d'un hub à l'outil de suivi d'un client -
    if "ref_externe" in fm:
        ref = fm.get("ref_externe")
        if not vide(ref):
            if type_str not in R.types_hub:
                add("ERROR", "ref-externe-hors-hub",
                    f"`ref_externe:` sur `type: {type_str or '?'}` — réservée aux hubs")
            if isinstance(ref, bool) or not isinstance(ref, int) or ref <= 0:
                add("ERROR", "ref-externe-invalide",
                    f"`{ref}` — `ref_externe:` est l'identifiant entier du projet externe")
            if not rel.startswith(R.dossiers_ref_externe):
                add("ERROR", "ref-externe-hors-perimetre",
                    "`ref_externe:` n'a de sens que dans un dossier client relié à "
                    f"un outil de suivi ({', '.join(R.dossiers_ref_externe)})")

    # -- source : la règle « human = corps immuable » ne protège que ce qui
    #    est qualifié ------------------------------------------------------
    src = fm.get("source")
    if vide(src):
        add("WARN", "source-absent")
    elif str(src).strip() not in R.sources:
        add("ERROR", "source-invalide",
            f"`{str(src)[:40]}` (attendu : {' | '.join(sorted(R.sources))})")

    # -- created ------------------------------------------------------------
    cr = fm.get("created")
    if vide(cr):
        add("WARN", "created-absent")
    else:
        cr_str = cr.isoformat() if hasattr(cr, "isoformat") else str(cr).strip()
        if not RE_DATE.fullmatch(cr_str):
            add("WARN", "created-format", f"`{cr_str}` (attendu AAAA-MM-JJ)")

    # -- peremption ---------------------------------------------------------
    per = fm.get("peremption")
    if not vide(per):
        per_str = per.isoformat()[:7] if hasattr(per, "isoformat") else str(per).strip()
        if not RE_PEREMPTION.fullmatch(per_str):
            add("WARN", "peremption-format", f"`{per_str}` (attendu AAAA | AAAA-MM | permanent)")
        elif per_str != "permanent":
            fin = per_str if len(per_str) == 7 else f"{per_str}-12"
            annee, mois = int(fin[:4]), int(fin[5:7])
            expire = datetime(annee + (mois // 12), (mois % 12) + 1, 1)
            if expire <= datetime.now() and str(st).strip() != "archive":
                add("INFO", "perime-non-archive", f"valide jusqu'à {fin}, status `{st}`")

    # -- importance ---------------------------------------------------------
    imp = fm.get("importance")
    if not vide(imp):
        try:
            if not 1 <= int(imp) <= 5:
                add("WARN", "importance-hors-bornes", f"`{imp}` (attendu 1-5)")
        except (ValueError, TypeError):
            add("WARN", "importance-non-numerique", f"`{imp}`")

    # -- tags en frontmatter ------------------------------------------------
    tags_fm = [str(t) for t in en_liste(fm.get("tags"))]
    # Le `#` dans une valeur de frontmatter crée un tag DISTINCT de la même
    # valeur sans `#` : deux tags qui coexistent et divergent.
    diese = [t for t in tags_fm if t.startswith("#")]
    if diese:
        add("ERROR", "diese-dans-frontmatter",
            f"{', '.join('`' + t + '`' for t in diese[:3])} — retirer le `#`, il crée un tag en double")
    tags_dette = [t for t in tags_fm
                  if t.lstrip("#").split("/")[0].lower() not in R.familles_miroir]
    if tags_dette:
        apercu = ", ".join(f"`{t}`" for t in tags_dette[:4])
        add("WARN", "tags-en-frontmatter",
            f"{len(tags_dette)} tag(s) : {apercu} — la taxonomie thématique relève de `sujet:`")

    lignes_corps = corps.splitlines()

    # -- encarts de réponse vides (notes de cadrage) ------------------------
    en_attente = 0
    fence = False
    for i, ligne in enumerate(lignes_corps):
        if ligne.strip().lstrip("> ").startswith("```"):
            fence = not fence
            continue
        if fence or not re.match(r"^(?:>\s?)+\[!todo\]\s*R[ée]ponse\s*$",
                                 ligne.strip(), re.IGNORECASE):
            continue
        rempli = False
        for suite in lignes_corps[i + 1:]:
            if not suite.strip().startswith(">"):
                break
            contenu = re.sub(r"^(?:>\s?)+", "", suite).strip()
            if contenu.startswith("[!"):
                break
            if contenu:
                rempli = True
                break
        if not rempli:
            en_attente += 1
    if en_attente:
        add("INFO", "reponses-en-attente",
            f"{en_attente} encart(s) « Réponse » vide(s) — des questions attendent l'humain")

    # -- commentaire de l'humain sans réponse de l'agent --------------------
    # Symétrique, charge inversée : c'est un travail de l'AGENT qui manque.
    # Casse et espaces libres : Obsidian accepte `[!Quote]`, `> >[!quote]`. Un
    # contrôle sensible à la casse se tairait sur des blocs valides — c'est
    # exactement ce qui a laissé passer sept commentaires dans une même note
    # sur le référentiel d'origine.
    quotes_orphelins = 0
    fence = False
    re_quote = re.compile(r"^((?:>\s*)+)\[!quote\]\s*" + re.escape(R.nom_humain) + r"\b",
                          re.IGNORECASE)
    for i, ligne in enumerate(lignes_corps):
        if ligne.strip().lstrip("> ").startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re_quote.match(ligne)
        if not m:
            continue
        prof = m.group(1).count(">")
        repondu = False
        for suite in lignes_corps[i + 1:]:
            if not suite.lstrip().startswith(">"):
                break
            ms = re.match(r"^((?:>\s*)+)(.*)$", suite)
            if not ms:
                break
            p_s, contenu = ms.group(1).count(">"), ms.group(2).strip()
            if contenu.startswith("[!"):
                if p_s > prof and re.match(r"\[!check\]", contenu, re.IGNORECASE):
                    repondu = True
                    break
                if p_s <= prof:
                    break
        if not repondu:
            quotes_orphelins += 1
    if quotes_orphelins:
        add("WARN", "quote-sans-reponse",
            f"{quotes_orphelins} commentaire(s) « [!quote] {R.nom_humain} » sans "
            f"« [!check] {R.reponse_agent} » imbriqué — travail de l'agent qui manque")

    # -- parcours ligne à ligne : retours chariot, tâches, tags, jalons ------
    dans_code = False
    retours_phrase = 0
    taches_journal = 0
    est_journal = type_str in R.types_journal
    prec_prose = False
    dans_quote_humain = False
    for ligne in lignes_corps:
        nu = ligne.strip()
        if nu.lstrip("> ").startswith("```"):
            dans_code = not dans_code
            prec_prose = False
            continue
        if dans_code or RE_TITRE_MD.match(nu):
            prec_prose = False
            continue

        # Retour chariot en cours de phrase : le retour à la ligne PORTE DU
        # SENS (paragraphe, item), il ne force jamais une largeur de colonne.
        # Une ligne de prose qui commence par une minuscule après une ligne
        # de prose est une phrase coupée.
        m_quote = re.match(r"^((?:>\s?)+)", ligne)
        prof_quote = m_quote.group(1).count(">") if m_quote else 0
        contenu_sans_quote = re.sub(r"^(?:>\s?)+", "", ligne)
        nu_sq = contenu_sans_quote.strip()
        est_structure = bool(re.match(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)", contenu_sans_quote)) \
            or nu_sq.startswith("<!--") or nu_sq.startswith("[!")
        if nu_sq.startswith("[!"):
            dans_quote_humain = nu_sq.lower().startswith("[!quote]")
        elif prof_quote == 0:
            dans_quote_humain = False
        # À partir de `> >` on est dans un encart de l'humain : ses retours
        # à la ligne sont les siens.
        if nu_sq and not est_structure and prec_prose and prof_quote < 2 \
                and not dans_quote_humain and re.match(r"^[a-zà-öø-ÿ]", nu_sq):
            retours_phrase += 1
        prec_prose = bool(nu_sq) and not nu_sq.startswith("<!--") \
            and not nu_sq.endswith("-->") and not nu_sq.startswith("[!") \
            and prof_quote < 2 and not re.match(r"^\s*\|", contenu_sans_quote)

        m_tache = RE_LIGNE_TACHE.match(ligne)
        est_tache = bool(m_tache)
        est_jalon = est_tache and m_tache.group(1) == "J"
        neutre = neutraliser(ligne)

        # Une tâche vit dans son hub, jamais dans un journal.
        if est_journal and est_tache and m_tache.group(1) not in STATUTS_FAITS \
                and re.search(r"(?:^|\s)#task(?:\s|$)", neutre):
            taches_journal += 1

        # Jalon = statut `[J]` + préfixe `🏁 JALON — `, sans tag d'énergie.
        if est_jalon and PREFIXE_JALON not in ligne:
            add("WARN", "jalon-sans-prefixe", "statut `[J]` sans `🏁 JALON — ` en tête")
        # Un jalon franchi passe en `[x]` et garde son `🏁` : pas une faute.
        if est_tache and not est_jalon and "🏁" in neutre and m_tache.group(1) not in STATUTS_FAITS:
            add("WARN", "jalon-sans-statut", "`🏁` sur une tâche ouverte qui n'est pas au statut `[J]`")
        if not est_tache and ("🆔" in neutre or "⛔" in neutre):
            add("WARN", "emoji-reserve-hors-tache",
                "`🆔`/`⛔` sont réservés aux lignes de tâches — en décoration, écrire une étiquette texte")

        # Le `#` ne s'écrit que pour les titres : un `#mot` dans le corps
        # crée un tag silencieusement.
        for t in RE_TAG_LIGNE.findall(neutre):
            if t.endswith("/"):
                continue  # préfixe cité, pas un tag
            racine = t.split("/")[0].lower()
            if racine in R.tags_fonctionnels or t in R.tags_ligne_autorises:
                continue
            if racine in R.tags_energie:
                if not est_tache:
                    add("INFO", "tag-hors-ligne-tache", f"`#{t}` sur une ligne qui n'est pas une tâche")
                elif est_jalon:
                    add("WARN", "jalon-avec-energie", f"`#{t}` sur un jalon — un jalon n'est pas du travail")
            else:
                add("WARN", "tag-inline-hors-whitelist",
                    f"`#{t}` — `#` réservé aux titres, sauf tags d'énergie sur une tâche "
                    "et marqueurs de ligne déclarés")

    if taches_journal:
        add("WARN", "tache-dans-journal",
            f"{taches_journal} tâche(s) ouverte(s) dans un journal — une tâche vit dans "
            "son hub ; le journal n'en garde qu'un résumé et un [[lien]]")

    # Une note `source: human` a un corps immuable : signaler une dette
    # qu'on n'a pas le droit de corriger serait du bruit.
    if retours_phrase and str(fm.get("source") or "").strip() != "human":
        add("WARN", "retour-chariot-en-phrase",
            f"{retours_phrase} ligne(s) coupée(s) en cours de phrase — le retour à la "
            "ligne porte du sens, il ne gère pas la largeur")

    # Note endormie : ses constats deviennent de la dette froide. Les sorties
    # anticipées (frontmatter absent ou cassé) restent chaudes : sans
    # frontmatter lisible, le statut est inconnaissable.
    if str(fm.get("status") or "").strip() in R.statuses_endormis:
        for constat in c:
            constat.froid = True
    return c


# --------------------------------------------------------------------------
# 6. CONTRÔLES DE STRUCTURE ET DE DURÉE
# --------------------------------------------------------------------------

def controler_dossiers(rels: set[str]) -> list[Constat]:
    """`dossier-non-frontiere` : tout dossier plus profond que le niveau
    frontière de sa racine, et absent de la liste blanche. Un dossier ne
    classe pas, il cloisonne."""
    vus: set[str] = set()
    for rel in rels:
        parts = rel.split("/")[:-1]
        if not parts:
            continue
        niveau = R.profondeur_frontiere.get(parts[0], 1)
        for prof in range(niveau + 1, len(parts) + 1):
            vus.add("/".join(parts[:prof]))
    return [Constat("INFO", "dossier-non-frontiere", d + "/",
                    "sous-dossier hors liste blanche — il doit matérialiser une "
                    "frontière de partage, sinon properties + vue")
            for d in sorted(vus - R.dossiers_autorises)]


def controler_agents_md(vault: Path) -> list[Constat]:
    """`agents-md-taille` : plafond en caractères du fichier d'instructions."""
    p = vault / "AGENTS.md"
    try:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            n = len(f.read())
    except OSError:
        return []
    if n <= R.agents_md_seuil:
        return []
    return [Constat("WARN", "agents-md-taille", "AGENTS.md",
                    f"{n} caractères (seuil {R.agents_md_seuil}) — la doctrine regrossit")]


def dates_git(vault: Path) -> dict[str, float] | None:
    """chemin relatif au vault -> horodatage du dernier commit qui le touche.
    Les fichiers modifiés ou non suivis valent « maintenant ». Un seul
    `git log` parcouru une fois, pas un appel par fichier. None si git est
    indisponible. Le mtime n'est pas fiable (une migration de masse le
    réécrit d'un coup) ; git sait ce qui a réellement changé."""
    kw = dict(cwd=vault, capture_output=True)
    try:
        pref = subprocess.run(["git", "rev-parse", "--show-prefix"], **kw)
        if pref.returncode != 0:
            return None
        prefixe = pref.stdout.decode().strip()
        log = subprocess.run(["git", "-c", "core.quotePath=false", "log", "--name-only",
                              "--no-renames", "--format=\x01%ct", "--", "."], **kw, timeout=180)
        st = subprocess.run(["git", "status", "--porcelain", "-z",
                             "--untracked-files=all", "--", "."], **kw, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if st.returncode != 0:
        return None
    if log.returncode != 0:
        log.stdout = b""  # dépôt sans aucun commit : rien n'est daté par l'historique

    def relatif(chemin: str) -> str | None:
        return chemin[len(prefixe):] if chemin.startswith(prefixe) else None

    dates: dict[str, float] = {}
    courant = 0.0
    for ligne in log.stdout.decode("utf-8", errors="replace").splitlines():
        if ligne.startswith("\x01"):
            courant = float(ligne[1:] or 0)
        elif ligne and (r := relatif(ligne)) and dates.get(r, 0.0) < courant:
            dates[r] = courant
    maintenant = time.time()
    champs = st.stdout.decode("utf-8", errors="replace").split("\0")
    i = 0
    while i < len(champs):
        champ = champs[i]
        i += 1
        if len(champ) < 4:
            continue
        xy, chemin = champ[:2], champ[3:]
        if (r := relatif(chemin)) is not None:
            dates[r] = maintenant
        if "R" in xy or "C" in xy:
            i += 1  # chemin d'origine d'un renommage
    return dates


def controler_dormants(candidats: list[str], dates: dict[str, float]) -> list[Constat]:
    """`actif-dormant` sur les hubs `active` non récurrents."""
    c: list[Constat] = []
    limite = time.time() - R.dormant_jours * 86400
    for rel in candidats:
        ts = dates.get(rel)
        if ts is None or ts >= limite:
            continue
        jours = int((time.time() - ts) // 86400)
        c.append(Constat("INFO", "actif-dormant", rel,
                         f"hub `active` sans modification depuis {jours} j (seuil "
                         f"{R.dormant_jours} j) — à basculer en `standby` lors d'un "
                         "traitement en bloc, jamais automatiquement"))
    return c


# --------------------------------------------------------------------------
# 7. PARCOURS
# --------------------------------------------------------------------------

def basse_priorite(rel: str) -> bool:
    return rel.startswith(R.dossiers_basse_priorite)


def retrograder(sev: str) -> str:
    return {"ERROR": "WARN", "WARN": "INFO", "INFO": "INFO"}[sev]


def fichiers_git(vault: Path, mode: str) -> set[str] | None:
    """Notes en index (`staged`) ou modifiées depuis HEAD (`changed`)."""
    cmd = {"staged": ["git", "diff", "--cached", "--name-only", "--relative", "--diff-filter=ACMR"],
           "changed": ["git", "diff", "HEAD", "--name-only", "--relative", "--diff-filter=ACMR"]}[mode]
    try:
        out = subprocess.run(cmd, cwd=vault, capture_output=True, text=True,
                             encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return {l.strip() for l in out.stdout.splitlines() if l.strip().endswith(".md")}


def parcourir(vault: Path, sujets_valides: set[str], sous_chemin: str | None = None,
              selection_git: set[str] | None = None,
              avec_git: bool = True) -> tuple[list[Constat], int]:
    constats: list[Constat] = []
    scannees = 0
    rels_scannes: set[str] = set()
    racine = vault / sous_chemin if sous_chemin else vault
    if not racine.exists():
        sys.exit(f"chemin introuvable : {racine}")

    # Index global (toujours sur TOUT le vault : une cible de `projet:` peut
    # vivre hors du sous-chemin scanné).
    index_types = indexer_types(vault)
    candidats_dormants: list[str] = []

    for p, rel in notes_du_vault(vault, avec_templates=True):
        if sous_chemin and not p.is_relative_to(racine):
            continue
        if selection_git is not None and rel not in selection_git:
            continue
        scannees += 1
        rels_scannes.add(rel)
        texte = lire(p)
        if texte is None:
            constats.append(Constat("ERROR", "illisible", rel, "lecture impossible"))
            continue
        for c in controler(rel, texte, sujets_valides, index_types):
            if basse_priorite(rel):
                c.severite = retrograder(c.severite)
            constats.append(c)
        fm, _, err = lire_frontmatter(texte)
        if isinstance(fm, dict) and not err \
                and str(fm.get("type") or "").strip() in R.types_hub \
                and str(fm.get("status") or "").strip() == "active" \
                and vide(fm.get("recurrence")):
            candidats_dormants.append(rel)

    # Contrôles globaux : index sur tout le vault, constats restreints au
    # périmètre scanné (pour que --staged ne remonte pas les notes des autres).
    globaux = (controler_graphe(indexer_taches(vault))
               + controler_doublons(indexer_taches_ouvertes(vault))
               + controler_focus(indexer_focus(vault)))
    for c in globaux:
        if c.note in rels_scannes:
            if basse_priorite(c.note):
                c.severite = retrograder(c.severite)
            constats.append(c)

    if avec_git:
        dates = dates_git(vault)
        if dates is None:
            print("git indisponible — contrôle `actif-dormant` ignoré.", file=sys.stderr)
        else:
            constats.extend(controler_dormants(candidats_dormants, dates))

    constats.extend(controler_dossiers(rels_scannes))
    if (selection_git is None and not sous_chemin) \
            or (selection_git is not None and "AGENTS.md" in selection_git):
        constats.extend(controler_agents_md(vault))
    return constats, scannees


# --------------------------------------------------------------------------
# 8. RESTITUTION
# --------------------------------------------------------------------------

def compter(constats: list[Constat]) -> dict[str, int]:
    n = dict.fromkeys(SEVERITES, 0)
    for c in constats:
        n[c.severite] += 1
    return n


def afficher_resume(constats: list[Constat], scannees: int, seuil: str = "INFO") -> None:
    # Sous --seuil ERROR, les WARN/INFO ne sont ni listés ni comptés ligne à
    # ligne : le signal reste binaire pour un agent (propre, ou actionnable).
    rang = {s: i for i, s in enumerate(SEVERITES)}
    retenus = [c for c in constats if rang[c.severite] <= rang[seuil]]
    masques = len(constats) - len(retenus)
    n = compter(retenus)
    par_regle = Counter(c.regle for c in retenus)
    print(f"lint : {scannees} notes scannées, {len({c.note for c in retenus})} "
          f"avec au moins un constat au seuil {seuil}")
    print("  " + "   ".join(f"{s} {n[s]:4d}" for s in SEVERITES if rang[s] <= rang[seuil]))
    for regle, cpt in par_regle.most_common(5):
        print(f"  · {regle:28s} {cpt:4d}")
    if masques:
        print(f"  ({masques} constat(s) sous le seuil masqué(s))")


def afficher_detail(constats: list[Constat], seuil: str, limite: int) -> None:
    rang = {s: i for i, s in enumerate(SEVERITES)}
    par_note: dict[str, list[Constat]] = defaultdict(list)
    for c in constats:
        if rang[c.severite] <= rang[seuil]:
            par_note[c.note].append(c)
    ordre = sorted(par_note.items(),
                   key=lambda kv: (min(rang[c.severite] for c in kv[1]), kv[0]))
    for note, cs in ordre[:limite]:
        print(f"\n{note}")
        for c in sorted(cs, key=lambda x: rang[x.severite]):
            d = f" — {c.detail}" if c.detail else ""
            print(f"  [{c.severite:5s}] {c.regle}{d}")
    if len(ordre) > limite:
        print(f"\n… {len(ordre) - limite} notes supplémentaires (--limite 0 pour tout afficher)")


# --------------------------------------------------------------------------
# 9. CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    global R
    ap = argparse.ArgumentParser(description="Contrôle le frontmatter et les tâches du vault. Lecture seule.")
    ap.add_argument("--vault", required=True, help="racine du vault")
    ap.add_argument("--regles", default=str(REFERENTIEL_DEFAUT), help="fichier référentiel YAML")
    ap.add_argument("--path", help="restreindre à un sous-dossier")
    ap.add_argument("--staged", action="store_true", help="seulement les notes en index git (hook pre-commit)")
    ap.add_argument("--changed", action="store_true", help="seulement les notes modifiées depuis HEAD")
    ap.add_argument("--seuil", choices=SEVERITES, default="WARN", help="sévérité minimale détaillée")
    ap.add_argument("--limite", type=int, default=30, help="nombre de notes détaillées (0 = toutes)")
    ap.add_argument("--summary", action="store_true", help="résumé seul")
    ap.add_argument("--strict", action="store_true", help="code de sortie 1 si au moins un ERROR")
    ap.add_argument("--froid", action="store_true", help="inclure la dette froide (notes endormies)")
    args = ap.parse_args(argv)

    R = charger_referentiel(Path(args.regles))
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        sys.exit(f"vault introuvable : {vault}")

    sujets_valides = charger_vocabulaire_sujet(vault)
    if not sujets_valides:
        print(f"`{R.dossier_sujets}/` introuvable ou vide — contrôle du vocabulaire "
              "`sujet` désactivé.", file=sys.stderr)

    selection_git = None
    if args.staged or args.changed:
        mode = "staged" if args.staged else "changed"
        selection_git = fichiers_git(vault, mode)
        if selection_git is None:
            print(f"git indisponible — --{mode} ignoré, scan complet.", file=sys.stderr)
        elif not selection_git:
            print(f"aucune note .md en {mode} — rien à contrôler.")
            return 0

    constats, scannees = parcourir(vault, sujets_valides, args.path, selection_git)
    froids = [c for c in constats if c.froid]
    if not args.froid:
        constats = [c for c in constats if not c.froid]
    afficher_resume(constats, scannees, args.seuil)
    if froids and not args.froid:
        print(f"  · dette froide : {len(froids)} constat(s) sur "
              f"{len({c.note for c in froids})} note(s) endormie(s) (--froid pour détailler)")
    if not args.summary:
        afficher_detail(constats, args.seuil, args.limite if args.limite > 0 else 10**9)
    if args.strict and compter(constats)["ERROR"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
