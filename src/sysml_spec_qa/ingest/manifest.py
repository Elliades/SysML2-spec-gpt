from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecDoc:
    id: str
    title: str
    version: str
    family: str
    lang_version: str
    pdf_urls: tuple[str, ...]
    metamodel_urls: tuple[str, ...] = ()


STACKS: dict[str, tuple[SpecDoc, ...]] = {
    "2.0": (
        SpecDoc(
            id="kerml-1.0",
            title="Kernel Modeling Language (KerML) 1.0",
            version="2.0",
            family="kerml",
            lang_version="1.0",
            pdf_urls=(
                "https://www.omg.org/spec/KerML/1.0/PDF",
                "https://www.omg.org/spec/KerML/1.0/PDF/",
            ),
            metamodel_urls=(
                "https://www.omg.org/spec/KerML/20250201/KerML.xmi",
                "https://www.omg.org/spec/KerML/20250201/KerML.json",
            ),
        ),
        SpecDoc(
            id="sysml-2.0-language",
            title="OMG System Modeling Language (SysML) 2.0 Language",
            version="2.0",
            family="sysml",
            lang_version="2.0",
            pdf_urls=(
                "https://www.omg.org/spec/SysML/2.0/Language/PDF",
                "https://www.omg.org/spec/SysML/2.0/Language/PDF/",
            ),
            metamodel_urls=(
                "https://www.omg.org/spec/SysML/20250201/SysML.xmi",
                "https://www.omg.org/spec/SysML/20250201/SysML.json",
            ),
        ),
    ),
    "2.1": (
        SpecDoc(
            id="kerml-1.1",
            title="Kernel Modeling Language (KerML) 1.1 Beta",
            version="2.1",
            family="kerml",
            lang_version="1.1",
            pdf_urls=(
                "https://raw.githubusercontent.com/Systems-Modeling/SysML-v2-Release/master/doc/1-Kernel_Modeling_Language.pdf",
                "https://media.githubusercontent.com/media/Systems-Modeling/SysML-v2-Release/master/doc/1-Kernel_Modeling_Language.pdf",
                "https://github.com/Systems-Modeling/SysML-v2-Release/raw/master/doc/1-Kernel_Modeling_Language.pdf",
            ),
            metamodel_urls=(
                "https://www.omg.org/spec/KerML/20250201/KerML.xmi",
            ),
        ),
        SpecDoc(
            id="sysml-2.1-language",
            title="OMG System Modeling Language (SysML) 2.1 Beta Language",
            version="2.1",
            family="sysml",
            lang_version="2.1",
            pdf_urls=(
                "https://raw.githubusercontent.com/Systems-Modeling/SysML-v2-Release/master/doc/2a-OMG_Systems_Modeling_Language.pdf",
                "https://media.githubusercontent.com/media/Systems-Modeling/SysML-v2-Release/master/doc/2a-OMG_Systems_Modeling_Language.pdf",
                "https://github.com/Systems-Modeling/SysML-v2-Release/raw/master/doc/2a-OMG_Systems_Modeling_Language.pdf",
            ),
            metamodel_urls=(
                "https://www.omg.org/spec/SysML/20250201/SysML.xmi",
            ),
        ),
    ),
}


def stack_docs(version: str) -> tuple[SpecDoc, ...]:
    if version not in STACKS:
        known = ", ".join(sorted(STACKS))
        raise ValueError(f"Unknown spec version {version!r}. Known: {known}")
    return STACKS[version]
