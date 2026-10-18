#!/usr/bin/env python3
"""
commit_guard.py — Garde-fou de commit pour un dépôt git où écrivent plusieurs
sessions d'agents en parallèle.

Contexte : un même dépôt (le second cerveau) reçoit les écritures de deux ou
trois sessions d'agents simultanées sur un poste, plus celles d'un agent
autonome sur un serveur. L'interdiction de `git add -A` était écrite dans les
instructions de l'agent dès le premier incident ; elle a été violée trois fois
en trois jours par le même agent qui l'avait sous les yeux. Rien n'a été perdu,
mais un historique qui ment ne se répare pas : il se prévient. Ce script est le
point d'entrée unique pour commiter ; le hook `hooks/block_git_add_all.py`
refuse le staging aveugle avant même son exécution.

Trois défauts traités, pas un :

  1. `git add -A` stage tout le worktree, y compris le travail en cours d'une
     autre session. → On stage par chemins explicites, et ce qui reste est
     AFFICHÉ au lieu d'être avalé (le résidu se lit, il ne se survole pas).
  2. Deux sessions partagent le même `.git/index`. Un `git commit` emporte ce
     que l'autre a déjà stagé, même sans `add -A`. → On contrôle l'index avant
     de toucher quoi que ce soit.
  3. `... 2>/dev/null; git push` rend un échec invisible. → Codes de sortie
     explicites, aucune erreur masquée.

Registre de sessions : `<git-common-dir>/agent-sessions/` — jamais commité,
jamais synchronisé. Chaque session s'y enregistre au démarrage (`--register`)
et s'en retire en fin de session (`--release`). TTL de 12 h d'INACTIVITÉ : le
marqueur porte `last_seen`, rafraîchi à chaque appel qui connaît la session.
Une session qui dort perd sa protection et la retrouve au premier geste. Avec
au moins deux sessions enregistrées, `--all` est refusé.

Provenance : chaque commit porte un trailer `Session: <id> (<libellé>)`.
L'auteur est celui de la config git du dépôt (la personne responsable), jamais
une ligne `Co-Authored-By` d'agent. En cas d'ambiguïté sur la session
appelante, l'outil refuse de deviner et le dit.

Synchronisation avant le push (compare-and-swap) : branche, remote et amont
sont DÉTECTÉS. Après le commit local, `git fetch`, puis :
  - l'amont a modifié, depuis la base commune, un fichier du lot local → REFUS,
    code 2, commit local fait. Exception : fichiers `merge=union` de
    `.gitattributes` (append-only : journaux, la fusion y est toujours juste) ;
  - l'amont a modifié un fichier portant du travail non commité dans l'arbre
    → push DIFFÉRÉ, code 2 ;
  - sinon rebase dans un worktree TEMPORAIRE, puis `git reset --keep` : aucun
    fichier d'autrui n'est réécrit, empreintes vérifiées avant/après.
Jamais d'`--autostash` : sur banc, il retire puis réapplique le travail des
AUTRES sessions, dont les documents reculent le temps de l'opération.
Un push rejeté parce que l'amont a encore bougé relance le cycle (3 essais).

Usage (depuis la racine du dépôt) :
    python commit_guard.py --register --label "claude-poste"
    python commit_guard.py --status
    python commit_guard.py --commit --push --id <sid> -m "msg" -- chemin1 chemin2
    python commit_guard.py --commit -m "msg" --all          # seul sur le dépôt
    python commit_guard.py --sync --id <sid> [--accepter-amont]
    python commit_guard.py --release --id <sid>

Codes de sortie :
    0  succès (ou rien à commiter)
    1  échec technique
    2  REFUS délibéré : concurrence détectée, action humaine requise. Un code 2
       n'est pas une panne, c'est le garde-fou qui fonctionne : ne jamais le
       contourner par un `git` à la main ni par `push --force`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

TTL_SECONDES = 12 * 3600
DOSSIER_SESSIONS = "agent-sessions"


@dataclass(frozen=True)
class Config:
    """Ce qui distingue un dépôt d'un autre — et rien d'autre.

    commande        : forme complète citée dans les messages de résolution
    commande_courte : forme courte citée dans le refus de `--all`
    designation     : « ce dépôt », « ce vault »… dans les messages
    variable_session: variable d'environnement portant l'id de session
    sans_amont_code : code rendu quand `--push` tombe sur une branche sans amont
                      (0 = on le dit et on continue ; 1 = l'amont est obligatoire)
    sans_amont_message : message alors affiché (None = message détaillé générique)
    prefixe_tmp     : préfixe du worktree temporaire de rebase
    afficher_depot  : `--status` affiche dépôt, branche, remote, amont
    option_repo     : la CLI accepte `--repo <chemin>`
    """
    commande: str = f"python {Path(__file__).resolve()}"
    commande_courte: str = "commit_guard.py"
    designation: str = "ce dépôt"
    variable_session: str = "AGENT_SESSION_ID"
    sans_amont_code: int = 0
    sans_amont_message: str | None = None
    prefixe_tmp: str = "commit-guard-rebase-"
    afficher_depot: bool = True
    option_repo: bool = True


CONFIG_DEFAUT = Config()


def git(*args: str, cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    # `core.quotepath=false` : sans lui git échappe les chemins accentués en
    # octal (`R\303\251flexion.md`) — illisible, et le résidu affiché est
    # justement ce que l'humain doit pouvoir relire d'un coup d'œil.
    return subprocess.run(["git", "-c", "core.quotepath=false", *args],
                          cwd=cwd, check=check,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def racine(depuis: str | Path | None = None) -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       cwd=depuis or None, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Pas un depot git.")
    return Path(r.stdout.strip())


def dossier_git(depot: Path) -> Path:
    """Le dossier git COMMUN (`.git` d'un clone normal ; celui du dépôt
    principal depuis un worktree lié — le registre doit être partagé)."""
    r = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=depot)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    return depot / ".git"


def dossier_sessions(depot: Path, creer: bool = True) -> Path:
    """`creer=False` pour les lectures : `--status` sur un dépôt jamais
    enregistré ne doit rien écrire, pas même un dossier vide."""
    d = dossier_git(depot) / DOSSIER_SESSIONS
    if creer:
        d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# REGISTRE DE SESSIONS
# --------------------------------------------------------------------------

def purger(depot: Path) -> int:
    """Retire les marqueurs périmés. L'âge se compte depuis le DERNIER GESTE
    (`last_seen`), pas depuis l'enregistrement. Chaque purge laisse une pierre
    tombale `<id>.purge` (gardée 7 jours) : c'est elle qui permet à `--release`
    de dire « purgé par inactivité » plutôt qu'un message ambigu."""
    d = dossier_sessions(depot, creer=False)
    if not d.is_dir():
        return 0
    n = 0
    for f in d.glob("*.json"):
        m = {}
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            age = time.time() - m.get("last_seen", m["started"])
        except Exception:
            age = TTL_SECONDES + 1          # marqueur illisible = périmé
        if age > TTL_SECONDES:
            (d / f"{f.stem}.purge").write_text(json.dumps({
                "quand": time.strftime("%Y-%m-%d %H:%M"),
                "label": m.get("label", "?")}, ensure_ascii=False),
                encoding="utf-8")
            f.unlink(missing_ok=True)
            n += 1
    for f in d.glob("*.purge"):
        if time.time() - f.stat().st_mtime > 7 * 86400:
            f.unlink(missing_ok=True)
    return n


def id_claude() -> dict:
    """L'identifiant de session Claude Code (`CLAUDE_CODE_SESSION_ID`), stocké
    dans le marqueur : pont entre le `session_id` d'un hook et l'id du
    registre. Absent sous OpenCode."""
    c = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return {"claude_session_id": c} if c else {}


def toucher(depot: Path, sid: str | None) -> dict | None:
    """Rafraîchit `last_seen` du marqueur `sid` et le rend. Si le marqueur a
    été purgé, il est RECRÉÉ : une session qui dort perd sa protection, elle la
    retrouve au premier geste."""
    if not sid:
        return None
    d = dossier_sessions(depot)
    f = d / f"{sid}.json"
    try:
        m = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        tombe = d / f"{sid}.purge"
        try:
            label = json.loads(tombe.read_text(encoding="utf-8"))["label"]
        except Exception:
            label = "session reprise"
        m = {"id": sid, "label": label, "started": time.time(),
             "started_iso": time.strftime("%Y-%m-%d %H:%M"), "reprise": True,
             **id_claude()}
        tombe.unlink(missing_ok=True)
    m["last_seen"] = time.time()
    m["last_seen_iso"] = time.strftime("%Y-%m-%d %H:%M")
    f.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def sessions_actives(depot: Path, sauf: str | None = None) -> list[dict]:
    purger(depot)
    out = []
    for f in dossier_sessions(depot, creer=False).glob("*.json"):
        if sauf and f.stem == sauf:
            continue
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda s: s.get("started", 0))


