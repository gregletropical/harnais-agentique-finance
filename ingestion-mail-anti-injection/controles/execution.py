"""Exécution des décisions VALIDÉES par l'humain sur une note de revue (le GO).

La passe de revue ne fait que proposer. L'humain relit la note, écrit sa décision
dans une colonne « Décision », puis cette commande l'exécute — en simulation
d'abord, réellement ensuite. Quatre garde-fous :

1. vocabulaire fermé : seules `archiver`, `a_faire`, `garder` et `revue_humaine`
   sont exécutables. Une décision hors liste (`supprimer`, `envoyer`, `transférer`,
   une phrase libre) n'est PAS interprétée : elle est listée en anomalie ;
2. contrôle d'identité : la ligne porte le `Message-ID` lu lors de la passe ; s'il
   ne correspond plus au message ciblé, on n'agit pas ;
3. les gestes passent par `ClientMessagerie`, donc par sa liste blanche ;
4. une ligne commentée par l'humain est sautée : le commentaire se traite d'abord.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DECISIONS_EXECUTABLES = ("archiver", "a_faire", "garder", "revue_humaine")


@dataclass
class Bilan:
    archives: list = field(default_factory=list)
    taches: list = field(default_factory=list)
    inchanges: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)


def executer(decisions: list[dict], client, appliquer: bool = False) -> Bilan:
    """`decisions` : [{cle, ident, message_id, decision, commentaire?, resume?}]."""
    bilan = Bilan()
    for d in decisions:
        cle = d.get("cle", "?")
        if d.get("commentaire"):
            bilan.anomalies.append((cle, "commentaire_a_traiter_d_abord"))
            continue
        decision = (d.get("decision") or "").strip().lower()
        if decision not in DECISIONS_EXECUTABLES:
            bilan.anomalies.append((cle, "decision_hors_vocabulaire"))
            continue
        meta = client.appel(("messages", "get"), {"id": d["ident"]})
        lu = (meta["headers"].get("message-id") or [""])[0].strip()
        if lu != d.get("message_id", "").strip():
            bilan.anomalies.append((cle, "identite_non_confirmee"))
            continue
        if decision == "archiver":
            if appliquer:
                client.archiver(d["ident"])
            bilan.archives.append(cle)
        elif decision == "a_faire":
            bilan.taches.append(f"- [ ] #task {d.get('resume') or 'Traiter le message ' + cle}")
        else:
            bilan.inchanges.append(cle)
    return bilan
