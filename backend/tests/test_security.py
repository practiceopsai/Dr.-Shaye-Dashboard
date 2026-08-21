from app.security import contains_phi, payload_hash


def test_phi_detection():
    assert contains_phi("Patient John Smith DOB: 1/2/1960")
    assert not contains_phi("Prepare the board agenda for Thursday")


def test_hash_is_stable_and_sensitive():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})

