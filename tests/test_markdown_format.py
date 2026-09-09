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
