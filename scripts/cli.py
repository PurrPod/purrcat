"""PurrCat CLI - Backward compatibility shim"""

import sys
import os

if __name__ == "__main__":
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    from scripts.cli.main import main

    main()
