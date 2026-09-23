from sysml_spec_qa.highlights import _quote_needles, focus_bboxes, focus_quote


def test_quote_needles_prefer_full_sentence():
    quote = (
        "The definitions given must be consistent with the kind of usage being defined."
    )
    needles = _quote_needles(quote)
    assert needles[0] == quote
    assert all(len(n.split()) != 10 or n == quote for n in needles)


def test_focus_quote_prefers_passed_quote():
    row = {"text": "Long clause text about flows and connections."}
    assert focus_quote(row, quote="All memberships must be distinguishable.") == (
        "All memberships must be distinguishable."
    )


def test_focus_bboxes_limits_to_matching_blocks():
    bboxes = [
        {"page": 1, "x0": 1, "y0": 1, "x1": 2, "y1": 2, "text": "8.4.12.1 Flow Definitions"},
        {
            "page": 1,
            "x0": 1,
            "y0": 3,
            "x1": 2,
            "y1": 4,
            "text": "A FlowDefinition is a kind of ActionDefinition, and a kind of KerML Interaction.",
        },
        {
            "page": 1,
            "x0": 1,
            "y0": 5,
            "x1": 2,
            "y1": 6,
            "text": "abstract flow def M specializes Flows::MessageAction {",
        },
    ]
    quote = "A FlowDefinition is a kind of ActionDefinition"
    picked = focus_bboxes(bboxes, quote, page=1, limit=4)
    assert len(picked) <= 2
    assert all("FlowDefinition" in (b.get("text") or "") for b in picked)
