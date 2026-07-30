"""Options for the selected row, built generically from the registry.

No conversion-specific UI code lives here: a converter declares its
:class:`~xfatools.core.registry.Option` list and the right editor appears.
Adding an option to a converter needs no change in this file.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core import registry
from ...core.registry import Converter, Option
from ..i18n import tr, translator


class OptionsPanel(QFrame):
    """Renders the options of whichever converter the selected row targets."""

    options_changed = Signal(dict)
    apply_to_all_requested = Signal(str, dict)  # converter id, options

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._converter: Converter | None = None
        self._editors: dict[str, QWidget] = {}
        self._values: dict[str, Any] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        self.title = QLabel(self)
        self.title.setObjectName("SectionTitle")
        outer.addWidget(self.title)

        self.description = QLabel(self)
        self.description.setWordWrap(True)
        self.description.setProperty("variant", "muted")
        outer.addWidget(self.description)

        self.form_host = QWidget(self)
        self.form_host.setObjectName("PanelBody")
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 4, 0, 0)
        self.form.setSpacing(10)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        outer.addWidget(self.form_host)

        self.empty_label = QLabel(self)
        self.empty_label.setWordWrap(True)
        self.empty_label.setProperty("variant", "muted")
        outer.addWidget(self.empty_label)

        outer.addStretch(1)

        self.apply_all_button = QPushButton(self)
        self.apply_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_all_button.clicked.connect(self._emit_apply_to_all)
        outer.addWidget(self.apply_all_button)

        self.reset_button = QPushButton(self)
        self.reset_button.setProperty("variant", "ghost")
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset)
        outer.addWidget(self.reset_button)

        self.retranslate()
        translator.language_changed.connect(self.retranslate)
        self.show_converter(None, {})

    def retranslate(self) -> None:
        self.title.setText(tr("options.title"))
        self.reset_button.setText(tr("options.reset"))
        self.apply_all_button.setText(tr("options.apply_all"))
        if self._converter is None:
            self.empty_label.setText(tr("options.no_selection"))
        elif not self._converter.options:
            self.empty_label.setText(tr("options.none"))
        else:
            # Rebuild so option labels and help text pick up the new language.
            self.show_converter(self._converter, dict(self._values))

    # -- population -------------------------------------------------------

    def show_converter(self, converter: Converter | None, values: dict[str, Any]) -> None:
        """Display the options of ``converter``, pre-filled with ``values``."""
        self._converter = converter
        self._editors.clear()
        self._clear_form()

        if converter is None:
            self.description.setText("")
            self.description.setVisible(False)
            self.empty_label.setText(tr("options.no_selection"))
            self.empty_label.setVisible(True)
            self.form_host.setVisible(False)
            self.reset_button.setVisible(False)
            self.apply_all_button.setVisible(False)
            self._values = {}
            return

        self.description.setText(converter.description)
        self.description.setVisible(bool(converter.description))

        self._values = {**converter.defaults(), **values}

        if not converter.options:
            self.empty_label.setText(tr("options.none"))
            self.empty_label.setVisible(True)
            self.form_host.setVisible(False)
            self.reset_button.setVisible(False)
            self.apply_all_button.setVisible(False)
            return

        self.empty_label.setVisible(False)
        self.form_host.setVisible(True)
        self.reset_button.setVisible(True)
        self.apply_all_button.setVisible(True)

        for option in converter.options:
            editor = self._build_editor(option, self._values.get(option.key, option.default))
            if editor is None:
                continue
            self._editors[option.key] = editor
            label = QLabel(option.label, self)
            self.form.addRow(label, editor)
            if option.help:
                help_label = QLabel(option.help, self)
                help_label.setObjectName("OptionHelp")
                help_label.setWordWrap(True)
                self.form.addRow("", help_label)

    def _build_editor(self, option: Option, value: Any) -> QWidget | None:
        if option.kind == "int":
            spin = QSpinBox(self)
            spin.setRange(option.minimum, option.maximum)
            spin.setValue(int(value) if value is not None else option.default)
            if option.suffix:
                spin.setSuffix(option.suffix)
            spin.valueChanged.connect(lambda v, key=option.key: self._set_value(key, v))
            return spin

        if option.kind == "choice":
            combo = QComboBox(self)
            for label, choice_value in option.choices:
                combo.addItem(label, choice_value)
            position = combo.findData(value)
            combo.setCurrentIndex(position if position >= 0 else 0)
            combo.currentIndexChanged.connect(
                lambda _i, key=option.key, box=combo: self._set_value(key, box.currentData())
            )
            return combo

        if option.kind == "bool":
            check = QCheckBox(self)
            check.setChecked(bool(value))
            check.toggled.connect(lambda checked, key=option.key: self._set_value(key, checked))
            return check

        if option.kind == "text":
            line = QLineEdit(self)
            line.setText("" if value is None else str(value))
            line.textChanged.connect(lambda text, key=option.key: self._set_value(key, text))
            return line

        return None

    def _clear_form(self) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # -- values -----------------------------------------------------------

    def _set_value(self, key: str, value: Any) -> None:
        self._values[key] = value
        self.options_changed.emit(dict(self._values))

    def values(self) -> dict[str, Any]:
        return dict(self._values)

    def _reset(self) -> None:
        if self._converter is not None:
            self.show_converter(self._converter, {})
            self.options_changed.emit(dict(self._values))

    def _emit_apply_to_all(self) -> None:
        if self._converter is not None:
            self.apply_to_all_requested.emit(self._converter.id, dict(self._values))


class ResultPanel(QFrame):
    """Shows the outcome of the selected row: badge, warnings, output files."""

    open_file_requested = Signal(object)
    open_folder_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._result = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self.title = QLabel(self)
        self.title.setObjectName("SectionTitle")
        layout.addWidget(self.title)

        self.badge = QLabel(self)
        self.badge.setVisible(False)
        layout.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignLeft)

        self.source_label = QLabel(self)
        self.source_label.setWordWrap(True)
        self.source_label.setProperty("variant", "muted")
        layout.addWidget(self.source_label)

        self.warnings_label = QLabel(self)
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setProperty("state", "warning")
        self.warnings_label.setVisible(False)
        layout.addWidget(self.warnings_label)

        self.outputs_label = QLabel(self)
        self.outputs_label.setWordWrap(True)
        self.outputs_label.setProperty("variant", "muted")
        layout.addWidget(self.outputs_label)

        self.open_button = QPushButton(self)
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(lambda: self.open_file_requested.emit(self._result))
        layout.addWidget(self.open_button)

        self.folder_button = QPushButton(self)
        self.folder_button.setProperty("variant", "ghost")
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.clicked.connect(lambda: self.open_folder_requested.emit(self._result))
        layout.addWidget(self.folder_button)

        self.retranslate()
        translator.language_changed.connect(self.retranslate)
        self.show_result(None)

    def retranslate(self) -> None:
        self.title.setText(tr("result.title"))
        self.open_button.setText(tr("queue.open_file"))
        self.folder_button.setText(tr("queue.open_folder"))
        self.show_result(self._result)

    def show_result(self, result) -> None:
        self._result = result
        visible = result is not None and bool(getattr(result, "outputs", None))
        self.setVisible(result is not None)
        if result is None:
            return

        if result.badge:
            self.badge.setText(tr(f"badge.{result.badge}"))
            self.badge.setProperty("badge", result.badge)
            self.badge.setToolTip(tr(f"badge.{result.badge.lower()}.tooltip"))
            self.badge.setVisible(True)
            from ..theme import restyle

            restyle(self.badge)
        else:
            self.badge.setVisible(False)

        self.source_label.setText(
            f"{tr('result.source')} {result.detail}" if result.detail else result.message
        )
        self.source_label.setVisible(bool(result.detail or result.message))

        if result.warnings:
            bullets = "\n".join(f"- {w}" for w in result.warnings)
            self.warnings_label.setText(f"{tr('result.warnings')}:\n{bullets}")
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

        if result.outputs:
            names = "\n".join(p.name for p in result.outputs[:6])
            extra = f"\n(+{len(result.outputs) - 6})" if len(result.outputs) > 6 else ""
            self.outputs_label.setText(f"{tr('result.outputs')}:\n{names}{extra}")
            self.outputs_label.setVisible(True)
        else:
            self.outputs_label.setVisible(False)

        self.open_button.setVisible(visible)
        self.folder_button.setVisible(visible)


def default_options_for(converter_id: str) -> dict[str, Any]:
    """Defaults for a converter, used when a row has never been customised."""
    try:
        return registry.get(converter_id).defaults()
    except Exception:
        return {}
