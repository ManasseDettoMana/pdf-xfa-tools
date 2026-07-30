"""Tests for writing XML back into a PDF, and for the unlock transform."""

from __future__ import annotations

from pathlib import Path

import pytest

from xfatools.core.errors import InjectionError, XfaToolsError
from xfatools.core.extract import extract_xfa_datasets
from xfatools.core.inject import inject_xml, validate_xml
from xfatools.core.unlock import unlock_pdf


class TestValidation:
    def test_accepts_well_formed(self):
        validate_xml("<root><child>x</child></root>")

    def test_rejects_malformed(self):
        with pytest.raises(InjectionError):
            validate_xml("<root><unclosed>")


class TestInjection:
    def test_round_trip_preserves_edit(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        original = extract_xfa_datasets(source)

        edited = original.replace("<MemberFullName/>", "<MemberFullName>Mario Rossi</MemberFullName>")
        assert edited != original, "il PDF di esempio deve contenere MemberFullName"

        out = inject_xml(source, edited)
        assert out.exists()

        reread = extract_xfa_datasets(out)
        assert "<MemberFullName>Mario Rossi</MemberFullName>" in reread

    def test_does_not_touch_the_source(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        before = source.read_bytes()
        xml = extract_xfa_datasets(source)
        inject_xml(source, xml)
        assert source.read_bytes() == before

    def test_rejects_non_xfa_pdf(self, pdf_copy, non_xfa_pdf: Path):
        source = pdf_copy(non_xfa_pdf)
        with pytest.raises(InjectionError, match="non e' un modulo XFA"):
            inject_xml(source, "<xfa:data xmlns:xfa='x'\n></xfa:data\n>")

    def test_rejects_wrong_root(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        with pytest.raises(InjectionError, match="radice"):
            inject_xml(source, "<wrong-root/>")

    def test_rejects_unwritable_packet(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        with pytest.raises(InjectionError, match="non scrivibile"):
            inject_xml(source, "<xfa:data xmlns:xfa='x'\n></xfa:data\n>", packet="preamble")

    def test_rejects_malformed_xml_before_writing(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        expected = source.with_name(f"{source.stem}_updated.pdf")
        with pytest.raises(InjectionError):
            inject_xml(source, "<xfa:data><unclosed></xfa:data>")
        assert not expected.exists(), "nessun PDF deve essere scritto se l'XML e' invalido"


class TestUnlock:
    def test_produces_editable_form(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        result = unlock_pdf(source)

        assert result.out_path.exists()
        assert result.out_path.parent == source.parent, "l'output va accanto al PDF di origine"
        assert result.fields_opened > 0
        assert result.scrollbars_added > 0

    def test_output_is_still_a_valid_xfa_form(self, pdf_copy, xfa_pdf: Path):
        source = pdf_copy(xfa_pdf)
        result = unlock_pdf(source)
        xml = extract_xfa_datasets(result.out_path)
        assert "<form1>" in xml

    def test_rejects_non_xfa_pdf(self, pdf_copy, non_xfa_pdf: Path):
        source = pdf_copy(non_xfa_pdf)
        with pytest.raises(XfaToolsError, match="non e' un modulo XFA"):
            unlock_pdf(source)
