"""
app.py and worker.py both do `sys.path.append("/app/common")` — correct
inside their containers, meaningless when running pytest locally. This
conftest adds the real local paths to the same three source directories
so `import app`, `import worker`, `import jobstate`, `import storage`,
and `import metrics` all resolve correctly outside Docker too.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

for path in (
    os.path.join(ROOT, "common"),
    os.path.join(ROOT, "services", "api"),
    os.path.join(ROOT, "services", "worker"),
):
    if path not in sys.path:
        sys.path.insert(0, path)