def session_appelante(depot: Path, sid: str | None,
                      cfg: Config = CONFIG_DEFAUT) -> str | None:
    """`--id`, sinon la variable de session, sinon — et seulement si UNE seule
    session est enregistrée — celle-là. Jamais `.courante` quand plusieurs
    tournent : la dernière enregistrée écrase ce marqueur."""
    if sid:
        return sid
    if os.environ.get(cfg.variable_session):
        return os.environ[cfg.variable_session]
    act = sessions_actives(depot)
    return act[0]["id"] if len(act) == 1 else None


def derniere_enregistree(depot: Path, cfg: Config = CONFIG_DEFAUT) -> str | None:
    """Repli de `--release` quand aucun id n'est fourni Attention : ne PAS s'en servir
    pour décider quoi que ce soit de sensible (cf. `commiter()`)."""
    if os.environ.get(cfg.variable_session):
        return os.environ[cfg.variable_session]
    marqueur = dossier_sessions(depot, creer=False) / ".courante"
    if marqueur.exists():
        return marqueur.read_text(encoding="utf-8").strip() or None
    return None


def enregistrer(depot: Path, label: str) -> str:
    sid = uuid.uuid4().hex[:8]
    (dossier_sessions(depot) / f"{sid}.json").write_text(json.dumps({
        "id": sid, "label": label, "started": time.time(),
        "started_iso": time.strftime("%Y-%m-%d %H:%M"),
        "last_seen": time.time(),
        "last_seen_iso": time.strftime("%Y-%m-%d %H:%M"),
        **id_claude(),
    }, ensure_ascii=False), encoding="utf-8")
    (dossier_sessions(depot) / ".courante").write_text(sid, encoding="utf-8")
    return sid


