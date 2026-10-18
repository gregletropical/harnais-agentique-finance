"""Extraction du texte visible d'un corps HTML, SANS rendu (barrière 2).

Ce qui rend le HTML dangereux, ce n'est pas la présence de balises, c'est le
RENDU : le chargement des ressources distantes (une image distante est à la fois
un traqueur et un canal d'exfiltration — c'était le canal d'EchoLeak,
CVE-2025-32711) et l'exécution des scripts.

Ici, aucun moteur de rendu et aucune bibliothèque réseau : on parcourt le
balisage avec `html.parser` (bibliothèque standard), on JETTE intégralement le
contenu de <script>, <style>, <title>, <noscript> et des commentaires, et on ne
conserve que le texte. Aucune URL n'est résolue, aucune ressource n'est chargée,
aucun attribut n'est interprété. Le résultat est une chaîne inerte.

Ce que ce module ne fait PAS, volontairement : filtrer le texte caché par CSS
(`display:none`, blanc sur blanc). L'extracteur ne connaît pas le CSS ; le texte
caché ressort comme le texte visible. Ce n'est pas le rôle de la barrière 2 :
tout le texte extrait, visible ou non, est une donnée, et c'est la délimitation
de la barrière 4 qui le neutralise. Ne jamais supposer qu'un texte invisible à
l'écran est absent du flux envoyé au modèle.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# Balises dont le CONTENU est jeté. Elles doivent toutes avoir une fermeture :
# une balise orpheline (`<meta>`, `<link>`) incrémenterait un compteur que rien ne
# décrémente, et tout le message serait jeté à partir de là. Bogue réel rencontré
# en production : `<meta>` dans cette liste rendait une chaîne VIDE pour tout
# message HTML ayant un en-tête, c'est-à-dire presque tous.
IGNORES = {"script", "style", "title", "noscript"}

# Balises orphelines : jamais dans un comptage de profondeur.
ORPHELINES = {"meta", "link", "br", "img", "hr", "input", "source", "area", "col", "base",
              "embed", "param", "track", "wbr"}
BLOCS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote"}


class _Extracteur(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self._profondeur_ignoree = 0

    def handle_starttag(self, tag, attrs):
        if tag in ORPHELINES:
            if tag in BLOCS:
                self.morceaux.append("\n")
            return
        if tag in IGNORES:
            self._profondeur_ignoree += 1
        elif tag in BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, tag):
        if tag in ORPHELINES:
            return
        if tag in IGNORES and self._profondeur_ignoree:
            self._profondeur_ignoree -= 1
        elif tag in BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data):
        if not self._profondeur_ignoree and data.strip():
            self.morceaux.append(data)

    def handle_comment(self, data):
        # Les commentaires (et le balisage conditionnel des clients de messagerie) sont jetés.
        return


def html_vers_texte(html: str, max_car: int = 200_000) -> str:
    """Retourne le texte visible. Ne lève jamais : un HTML cassé reste du texte."""
    if not html:
        return ""
    p = _Extracteur()
    try:
        p.feed(html[:max_car])
        p.close()
        texte = "".join(p.morceaux)
    except Exception:
        # Repli défensif : suppression brute du balisage, toujours sans rendu.
        texte = re.sub(r"<[^>]+>", " ", html[:max_car])
    texte = re.sub(r"[ \t\xa0]+", " ", texte)
    texte = re.sub(r"\n\s*\n\s*\n+", "\n\n", texte)
    return texte.strip()
