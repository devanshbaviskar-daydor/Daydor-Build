"""Regenerate src/daydor_api/enums/provisional.json by scanning the backend.

    python scripts/gen_enums.py [path/to/daydor-backend]
"""
import sys
from pathlib import Path

import daydor
from daydor_api import enum_scan

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(daydor.__file__).resolve().parents[2]
pkg = Path(enum_scan.__file__).parent
result = enum_scan.write(root, pkg / "enums" / "provisional.json", pkg / "enums" / "overrides.json")
print(f"{len(result['enums'])} of {result['enum_column_count']} enum columns have discovered values")