def liberer(depot: Path, sid: str | None = None,
            cfg: Config = CONFIG_DEFAUT) -> str:
    """Retire le marqueur de session et rend le CAS rencontré, nommé :
    `libere`, `purge:<quand>`, `sans-id`, `inconnu`."""
    sid = sid or derniere_enregistree(depot, cfg)
    if not sid:
        return "sans-id"
    d = dossier_sessions(depot, creer=False)
    f = d / f"{sid}.json"
    tombe = d / f"{sid}.purge"
    existait = f.exists()
    f.unlink(missing_ok=True)
    courante = d / ".courante"
    if courante.exists() and courante.read_text(encoding="utf-8").strip() == sid:
        courante.unlink(missing_ok=True)
    if existait:
        tombe.unlink(missing_ok=True)
        return "libere"
    if tombe.exists():
        try:
            quand = json.loads(tombe.read_text(encoding="utf-8"))["quand"]
        except Exception:
            quand = "?"
        tombe.unlink(missing_ok=True)
        return f"purge:{quand}"
    return "inconnu"


# --------------------------------------------------------------------------
# ÉTAT DU WORKTREE ET DE LA BRANCHE
# --------------------------------------------------------------------------

def sales(depot: Path) -> list[tuple[str, str]]:
    """[(code, chemin)] — code sur 2 caractères, format porcelain v1."""
    r = git("status", "--porcelain", cwd=depot)
    out = []
    for l in r.stdout.splitlines():
        if not l.strip():
            continue
        code, chemin = l[:2], l[3:].strip()
        if " -> " in chemin:                     # renommage
            chemin = chemin.split(" -> ", 1)[1]
        out.append((code, chemin.strip('"')))
    return out


