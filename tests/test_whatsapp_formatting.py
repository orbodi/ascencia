from app.whatsapp.formatting import markdown_to_whatsapp


def test_bold_markdown_becomes_whatsapp_bold():
    assert markdown_to_whatsapp("**Mardi 04/08**") == "*Mardi 04/08*"


def test_italic_markdown_becomes_whatsapp_italic():
    assert markdown_to_whatsapp("*Bases de données*") == "_Bases de données_"


def test_schedule_line_from_system_prompt_rule_20():
    line = (
        "**Mardi 04/08 (08:00 - 10:00)** : *Bases de données* "
        "(L3 Info A) avec Bruno Dupont en salle B202 (Séance #2)"
    )
    expected = (
        "*Mardi 04/08 (08:00 - 10:00)* : _Bases de données_ "
        "(L3 Info A) avec Bruno Dupont en salle B202 (Séance #2)"
    )
    assert markdown_to_whatsapp(line) == expected


def test_multiple_schedule_lines():
    text = (
        "- **Mardi 04/08 (08:00 - 10:00)** : *Bases de données* (Séance #2)\n"
        "- **Mercredi 05/08 (10:00 - 12:00)** : *Algorithmique* (Séance #3)"
    )
    expected = (
        "- *Mardi 04/08 (08:00 - 10:00)* : _Bases de données_ (Séance #2)\n"
        "- *Mercredi 05/08 (10:00 - 12:00)* : _Algorithmique_ (Séance #3)"
    )
    assert markdown_to_whatsapp(text) == expected


def test_dash_bullet_lists_are_left_untouched():
    text = "1. Lundi 09h\n2. Mardi 14h\n3. Jeudi 10h"
    assert markdown_to_whatsapp(text) == text


def test_plain_text_without_asterisks_is_unchanged():
    text = "Titre : 4h restantes (2h faites / 6h prévues)"
    assert markdown_to_whatsapp(text) == text


def test_empty_string():
    assert markdown_to_whatsapp("") == ""


def test_unmatched_single_asterisk_left_alone():
    text = "3 * 4 = 12 et pas de fermeture"
    assert markdown_to_whatsapp(text) == text
