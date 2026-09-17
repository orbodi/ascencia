"""Aides de présentation pour le planning (indépendantes du stockage).

`StudentGroup.name` est saisi en base sous la forme "L3 Info A", "M1 IA",
etc. : le code de parcours (L1, L2, L3, M1, M2…) est concaténé au début
du nom, il n'existe pas de colonne séparée. Sur le planning (texte agent
/ WhatsApp, rappels, distribution), répéter ce code sur chaque ligne est
redondant — l'audience du document ou de la conversation est déjà connue
par ailleurs. Cette fonction retire ce préfixe uniquement à l'affichage ;
elle ne modifie jamais la donnée stockée (identifiant, unicité du nom,
etc. restent inchangés).
"""

from __future__ import annotations

import re

_LEVEL_CODE_PREFIX_RE = re.compile(r"^(?:L|M)\d{1,2}\s+", re.IGNORECASE)


def strip_level_code(name: str | None) -> str | None:
    """Retire un préfixe de code de parcours (« L3 », « M1 »…) d'un nom de
    groupe pour l'affichage. Renvoie le nom inchangé si aucun préfixe ne
    correspond, ou si le retirer ne laisserait plus rien (le nom est alors
    conservé tel quel pour ne jamais afficher une chaîne vide).
    """
    if not name:
        return name
    stripped = _LEVEL_CODE_PREFIX_RE.sub("", name).strip()
    return stripped or name
