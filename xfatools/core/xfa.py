"""Low-level access to the XFA packets embedded in a PDF form.

An XFA-enabled PDF stores its form definition under ``/Root/AcroForm/XFA`` in one
of two shapes:

* a flat array alternating names and streams -
  ``[ "preamble", <stream>, "config", <stream>, "template", <stream>, ... ]``
* a single stream holding the whole XDP document (rarer, produced by some
  generators and by "XFA as one blob" workflows)

``XfaObj`` normalises both into a ``dict``-like object keyed by packet name.
Reading a key gives you ``str``; assigning a ``str`` writes it back into the PDF
in place, so the caller only has to ``pdf.save(...)`` afterwards.

This class is the one piece of the original toolkit that was already correct and
is deliberately preserved: the ``i % 2`` pairing over the flat array and the
UTF-8 encode/decode round-trip come straight from the historical ``xfaTools.py``.
"""

from __future__ import annotations

import pikepdf

from .errors import NoXfaError, PacketNotFoundError

#: Name used for the synthetic key when ``/XFA`` is a single unsplit stream.
WHOLE_DOCUMENT_KEY = "<whole document>"

#: Packet names that carry actual form data, in the order we prefer them.
DATA_PACKETS = ("datasets",)


class XfaObj(dict):
    """A ``dict`` view over the XFA packets of an open :class:`pikepdf.Pdf`."""

    def __init__(self, source_pdf: pikepdf.Pdf):
        self.source = source_pdf
        self.xfaDict: dict[str, object] = {}

        try:
            self.root = source_pdf.Root.AcroForm.XFA
        except (AttributeError, KeyError) as exc:
            raise NoXfaError(
                "Il PDF non contiene un modulo XFA (/Root/AcroForm/XFA assente)."
            ) from exc

        if isinstance(self.root, pikepdf.Stream):
            # Single-stream form: the whole XDP lives in one object.
            self.xfaDict[WHOLE_DOCUMENT_KEY] = self.root
        else:
            for i, item in enumerate(self.root):
                if i % 2 == 0 and isinstance(item, pikepdf.String):
                    self.xfaDict[str(item)] = self.root[i + 1]

        if not self.xfaDict:
            raise NoXfaError("Il modulo XFA e' presente ma non contiene pacchetti leggibili.")

        super().__init__(self.xfaDict)

    def __getitem__(self, key: str) -> str:
        try:
            value = self.xfaDict[key]
        except KeyError as exc:
            available = ", ".join(self.xfaDict) or "(nessuno)"
            raise PacketNotFoundError(
                f"Pacchetto XFA '{key}' non trovato. Disponibili: {available}."
            ) from exc

        if isinstance(value, pikepdf.Stream):
            return value.read_bytes().decode("utf-8", errors="replace")
        # Not a stream: hand back a textual rendering rather than a pikepdf object,
        # so callers never have to care about the underlying type.
        return str(value)

    def __setitem__(self, key: str, value: str | bytes) -> None:
        if key not in self.xfaDict:
            raise PacketNotFoundError(f"Pacchetto XFA '{key}' non trovato: impossibile scriverlo.")
        target = self.xfaDict[key]
        if not isinstance(target, pikepdf.Stream):
            raise PacketNotFoundError(f"Il pacchetto XFA '{key}' non e' uno stream scrivibile.")
        if isinstance(value, str):
            value = value.encode("utf-8")
        target.write(value)

    # -- convenience ------------------------------------------------------

    @property
    def packet_names(self) -> list[str]:
        return list(self.xfaDict)

    def has(self, key: str) -> bool:
        return key in self.xfaDict

    def data_packet_name(self) -> str | None:
        """Return the name of the packet holding form data, if any."""
        for name in DATA_PACKETS:
            if name in self.xfaDict:
                return name
        # Single-stream forms embed <xfa:datasets> inside the whole document.
        if WHOLE_DOCUMENT_KEY in self.xfaDict and "<xfa:datasets" in self[WHOLE_DOCUMENT_KEY]:
            return WHOLE_DOCUMENT_KEY
        return None


def safe_packet_filename(key: str) -> str:
    """Turn an XFA packet name into a filesystem-safe stem.

    Packet names may contain characters that Windows rejects (``<``, ``>``, ``:``)
    and the synthetic whole-document key contains spaces.  ``/`` becomes ``END``
    to preserve the historical behaviour of ``xfa-extract-all.py``.
    """
    import re

    cleaned = re.sub(r"[<>:\"|?*\s]", "", key)
    cleaned = cleaned.replace("/", "END")
    return cleaned or "packet"
