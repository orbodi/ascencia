from app.services.display import strip_level_code


def test_strips_licence_code():
    assert strip_level_code("L3 Info A") == "Info A"


def test_strips_master_code():
    assert strip_level_code("M1 IA") == "IA"


def test_strips_two_digit_level():
    assert strip_level_code("L12 Test") == "Test"


def test_leaves_name_without_code_unchanged():
    assert strip_level_code("Info A") == "Info A"


def test_none_is_passed_through():
    assert strip_level_code(None) is None


def test_empty_string_is_passed_through():
    assert strip_level_code("") == ""


def test_name_that_is_only_the_code_is_kept_as_is():
    # Ne doit jamais renvoyer une chaîne vide si le nom est juste le code.
    assert strip_level_code("L3") == "L3"


def test_case_insensitive_prefix():
    assert strip_level_code("l3 info a") == "info a"
