"""Qualification-only host-name fixture, reapplied after Docker regenerates /etc/hosts."""
import socket
from pathlib import Path

assert socket.gethostname() == 'mastermind-qualification-host'
path=Path('/etc/hosts')
owned={'github.com','api.github.com','mastermind.qualification.test','kernel.mastermind.test','volt.mastermind.test','saturn.mastermind.test','chronos.mastermind.test','registry.mastermind.test'}
lines=[]
for line in path.read_text().splitlines():
    parts=line.split()
    if not parts or line.lstrip().startswith('#'):
        lines.append(line)
    else:
        names=[name for name in parts[1:] if name not in owned]
        if names: lines.append(parts[0]+'\t'+' '.join(names))
lines += ['127.0.0.1 github.com api.github.com mastermind.qualification.test',
          '172.31.0.2 kernel.mastermind.test volt.mastermind.test chronos.mastermind.test',
          '172.31.0.5 saturn.mastermind.test','172.31.0.3 registry.mastermind.test']
path.write_text('\n'.join(lines)+'\n')
