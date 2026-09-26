from notes import format_note


def test_keeps_leading_and_trailing_spaces():
    assert format_note(" a ") == " a "
