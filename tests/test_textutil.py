from sysml_spec_qa.textutil import cite_sentence, excerpt, fts_query, normative_line_quote, word_count


def test_word_count():
    assert word_count("one two three") == 3


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


def test_excerpt_truncates():
    text = " ".join(["word"] * 200)
    snip = excerpt(text, ["word"], 50)
    assert word_count(snip) <= 51


def test_fts_query_caps_terms():
    terms = [f"term{i}" for i in range(30)]
    q = fts_query(terms)
    assert q.count(" OR ") <= 11
