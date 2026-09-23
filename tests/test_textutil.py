from sysml_spec_qa.textutil import (
    cite_sentence,
    estimate_tokens,
    excerpt,
    fit_quote,
    fts_query,
    normative_line_quote,
    unwrap_pdf_lines,
    word_count,
)


def test_word_count():
    assert word_count("one two three") == 3


def test_estimate_tokens_empty_and_nonempty():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0
    assert estimate_tokens("one two three") == 4


def test_cite_sentence_finds_term():
    text = (
        "Intro sentence. Every owned name in a Namespace must be unique. "
        "Another sentence follows here."
    )
    quote = cite_sentence(text, ["namespace", "unique"], max_words=80)
    assert "unique" in quote.lower()
    assert word_count(quote) <= 80


def test_normative_line_quote_finds_constraint_english():
    text = (
        "deriveNamespaceOwnedMembership\n"
        "The ownedMemberships of a Namespace are all its ownedRelationships that are Memberships.\n"
        "validateNamespaceDistinguishibility\n"
        "All memberships of a Namespace must be distinguishable from each other.\n"
        "membership->forAll(m1 |"
    )
    quote = normative_line_quote(text, ["distinguishable", "membership"])
    assert quote == "All memberships of a Namespace must be distinguishable from each other."


def test_cite_sentence_prefers_normative_over_description():
    text = (
        "8.3.2.4.5 Namespace Description A Namespace is an Element that contains other Elements. "
        "All memberships of a Namespace must be distinguishable from each other."
    )
    quote = cite_sentence(text, ["namespace", "membership"], max_words=80)
    assert "distinguishable" in quote.lower()


def test_unwrap_pdf_lines_joins_wrapped_sentence():
    text = (
        "The definitions given must be consistent with the kind of usage being\n"
        "defined.\n"
        "2.\n"
        "Subsettings specify other usages subsetted by the owning usage."
    )
    joined = unwrap_pdf_lines(text)
    assert "usage being defined." in joined
    quote = cite_sentence(text, ["subsetting", "definitions", "usage"], max_words=80)
    assert quote.endswith(".")
    assert "being defined" in quote or "Subsettings specify" in quote
    assert not quote.endswith("being")


def test_fit_quote_stops_at_sentence_end():
    text = (
        "Feature typings specify the definitions of a usage. "
        "Subsettings specify other usages subsetted by the owning usage. "
        + " ".join(["extra"] * 90)
    )
    out = fit_quote(text, max_words=20)
    assert out.endswith(".")
    assert "…" not in out or out.endswith(".")


def test_word_re_keeps_french_accents():
    assert word_count("quels sont les éléments") == 4


def test_cite_sentence_skips_pdf_header_and_example():
    text = (
        "Systems Modeling Language v2.0, Part 1\n"
        "117\n"
        "state def Exercising {\n"
        "entry action warmup : WarmUp;\n"
        "}\n"
        "In addition, entry, do and exit actions can be declared (at most one of each) "
        "in the body of a state definition or usage.\n"
        "A state definition or usage may hierarchically contain state usages in its body."
    )
    quote = cite_sentence(text, ["state", "entry", "exit"], max_words=80)
    assert "can be declared" in quote
    assert "Systems Modeling Language" not in quote
    assert "Exercising" not in quote


def test_excerpt_truncates():
    text = " ".join(["word"] * 200)
    snip = excerpt(text, ["word"], 50)
    assert word_count(snip) <= 51


def test_fts_query_caps_terms():
    terms = [f"term{i}" for i in range(30)]
    q = fts_query(terms)
    assert q.count(" OR ") <= 11
