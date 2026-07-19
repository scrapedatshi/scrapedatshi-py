"""
scrapedatshi CLI — project scaffolding tool.

Usage:
    scrapedatshi init [project-name]
"""

from __future__ import annotations

import os
import sys
import textwrap

from scrapedatshi._templates import (
    ENV_TEMPLATE,
    GITIGNORE_TEMPLATE,
    README_TEMPLATE,
    EXAMPLES,
)

# ── CLI implementation ────────────────────────────────────────────────────────


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def cmd_init(args: list[str]) -> None:
    project_name = args[0] if args else "scrapedatshi-project"
    target = os.path.abspath(project_name)

    if os.path.exists(target):
        print(f"Error: '{project_name}' already exists.", file=sys.stderr)
        sys.exit(1)

    print(f"\n🚀 Creating scrapedatshi project: {project_name}/\n")

    # Prompt for API key
    api_key = ""
    try:
        api_key = input(
            "Enter your scrapedatshi API key (press Enter to skip): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        pass

    # Write .env
    env_content = ENV_TEMPLATE
    if api_key:
        env_content = env_content.replace(
            "SCRAPEDATSHI_API_KEY=sds_...", f"SCRAPEDATSHI_API_KEY={api_key}"
        )
    _write_file(os.path.join(target, ".env"), env_content)

    # Write .gitignore
    _write_file(os.path.join(target, ".gitignore"), GITIGNORE_TEMPLATE)

    # Write README
    _write_file(os.path.join(target, "README.md"), README_TEMPLATE)

    # Write example scripts
    examples_dir = os.path.join(target, "examples")
    for filename, content in EXAMPLES.items():
        _write_file(os.path.join(examples_dir, filename), content)

    # Summary
    files_written = 3 + len(EXAMPLES)  # .env + .gitignore + README + examples
    print(f"  ✓ .env")
    print(f"  ✓ .gitignore")
    print(f"  ✓ README.md")
    for filename in EXAMPLES:
        print(f"  ✓ examples/{filename}")

    print(f"\n✅ Project created ({files_written} files)\n")
    print(textwrap.dedent(f"""\
        Next steps:
          1. cd {project_name}
          2. Edit .env — add your API keys
          3. python examples/00_discover_providers.py
          4. python examples/01_scrape_url.py

        Docs: https://scrapedatshi.com/dev
    """))


def main() -> None:
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(textwrap.dedent("""\
            scrapedatshi CLI

            Commands:
              init [project-name]   Create a new scrapedatshi sandbox project
                                    (default name: scrapedatshi-project)

            Examples:
              scrapedatshi init
              scrapedatshi init my-rag-project
        """))
        return

    command = argv[0]
    rest = argv[1:]

    if command == "init":
        cmd_init(rest)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Run `scrapedatshi --help` for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
