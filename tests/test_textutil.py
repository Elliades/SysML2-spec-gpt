from sysml_spec_qa.synonyms import expand_query
from sysml_spec_qa.textutil import excerpt, fts_query, parse_clause_title, word_count


def test_parse_clause_title():
    clause_id, rest = parse_clause_title("7.2.5 Namespaces")
    assert clause_id == "7.2.5"
    assert rest == "Namespaces"


def test_french_uniqueness_expands_to_namespace():
    terms = [t.lower() for t in expand_query("c’est quoi les règles d’unicité des noms ?")]
    assert "unique" in terms or "uniqueness" in terms
    assert "namespace" in terms or "name" in terms
    assert "quoi" not in terms


def test_connector_french_expands():
    terms = [t.lower() for t in expand_query("à quoi je peux connecter un connector ?")]
    assert "connector" in terms


def test_excerpt_budget():
    text = "alpha " * 400 + "unique name inside a namespace " + "omega " * 400
    snip = excerpt(text, ["unique", "namespace"], 40)
    assert word_count(snip) <= 42
    assert "unique" in snip.lower()


def test_fts_query_quotes_pascalcase():
    q = fts_query(["Connector", "unique"])
    assert '"Connector"' in q
    assert "unique*" in q
