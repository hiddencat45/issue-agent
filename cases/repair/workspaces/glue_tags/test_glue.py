from glue import glue_tags


def test_glue_tags_uses_comma_space():
    assert glue_tags(["a", "b"]) == "a, b"
