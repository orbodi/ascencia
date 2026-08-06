"""Annuaire WhatsApp (admins + profs) depuis le .env en JSON."""

from __future__ import annotations

from app.config.settings import WhatsAppPerson, settings
from app.whatsapp.client import normalize_phone


def all_whatsapp_people() -> list[WhatsAppPerson]:
    return [*settings.whatsapp_admins, *settings.whatsapp_teachers]


def find_person_by_phone(phone: str) -> WhatsAppPerson | None:
    incoming = normalize_phone(phone)
    if not incoming:
        return None
    for person in all_whatsapp_people():
        stored = normalize_phone(person.numero)
        if not stored:
            continue
        if (
            stored == incoming
            or stored.endswith(incoming[-9:])
            or incoming.endswith(stored[-9:])
        ):
            return person
    return None


def phones_for_role(role: str) -> set[str]:
    role_l = role.lower()
    return {
        normalize_phone(p.numero)
        for p in all_whatsapp_people()
        if p.role.lower() == role_l and normalize_phone(p.numero)
    }