def deja_stage(depot: Path) -> list[str]:
    return [l for l in git("diff", "--cached", "--name-only",
                           cwd=depot).stdout.splitlines() if l.strip()]


def etat_branche(depot: Path) -> dict:
    """Branche, remotes, amont — détectés, jamais supposés.

    Rend {branche, remotes, amont (ex. origin/main), remote, ref_amont
    (ex. refs/heads/main)} ; les clés absentes valent None / []."""
    b = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=depot)
    branche = b.stdout.strip() if b.returncode == 0 else None
    remotes = [l for l in git("remote", cwd=depot).stdout.splitlines() if l.strip()]
    e = {"branche": branche, "remotes": remotes, "amont": None,
         "remote": None, "ref_amont": None}
    u = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", cwd=depot)
    if u.returncode == 0 and u.stdout.strip() and branche:
        e["amont"] = u.stdout.strip()
        e["remote"] = git("config", f"branch.{branche}.remote", cwd=depot).stdout.strip() or None
        e["ref_amont"] = git("config", f"branch.{branche}.merge", cwd=depot).stdout.strip() or None
    return e


def message_sans_amont(e: dict) -> str:
    if not e["branche"]:
        return ("[INFO] HEAD détachée : commit local seulement, rien n'est poussé.")
    if not e["remotes"]:
        return ("[INFO] Dépôt sans remote : commit local seulement, rien n'est poussé "
                "(aucune copie hors de ce disque).")
    return (f"[INFO] Branche `{e['branche']}` sans amont (remote(s) : "
            f"{', '.join(e['remotes'])}) : commit local seulement, rien n'est poussé.\n"
            f"   Pour la lier une fois pour toutes : git push -u {e['remotes'][0]} "
            f"{e['branche']}")


# --------------------------------------------------------------------------
# SYNCHRONISATION AVANT PUSH (compare-and-swap)
# --------------------------------------------------------------------------

def _lignes(r: subprocess.CompletedProcess) -> list[str]:
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def fichiers_union(depot: Path, chemins: list[str]) -> set[str]:
    """Les chemins portant `merge=union` dans `.gitattributes`."""
    if not chemins:
        return set()
    r = git("check-attr", "-z", "merge", "--", *chemins, cwd=depot)
    morceaux = r.stdout.split("\0")
    out = set()
    for i in range(0, len(morceaux) - 2, 3):
        if morceaux[i + 2] == "union":
            out.add(morceaux[i])
    return out


def empreintes(depot: Path, chemins: list[str]) -> dict[str, str]:
    """Contenu des fichiers d'autrui, avant/après : la preuve qu'aucun travail
    non commité n'a été touché par la synchro."""
    out = {}
    for c in chemins:
        f = depot / c
        if f.is_file():
            out[c] = git("hash-object", "--", c, cwd=depot).stdout.strip()
        else:
            out[c] = "(absent)" if not f.exists() else "(dossier)"
    return out


def rebaser_a_part(depot: Path, cible: str,
                   prefixe: str = CONFIG_DEFAUT.prefixe_tmp) -> tuple[str | None, list[str], str]:
    """Rejoue les commits locaux sur `cible` dans un worktree TEMPORAIRE :
    l'arbre de travail partagé n'est pas touché. Rend (sha, conflits, erreur)."""
    tmp = Path(tempfile.mkdtemp(prefix=prefixe))
    wt = tmp / "wt"
    try:
        r = git("worktree", "add", "--detach", str(wt), "HEAD", cwd=depot)
        if r.returncode != 0:
            return None, [], (r.stderr or r.stdout).strip()
        r = git("rebase", cible, cwd=wt)
        if r.returncode != 0:
            conflits = _lignes(git("diff", "--name-only", "--diff-filter=U", cwd=wt))
            git("rebase", "--abort", cwd=wt)
            return None, conflits, (r.stdout + r.stderr).strip()
        return git("rev-parse", "HEAD", cwd=wt).stdout.strip(), [], ""
    finally:
        git("worktree", "remove", "--force", str(wt), cwd=depot)
        shutil.rmtree(tmp, ignore_errors=True)
        git("worktree", "prune", cwd=depot)


