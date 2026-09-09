from app.utils.location import normalize_state, normalize_city, normalize_location, city_in_state


def test_normalize_state_abbreviation():
    assert normalize_state("CG") == "Chhattisgarh"
    assert normalize_state("mp") == "Madhya Pradesh"


def test_normalize_state_full_name_case_insensitive():
    assert normalize_state("chhattisgarh") == "Chhattisgarh"


def test_normalize_city_strips_suffix():
    assert normalize_city("Raipur, CG") == "Raipur"
    assert normalize_city("raipur") == "Raipur"


def test_normalize_location_variants_agree():
    a = normalize_location("Raipur, CG")
    b = normalize_location("Raipur, Chhattisgarh")
    c = normalize_location("Raipur")
    assert a == ("Raipur", "Chhattisgarh")
    assert b == ("Raipur", "Chhattisgarh")
    assert c == ("Raipur", "Chhattisgarh")  # inferred via CITY_STATE_HINTS


def test_city_in_state_mismatch_detected():
    assert city_in_state("Raipur", "Maharashtra") is False
    assert city_in_state("Pune", "Maharashtra") is True


def test_city_in_state_unknown_city_not_over_filtered():
    # A city not in our hints map should not be excluded just because we
    # don't recognize it — avoids silently dropping legitimate jobs.
    assert city_in_state("SomeSmallTown", "Chhattisgarh") is True
