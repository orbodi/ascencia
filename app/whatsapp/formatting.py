"""Conversion de la mise en forme Markdown (utilisée par le prompt de
l'agent et le rendu riche du chat back-office, cf. FORMAT_HINT dans
app/services/system_config.py et ChatMessageContent.tsx côté front) vers
la syntaxe de formatage réelle de WhatsApp Cloud API.

Le prompt système produit du Markdown classique (``**gras**``,
``*italique*``) car c'est ce qu'attend le parseur du chat back-office pour
dessiner les tableaux/cartes de planning. WhatsApp, lui, utilise une
syntaxe différente :

    **gras**    (Markdown) -> *gras*     (WhatsApp)
    *italique*  (Markdown) -> _italique_ (WhatsApp)

Sans conversion, les utilisateurs WhatsApp voient des doubles astérisques
littéraux et du texte mis en gras là où l'agent voulait de l'italique.
Cette fonction est appliquée uniquement juste avant l'envoi WhatsApp
(WhatsAppWebhookService._chat_and_reply) ; le texte utilisé par le
back-office n'est jamais touché.
"""

from __future__ import annotations

import re

# **gras** Markdown, non-greedy, multi-lignes.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

# *italique* Markdown restant après extraction du gras : un astérisque
# isolé (ni précédé ni suivi d'un autre astérisque) de chaque côté.
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)

# Emplacement temporaire pour le contenu du gras pendant la conversion,
# le temps de traiter l'italique sans confondre les deux.
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def markdown_to_whatsapp(text: str) -> str:
    """Convertit ``**gras**``/``*italique*`` (Markdown) en ``*gras*``/
    ``_italique_`` (syntaxe WhatsApp). Idempotente sur du texte qui ne
    contient déjà aucun astérisque ; ne touche pas les listes à tirets
    (``- item``) ni les autres caractères.
    """
    if not text or "*" not in text:
        return text

    stashed: list[str] = []

    def _stash_bold(match: re.Match[str]) -> str:
        stashed.append(match.group(1))
        return f"\x00{len(stashed) - 1}\x00"

    # 1) Met de côté le **gras** Markdown pour ne pas le confondre avec
    #    de l'italique une fois ses doubles astérisques retirés.
    without_bold = _BOLD_RE.sub(_stash_bold, text)

    # 2) *italique* Markdown restant -> _italique_ WhatsApp.
    converted = _ITALIC_RE.sub(lambda m: f"_{m.group(1)}_", without_bold)

    # 3) Réinjecte le gras avec la syntaxe WhatsApp (simple astérisque).
    def _restore_bold(match: re.Match[str]) -> str:
        return f"*{stashed[int(match.group(1))]}*"

    return _PLACEHOLDER_RE.sub(_restore_bold, converted)
