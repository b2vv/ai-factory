"""Authored fixture data only; no extraction, upstream sources or commands."""
import gzip,io,tarfile
from pathlib import Path
PAYLOAD=b'AF03 ownership-neutral option fixture\n'
def fixture():
 raw=io.BytesIO()
 with tarfile.open(fileobj=raw,mode='w',format=tarfile.USTAR_FORMAT) as archive:
  member=tarfile.TarInfo('authored.txt');member.uid=12345;member.gid=23456
  member.mode=0o600;member.mtime=0;member.size=len(PAYLOAD)
  archive.addfile(member,io.BytesIO(PAYLOAD))
 return gzip.compress(raw.getvalue(),mtime=0)
if __name__=='__main__':
 import sys
 with Path(sys.argv[1]).open('xb') as out:out.write(fixture())
