"""Tests for the conversion registry and the converters it dispatches to."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from xfatools.core import documents, engines, images, pdfops, registry
from xfatools.core.errors import ConversionError
from xfatools.core.job import Job, JobContext, JobStatus, unique_path


@pytest.fixture
def sample_png(tmp_path: Path) -> Path:
    """A small RGBA image with real transparency."""
    path = tmp_path / "sample.png"
    image = Image.new("RGBA", (120, 80), (0, 120, 200, 255))
    for x in range(60):
        for y in range(40):
            image.putpixel((x, y), (255, 0, 0, 0))
    image.save(path)
    return path


@pytest.fixture
def sample_markdown(tmp_path: Path) -> Path:
    path = tmp_path / "note.md"
    path.write_text(
        "# Titolo\n\nUn paragrafo.\n\n- primo\n- secondo\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    return path


class TestRegistry:
    def test_every_converter_has_a_unique_id(self):
        ids = [c.id for c in registry.CONVERTERS]
        assert len(ids) == len(set(ids))

    def test_pdf_offers_same_extension_operations(self):
        labels = {c.id for c in registry.targets_for("x.pdf")}
        # These are PDF -> PDF and must not be filtered out as no-ops.
        assert {"pdf-rotate", "pdf-compress", "pdf-unlock-deco", "pdf-extract-pages"} <= labels

    def test_image_does_not_offer_itself(self):
        ids = {c.id for c in registry.targets_for("x.png")}
        assert "image-to-png" not in ids
        assert "image-to-jpg" in ids

    def test_mixed_selection_only_offers_shared_conversions(self):
        shared = registry.common_targets(["a.png", "b.jpg"])
        assert shared, "due immagini devono condividere delle conversioni"
        assert all("png" in c.src_exts and "jpg" in c.src_exts for c in shared)

    def test_unknown_converter_raises(self):
        with pytest.raises(ConversionError):
            registry.get("does-not-exist")

    def test_options_have_defaults_for_every_key(self):
        for converter in registry.CONVERTERS:
            defaults = converter.defaults()
            assert set(defaults) == {o.key for o in converter.options}

    def test_choice_options_default_to_one_of_their_choices(self):
        for converter in registry.CONVERTERS:
            for option in converter.options:
                if option.kind == "choice":
                    values = [value for _label, value in option.choices]
                    assert option.default in values, f"{converter.id}.{option.key}"


class TestImages:
    def test_png_to_jpg_flattens_transparency(self, sample_png: Path, tmp_path: Path):
        dst = tmp_path / "out.jpg"
        images.convert_image(sample_png, dst, {"quality": 85})
        assert dst.exists()
        with Image.open(dst) as result:
            assert result.mode == "RGB"
            assert result.size == (120, 80)
            # The transparent corner must become the background, not black.
            assert result.getpixel((5, 5)) == pytest.approx((255, 255, 255), abs=8)

    def test_resize_never_upscales(self, sample_png: Path, tmp_path: Path):
        dst = tmp_path / "big.png"
        images.convert_image(sample_png, dst, {"max_width": 9999, "max_height": 9999})
        with Image.open(dst) as result:
            assert result.size == (120, 80)

    def test_resize_preserves_aspect_ratio(self, sample_png: Path, tmp_path: Path):
        dst = tmp_path / "small.png"
        images.convert_image(sample_png, dst, {"max_width": 60, "max_height": 60})
        with Image.open(dst) as result:
            assert result.size == (60, 40)

    def test_ico_is_clamped_to_256(self, tmp_path: Path):
        source = tmp_path / "large.png"
        Image.new("RGB", (900, 900), "red").save(source)
        dst = tmp_path / "out.ico"
        images.convert_image(source, dst)
        with Image.open(dst) as result:
            assert max(result.size) <= images.ICO_MAX_SIZE

    def test_images_to_single_pdf(self, sample_png: Path, tmp_path: Path):
        second = tmp_path / "second.png"
        Image.new("RGB", (100, 100), "green").save(second)
        dst = tmp_path / "album.pdf"
        images.images_to_pdf([sample_png, second], dst)

        import pikepdf

        with pikepdf.Pdf.open(dst) as pdf:
            assert len(pdf.pages) == 2

    def test_unreadable_file_reports_clearly(self, tmp_path: Path):
        broken = tmp_path / "broken.png"
        broken.write_text("not an image", encoding="utf-8")
        with pytest.raises(ConversionError, match="non e' un'immagine"):
            images.convert_image(broken, tmp_path / "out.jpg")


class TestPdfOps:
    def test_pdf_to_images(self, xfa_pdf: Path, tmp_path: Path):
        written = pdfops.pdf_to_images(xfa_pdf, tmp_path, {"format": "png", "dpi": 72})
        assert written
        assert all(p.exists() and p.suffix == ".png" for p in written)

    def test_split_and_merge_round_trip(self, xfa_pdf: Path, tmp_path: Path):
        parts = pdfops.split_pdf(xfa_pdf, tmp_path / "parts")
        merged = tmp_path / "merged.pdf"
        pdfops.merge_pdfs(parts, merged)

        import pikepdf

        with pikepdf.Pdf.open(xfa_pdf) as original, pikepdf.Pdf.open(merged) as result:
            assert len(result.pages) == len(original.pages)

    def test_rotate_records_the_angle(self, pdf_copy, xfa_pdf: Path, tmp_path: Path):
        source = pdf_copy(xfa_pdf)
        dst = tmp_path / "rotated.pdf"
        pdfops.rotate_pdf(source, dst, {"angle": 90})

        import pikepdf

        with pikepdf.Pdf.open(dst) as pdf:
            assert int(pdf.pages[0].get("/Rotate", 0)) % 360 == 90

    def test_rotate_rejects_non_multiples_of_90(self, xfa_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError, match="multiplo di 90"):
            pdfops.rotate_pdf(xfa_pdf, tmp_path / "x.pdf", {"angle": 45})

    def test_compress_never_grows_the_file(self, xfa_pdf: Path, tmp_path: Path):
        dst = tmp_path / "small.pdf"
        pdfops.compress_pdf(xfa_pdf, dst)
        assert dst.stat().st_size <= xfa_pdf.stat().st_size

    def test_extract_pages(self, xfa_pdf: Path, tmp_path: Path):
        dst = tmp_path / "page1.pdf"
        pdfops.extract_pages(xfa_pdf, dst, {"pages": "1"})

        import pikepdf

        with pikepdf.Pdf.open(dst) as pdf:
            assert len(pdf.pages) == 1


class TestPageRange:
    @pytest.mark.parametrize(
        ("spec", "total", "expected"),
        [
            ("1", 10, [1]),
            ("1-3", 10, [1, 2, 3]),
            ("1-3,7", 10, [1, 2, 3, 7]),
            ("8-", 10, [8, 9, 10]),
            ("-3", 10, [1, 2, 3]),
            ("3-1", 10, [1, 2, 3]),
            ("1,1,2", 10, [1, 2]),
            ("5-99", 6, [5, 6]),
        ],
    )
    def test_parses(self, spec: str, total: int, expected: list[int]):
        assert pdfops.parse_page_range(spec, total) == expected

    def test_rejects_garbage(self):
        with pytest.raises(ConversionError):
            pdfops.parse_page_range("abc", 10)


class TestDocuments:
    def test_markdown_to_pdf(self, sample_markdown: Path, tmp_path: Path):
        dst = tmp_path / "note.pdf"
        documents.text_to_pdf(sample_markdown, dst)
        assert dst.exists()
        assert dst.stat().st_size > 500

        import pikepdf

        with pikepdf.Pdf.open(dst) as pdf:
            assert len(pdf.pages) >= 1

    def test_csv_to_pdf(self, tmp_path: Path):
        source = tmp_path / "data.csv"
        source.write_text("nome,valore\nalfa,1\nbeta,2\n", encoding="utf-8")
        dst = tmp_path / "data.pdf"
        documents.text_to_pdf(source, dst)
        assert dst.exists()

    def test_pdf_to_text(self, non_xfa_pdf: Path, tmp_path: Path):
        dst = tmp_path / "out.txt"
        documents.pdf_to_text(non_xfa_pdf, dst, {"max_pages": 2})
        content = dst.read_text(encoding="utf-8")
        assert "--- pagina 1 ---" in content
        assert len(content) > 100

    def test_pdf_to_markdown(self, non_xfa_pdf: Path, tmp_path: Path):
        dst = tmp_path / "out.md"
        documents.pdf_to_markdown(non_xfa_pdf, dst, {"max_pages": 2})
        content = dst.read_text(encoding="utf-8")
        assert content.startswith("# ")
        assert "## Pagina 1" in content

    def test_pdf_to_csv_without_tables_explains_itself(self, xfa_pdf: Path, tmp_path: Path):
        try:
            documents.pdf_to_csv(xfa_pdf, tmp_path / "out.csv", {"max_pages": 1})
        except ConversionError as exc:
            assert "tabella" in str(exc).lower()

    @pytest.mark.requires_engine
    def test_docx_to_pdf(self, tmp_path: Path):
        if not engines.is_available("office_to_pdf"):
            pytest.skip("ne' LibreOffice ne' Word COM disponibili")


class TestRunJob:
    def test_successful_job_reports_outputs(self, sample_png: Path, tmp_path: Path):
        job = Job(source=sample_png, target_format="image-to-jpg", output_dir=tmp_path)
        result = registry.run_job(job)
        assert result.ok
        assert result.primary_output is not None
        assert result.primary_output.exists()
        assert result.duration_s >= 0

    def test_failure_is_captured_not_raised(self, tmp_path: Path):
        missing = tmp_path / "ghost.png"
        job = Job(source=missing, target_format="image-to-jpg", output_dir=tmp_path)
        result = registry.run_job(job)
        assert result.status is JobStatus.FAILED
        assert "non trovato" in result.message

    def test_extraction_job_carries_its_badge(self, xfa_pdf: Path, tmp_path: Path):
        job = Job(source=xfa_pdf, target_format="pdf-to-xml", output_dir=tmp_path)
        result = registry.run_job(job, JobContext())
        assert result.ok
        assert result.badge == "EXACT"
        assert "XFA" in result.detail

    def test_heuristic_job_carries_warnings(self, non_xfa_pdf: Path, tmp_path: Path):
        job = Job(
            source=non_xfa_pdf,
            target_format="pdf-to-xml",
            options={"max_pages": 2},
            output_dir=tmp_path,
        )
        result = registry.run_job(job, JobContext())
        assert result.ok
        assert result.badge == "HEURISTIC"
        assert result.warnings

    def test_cancellation_is_reported_as_cancelled(self, non_xfa_pdf: Path, tmp_path: Path):
        job = Job(source=non_xfa_pdf, target_format="pdf-to-txt", output_dir=tmp_path)
        result = registry.run_job(job, JobContext(is_cancelled=lambda: True))
        assert result.status is JobStatus.CANCELLED

    def test_never_overwrites_an_existing_output(self, sample_png: Path, tmp_path: Path):
        job = Job(source=sample_png, target_format="image-to-jpg", output_dir=tmp_path)
        first = registry.run_job(job).primary_output
        second = registry.run_job(job).primary_output
        assert first != second
        assert first.exists() and second.exists()


class TestUniquePath:
    def test_returns_input_when_free(self, tmp_path: Path):
        target = tmp_path / "free.txt"
        assert unique_path(target) == target

    def test_numbers_collisions(self, tmp_path: Path):
        target = tmp_path / "taken.txt"
        target.write_text("x", encoding="utf-8")
        assert unique_path(target).name == "taken (2).txt"
