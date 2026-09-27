"""Package the source tree without secrets, databases, caches or virtualenvs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

EXCLUDED_DIRS={'.git','.venv','venv','data','expanded','__pycache__','.pytest_cache','htmlcov','build','dist','.ruff_cache'}


def files(root: Path):
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink():continue
        rel=p.relative_to(root)
        if any(part in EXCLUDED_DIRS or part.endswith('.egg-info') for part in rel.parts):continue
        if p.name.startswith('.env') and p.name!='.env.example':continue
        if p.name in {'.coverage','.DS_Store'} or p.suffix in {'.pyc','.pyo','.zip','.sqlite3','.db'} or '.sqlite3-' in p.name:continue
        yield p


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('../vera-compass-codebase.zip'))
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    out=a.out.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    members=list(files(root))
    manifest=[{'path':f.relative_to(root).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in members]
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for f in members:archive.write(f,'vera-compass/'+f.relative_to(root).as_posix())
        archive.writestr('vera-compass/RELEASE_MANIFEST.json',json.dumps({'files':manifest,'note':'Manifest covers packaged source/doc/report files; not itself.'},indent=2))
    print(json.dumps({'archive':str(out),'files':len(members)+1,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':main()
