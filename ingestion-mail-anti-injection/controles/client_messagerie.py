"""Client de messagerie du pipeline : une LISTE BLANCHE, pas une consigne (barrière 7 et trois interdits).

Dans le système réel, ce client est le seul point de contact avec l'API de
messagerie (une CLI d'accès à Google Workspace, ou un serveur MCP Microsoft 365
dont la liste d'outils est filtrée). Ici, il n'y a aucun connecteur : le
`Transport` est remplacé par `TransportFichiers`, qui lit des `.eml` d'exemple et
journalise en mémoire les écritures qu'il aurait faites. Les garde-fous, eux,
sont identiques :

1. toute méthode absente de `methodes_autorisees` lève `MethodeInterdite` AVANT
   le moindre appel — il n'existe aucun chemin de code vers un envoi, une
   suppression, une corbeille ou un transfert ;
2. un profil de niveau `lecture` ne peut rien écrire, et un profil d'écriture
   doit être déclaré comme tel : l'incapacité d'écrire est vérifiée deux fois,
   par le client et par les scopes du jeton (cf. `controle_scopes.py`) ;
3. le niveau `plein` (envoi, suppression, partage) n'est JAMAIS chargé par le
   pipeline : il n'existe qu'en session, sur demande explicite de l'humain ;
4. un `modify` ne peut pas AJOUTER `TRASH` ni `SPAM` (suppression ou déclassement
   déguisés) ;
5. `messages.get` est forcé en métadonnées : aucun fragment de corps n'entre
   dans le pipeline de tri.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REGLES = json.loads((Path(__file__).resolve().parents[1] / "regles" / "gestes_interdits.json").read_text(encoding="utf-8"))
METHODES_AUTORISEES = frozenset(tuple(m) for m in REGLES["methodes_autorisees"])
METHODES_ECRITURE = frozenset(tuple(m) for m in REGLES["methodes_ecriture"])
LIBELLES_INTERDITS = frozenset(REGLES["libelles_systeme_interdits_en_ajout"])
NIVEAUX_PIPELINE = frozenset(REGLES["niveaux_utilisables_par_le_pipeline"])


class MethodeInterdite(PermissionError):
    pass


@dataclass(frozen=True)
class Profil:
    nom: str
    niveau: str          # lecture | maintenance | plein


class TransportFichiers:
    """Boîte simulée : un dossier de `.eml`. Les écritures sont journalisées, jamais exécutées."""

    def __init__(self, dossier: Path):
        from .ingestion import lire_eml
        self.messages = {p.stem: lire_eml(p) for p in sorted(Path(dossier).glob("*.eml"))}
        self.libelles = {k: {"INBOX", "UNREAD"} for k in self.messages}
        self.journal: list[tuple] = []

    def executer(self, methode: tuple, params: dict, corps: dict | None) -> dict:
        if methode == ("messages", "list"):
            return {"messages": [{"id": k} for k in self.messages]}
        if methode == ("messages", "get"):
            m = self.messages[params["id"]]
            entetes = {k: v for k, v in m.entetes.items()}
            return {"id": params["id"], "labelIds": sorted(self.libelles[params["id"]]), "headers": entetes}
        if methode == ("labels", "list"):
            return {"labels": sorted({l for ls in self.libelles.values() for l in ls})}
        if methode == ("labels", "create"):
            self.journal.append(("labels.create", corps["name"]))
            return {"id": corps["name"]}
        if methode == ("messages", "modify"):
            ident = params["id"]
            self.libelles[ident] |= set(corps.get("addLabelIds", []))
            self.libelles[ident] -= set(corps.get("removeLabelIds", []))
            self.journal.append(("messages.modify", ident, tuple(corps.get("addLabelIds", [])),
                                 tuple(corps.get("removeLabelIds", []))))
            return {"id": ident}
        raise MethodeInterdite(f"transport : méthode inconnue {methode}")  # pragma: no cover


class ClientMessagerie:
    def __init__(self, profil: Profil, transport, ecriture: bool = False):
        if profil.niveau not in NIVEAUX_PIPELINE:
            raise MethodeInterdite(f"niveau {profil.niveau!r} interdit au pipeline : session humaine uniquement")
        if ecriture and profil.niveau != "maintenance":
            raise MethodeInterdite(f"écriture demandée sur un profil {profil.niveau!r}")
        if not ecriture and profil.niveau != "lecture":
            # la simulation tourne sur le profil lecture : l'incapacité d'écrire est technique, pas supposée
            raise MethodeInterdite(f"simulation sur un profil non lecture : {profil.nom}")
        self.profil, self.transport, self.ecriture = profil, transport, ecriture

    def appel(self, methode: tuple, params: dict, corps: dict | None = None) -> dict:
        methode = tuple(methode)
        if methode not in METHODES_AUTORISEES:
            raise MethodeInterdite(f"méthode hors liste blanche : {'.'.join(methode)}")
        if methode in METHODES_ECRITURE and not self.ecriture:
            raise MethodeInterdite(f"méthode d'écriture en mode lecture : {'.'.join(methode)}")
        if methode == ("messages", "modify"):
            ajouts = set((corps or {}).get("addLabelIds", []))
            if ajouts & LIBELLES_INTERDITS:
                raise MethodeInterdite(f"libellé système interdit : {sorted(ajouts & LIBELLES_INTERDITS)}")
        if methode == ("messages", "get"):
            regle = REGLES["lecture_forcee_en_metadonnees"]
            params = {**params, "format": regle["format"]}
        return self.transport.executer(methode, params, corps)

    # --- gestes de maintenance, tous additifs et réversibles -------------------------------
    def poser_libelle(self, ident: str, libelle: str) -> dict:
        return self.appel(("messages", "modify"), {"id": ident}, {"addLabelIds": [libelle]})

    def archiver(self, ident: str) -> dict:
        """Archiver = sortir de la boîte de réception ET marquer lu. Réversible."""
        return self.appel(("messages", "modify"), {"id": ident}, {"removeLabelIds": ["INBOX", "UNREAD"]})
