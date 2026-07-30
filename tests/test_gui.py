"""Tests for the presentation layer.

Everything here runs headless (``QT_QPA_PLATFORM=offscreen``), so the suite works
on a build agent with no display.  The window is exercised for real: files are
queued, a batch is run and the results are asserted, which is what catches the
wiring mistakes that unit tests on the core never see.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 non installato")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from xfatools.core.job import JobStatus  # noqa: E402
from xfatools.gui.i18n import Translator, tr, translator  # noqa: E402
from xfatools.gui.settings import Settings  # noqa: E402
from xfatools.gui.theme import DARK, LIGHT, PALETTES, build_stylesheet, resolve  # noqa: E402
from xfatools.gui.translations import CATALOGS, ENGLISH, ITALIAN  # noqa: E402
from xfatools.gui.widgets.dropzone import collect_supported  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app


def pump(milliseconds: int = 200) -> None:
    """Run the event loop briefly so queued signals are delivered."""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class TestTranslations:
    def test_catalogs_have_identical_keys(self):
        missing_in_english = set(ITALIAN) - set(ENGLISH)
        missing_in_italian = set(ENGLISH) - set(ITALIAN)
        assert not missing_in_english, f"chiavi assenti in inglese: {missing_in_english}"
        assert not missing_in_italian, f"chiavi assenti in italiano: {missing_in_italian}"

    def test_no_empty_translations(self):
        for code, catalog in CATALOGS.items():
            empty = [key for key, value in catalog.items() if not value.strip()]
            assert not empty, f"traduzioni vuote in '{code}': {empty}"

    def test_placeholders_match_between_languages(self):
        import re

        pattern = re.compile(r"\{(\w+)\}")
        for key, italian in ITALIAN.items():
            assert pattern.findall(italian) == pattern.findall(ENGLISH[key]), (
                f"i segnaposto di '{key}' non coincidono fra le lingue"
            )

    def test_no_emoji_anywhere(self):
        """The project forbids emojis in the interface."""
        for code, catalog in CATALOGS.items():
            for key, value in catalog.items():
                assert all(ord(char) < 0x2190 for char in value), (
                    f"carattere non testuale in {code}:{key}"
                )

    def test_every_pdf_kind_has_a_label(self):
        from xfatools.core.probe import PdfKind

        for kind in PdfKind:
            assert f"kind.{kind.value}" in ITALIAN

    def test_every_status_has_a_label(self):
        for status in JobStatus:
            assert f"status.{status.value}" in ITALIAN

    def test_every_badge_has_a_label_and_tooltip(self):
        from xfatools.core.extract import SOURCE_LABELS

        badges = {label for label, _ in SOURCE_LABELS.values()} | {"APPROSSIMATO"}
        for badge in badges:
            assert f"badge.{badge}" in ITALIAN
            assert f"badge.{badge.lower()}.tooltip" in ITALIAN


class TestTranslator:
    def test_falls_back_to_the_key(self):
        assert tr("this.key.does.not.exist") == "this.key.does.not.exist"

    def test_formats_placeholders(self):
        translator.set_language("it")
        assert "7" in tr("queue.count", count=7)

    def test_missing_placeholder_does_not_raise(self):
        assert tr("queue.count") == ITALIAN["queue.count"]

    def test_switching_emits_once(self, qt_app):
        local = Translator()
        seen: list[str] = []
        local.language_changed.connect(seen.append)

        local.set_language("en")
        local.set_language("en")  # already active: must not emit again
        local.set_language("it")
        assert seen == ["en", "it"]

    def test_unknown_language_is_ignored(self):
        local = Translator()
        local.set_language("klingon")
        assert local.language == "it"


class TestTheme:
    def test_every_palette_renders(self):
        for palette in PALETTES.values():
            sheet = build_stylesheet(palette)
            assert "QWidget" in sheet
            assert "{" in sheet
            # An unsubstituted token would leave a literal brace pair behind.
            assert "{p." not in sheet

    def test_explicit_preference_wins(self):
        assert resolve("dark") is DARK
        assert resolve("light") is LIGHT

    def test_light_and_dark_differ_on_every_colour_role(self):
        from dataclasses import fields

        for f in fields(LIGHT):
            if f.name in ("name", "is_dark"):
                continue
            assert getattr(LIGHT, f.name) != getattr(DARK, f.name), (
                f"il ruolo '{f.name}' e' identico nei due temi"
            )


class TestSettings:
    def test_defaults_are_usable(self):
        settings = Settings()
        assert settings.worker_count() >= 1
        assert settings.resolved_output_dir(Path("x.pdf")) is None

    def test_custom_output_dir(self, tmp_path: Path):
        settings = Settings(output_mode="custom", output_dir=str(tmp_path))
        assert settings.resolved_output_dir(Path("x.pdf")) == tmp_path

    def test_recent_files_are_deduplicated_and_capped(self):
        settings = Settings()
        for index in range(30):
            settings.remember_file(f"file{index}.pdf")
        settings.remember_file("file29.pdf")
        assert len(settings.recent_files) <= 12
        assert settings.recent_files[0].endswith("file29.pdf")
        assert len(settings.recent_files) == len(set(settings.recent_files))

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        broken = tmp_path / "settings.json"
        broken.write_text("{not json at all", encoding="utf-8")
        monkeypatch.setattr(Settings, "path", classmethod(lambda cls: broken))
        assert Settings.load().theme == "system"

    def test_unknown_keys_are_ignored(self, tmp_path, monkeypatch):
        target = tmp_path / "settings.json"
        target.write_text('{"theme": "dark", "from_the_future": 1}', encoding="utf-8")
        monkeypatch.setattr(Settings, "path", classmethod(lambda cls: target))
        assert Settings.load().theme == "dark"

    def test_round_trip(self, tmp_path, monkeypatch):
        target = tmp_path / "settings.json"
        monkeypatch.setattr(Settings, "path", classmethod(lambda cls: target))
        Settings(theme="dark", language="en", max_pages=42).save()
        loaded = Settings.load()
        assert (loaded.theme, loaded.language, loaded.max_pages) == ("dark", "en", 42)


class TestCollectSupported:
    def test_filters_by_extension(self, tmp_path: Path):
        (tmp_path / "keep.png").write_bytes(b"x")
        (tmp_path / "skip.exe").write_bytes(b"x")
        accepted, rejected = collect_supported([tmp_path / "keep.png", tmp_path / "skip.exe"])
        assert [p.name for p in accepted] == ["keep.png"]
        assert rejected == 1

    def test_walks_folders_recursively(self, tmp_path: Path):
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "deep.pdf").write_bytes(b"x")
        (tmp_path / "top.png").write_bytes(b"x")
        accepted, _ = collect_supported([tmp_path])
        assert {p.name for p in accepted} == {"deep.pdf", "top.png"}

    def test_deduplicates(self, tmp_path: Path):
        target = tmp_path / "one.pdf"
        target.write_bytes(b"x")
        accepted, _ = collect_supported([target, target, tmp_path])
        assert len(accepted) == 1


class TestMainWindow:
    def _window(self, qt_app, tmp_path: Path):
        from xfatools.gui.main_window import MainWindow

        settings = Settings(output_mode="custom", output_dir=str(tmp_path))
        window = MainWindow(settings)
        window.show()
        return window

    def test_starts_on_the_drop_zone(self, qt_app, tmp_path):
        window = self._window(qt_app, tmp_path)
        try:
            assert window.stack.currentWidget() is window.drop_zone
            assert not window.convert_button.isEnabled()
        finally:
            window.runner.shutdown()
            window.close()

    def test_adding_files_switches_to_the_queue(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            assert window.stack.currentWidget() is window.queue
            assert len(window.queue.rows()) == 1
            assert window.convert_button.isEnabled()
        finally:
            window.runner.shutdown()
            window.close()

    def test_the_same_file_is_not_queued_twice(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            window.add_files([xfa_pdf])
            assert len(window.queue.rows()) == 1
        finally:
            window.runner.shutdown()
            window.close()

    def test_probing_fills_in_the_detected_type(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            pump(3000)
            row = window.queue.rows()[0]
            assert row.profile is not None
            assert "XFA" in row.type_label
        finally:
            window.runner.shutdown()
            window.close()

    def test_running_a_batch_end_to_end(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            pump(2000)

            finished: list[list] = []
            loop = QEventLoop()
            window.runner.batch_finished.connect(
                lambda results: (finished.append(results), loop.quit())
            )
            window.start_conversion()

            assert not window.convert_button.isEnabled(), "il pulsante deve bloccarsi durante l'esecuzione"
            assert window.cancel_button.isVisible()

            QTimer.singleShot(30000, loop.quit)
            loop.exec()

            assert finished, "il batch non si e' concluso"
            result = finished[0][0]
            assert result.status is JobStatus.DONE
            assert result.badge == "EXACT"
            assert result.primary_output.exists()
            assert result.primary_output.parent == tmp_path

            assert window.convert_button.isEnabled()
            assert not window.cancel_button.isVisible()
        finally:
            window.runner.shutdown()
            window.close()

    def test_language_switch_updates_live(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            translator.set_language("it")
            pump(100)
            italian = window.convert_button.text()
            # Column 1, not 0: "File" happens to be spelled the same in both
            # languages, so column 0 would pass even if nothing retranslated.
            header_it = window.queue.horizontalHeaderItem(1).text()

            translator.set_language("en")
            pump(100)
            assert window.convert_button.text() != italian
            assert window.queue.horizontalHeaderItem(1).text() != header_it
            assert window.queue.rowCount() == 1, "la coda deve sopravvivere al cambio lingua"
        finally:
            translator.set_language("it")
            window.runner.shutdown()
            window.close()

    def test_theme_toggle_flips_and_persists(self, qt_app, tmp_path, monkeypatch):
        monkeypatch.setattr(Settings, "path", classmethod(lambda cls: tmp_path / "s.json"))
        window = self._window(qt_app, tmp_path)
        try:
            window.toggle_theme()
            first = window.theme_preference
            window.toggle_theme()
            assert window.theme_preference != first
            assert window.settings.theme == window.theme_preference
        finally:
            window.runner.shutdown()
            window.close()

    def test_clearing_returns_to_the_drop_zone(self, qt_app, tmp_path, xfa_pdf):
        window = self._window(qt_app, tmp_path)
        try:
            window.add_files([xfa_pdf])
            window.queue.clear_all()
            assert window.stack.currentWidget() is window.drop_zone
            assert not window.convert_button.isEnabled()
        finally:
            window.runner.shutdown()
            window.close()
