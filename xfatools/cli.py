"""Command-line interface over the same core the GUI uses.

Kept deliberately scriptable: every subcommand accepts multiple files, exits
non-zero when any file fails, and writes progress to stderr so stdout stays
clean for piping.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, __version__
from .core import engines, registry
from .core.errors import XfaToolsError
from .core.extract import (
    AUTO_ORDER,
    DEFAULT_MAX_PAGES,
    build_xfdf,
    extract_all_packets,
    extract_xml,
)
from .core.inject import WRITABLE_PACKETS, inject_xml
from .core.job import Job, JobContext
from .core.probe import probe_pdf
from .core.unlock import unlock_pdf


def _progress_to_stderr(quiet: bool) -> JobContext:
    if quiet:
        return JobContext()

    def report(completed: int, total: int, message: str) -> None:
        if message:
            print(f"  {message}", file=sys.stderr)

    return JobContext(on_progress=report)


def _fail(path: Path, exc: Exception) -> None:
    print(f"ERRORE  {path.name}: {exc}", file=sys.stderr)
    hint = getattr(exc, "hint", None)
    if hint:
        print(f"        {hint}", file=sys.stderr)


def cmd_extract(args: argparse.Namespace) -> int:
    ctx = _progress_to_stderr(args.quiet)
    failures = 0
    for raw in args.files:
        path = Path(raw)
        try:
            result = extract_xml(
                path,
                mode=args.mode,
                ocr_lang=args.ocr_lang,
                ctx=ctx,
                max_pages=None if args.all_pages else args.max_pages,
            )
            out_dir = Path(args.output) if args.output else path.parent
            out_path = result.write(out_dir / f"{path.stem}.xml")
            print(f"{path.name}  [{result.badge}] {result.source_description}  ->  {out_path}")
            for warning in result.warnings:
                print(f"        avviso: {warning}", file=sys.stderr)
        except Exception as exc:
            _fail(path, exc)
            failures += 1
    return 1 if failures else 0


def cmd_extract_all(args: argparse.Namespace) -> int:
    failures = 0
    for raw in args.files:
        path = Path(raw)
        try:
            out_dir = Path(args.output) / path.stem if args.output else None
            written = extract_all_packets(path, out_dir)
            print(f"{path.name}  ->  {len(written)} pacchetti in {written[0].parent}")
        except Exception as exc:
            _fail(path, exc)
            failures += 1
    return 1 if failures else 0


def cmd_xfdf(args: argparse.Namespace) -> int:
    failures = 0
    for raw in args.files:
        path = Path(raw)
        try:
            xml = build_xfdf(path)
            out_dir = Path(args.output) if args.output else path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{path.stem}.xfdf"
            out_path.write_text(xml, encoding="utf-8")
            print(f"{path.name}  ->  {out_path}")
        except Exception as exc:
            _fail(path, exc)
            failures += 1
    return 1 if failures else 0


def cmd_inject(args: argparse.Namespace) -> int:
    try:
        out = inject_xml(args.pdf, Path(args.xml), packet=args.packet, out_path=args.output)
        print(f"{Path(args.pdf).name}  +  {Path(args.xml).name}  ->  {out}")
        return 0
    except Exception as exc:
        _fail(Path(args.pdf), exc)
        return 1


def cmd_unlock(args: argparse.Namespace) -> int:
    failures = 0
    for raw in args.files:
        path = Path(raw)
        try:
            out_dir = Path(args.output) if args.output else path.parent
            result = unlock_pdf(path, out_dir / f"{path.stem}_unlocked.pdf")
            print(
                f"{path.name}  ->  {result.out_path}  "
                f"({result.fields_opened} campi, {result.groups_moved} gruppi, "
                f"{result.personal_fields_cleared} dati personali rimossi)"
            )
            for warning in result.warnings:
                print(f"        avviso: {warning}", file=sys.stderr)
        except Exception as exc:
            _fail(path, exc)
            failures += 1
    return 1 if failures else 0


def cmd_info(args: argparse.Namespace) -> int:
    failures = 0
    for raw in args.files:
        path = Path(raw)
        try:
            profile = probe_pdf(path)
            print(f"{path.name}")
            print(f"  tipo             {profile.label}")
            print(f"  pagine           {profile.page_count}")
            print(f"  pacchetti XFA    {', '.join(profile.xfa_packets) or 'nessuno'}")
            print(f"  campi AcroForm   {profile.acroform_field_count}")
            print(f"  testo/pagina     {profile.text_chars_per_page:.0f} caratteri")
        except Exception as exc:
            _fail(path, exc)
            failures += 1
    return 1 if failures else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {__version__} - componenti rilevati\n")
    for engine in engines.detect_all(refresh=True):
        mark = "[ok]  " if engine.available else "[--]  "
        detail = engine.version or engine.path or ""
        print(f"{mark}{engine.name:<24}{detail}")
        print(f"      {engine.purpose}")
        if not engine.available and engine.install_hint:
            print(f"      -> {engine.install_hint}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    ctx = _progress_to_stderr(args.quiet)
    converter = registry.get(args.to)

    if not converter.available:
        print(f"ERRORE: '{converter.label}' non disponibile.", file=sys.stderr)
        print(f"        {converter.unavailable_reason}", file=sys.stderr)
        return 1

    options = dict(_parse_option_pairs(args.option))
    failures = 0

    for raw in args.files:
        path = Path(raw)
        job = Job(
            source=path,
            target_format=converter.id,
            options=options,
            output_dir=Path(args.output) if args.output else None,
        )
        result = registry.run_job(job, ctx)

        if result.ok:
            badge = f"[{result.badge}] " if result.badge else ""
            targets = ", ".join(str(p) for p in result.outputs[:3])
            more = f" (+{len(result.outputs) - 3})" if len(result.outputs) > 3 else ""
            print(f"{path.name}  {badge}->  {targets}{more}")
            for warning in result.warnings:
                print(f"        avviso: {warning}", file=sys.stderr)
        else:
            print(f"ERRORE  {path.name}: {result.message}", file=sys.stderr)
            if result.hint:
                print(f"        {result.hint}", file=sys.stderr)
            failures += 1

    return 1 if failures else 0


def _parse_option_pairs(pairs: list[str] | None) -> dict[str, object]:
    """Turn ``--option dpi=300`` arguments into a typed options dict."""
    options: dict[str, object] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise XfaToolsError(f"Opzione non valida: '{pair}'. Usa chiave=valore.")
        key, _, value = pair.partition("=")
        options[key.strip()] = _coerce(value.strip())
    return options


def _coerce(value: str) -> object:
    if value.lower() in ("true", "yes", "si"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        return value


def cmd_formats(args: argparse.Namespace) -> int:
    if args.files:
        converters = registry.common_targets(args.files)
        if not converters:
            print("Nessuna conversione applicabile a tutti i file indicati.", file=sys.stderr)
            return 1
    else:
        converters = list(registry.CONVERTERS)

    for category, group in registry.categories_of(converters):
        print(f"\n{registry.CATEGORY_LABELS[category]}")
        for converter in group:
            mark = " " if converter.available else "!"
            accepts = ", ".join(converter.src_exts[:6])
            if len(converter.src_exts) > 6:
                accepts += ", ..."
            print(f"  {mark} {converter.id:<24}{converter.label:<32}da: {accepts}")
            if not converter.available:
                print(f"      -> {converter.unavailable_reason}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xfatools",
        description=f"{APP_NAME} {__version__} - estrazione XML da PDF e conversione file.",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("files", nargs="+", help="uno o piu' file PDF")
        p.add_argument("-o", "--output", help="cartella di destinazione")
        p.add_argument("-q", "--quiet", action="store_true", help="non stampare l'avanzamento")

    p_extract = sub.add_parser("extract", help="estrai un XML dal PDF (catena automatica)")
    add_common(p_extract)
    p_extract.add_argument(
        "-m",
        "--mode",
        default="auto",
        choices=["auto", *(s.value for s in AUTO_ORDER)],
        help="forza una strategia invece della catena automatica",
    )
    p_extract.add_argument("--ocr-lang", default="ita+eng", help="lingue Tesseract (es. ita+eng)")
    p_extract.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"pagine massime per testo/OCR (default {DEFAULT_MAX_PAGES})",
    )
    p_extract.add_argument("--all-pages", action="store_true", help="nessun limite di pagine")
    p_extract.set_defaults(func=cmd_extract)

    p_all = sub.add_parser("extract-all", help="salva ogni pacchetto XFA come XML separato")
    add_common(p_all)
    p_all.set_defaults(func=cmd_extract_all)

    p_xfdf = sub.add_parser("xfdf", help="esporta i valori AcroForm in formato XFDF")
    add_common(p_xfdf)
    p_xfdf.set_defaults(func=cmd_xfdf)

    p_inject = sub.add_parser("inject", help="scrivi un XML dentro un pacchetto XFA del PDF")
    p_inject.add_argument("pdf", help="PDF di destinazione")
    p_inject.add_argument("xml", help="file XML da inserire")
    p_inject.add_argument("-p", "--packet", default="datasets", choices=list(WRITABLE_PACKETS))
    p_inject.add_argument("-o", "--output", help="percorso del PDF risultante")
    p_inject.set_defaults(func=cmd_inject)

    p_unlock = sub.add_parser("unlock", help="rendi editabile una decorazione AF")
    add_common(p_unlock)
    p_unlock.set_defaults(func=cmd_unlock)

    p_info = sub.add_parser("info", help="mostra cosa contiene un PDF")
    add_common(p_info)
    p_info.set_defaults(func=cmd_info)

    p_convert = sub.add_parser("convert", help="converti file in un altro formato")
    p_convert.add_argument("files", nargs="+", help="uno o piu' file da convertire")
    p_convert.add_argument(
        "-t",
        "--to",
        required=True,
        metavar="CONVERTITORE",
        help="id della conversione, come elencato da 'xfatools formats'",
    )
    p_convert.add_argument(
        "-x",
        "--option",
        action="append",
        metavar="CHIAVE=VALORE",
        help="opzione del convertitore, ripetibile (es. -x dpi=300 -x quality=80)",
    )
    p_convert.add_argument("-o", "--output", help="cartella di destinazione")
    p_convert.add_argument("-q", "--quiet", action="store_true", help="non stampare l'avanzamento")
    p_convert.set_defaults(func=cmd_convert)

    p_formats = sub.add_parser("formats", help="elenca le conversioni disponibili")
    p_formats.add_argument(
        "files", nargs="*", help="se indicati, mostra solo cio' che vale per tutti"
    )
    p_formats.set_defaults(func=cmd_formats)

    p_doctor = sub.add_parser("doctor", help="elenca i componenti disponibili")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except XfaToolsError as exc:
        print(f"ERRORE: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrotto.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
