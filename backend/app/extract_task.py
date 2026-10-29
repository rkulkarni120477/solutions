"""Isolated, bounded document parser. Binary input, JSON output, no shell."""
import json
import sys
if sys.platform != 'win32':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
from .context import extract
from .config import settings

try:
    data = sys.stdin.buffer.read(settings.upload_max_mb * 1024 * 1024 + 1)
    passages, warning = extract(sys.argv[1], data)
    print(json.dumps({'passages': passages, 'warning': warning}))
except ValueError as exc:
    print(json.dumps({'error': str(exc)}))
    sys.exit(1)
except Exception:
    print(json.dumps({'error': 'Extraction failed. Check file validity or optional OCR installation.'}))
    sys.exit(1)
