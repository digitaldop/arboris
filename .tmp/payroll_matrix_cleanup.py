import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'diff', '--name-only', '--', '*.pyc'], cwd=root, text=True).splitlines()
for relative in files:
    target = (root / relative).resolve()
    assert target.is_relative_to(root) and target.suffix == '.pyc'
    # These tracked build artifacts were all clean before the test run.
    target.write_bytes(subprocess.check_output(['git', 'show', f'HEAD:{relative}'], cwd=root))
relative = 'gestione_amministrativa/models.py'
target = root / relative
original = subprocess.check_output(['git', 'show', f'HEAD:{relative}'], cwd=root)
assert target.read_bytes().replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n')
target.write_bytes(original)
print(f'Restored {len(files)} generated cache files; model unchanged.')
