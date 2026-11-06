#!/usr/bin/env python3
"""
Convert Markdown to PDF using md-to-pdf (npx).
Usage: python3 md_to_pdf.py input.md [output.pdf]
"""

import sys
import subprocess
from pathlib import Path


def convert_md_to_pdf(input_path: str, output_path: str = None):
    """Convert markdown file to PDF using md-to-pdf."""

    input_file = Path(input_path)

    if not input_file.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    # Determine output path
    if output_path is None:
        output_file = input_file.with_suffix('.pdf')
    else:
        output_file = Path(output_path)

    # Run md-to-pdf via npx
    try:
        result = subprocess.run(
            ['npx', 'md-to-pdf', str(input_file)],
            cwd=input_file.parent,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            sys.exit(1)

        # md-to-pdf creates file with same name but .pdf extension
        created_pdf = input_file.with_suffix('.pdf')

        # Rename if different output path requested
        if output_file != created_pdf and created_pdf.exists():
            created_pdf.rename(output_file)

        print(f"✓ Created PDF: {output_file}")
        return str(output_file)

    except FileNotFoundError:
        print("Error: npx not found. Please install Node.js.")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 md_to_pdf.py input.md [output.pdf]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    convert_md_to_pdf(input_path, output_path)


if __name__ == "__main__":
    main()
