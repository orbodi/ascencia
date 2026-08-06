import json
import os

from app.config.settings import WhatsAppPerson, get_settings
from app.whatsapp.contacts import find_person_by_phone, phones_for_role
from app.whatsapp.client import normalize_phone
from app.whatsapp.webhook_service import extract_inbound_messages, verify_meta_signature


def test_normalize_phone():
    assert normalize_phone("+33 6 10 00 00 01") == "33610000001"
    assert normalize_phone("33610000001") == "33610000001"


def test_extract_inbound_text_messages():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "33610000001",
                                    "id": "wamid.1",
                                    "type": "text",
                                    "text": {"body": "Je confirme la séance #3"},
                                },
                                {
                                    "from": "33610000002",
                                    "id": "wamid.2",
                                    "type": "image",
                                },
                            ]
                        }
                    }
                ]
            }
        ]
    }
    msgs = extract_inbound_messages(payload)
    assert len(msgs) == 1
    assert msgs[0]["from"] == "33610000001"
    assert "confirme" in msgs[0]["text"]


def test_verify_signature_without_secret_allows():
    assert verify_meta_signature(b"{}", None) is True


def test_contacts_from_json_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv(
        "WHATSAPP_ADMINS",
        json.dumps(
            [
                {
                    "nom": "Admin",
                    "prenom": "Demo",
                    "numero": "33600000000",
                    "role": "admin",
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "WHATSAPP_TEACHERS",
        json.dumps(
            [
                {
                    "nom": "Martin",
                    "prenom": "Alice",
                    "numero": "+33 6 10 00 00 01",
                    "role": "teacher",
                }
            ]
        ),
    )
    get_settings.cache_clear()
    from app.config.settings import Settings

    s = Settings()
    assert len(s.whatsapp_admins) == 1
    assert s.whatsapp_admins[0].role == "admin"
    assert len(s.whatsapp_teachers) == 1
    assert s.whatsapp_teachers[0].full_name == "Alice Martin"

    # find_person uses cached settings — patch module settings
    import app.whatsapp.contacts as contacts_mod
    import app.config as config_mod

    monkeypatch.setattr(config_mod, "settings", s)
    monkeypatch.setattr(contacts_mod, "settings", s)

    person = find_person_by_phone("33610000001")
    assert person is not None
    assert person.role == "teacher"
    assert "33600000000" in phones_for_role("admin")
