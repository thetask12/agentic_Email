from app.sources.source_manager import build_queries, guess_company_name_from_title
from app.models.enums import JobSource


def test_build_queries_scopes_to_source_domain():
    queries = build_queries("MIS Executive", "Chhattisgarh", "Raipur", JobSource.NAUKRI)
    assert len(queries) == 1
    assert "site:naukri.com" in queries[0]
    assert '"MIS Executive"' in queries[0]
    assert '"Raipur"' in queries[0]
    assert '"Chhattisgarh"' in queries[0]


def test_build_queries_not_hardcoded_to_mis_executive():
    queries = build_queries("Data Analyst", "Maharashtra", "Pune", JobSource.INDEED)
    assert '"Data Analyst"' in queries[0]
    assert '"MIS Executive"' not in queries[0]


def test_build_queries_google_search_uses_general_discovery():
    queries = build_queries("MIS Manager", "Chhattisgarh", "Raipur", JobSource.GOOGLE_SEARCH)
    assert len(queries) == 2
    assert all("site:" not in q for q in queries)


def test_guess_company_name_from_title():
    assert guess_company_name_from_title("MIS Executive - ABC Pvt Ltd - Naukri.com") == "ABC Pvt Ltd"
    assert guess_company_name_from_title("Just a title with no separators") is None