def synchroniser(depot: Path, accepter_amont: bool = False,
                 sid: str | None = None, cfg: Config = CONFIG_DEFAUT) -> int:
    """fetch → contrôle de l'amont sur le lot → rebase à part → push."""
    e = etat_branche(depot)
    if not e["amont"]:
        print(cfg.sans_amont_message or message_sans_amont(e), file=sys.stderr)
        return cfg.sans_amont_code
    push = ["push"]
    if e["remote"] and e["remote"] != "." and e["ref_amont"]:
        push = ["push", e["remote"], f"HEAD:{e['ref_amont']}"]
    for essai in range(1, 4):
        r = git("fetch", "--quiet", *([e["remote"]] if e["remote"] and e["remote"] != "." else []),
                cwd=depot)
        if r.returncode != 0:
            print("[ATTENTION] `git fetch` a échoué (le commit local est fait, rien "
                  "n'est poussé) :", file=sys.stderr)
            print((r.stderr or r.stdout).strip()[:500], file=sys.stderr)
            return 1
        amont = git("rev-parse", "@{u}", cwd=depot).stdout.strip()
        nom_amont = e["amont"]
        base = git("merge-base", "HEAD", amont, cwd=depot).stdout.strip()
        if not base:
            print("[REFUS] Aucune base commune avec l'amont — historiques sans "
                  "rapport, arbitrage humain requis.", file=sys.stderr)
            return 2
        en_avance = int(git("rev-list", "--count", f"{amont}..HEAD",
                            cwd=depot).stdout.strip() or 0)
        en_retard = int(git("rev-list", "--count", f"HEAD..{amont}",
                            cwd=depot).stdout.strip() or 0)
        if en_avance == 0:
            print("Rien à pousser — la branche locale ne porte aucun commit "
                  "absent de l'amont.")
            return 0

        if en_retard:
            lot = set(_lignes(git("diff", "--name-only", base, "HEAD", cwd=depot)))
            touches_amont = set(_lignes(git("diff", "--name-only", base, amont,
                                            cwd=depot)))
            communs = sorted(lot & touches_amont)
            union = fichiers_union(depot, communs)
            conflits = [c for c in communs if c not in union]
            if conflits and not accepter_amont:
                sha = git("rev-parse", "--short", "HEAD", cwd=depot).stdout.strip()
                b7 = base[:7]
                print(f"[REFUS] Push refusé : l'amont ({nom_amont}, {en_retard} "
                      f"commit(s) de plus) a modifié {len(conflits)} fichier(s) de "
                      f"ton lot depuis la base commune {b7} :", file=sys.stderr)
                for c in conflits:
                    print(f"     {c}", file=sys.stderr)
                print(f"\n   Le commit local {sha} est fait, rien n'est perdu : il "
                      "n'est simplement pas poussé.\n"
                      "   Pousser maintenant écraserait ou mêlerait le travail d'un "
                      "autre écrivain sans que personne l'ait lu.\n"
                      "   Résolution :\n"
                      f"     1. lire ce que l'amont a changé : git log -p {b7}..{nom_amont} -- \"<fichier>\"\n"
                      "     2. si c'est compatible (autres sections, autres lignes) :\n"
                      f"          {cfg.commande} --sync --accepter-amont --id {sid or '<SESSION>'}\n"
                      "        (le rebase se fait à part ; en cas de conflit il est "
                      "annulé et rien n'est touché)\n"
                      "     3. sinon, arbitrer avec le responsable du dépôt — jamais de `git push --force`.",
                      file=sys.stderr)
                return 2
            if union:
                print(f"   {len(union)} fichier(s) append-only modifié(s) des deux "
                      "côtés, fusionné(s) par merge=union : " + ", ".join(sorted(union)))

            # Travail non commité d'autrui sur un fichier que l'amont modifie :
            # on ne le réécrit jamais sous ses pieds.
            sale = [f for _, f in sales(depot)]
            sous_ses_pieds = sorted(set(sale) & touches_amont)
            if sous_ses_pieds:
                print("[DIFFÉRÉ] Push différé : l'amont a modifié des fichiers qui portent "
                      "du travail NON COMMITÉ dans l'arbre (une autre session, ou un "
                      "oubli) :", file=sys.stderr)
                for c in sous_ses_pieds:
                    print(f"     {c}", file=sys.stderr)
                print("\n   Le commit local est fait, rien n'est perdu. Mettre la "
                      "branche à jour réécrirait ces fichiers sous les pieds de "
                      "leur auteur.\n   La synchro se fera au prochain commit, une "
                      "fois ce travail commité : relancer alors\n"
                      f"     {cfg.commande} --sync --id {sid or '<SESSION>'}",
                      file=sys.stderr)
                return 2

            nouveau, conflits_rebase, err = rebaser_a_part(depot, amont, cfg.prefixe_tmp)
            if not nouveau:
                if conflits_rebase:
                    print("[REFUS] Le rebase sur l'amont produit un conflit "
                          "réel, il a été annulé (arbre et branche intacts) :",
                          file=sys.stderr)
                    for c in conflits_rebase:
                        print(f"     {c}", file=sys.stderr)
                    print("   Arbitrage humain requis — fusion à la main, jamais "
                          "de `git push --force`.", file=sys.stderr)
                    return 2
                print("[ATTENTION] Rebase impossible (rien n'a été touché) :",
                      file=sys.stderr)
                print(err[:500], file=sys.stderr)
                return 1

            avant = empreintes(depot, sale)
            # L'index est partagé : `reset --keep` remettrait à zéro ce qu'une
            # autre session a déjà stagé. On note ses entrées pour les reposer.
            stages = deja_stage(depot)
            entrees = git("ls-files", "-s", "--", *stages, cwd=depot).stdout if stages else ""
            r = git("reset", "--keep", nouveau, cwd=depot)
            if r.returncode != 0:
                print("[DIFFÉRÉ] Push différé : `git reset --keep` a refusé d'avancer la "
                      "branche (un fichier modifié par l'amont a changé dans "
                      "l'arbre entre-temps). Rien n'a été touché :",
                      file=sys.stderr)
                print((r.stderr or r.stdout).strip()[:500], file=sys.stderr)
                return 2
            if stages:
                subprocess.run(["git", "update-index", "--index-info"], cwd=depot,
                               input=entrees, text=True, capture_output=True)
                presents = {l.split("\t", 1)[1] for l in entrees.splitlines() if "\t" in l}
                for c in stages:
                    if c not in presents:      # suppression stagée (`git rm`)
                        git("update-index", "--force-remove", "--", c, cwd=depot)
            apres = empreintes(depot, sale)
            abimes = [c for c in sale if avant.get(c) != apres.get(c)]
            if abimes:
                print("[ATTENTION] Des fichiers non commités ont changé pendant la "
                      "synchro — à vérifier par le responsable du dépôt :", file=sys.stderr)
                for c in abimes:
                    print(f"     {c}", file=sys.stderr)
                return 1
            print(f"[OK] Rebasé sur {nom_amont} ({en_retard} commit(s) intégré(s)) — "
                  f"{len(sale)} fichier(s) non commité(s) d'autrui intact(s).")

        r = git(*push, cwd=depot)
        if r.returncode == 0:
            print("[OK] Push OK")
            return 0
        sortie = (r.stderr or r.stdout)
        if essai < 3 and ("fetch first" in sortie or "non-fast-forward" in sortie):
            print(f"   L'amont a bougé pendant la synchro — nouvel essai ({essai + 1}/3).")
            continue
        print("[ATTENTION] Push échoué (le commit local est fait) :", file=sys.stderr)
        print(sortie.strip()[:500], file=sys.stderr)
        return 1
    return 1


