"""Read exact-image applicability facts without changing scanner findings."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROGRAM = r'''
import importlib.util, json, os, pathlib, shutil, struct, subprocess, sys
import xml.parsers.expat
targets = {'strfmon','strfmon_l','ns_printrr','ns_printrrf','fp_nquery','gzwrite','gzprintf'}
imports, errors, seen = {}, [], set()
count = 0
for directory in ('/usr','/opt','/app'):
    for current, _, names in os.walk(directory, followlinks=False):
        for name in names:
            path = pathlib.Path(current)/name
            if path.is_symlink() or not path.is_file(): continue
            identity = (path.stat().st_dev, path.stat().st_ino)
            if identity in seen: continue
            seen.add(identity)
            with path.open('rb') as source:
                header = source.read(64)
                if header[:4] != b'\x7fELF': continue
                if header[4:6] != b'\x02\x01':
                    errors.append({'file':str(path),'error':'unsupported ELF class or endian'}); continue
                count += 1
                offset, = struct.unpack_from('<Q',header,40)
                width, number = struct.unpack_from('<HH',header,58)
                if not offset or not number: continue
                if width != 64 or number > 65535 or offset + number*width > path.stat().st_size:
                    errors.append({'file':str(path),'error':'invalid section bounds'}); continue
                source.seek(offset)
                sections = list(struct.iter_unpack('<IIQQQQIIQQ',source.read(number*width)))
                for section in sections:
                    if section[1] != 11: continue
                    link, entry_size = section[6], section[9]
                    if link >= len(sections) or entry_size != 24 or section[5] > 64*1024**2:
                        errors.append({'file':str(path),'error':'invalid symbol table'}); continue
                    strings = sections[link]
                    if strings[5] > 64*1024**2:
                        errors.append({'file':str(path),'error':'oversize string table'}); continue
                    source.seek(strings[4]); names_blob = source.read(strings[5])
                    source.seek(section[4]); symbols = source.read(section[5])
                    for symbol in struct.iter_unpack('<IBBHQQ',symbols):
                        if symbol[3] != 0: continue
                        start = symbol[0]; end = names_blob.find(b'\0',start)
                        name = names_blob[start:end].decode('utf-8','replace')
                        if name in targets: imports.setdefault(name,[]).append(str(path))
def optional(command):
    result = subprocess.run(command,capture_output=True,text=True,timeout=15)
    return result.stdout.strip() if result.returncode == 0 else None
packages = subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'],text=True)
permissions = {line.split(':')[0]:line.split(':',1)[1].strip() for line in pathlib.Path('/proc/self/status').read_text().splitlines()
               if line.startswith(('Uid:','CapEff:','NoNewPrivs:'))}
print(json.dumps({'python':sys.version.split()[0],'expat':xml.parsers.expat.EXPAT_VERSION,
    'debian_python':optional(['/usr/bin/python3','--version']) if pathlib.Path('/usr/bin/python3').exists() else None,
    'archive_tar':optional(['perl','-MArchive::Tar','-e','print $Archive::Tar::VERSION']) if shutil.which('perl') else None,
    'tools':{name:shutil.which(name) for name in ('cupsd','tiffcrop','infocmp','getfacl','setfacl','chacl','mount','nsenter')},
    'python_libxml2':importlib.util.find_spec('libxml2') is not None,'audit_process_permissions':permissions,
    'elf_files':count,'dynamic_imports':{name:sorted(set(imports.get(name,[]))) for name in sorted(targets)},
    'elf_errors':errors,'packages':dict(line.split('\t',1) for line in packages.splitlines())},indent=2))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    images = json.loads(args.images.read_text("utf-8"))
    if set(images) != {"core", "runtime", "worker"}:
        raise ValueError("Complete immutable image identities are required")
    result = {"schema": "mastermind.security-inventory.v1", "images": images, "components": {},
              "scope": "Applicability facts only; no scanner suppression or risk acceptance"}
    for name, identity in images.items():
        actual = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", identity], text=True).strip()
        if actual != identity:
            raise ValueError("Supply actual image config digests")
        output = subprocess.check_output(["docker", "run", "--rm", "-i", "--network", "none", "--read-only",
            "--user", "10001:10001", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--memory", "1g", "--cpus", "2", "--entrypoint", "python", identity, "-"], input=PROGRAM.encode(), timeout=180)
        result["components"][name] = json.loads(output)
        print("Collected exact-image facts: " + name, flush=True)
    result["probe_sha256"] = hashlib.sha256(PROGRAM.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
