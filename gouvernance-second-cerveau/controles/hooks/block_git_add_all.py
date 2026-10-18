#!/usr/bin/env python3
"""
block_git_add_all.py — Hook PreToolUse (Bash) de Claude Code : interdit le staging aveugle.

Raison d'être : trois fois en un mois, un `git add -A` de fin de session a
emporté le travail d'une session parallèle sous un message qui ne le décrivait
pas. L'interdit vivait dans le fichier d'instructions de l'agent — une
consigne rend la violation reprochable, elle ne la rend pas impossible. Ce
hook la rend impossible : il s'exécute AVANT chaque commande Bash de l'agent,
et refuse celles qui stagent à l'aveugle.

Ce qui est bloqué (au niveau token, pas par sous-chaîne) :
  - `git add -A` / `git add --all` / `git add --no-ignore-removal`
  - `git add .` (le point comme pathspec seul — `git add ./fichier` passe)
  - `git commit -a` et ses clusters courts (`-am`, `-sa`...) / `git commit --all`

Ce qui passe : tout le reste, y compris `git commit -m` sur des chemins déjà
stagés (commit_guard.py), `git commit --amend`, et les commits par chemins
explicites. Branché dans la configuration UTILISATEUR, il vaut pour tous les
dépôts atteints depuis une session — c'est voulu : le risque est souvent
ailleurs que dans le dépôt qu'on a pensé à protéger.

Faux positif corrigé : un heredoc (`git commit -F - <<'MSG'`) dont le corps
*cite* la chaîne interdite était lui-même refusé, parce que chaque ligne du
corps était traitée comme une commande. Le corps d'un heredoc n'est jamais du
code shell : il est retiré avant le découpage en segments. Ce qui suit la fin
du heredoc reste analysé : un vrai `git add -A` placé après le délimiteur est
toujours bloqué (un test le prouve). Un contrôle doit être JUSTE : un contrôle
qui bloque à tort pousse à le contourner.

Sortie : JSON PreToolUse (permissionDecision deny) sur stdout, exit 0.
En cas de doute (commande imparsable), on laisse passer — le hook protège
contre l'étourderie, il ne prétend pas être un bac à sable.

Test à vide :
  echo '{"tool_name":"Bash","tool_input":{"command":"git add -A"}}' \
      | python controles/hooks/block_git_add_all.py
"""

import json
import re
import shlex
import sys


_HEREDOC_RE = re.compile(r"<<(-?)\s*(?:(['\"])(\w+)\2|(\w+))")


def strip_heredocs(commande: str) -> str:
    """Retire le CORPS de chaque heredoc (`<<EOF ... EOF`, `<<-EOF`,
    `<<'EOF'`, `<<\"EOF\"`) — texte cite, jamais du code a analyser. La ligne
    d'ouverture est conservee (elle peut porter un appel git legitime, ex.
    `git commit -F - <<'MSG'`) ; les lignes du corps et la ligne du
    delimiteur de fin sont supprimees. Ce qui suit la fin du heredoc, sur les
    lignes suivantes, reste present et sera analyse normalement."""
    lines = commande.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        i += 1
        for dash, _q, d1, d2 in _HEREDOC_RE.findall(line):
            delim = d1 or d2
            if not delim:
                continue
            while i < n:
                body = lines[i]
                check = body.lstrip("\t") if dash else body
                i += 1
                if check == delim:
                    break
    return "\n".join(out)


def segments(commande: str):
    """Decoupe une ligne shell en segments sur && || ; | et les sauts de
    ligne — assez fin pour attraper `cd x && git add -A`. Les corps de
    heredoc sont retires en amont (cf. `strip_heredocs`) : ce ne sont jamais
    des commandes."""
    return re.split(r"&&|\|\||;|\||\n", strip_heredocs(commande))


def sous_commande_git(tokens: list[str]):
    """(sous-commande, args) du premier appel git du segment, sinon None.
    Saute les options globales de git (-c x, -C x, --git-dir=...)."""
    try:
        i = tokens.index("git")
    except ValueError:
        return None
    j = i + 1
    while j < len(tokens):
        t = tokens[j]
        if t in ("-c", "-C"):
            j += 2
            continue
        if t.startswith("-"):
            j += 1
            continue
        return t, tokens[j + 1:]
    return None


def est_bloquee(commande: str):
    """Retourne le motif du blocage, ou None si la commande est saine."""
    for seg in segments(commande):
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            continue                      # segment imparsable : on ne juge pas
        sub = sous_commande_git(tokens)
        if not sub:
            continue
        nom, args = sub
        if nom == "add":
            if any(a in ("-A", "--all", "--no-ignore-removal") for a in args):
                return "`git add -A/--all` stage tout le worktree"
            # le point comme pathspec SEUL (apres un eventuel `--`)
            if "." in [a for a in args if a != "--"]:
                return "`git add .` stage tout le repertoire courant"
        elif nom == "commit":
            for a in args:
                if a == "--all":
                    return "`git commit --all` stage puis commite tout"
                # cluster court a un tiret contenant `a` : -a, -am, -sa...
                if re.fullmatch(r"-[a-zA-Z]*a[a-zA-Z]*", a):
                    return f"`git commit {a}` stage puis commite tout le suivi"
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        commande = payload.get("tool_input", {}).get("command", "")
    except Exception:
        return                            # payload illisible : ne pas bloquer

    motif = est_bloquee(commande)
    if not motif:
        return

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOQUÉ par le garde-fou de commit : {motif}. "
                "Ce geste emporte le travail des sessions parallèles sous un "
                "message qui ne le décrit pas. Commite par CHEMINS EXPLICITES "
                "via le point d'entrée unique : `python controles/vault_commit.py "
                "--commit -m \"...\" -- <fichiers>` (ou `--all` si tu es seul — "
                "le script vérifie le registre de sessions). Pour un autre dépôt : "
                "`git add <chemins>` puis `git commit`, jamais de staging aveugle."
            ),
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
