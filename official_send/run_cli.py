from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    package_parent = Path(__file__).resolve().parent.parent
    if str(package_parent) not in sys.path:
        sys.path.insert(0, str(package_parent))

    from official_send.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

