from sysml_spec_qa.markdown import format_clause_body, render_clause_html


SAMPLE = """\
7.16.2 Flow Definitions and Usages
A flow definition is declared like a regular connection definition (see 7.13.2 ), but using the kind keyword flow. A
flow usage is declared like a regular connection usage (see 7.13.2 ), but using one of the kind keywords message,
flow, or succession flow (as discussed further below).
flow def FuelFlow {
ref item :>> payload : Fuel;
end tank : FuelTank;
end eng : Engine;
}
part def Vehicle {
part engine {
Systems Modeling Language v2.0, Part 1
83
event occurrence receiveControl;
}
}
▪
messages for a message.
84
Systems Modeling Language v2.0, Part 1
"""


def test_format_clause_body_fences_code_and_strips_headers():
    out = format_clause_body(SAMPLE)
    assert "Systems Modeling Language" not in out
    assert "```sysml" in out
    assert "flow def FuelFlow" in out
    assert "- messages for a message." in out
    assert "flow usage is declared" in out.replace("\n", " ")


def test_render_clause_html_has_paragraphs_and_pre():
    html = render_clause_html(SAMPLE, title="7.16.2 Flow Definitions and Usages", clause_id="7.16.2")
    assert "<p>" in html
    assert "<pre>" in html
    assert "Systems Modeling Language" not in html


def test_highlight_skips_code_blocks():
    html = render_clause_html(SAMPLE, query="flow", clause_id="7.16.2")
    assert html.count("<mark") <= 16
    assert "<pre><code" in html
    pre = html.split("<pre>")[1].split("</pre>")[0]
    assert "<mark" not in pre


def test_linkify_clause_refs():
    html = render_clause_html(
        "See (see 7.13.2 ) and [KerML, 7.4.10] for details.",
        doc_id="sysml-2.0-language",
        version="2.0",
    )
    assert 'class="clause-ref"' in html
    assert "7.13.2" in html
