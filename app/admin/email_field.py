"""Type e-mail Pydantic tolérant aux domaines de démonstration.

`pydantic.EmailStr` (via `email_validator`) rejette par défaut les domaines
« special-use / reserved » tels que `.test`, `.example` ou `.invalid`
(RFC 2606). Or ce projet utilise volontairement des adresses `@example.test`
pour son jeu de données de démonstration (voir `scripts/seed.py`, `README.md`)
— avec `EmailStr` strict, `GET /admin/teachers` plante en
`ResponseValidationError` (HTTP 500) dès qu'un seul enseignant démo est en
base, et l'interface d'administration se retrouve à afficher silencieusement
« aucun enseignant » (React Query retombe sur une liste vide en cas
d'erreur) au lieu du moindre message d'erreur.

`DemoEmailStr` garde une validation de syntaxe stricte (RFC 5321/5322,
pas de vérification DNS/MX — `check_deliverability=False`, comme le fait déjà
`EmailStr` par défaut) mais autorise en plus les domaines `.test` via l'option
`test_environment=True` d'`email_validator`, pensée exactement pour ce cas
d'usage. Les domaines encore plus rarement rencontrés comme `.local` restent
rejetés — c'est correct : ce ne sont pas des adresses e-mail valides pour
un envoi réel (mDNS), contrairement à `.test`, qui n'est qu'une convention de
nommage documentaire.
"""

from __future__ import annotations

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator


def _validate_demo_friendly_email(value: str) -> str:
    try:
        result = validate_email(
            value,
            check_deliverability=False,
            test_environment=True,
        )
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized


DemoEmailStr = Annotated[str, AfterValidator(_validate_demo_friendly_email)]
