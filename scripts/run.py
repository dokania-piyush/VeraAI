"""Start one local/server worker with a minimal, non-executing .env loader."""
import argparse
import os
from pathlib import Path
import re
import uvicorn


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line=line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'{path}:{number}: expected KEY=value')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',key):
            raise ValueError(f'{path}:{number}: invalid environment key')
        if value[:1] in {'"', "'"}:
            if len(value)<2 or value[-1] != value[0]:
                raise ValueError(f'{path}:{number}: unmatched quotation mark')
            value=value[1:-1]
        # No shell expansion, command substitution, interpolation or inline comments.
        os.environ.setdefault(key,value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env',type=Path,default=Path('.env'))
    p.add_argument('--host',default=os.getenv('HOST','127.0.0.1'))
    p.add_argument('--port',type=int,default=None)
    args=p.parse_args();load_env(args.env)
    port=args.port if args.port is not None else int(os.getenv('PORT','8080'))
    uvicorn.run('bot:app',host=args.host,port=port,workers=1,access_log=False,log_level='info')

if __name__=='__main__':main()
