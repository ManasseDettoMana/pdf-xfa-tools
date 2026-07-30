"""Make an AF decoration PDF fully editable.

Ported from the original ``deco-unlock.py`` with its behaviour preserved: the
transforms below are tuned to the Air Force decoration forms in ``decos/`` and
changing them changes the output for real users.  The only deliberate change is
that the result is written next to the source PDF instead of into the current
working directory, matching every other operation in this toolkit.

What it does to the ``template`` packet:

* moves the radio-button groups (``exclGroup``) into a visible stack at x=0
* marks every field and group ``access="open"`` / ``presence="visible"``
* gives every text field ``vScrollPolicy="auto"`` so long text scrolls instead
  of being silently clipped
* clones the form's existing font-size event and re-fires it on mouse click, so
  the user can switch font while filling the form
* relocates ``PreviewGraphic`` / ``PrintGraphic``

and to the ``datasets`` packet: clears any personal data left in the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from bs4 import BeautifulSoup

from .errors import NoXfaError, XfaToolsError
from .xfa import XfaObj

#: Field names whose contents are personal data and must not survive conversion.
PERSONAL_DATA_RE = r"(Narrative)|(MemberFullName)|(Sign.*\d+)"

#: Vertical spacing used when stacking the relocated controls.
GROUP_SPACING_MM = 20
GRAPHIC_SPACING_MM = 5

RELOCATED_GRAPHICS = ("PreviewGraphic", "PrintGraphic")


@dataclass
class UnlockResult:
    """What the unlock pass changed, for reporting in the GUI."""

    out_path: Path
    groups_moved: int = 0
    fields_opened: int = 0
    scrollbars_added: int = 0
    personal_fields_cleared: int = 0
    warnings: list[str] = field(default_factory=list)


def soup_copy(soup):
    """Deep-copy a tag by round-tripping it through the parser."""
    return BeautifulSoup(str(soup), "xml").find()


def unlock_pdf(path: str | Path, out_path: str | Path | None = None) -> UnlockResult:
    """Rewrite ``path`` into an editable decoration form."""
    path = Path(path)
    out_path = Path(out_path) if out_path else path.with_name(f"{path.stem}_unlocked.pdf")
    result = UnlockResult(out_path=out_path)

    with pikepdf.Pdf.open(str(path)) as pdf:
        try:
            xfa = XfaObj(pdf)
        except NoXfaError as exc:
            raise XfaToolsError(
                f"'{path.name}' non e' un modulo XFA: lo sblocco funziona solo sulle "
                "decorazioni AF generate da vPC.",
                hint="Verifica di aver scaricato il PDF originale e non una copia appiattita.",
            ) from exc

        if not xfa.has("template"):
            raise XfaToolsError("Il modulo XFA non contiene un pacchetto 'template'.")

        template_soup = BeautifulSoup(xfa["template"], "xml")

        y_offset = 0
        for tag in template_soup.find_all("exclGroup"):
            tag["x"] = "0mm"
            tag["y"] = f"{y_offset}mm"
            y_offset += GROUP_SPACING_MM
            tag["access"] = "open"
            tag["presence"] = "visible"
            result.groups_moved += 1

        personal_data_tags: list[str] = []

        # Clone the event/script that hides the font-size boxes and re-fire it on
        # mouse click, so the font switcher stays usable in the unlocked form.
        source_event = template_soup.find("event")
        new_event = None
        if source_event is not None:
            new_event = soup_copy(source_event)
            new_event["activity"] = "click"
        else:
            result.warnings.append(
                "Nessun <event> trovato nel template: il selettore del font non sara' "
                "riattivato."
            )

        for tag in template_soup.find_all("field"):
            text_edit = tag.find("textEdit")
            name = tag.get("name", "")
            if text_edit:
                if name and re.match(PERSONAL_DATA_RE, name):
                    personal_data_tags.append(name)
                text_edit["vScrollPolicy"] = "auto"
                result.scrollbars_added += 1

            tag["access"] = "open"
            tag["presence"] = "visible"
            result.fields_opened += 1

            if new_event is not None:
                tag.append(soup_copy(new_event))

            if name in RELOCATED_GRAPHICS:
                tag["x"] = "0mm"
                tag["y"] = f"{y_offset}mm"
                y_offset += GRAPHIC_SPACING_MM

        xfa["template"] = str(template_soup.find())

        if xfa.has("datasets") and personal_data_tags:
            data_soup = BeautifulSoup(xfa["datasets"], "xml")
            for tag_name in personal_data_tags:
                tag = data_soup.find(tag_name)
                if tag:
                    tag.contents = []
                    result.personal_fields_cleared += 1
            # find() returns the root tag, dropping the <?xml ...?> declaration
            # that the parser prepends - XFA packets must not carry one.
            xfa["datasets"] = str(data_soup.find())

        out_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.save(str(out_path))

    return result
