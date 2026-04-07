# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "opencc-python-reimplemented>=0.1.7",
# ]
# ///
"""Convert Kaishi 1500 TSV into a Typst document and optionally run `typst compile` to produce a PDF.

Usage:
    python convert_kaishi.py [--tsv FILE] [--out TYP_FILE] [--pdf OUT.pdf] [--compile]
                             [--typst-binary PATH] [--font-path PATH] [--columns N]

Examples:
    # Just generate the .typ file
    python convert_kaishi.py

    # Generate and compile to PDF (uses `typst` on PATH if available)
    python convert_kaishi.py --compile --font-path "/Users/alan/Library/Fonts"

    # Specify file names
    python convert_kaishi.py --tsv kaishi-1500.tsv --out kaishi-1500.typ --pdf kaishi-1500.pdf --compile

    # Force a different page column count
    python convert_kaishi.py --columns 2
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shlex
import shutil
import subprocess
import sys
from typing import Iterable, List, Mapping

# Defaults
PAPER_SIZE = 'a5'
DEFAULT_TSV = "kaishi-1500.tsv"
DEFAULT_TYP = "kaishi-1500.typ"
DEFAULT_PDF = None
FONTS = ("Hiragino Mincho ProN", "芫荽")
MARGIN = "0.05cm"
TEXT_SIZE = "10pt"
INSET = '3pt'
COLUMNS = 1
COLUMN_GAP = "0.25cm"
TYPST_TIMEOUT_SEC = 60


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    # Strip all HTML tags including attributes
    return re.sub(r"<[^>]*>", "", text)


def typst_escape(t: str) -> str:
    """Escape characters that Typst would treat as special inside table cells."""
    if t is None:
        return ""
    # Escape backslash first
    res = t.replace("\\", "\\\\")
    # Escape characters that may be interpreted by typst inside inline content.
    for ch in ("[", "]", "#", "_", "*", "$"):
        res = res.replace(ch, f"\\{ch}")
    return res


def read_tsv(tsv_file: str) -> List[Mapping[str, object]]:
    if not os.path.exists(tsv_file):
        raise FileNotFoundError(f"TSV file not found: {tsv_file}")

    data: List[Mapping[str, object]] = []
    with open(tsv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or len(row) < 11:
                continue

            word = strip_html(row[0])
            reading = strip_html(row[1])
            meaning = strip_html(row[2])
            sentence = strip_html(row[4])
            sentence_meaning = strip_html(row[5])
            frequency_raw = row[10] if len(row) > 10 else ""

            try:
                clean_freq = frequency_raw.replace('"', "").strip()
                frequency = int(clean_freq) if clean_freq else 999_999
            except ValueError:
                frequency = 999_999

            data.append(
                {
                    "word": word,
                    "reading": reading,
                    "meaning": meaning,
                    "sentence": f"{sentence} ({sentence_meaning})" if sentence or sentence_meaning else "",
                    "frequency": frequency,
                }
            )

    # Sort by frequency (ascending: more frequent first)
    data.sort(key=lambda x: x["frequency"])
    return data


def generate_typst_content(
    data: Iterable[Mapping[str, object]],
    fonts: Iterable[str] = FONTS,
    margin: str = MARGIN,
    text_size: str = TEXT_SIZE,
    page_columns: int = COLUMNS,
    column_gap: str = COLUMN_GAP,
) -> List[str]:
    typst_lines: List[str] = []
    font_items = ", ".join([f'"{f}"' for f in fonts]) if fonts else ""
    font_str = f"font: ({font_items}), " if font_items else ""

    typst_lines.append(f'#set page(paper: "{PAPER_SIZE}", margin: {margin}, columns: {page_columns})') # , column-gutter: {column_gap}
    typst_lines.append(f'#set text({font_str}size: {text_size})')
    typst_lines.append('#show table.cell.where(y: 0): set text(weight: "bold")')
    typst_lines.append("#table(")
    typst_lines.append("  columns: (15%, 15%, 28%, 42%),")
    typst_lines.append(f"  inset: {INSET},")
    typst_lines.append("  stroke: 0.3pt + luma(200),")
    typst_lines.append("  align: (center, center, left, left),")
    typst_lines.append("  table.header([Word], [Reading], [Meaning], [Sentence]),")

    for item in data:
        w = typst_escape(str(item.get("word", "")))
        r = typst_escape(str(item.get("reading", "")))
        m = typst_escape(str(item.get("meaning", "")))
        s = typst_escape(str(item.get("sentence", "")))
        typst_lines.append(f"  [{w}], [{r}], [{m}], [{s}],")

    typst_lines.append(")")

    # Add Kana tables at the end
    # typst_lines.append("#v(2em)")

    kana_rows = [
        ["a", "i", "u", "e", "o"],
        ["ka", "ki", "ku", "ke", "ko"],
        ["sa", "shi", "su", "se", "so"],
        ["ta", "chi", "tsu", "te", "to"],
        ["na", "ni", "nu", "ne", "no"],
        ["ha", "hi", "fu", "he", "ho"],
        ["ma", "mi", "mu", "me", "mo"],
        ["ya", "", "yu", "", "yo"],
        ["ra", "ri", "ru", "re", "ro"],
        ["wa", "", "", "", "wo"],
        ["n", "", "", "", ""],
    ]

    hira_grid = {
        "a": "あ",
        "i": "い",
        "u": "う",
        "e": "え",
        "o": "お",
        "ka": "か",
        "ki": "き",
        "ku": "く",
        "ke": "け",
        "ko": "こ",
        "sa": "さ",
        "shi": "し",
        "su": "す",
        "se": "せ",
        "so": "そ",
        "ta": "た",
        "chi": "ち",
        "tsu": "つ",
        "te": "て",
        "to": "と",
        "na": "な",
        "ni": "に",
        "nu": "ぬ",
        "ne": "ね",
        "no": "の",
        "ha": "は",
        "hi": "ひ",
        "fu": "ふ",
        "he": "へ",
        "ho": "ほ",
        "ma": "ま",
        "mi": "み",
        "mu": "む",
        "me": "め",
        "mo": "も",
        "ya": "や",
        "yu": "ゆ",
        "yo": "よ",
        "ra": "ら",
        "ri": "り",
        "ru": "る",
        "re": "れ",
        "ro": "ろ",
        "wa": "わ",
        "wo": "を",
        "n": "ん",
    }

    kata_grid = {
        "a": "ア",
        "i": "イ",
        "u": "ウ",
        "e": "エ",
        "o": "オ",
        "ka": "カ",
        "ki": "キ",
        "ku": "ク",
        "ke": "ケ",
        "ko": "コ",
        "sa": "サ",
        "shi": "シ",
        "su": "ス",
        "se": "セ",
        "so": "ソ",
        "ta": "タ",
        "chi": "チ",
        "tsu": "ツ",
        "te": "テ",
        "to": "ト",
        "na": "ナ",
        "ni": "ニ",
        "nu": "ヌ",
        "ne": "ネ",
        "no": "ノ",
        "ha": "ハ",
        "hi": "ヒ",
        "fu": "フ",
        "he": "ヘ",
        "ho": "ホ",
        "ma": "マ",
        "mi": "ミ",
        "mu": "ム",
        "me": "メ",
        "mo": "モ",
        "ya": "ヤ",
        "yu": "ユ",
        "yo": "ヨ",
        "ra": "ラ",
        "ri": "リ",
        "ru": "ル",
        "re": "レ",
        "ro": "ロ",
        "wa": "ワ",
        "wo": "ヲ",
        "n": "ン",
    }

    def generate_kana_typst(title: str, grid: Mapping[str, str]) -> List[str]:
        res: List[str] = []
        res.append(f"#block(width: 100%, breakable: false)[")
        res.append(f"#heading(level: 2)[{title}]")
        res.append("#table(")
        res.append("  columns: (1fr, 1fr, 1fr, 1fr, 1fr),")
        res.append(f"  inset: {INSET},")
        res.append("  stroke: 0.2pt + luma(200),")
        res.append("  align: center,")
        for row_keys in kana_rows:
            for k in row_keys:
                if k and k in grid:
                    # show the kana and the romaji in the same text size
                    res.append(f'  [{grid[k]} #text(size: {TEXT_SIZE}, fill: rgb("#444444"))[{k}]],')
                else:
                    res.append("  [],")
        res.append(")")
        res.append("]")
        return res

    typst_lines.extend(generate_kana_typst("Hiragana (平假名)", hira_grid))
    # typst_lines.append("#v(1em)")
    typst_lines.extend(generate_kana_typst("Katakana (片假名)", kata_grid))

    return typst_lines


def write_typst_file(out_path: str, lines: Iterable[str]) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Successfully generated Typst source: {out_path}")


def find_typst_binary(provided: str | None = None) -> str | None:
    if provided:
        if shutil.which(provided) or os.path.isfile(provided):
            return provided
        return None
    # Try common name
    return shutil.which("typst")


def build_typst_command(typst_bin: str, typ_file: str, font_path: str | None, out_pdf: str | None) -> List[str]:
    # typst usage: `typst compile [OPTIONS] <INPUT> [OUTPUT]`
    cmd = [typst_bin, "compile"]
    if font_path:
        cmd.extend(["--font-path", font_path])
    # Input is positional; append the input file first.
    cmd.append(typ_file)
    # If an explicit output file was requested, pass it as the final positional argument
    # (do NOT use -o which some typst versions treat as an input value).
    if out_pdf:
        cmd.append(out_pdf)
    return cmd


def compile_typst(typst_bin: str, typ_file: str, font_path: str | None = None, out_pdf: str | None = None, timeout: int = TYPST_TIMEOUT_SEC) -> int:
    cmd = build_typst_command(typst_bin, typ_file, font_path, out_pdf)
    # For logging show the command in a way safe for printing
    printable = " ".join(shlex.quote(p) for p in cmd)
    print(f"Running: {printable}")
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        print(f"Error: typst binary not found at '{typst_bin}'.")
        return 2
    except subprocess.TimeoutExpired:
        print(f"Error: typst compile timed out after {timeout} seconds.")
        return 3

    # Print stdout/stderr to help debugging
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert Kaishi 1500 TSV to Typst and optionally compile to PDF.")
    p.add_argument("--tsv", "-i", default=DEFAULT_TSV, help="Input TSV file (default: kaishi-1500.tsv).")
    p.add_argument("--out", "-o", default=DEFAULT_TYP, help="Output Typst file (default: kaishi-1500.typ).")
    p.add_argument("--pdf", default=None, help="Output PDF filename when compiling (default: same basename as the .typ file).")
    p.add_argument("--compile", "-c", action="store_true", help="Run 'typst compile' after generating the Typst source.")
    p.add_argument("--typst-binary", default=None, help="Path to the 'typst' binary. If omitted, looks on PATH.")
    p.add_argument("--font-path", default="/Users/alan/Library/Fonts", help="Font path to pass to typst via --font-path (default: /Users/alan/Library/Fonts).")
    p.add_argument("--columns", type=int, default=COLUMNS, help="Number of page columns to use in Typst page layout (default: 2).")
    p.add_argument("--column-gap", default=COLUMN_GAP, help="Gap between columns (default: 0.25cm).")
    p.add_argument("--text-size", default=TEXT_SIZE, help="Base text size in Typst (default: 20pt).")
    p.add_argument("--margin", default=MARGIN, help="Page margin (default: 0.25cm).")
    p.add_argument("--timeout", type=int, default=TYPST_TIMEOUT_SEC, help=f"Timeout in seconds for typst compile (default: {TYPST_TIMEOUT_SEC}).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.pdf is None:
        args.pdf = os.path.splitext(args.out)[0] + ".pdf"

    try:
        data = read_tsv(args.tsv)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    typ_lines = generate_typst_content(
        data,
        fonts=FONTS,
        margin=args.margin,
        text_size=args.text_size,
        page_columns=args.columns,
        column_gap=args.column_gap,
    )
    write_typst_file(args.out, typ_lines)

    if args.compile:
        typst_bin = find_typst_binary(args.typst_binary)
        if not typst_bin:
            print("Error: 'typst' binary not found. Either install Typst or provide --typst-binary PATH.", file=sys.stderr)
            return 4

        rc = compile_typst(typst_bin, args.out, font_path=args.font_path, out_pdf=args.pdf, timeout=args.timeout)
        if rc != 0:
            print(f"Typst compile failed with exit code {rc}.", file=sys.stderr)
            return rc
        else:
            print(f"Successfully compiled PDF: {args.pdf}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
