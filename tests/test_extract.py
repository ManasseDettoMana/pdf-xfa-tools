"""Tests for the extraction fallback chain."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from xfatools.core.errors import ExtractionError, NoXfaError
from xfatools.core.extract import (
    Confidence,
    ExtractSource,
    extract_acroform_xml,
    extract_all_packets,
    extract_text_xml,
    extract_xfa_datasets,
    extract_xml,
    rewrap_datasets,
    unwrap_datasets,
)
from xfatools.core.job import JobContext
from xfatools.core.probe import PdfKind, probe_pdf


class TestProbe:
    def test_identifies_dynamic_xfa(self, xfa_pdf: Path):
        profile = probe_pdf(xfa_pdf)
        assert profile.kind is PdfKind.DYNAMIC_XFA
        assert profile.has_xfa
        assert "datasets" in profile.xfa_packets
        assert profile.has_xfa_data

    def test_identifies_plain_pdf(self, non_xfa_pdf: Path):
        profile = probe_pdf(non_xfa_pdf)
        assert not profile.has_xfa
        assert not profile.has_acroform
        assert profile.has_text_layer
        assert profile.kind is PdfKind.TEXT

    def test_missing_file_raises(self, tmp_path: Path):
        from xfatools.core.errors import PdfOpenError

        with pytest.raises(PdfOpenError):
            probe_pdf(tmp_path / "nope.pdf")


class TestXfaStrategy:
    def test_extracts_sample_data_xml(self, xfa_pdf: Path):
        xml = extract_xfa_datasets(xfa_pdf)
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<xfa:data ')
        assert "xmlns:xfa=" in xml
        assert "<xfa:datasets" not in xml
        assert xml.rstrip().endswith("</xfa:data\n>")

    def test_all_sample_forms_extract(self, all_xfa_pdfs: list[Path]):
        for pdf in all_xfa_pdfs:
            xml = extract_xfa_datasets(pdf)
            assert "<form1>" in xml, f"{pdf.name} non contiene il nodo form1"

    def test_chain_picks_xfa_and_reports_exact(self, xfa_pdf: Path):
        result = extract_xml(xfa_pdf)
        assert result.source is ExtractSource.XFA
        assert result.confidence is Confidence.EXACT
        assert result.badge == "EXACT"
        assert result.is_exact
        assert not result.warnings

    def test_extract_all_packets(self, pdf_copy, xfa_pdf: Path, tmp_path: Path):
        copied = pdf_copy(xfa_pdf)
        written = extract_all_packets(copied)
        names = {p.stem for p in written}
        assert {"template", "datasets", "config"} <= names
        assert all(p.read_text(encoding="utf-8").strip() for p in written)

    def test_non_xfa_pdf_raises_for_forced_mode(self, non_xfa_pdf: Path):
        with pytest.raises(NoXfaError):
            extract_xfa_datasets(non_xfa_pdf)


class TestUnwrapRoundTrip:
    RAW = (
        '<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/"\n'
        "><xfa:data\n><form1><name>Mario</name></form1></xfa:data\n></xfa:datasets\n>"
    )

    def test_unwrap_produces_data_root(self):
        out = unwrap_datasets(self.RAW)
        assert out.startswith("<xfa:data ")
        assert "xmlns:xfa=" in out
        assert "<form1><name>Mario</name></form1>" in out

    def test_rewrap_is_inverse(self):
        unwrapped = unwrap_datasets(self.RAW)
        rewrapped = rewrap_datasets(unwrapped)
        # The body must survive the round trip untouched.
        assert "<form1><name>Mario</name></form1>" in rewrapped
        assert rewrapped.startswith("<xfa:datasets ")
        assert unwrap_datasets(rewrapped).strip() == unwrapped.strip()

    def test_round_trip_on_real_form(self, xfa_pdf: Path):
        xml = extract_xfa_datasets(xfa_pdf)
        body = xml.split("?>\n", 1)[1]
        assert unwrap_datasets(rewrap_datasets(body)).strip() == body.strip()

    def test_rejects_unexpected_structure(self):
        with pytest.raises(ExtractionError):
            unwrap_datasets("<something-else/>")


class TestTextStrategy:
    def test_reconstructs_xml_with_positions(self, non_xfa_pdf: Path):
        xml, field_count = extract_text_xml(non_xfa_pdf, max_pages=3)
        assert '<document source=' in xml
        assert 'extraction="text-layout"' in xml
        assert "<line " in xml
        assert 'top="' in xml and 'left="' in xml
        assert field_count >= 0

    def test_marks_truncation_honestly(self, non_xfa_pdf: Path):
        xml, _ = extract_text_xml(non_xfa_pdf, max_pages=2)
        assert 'truncated="true"' in xml
        assert 'pagesProcessed="2"' in xml
        assert re.search(r'pages="\d{3,}"', xml), "il totale reale deve restare visibile"

    def test_reports_progress(self, non_xfa_pdf: Path):
        seen: list[str] = []
        ctx = JobContext(on_progress=lambda done, total, msg: seen.append(msg))
        extract_text_xml(non_xfa_pdf, ctx=ctx, max_pages=3)
        assert len(seen) >= 3

    def test_honours_cancellation(self, non_xfa_pdf: Path):
        from xfatools.core.errors import CancelledError

        ctx = JobContext(is_cancelled=lambda: True)
        with pytest.raises(CancelledError):
            extract_text_xml(non_xfa_pdf, ctx=ctx, max_pages=5)


class TestChainFallback:
    def test_falls_through_to_text_and_warns(self, non_xfa_pdf: Path):
        result = extract_xml(non_xfa_pdf, max_pages=3)
        assert result.source is ExtractSource.TEXT
        assert result.confidence is Confidence.HEURISTIC
        assert result.badge == "HEURISTIC"
        assert not result.is_exact
        assert any("ricostruito" in w for w in result.warnings), (
            "l'utente deve sapere che l'XML e' una ricostruzione"
        )

    def test_unknown_mode_is_rejected(self, xfa_pdf: Path):
        with pytest.raises(ExtractionError, match="sconosciuta"):
            extract_xml(xfa_pdf, mode="telepathy")

    def test_result_writes_utf8(self, xfa_pdf: Path, tmp_path: Path):
        result = extract_xml(xfa_pdf)
        out = result.write(tmp_path / "out.xml")
        assert out.exists()
        assert out.read_text(encoding="utf-8") == result.xml


class TestAcroForm:
    def test_raises_when_no_fields(self, non_xfa_pdf: Path):
        with pytest.raises(ExtractionError):
            extract_acroform_xml(non_xfa_pdf)
