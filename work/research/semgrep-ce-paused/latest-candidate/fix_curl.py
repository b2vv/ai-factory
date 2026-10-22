"""One hash-bound recipe edit inside the disposable source tree only."""
import hashlib,os,stat,sys
from pathlib import Path
BEFORE='a312ca84e211dc41b241d039b676135df42ec21ecfa88e1f145047516115e334'
AFTER='0d3e8a1c8d7fb35ca2f4792f2c809081b42f6b7546f40af90b9eead5ff442b67'
OLD=b'    tar xz < "curl-${CURL_VERSION}.tar.gz"\n'
NEW=b'    tar --no-same-owner -xz < "curl-${CURL_VERSION}.tar.gz"\n'
def transform(raw):
 if hashlib.sha256(raw).hexdigest()!=BEFORE or raw.count(OLD)!=1:raise ValueError('curl helper baseline mismatch')
 result=raw.replace(OLD,NEW)
 if hashlib.sha256(result).hexdigest()!=AFTER:raise ValueError('curl helper after mismatch')
 return result
def apply(root):
 root=Path(root);target=root/'scripts/build-static-libcurl.sh'
 for p in [target,*target.parents]:
  if p.is_symlink():raise ValueError('symlink path rejected')
 fd=os.open(target,os.O_RDWR|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>16384:raise ValueError('unexpected helper type/size')
  with os.fdopen(fd,'r+b',closefd=False) as f:
   raw=f.read(16385);result=transform(raw)
   f.seek(0)
   if f.read(16385)!=raw:raise ValueError('helper drift')
   f.seek(0);f.write(result);f.truncate();f.flush();os.fsync(fd);f.seek(0)
   if hashlib.sha256(f.read(16385)).hexdigest()!=AFTER:raise ValueError('helper write mismatch')
 finally:os.close(fd)
 return {'path':'scripts/build-static-libcurl.sh','before_sha256':BEFORE,'after_sha256':AFTER,'change':'curl extraction only: --no-same-owner','global_tar_options':False}
if __name__=='__main__':
 import json
 print(json.dumps(apply(Path(sys.argv[1]))))
