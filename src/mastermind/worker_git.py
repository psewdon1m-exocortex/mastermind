"""Shallow clone profile. Run only in the restricted Git sandbox behind PublicProxy."""
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

from .crusher_access import public_url
from .extractors import SECRET_NAMES, archive_path


def main():
    directory, port = Path(sys.argv[1]), int(sys.argv[2])
    source = json.loads((directory / "git-plan.json").read_text("utf-8"))
    url = public_url(source["url"])
    if not 1 <= port <= 65535:
        raise ValueError("Invalid broker port")
    repository = directory / "repository"
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(directory), "TMPDIR": str(directory), "LANG": "C.UTF-8",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                   "GIT_LFS_SKIP_SMUDGE": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0"}
    command = ["git", "-c", "protocol.allow=never", "-c", "protocol.http.allow=always", "-c", "protocol.https.allow=always",
               "-c", "protocol.file.allow=never", "-c", "http.proxy=http://127.0.0.1:" + str(port),
               "-c", "http.followRedirects=false", "-c", "http.sslVerify=true", "-c", "core.hooksPath=/dev/null",
               "-c", "credential.helper=", "-c", "filter.lfs.required=false", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=",
               "clone", "--depth=1", "--no-tags", "--single-branch", "--", url, str(repository)]
    subprocess.run(command, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=850)
    seen, files, total = {}, [], 0
    for root, directories, names in os.walk(repository, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        for name in directories + names:
            path = Path(root) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                raise ValueError("Repository contains special entries")
            relative = path.relative_to(repository).as_posix()
            archive_path(relative, seen, directory=path.is_dir())
            if len(seen) > 10_000:
                raise ValueError("Repository entry count exceeds its limit")
            if path.is_file():
                total += info.st_size
                if total > 8*1024**3 or info.st_size > 2*1024**3:
                    raise ValueError("Repository expansion exceeds its limit")
                if not SECRET_NAMES.search(relative):
                    files.append((relative, path))
    with zipfile.ZipFile(directory / "source.receiving", "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, path in sorted(files):
            archive.write(path, relative)
            if archive.fp.tell() > 2*1024**3:
                raise ValueError("Repository source archive exceeds its limit")


if __name__ == "__main__":
    main()
