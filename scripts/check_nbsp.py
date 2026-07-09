#!/usr/bin/env python3
"""
check_nbsp.py — detects non-breaking spaces (U+00A0) and other invisible
whitespace characters that look identical to normal spaces in most editors
but break Python's indentation parser.

WHY THIS EXISTS, SPECIFICALLY: Black and Flake8 do NOT catch this by
default. Black's tokenizer generally accepts \xa0 as part of a string or
even silently inside whitespace in some editor/terminal copy-paste paths
without raising during formatting, and Flake8's default checks (E1xx/W1xx)
target tabs-vs-spaces consistency, not non-ASCII whitespace specifically.
A generic "add a linter" recommendation would not have caught the bug
that caused storage.py's NameError — this script exists because the
generic tools genuinely don't cover this specific case.

Exit code 0 = clean. Exit code 1 = at least one bad character found,
with file/line/column reported so it can be fixed in seconds instead of
debugged from a cryptic runtime NameError in a container log.
"""
import sys

# Characters that render as whitespace but are NOT the ASCII space (0x20)
# or tab (0x09) Python's tokenizer expects for indentation.
SUSPICIOUS_WHITESPACE = {
    "\xa0": "NO-BREAK SPACE (U+00A0) — the exact character that broke storage.py",
    "\u2000": "EN QUAD (U+2000)",
    "\u2001": "EM QUAD (U+2001)",
    "\u2002": "EN SPACE (U+2002)",
    "\u2003": "EM SPACE (U+2003)",
    "\u200b": "ZERO WIDTH SPACE (U+200B)",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE / BOM (U+FEFF)",
}


def check_file(path: str) -> list[str]:
    problems = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError) as exc:
        return [f"{path}: could not read file ({exc})"]

    for lineno, line in enumerate(lines, start=1):
        for col, char in enumerate(line, start=1):
            if char in SUSPICIOUS_WHITESPACE:
                problems.append(
                    f"{path}:{lineno}:{col}: {SUSPICIOUS_WHITESPACE[char]}"
                )
    return problems


def main(argv: list[str]) -> int:
    files = argv[1:]
    if not files:
        print("Usage: check_nbsp.py <file.py> [file2.py ...]", file=sys.stderr)
        return 1

    all_problems = []
    for path in files:
        if not path.endswith(".py"):
            continue
        all_problems.extend(check_file(path))

    if all_problems:
        print("Invisible whitespace characters found — these break Python's", file=sys.stderr)
        print("indentation parser while looking completely normal in your editor:\n", file=sys.stderr)
        for problem in all_problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nFix: retype the offending indentation by hand, or run "
            "`sed -i 's/\\xc2\\xa0/ /g' <file>` to replace with real spaces.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