# --------------------------------------------------------------------------
# COMMIT
# --------------------------------------------------------------------------

def commiter(depot: Path, message: str, chemins: list[str],
             tout: bool, pousser: bool, sid: str | None = None,
             accepter_amont: bool = False, cfg: Config = CONFIG_DEFAUT) -> int:
    sid = session_appelante(depot, sid, cfg)
    moi = toucher(depot, sid)
    if not moi:
        print("[ATTENTION] Session appelante inconnue (ni `--id`, ni `"
              f"{cfg.variable_session}`, et plusieurs sessions enregistrees) : "
              "commit sans trailer `Session:` et sans rafraichissement du marqueur.",
              file=sys.stderr)
    # On ne cherche PAS à savoir laquelle des sessions on est : le NOMBRE
    # suffit. À partir de deux sessions enregistrées, `--all` est interdit.
    actives = sessions_actives(depot)
    concurrence = max(0, len(actives) - 1)

    sale = sales(depot)
    if not sale and not deja_stage(depot):
        print("Rien a commiter — arbre propre.")
        # Un commit local reste peut-être à pousser (push différé ou refusé
        # lors d'un appel précédent) : la synchro le reprend.
        return synchroniser(depot, accepter_amont, sid, cfg) if pousser else 0

    # -- Défaut 2 : l'index est partagé entre les sessions -----------------
    prealable = deja_stage(depot)
    if prealable:
        print("[REFUS] L'index contient DEJA des fichiers stages, que ce commit "
              "emporterait :", file=sys.stderr)
        for f in prealable[:20]:
            print(f"     {f}", file=sys.stderr)
        if len(prealable) > 20:
            print(f"     … +{len(prealable) - 20}", file=sys.stderr)
        print("\n   Deux sessions partagent le meme `.git/index`. Verifie a qui "
              "appartient ce travail,\n   puis soit tu le commites avec le tien, "
              "soit tu le retires : `git restore --staged <chemin>`.",
              file=sys.stderr)
        return 2

    # -- Défaut 1 : jamais de `add -A` à l'aveugle -------------------------
    if tout:
        if concurrence:
            print(f"[REFUS] {len(actives)} sessions enregistrees sur "
                  f"{cfg.designation} (dont la tienne).", file=sys.stderr)
            for s in actives:
                print(f"     · {s.get('label', '?')} — depuis "
                      f"{s.get('started_iso', '?')}", file=sys.stderr)
            print("\n   `--all` stagerait leur travail en cours sous TON message. "
                  "C'est exactement\n   l'incident que ce garde-fou existe pour empêcher. Commite par "
                  "chemins explicites :\n"
                  f"     {cfg.commande_courte} --commit -m \"msg\" -- <tes fichiers>",
                  file=sys.stderr)
            return 2
        print(f"Seule session active. {len(sale)} fichier(s) a commiter :")
        for code, f in sale:
            print(f"     {code} {f}")
        r = git("add", "-A", cwd=depot)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return 1
    else:
        if not chemins:
            print("Aucun chemin fourni. Utilise `--all` (session seule) ou "
                  "liste tes fichiers.", file=sys.stderr)
            return 1
        r = git("add", "--", *chemins, cwd=depot)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return 1
        stages = deja_stage(depot)
        print(f"{len(stages)} fichier(s) stage(s) :")
        for f in stages[:40]:
            print(f"     {f}")
        if len(stages) > 40:
            print(f"     … +{len(stages) - 40}")

        # Le résidu est AFFICHÉ, jamais avalé : c'est tout l'objet du script.
        reste = [(c, f) for c, f in sales(depot) if f not in set(stages)]
        if reste:
            print(f"\n[ATTENTION] {len(reste)} fichier(s) NON commite(s) — "
                  "verifie qu'aucun ne t'appartient :")
            for c, f in reste[:30]:
                print(f"     {c} {f}")
            if len(reste) > 30:
                print(f"     … +{len(reste) - 30}")
            if concurrence:
                print(f"   ({len(actives)} sessions enregistrees — une autre "
                      "travaille en parallele, ne touche pas a ses fichiers.)")

    if not deja_stage(depot):
        print("Rien de stage au final — aucun commit.")
        return synchroniser(depot, accepter_amont, sid, cfg) if pousser else 0

    # -- Défaut 3 : plus aucune erreur masquée -----------------------------
    args = ["commit", "-m", message]
    if moi:
        args += ["--trailer", f"Session: {moi['id']} ({moi.get('label', '?')})"]
    r = git(*args, cwd=depot)
    if r.returncode != 0:
        print("Echec du commit :", file=sys.stderr)
        print(r.stdout or r.stderr, file=sys.stderr)
        return 1
    sha = git("rev-parse", "--short", "HEAD", cwd=depot).stdout.strip()
    print(f"\n[OK] Commit {sha} — {message}")

    if pousser:
        return synchroniser(depot, accepter_amont, moi["id"] if moi else sid, cfg)
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(cfg: Config = CONFIG_DEFAUT, argv: list[str] | None = None) -> int:
    # stdout ligne par ligne : sinon, redirigé, il sort APRÈS stderr et le
    # refus s'affiche avant le commit qu'il concerne.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--label", default="session")
    ap.add_argument("--id", default="", help="identifiant rendu par --register")
    ap.add_argument("-m", "--message", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--sync", action="store_true",
                    help="synchroniser et pousser les commits locaux, sans commiter")
    ap.add_argument("--accepter-amont", action="store_true",
                    help="rebaser meme si l'amont a touche un fichier du lot "
                         "(apres lecture de ses changements)")
    if cfg.option_repo:
        ap.add_argument("--repo", default="",
                        help="depot vise (defaut : celui du repertoire courant)")
    ap.add_argument("chemins", nargs="*")
    a = ap.parse_args(argv)

    depot = racine(getattr(a, "repo", "") or None)

    if a.register:
        sid = enregistrer(depot, a.label)
        autres = sessions_actives(depot, sauf=sid)
        print(f"Session {sid} enregistree ({a.label}).")
        print(f"   → note cet identifiant : en fin de session, "
              f"`--release --id {sid}`.")
        if autres:
            print(f"[ATTENTION] {len(autres)} autre(s) session(s) active(s) sur {cfg.designation} :")
            for s in autres:
                print(f"     · {s.get('label','?')} — depuis {s.get('started_iso','?')}")
            print("   → en fin de session, commite par CHEMINS EXPLICITES, "
                  "jamais `--all`.")
        return 0

    if a.release:
        cas = liberer(depot, a.id or None, cfg)
        if cas == "libere":
            print("Session liberee.")
        elif cas.startswith("purge:"):
            print(f"Rien a liberer : le marqueur avait ete purge par inactivite "
                  f"(> 12 h sans geste) le {cas[6:]}.")
        elif cas == "sans-id":
            print("Rien a liberer : aucun identifiant fourni ni connu. "
                  "Passe `--id <sid>`.")
        else:
            print(f"Rien a liberer : identifiant `{a.id}` inconnu du registre "
                  "(jamais enregistre, ou purge il y a plus de 7 jours).")
        return 0

    if a.status:
        toucher(depot, a.id or os.environ.get(cfg.variable_session))
        if cfg.afficher_depot:
            e = etat_branche(depot)
            print(f"Depot : {depot}")
            print(f"Branche : {e['branche'] or '(HEAD detachee)'} — "
                  f"remote(s) : {', '.join(e['remotes']) or 'aucun'} — "
                  f"amont : {e['amont'] or 'aucun (pas de push possible)'}")
        act = sessions_actives(depot)
        sale = sales(depot)
        print(f"Sessions actives : {len(act)}")
        for s in act:
            print(f"     · {s.get('label','?')} ({s.get('id','?')}) — "
                  f"depuis {s.get('started_iso','?')}, dernier geste "
                  f"{s.get('last_seen_iso', s.get('started_iso','?'))}")
        print(f"Fichiers modifies : {len(sale)}")
        stage = deja_stage(depot)
        if stage:
            print(f"[ATTENTION] {len(stage)} fichier(s) deja stage(s) dans l'index partage")
        return 0

    if a.sync:
        sid = session_appelante(depot, a.id or None, cfg)
        toucher(depot, sid)
        return synchroniser(depot, a.accepter_amont, sid, cfg)

    if a.commit:
        if not a.message:
            print("`-m` est obligatoire.", file=sys.stderr)
            return 1
        return commiter(depot, a.message, a.chemins, a.all, a.push,
                        a.id or None, a.accepter_amont, cfg)

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
