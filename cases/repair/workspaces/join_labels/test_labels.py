from labels import join_labels


def test_join_labels_with_comma_space():
    assert join_labels(["red", "blue"]) == "red, blue"
