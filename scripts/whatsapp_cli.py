"""Outil sûr de test WhatsApp Business Cloud API.

Les secrets sont lus depuis .env par app.config.settings. Ils ne sont jamais
acceptés en argument ni affichés. Le mode WHATSAPP_MOCK=true permet un test à blanc.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.whatsapp.client import WhatsAppClient, normalize_phone


def _phone(value: str) -> str:
    normalized = normalize_phone(value)
    if len(normalized) < 8 or len(normalized) > 15:
        raise argparse.ArgumentTypeError(
            "utilisez un numéro international de 8 à 15 chiffres, sans préfixe 00"
        )
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Envoyer un texte, un modèle approuvé ou un document WhatsApp."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    text = subparsers.add_parser("text", help="texte libre (fenêtre client de 24 h)")
    text.add_argument("--to", required=True, type=_phone)
    text.add_argument("--message", required=True)

    template = subparsers.add_parser(
        "template", help="modèle Meta approuvé (hors fenêtre de 24 h)"
    )
    template.add_argument("--to", required=True, type=_phone)
    template.add_argument("--name", required=True)
    template.add_argument("--language", default="fr")

    document = subparsers.add_parser("document", help="document accompagné d'une légende")
    document.add_argument("--to", required=True, type=_phone)
    document.add_argument("--file", required=True, type=Path)
    document.add_argument("--caption")
    return parser


async def run(args: argparse.Namespace) -> dict[str, Any]:
    client = WhatsAppClient()
    if args.command == "text":
        return await client.send_text(args.to, args.message)
    if args.command == "template":
        return await client.send_template(args.to, args.name, args.language)
    if not args.file.is_file():
        return {"ok": False, "error": f"Fichier introuvable: {args.file}"}
    return await client.send_document(args.to, args.file, caption=args.caption)


def main() -> int:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    safe_result = {key: value for key, value in result.items() if key != "response"}
    print(json.dumps(safe_result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
