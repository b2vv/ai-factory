#!/bin/sh
set -eu
umask 077
phase=$1
case "$phase" in online|offline) ;; *) exit 78;; esac
unset ENV BASH_ENV SEMGREP_APP_TOKEN
export HOME=/work/home OPAMROOT=/work/opam
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
export SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0
export SEMGREP_GIT_COMMIT=72d3525fe7e02f486428386078f192f8c4756804
export OPAMJOBS=4 MAKEFLAGS=-j4 CARGO_BUILD_JOBS=4
# No build state from the online container is permitted here.
test "$(uname -m)" = x86_64
test ! -e /work/home
mkdir /work/home /work/source /work/evidence /work/apk
stage() {
  current_stage=$1
  printf 'AF03_STAGE phase=%s stage=%s\n' "$phase" "$current_stage"
  printf 'phase=%s stage=%s\n' "$phase" "$current_stage" > /work/evidence/stage.txt
}
trap 'rc=$?; printf "AF03_EXIT phase=%s stage=%s exit=%s\n" "$phase" "${current_stage:-setup}" "$rc" >&2' 0
stage setup
printf '%s  %s\n' be58ce9c2b00934cb5907f09483c6848b3777006154c30f62b1d0db624ce4f3e /input/source.tar.gz | sha256sum -c -
tar -xzf /input/source.tar.gz -C /work/source
cd /work/source/semgrep-72d3525fe7e02f486428386078f192f8c4756804
# APK installs may execute vendor scripts. No capability relaxation on failure.
apks='bash build-base git make rsync opam curl python3 py3-setuptools py3-pip git-lfs openssh jq pkgconf openssl-dev openssl-libs-static zlib-static pcre2-static gmp-static zstd-static xz-static bzip2-static libunwind-static'
if [ "$phase" = online ]; then
  mkdir /capture/apk /capture/git /capture/python-wheels /capture/curl
  ln -s /capture/apk /etc/apk/cache
  apk --cache-dir /capture/apk --update-cache add $apks
else
  cp -R /capture/apk/. /work/apk/
  ln -s /work/apk /etc/apk/cache
  apk --no-network --cache-dir /work/apk add $apks
fi
stage tar-preflight-start
/bin/sh /input/tar-preflight.sh > /work/evidence/tar-preflight.txt
cat /work/evidence/tar-preflight.txt
stage tar-preflight-complete
# Every named fork is a commit-qualified public source; no Semgrep PyPI engine.
while IFS= read -r spec; do
  url=${spec%#*}; rev=${spec##*#}; dest=/capture/git/$rev
  if [ "$phase" = online ]; then
    git init --bare "$dest"
    git -C "$dest" fetch --depth=1 "$url" "$rev"
    test "$(git -C "$dest" rev-parse FETCH_HEAD)" = "$rev"
    git -C "$dest" update-ref refs/heads/pinned "$rev"
    git -C "$dest" symbolic-ref HEAD refs/heads/pinned
  fi
  git config --global url."file://$dest".insteadOf "$url"
done < /input/git-pins.txt
git config --global protocol.file.allow always
if [ "$phase" = online ]; then
  git init /capture/opam-repository
  git -C /capture/opam-repository fetch --depth=1 https://github.com/ocaml/opam-repository.git 78d29aba187e8362b8ab86c189790c0af9153d4b
  git -C /capture/opam-repository checkout --detach FETCH_HEAD
  test "$(git -C /capture/opam-repository rev-parse HEAD)" = 78d29aba187e8362b8ab86c189790c0af9153d4b
  curl --fail --location --max-time 120 --output /capture/curl/curl-8.5.0.tar.gz https://curl.se/download/curl-8.5.0.tar.gz
fi
printf '%s  %s\n' 05fc17ff25b793a437a0906e0484b82172a9f4de02be5ed447e0cab8c3475add /capture/curl/curl-8.5.0.tar.gz | sha256sum -c -
mkdir /work/shims
cp /input/curl-shim /work/shims/curl
chmod 500 /work/shims/curl
export PATH=/work/shims:$PATH
# Reused repository snapshot only, no installed switch/build tree copied.
opam init --bare --yes --disable-sandboxing default /capture/opam-repository
if [ "$phase" = offline ]; then
  mkdir -p "$OPAMROOT/download-cache"
  cp -R /capture/opam-download-cache/. "$OPAMROOT/download-cache/"
fi
stage switch-start
make switch
stage switch-complete
# Exact local helper patch only; no ownership capability or global tar setting.
stage curl-patch-start
python3 /input/fix_curl.py "$PWD" > /work/evidence/curl-recipe-patch.json
stage curl-patch-complete
stage install-deps-start
make install-deps
stage install-deps-complete
stage core-start
opam exec -- make install-pyro-caml
opam exec -- make core
if [ ! -e bin ] && [ ! -L bin ]; then ln -s _build/install/default/bin bin; fi
./scripts/validate-compiler-sha.sh bin/semgrep-core
./bin/semgrep-core -ocaml_version > /work/evidence/compiler.txt
grep -F '+semgrep-fork@4046c817ed2ed5c2431300902d1bd306230bf3dd' /work/evidence/compiler.txt
cp _build/default/src/main/Main.exe cli/src/semgrep/bin/semgrep-core
stage core-complete
stage cli-start
python3 -m venv /work/venv
if [ "$phase" = offline ]; then
  export PIP_NO_INDEX=1 PIP_FIND_LINKS=/capture/python-wheels
fi
/work/venv/bin/python -m pip install ./cli
if [ "$phase" = online ]; then
  cp -R "$OPAMROOT/download-cache" /capture/opam-download-cache
  # Installed third-party distributions only: do not fetch an official Semgrep wheel.
  /work/venv/bin/python -c 'import importlib.metadata as m; print("\n".join(sorted(d.metadata["Name"]+"=="+d.version for d in m.distributions() if d.metadata["Name"].lower() != "semgrep")))' > /capture/python-requirements.txt
  /work/venv/bin/python -m pip wheel --wheel-dir /capture/python-wheels -r /capture/python-requirements.txt
  /work/venv/bin/python -m pip wheel --wheel-dir /capture/python-wheels setuptools wheel
fi
stage cli-complete
mkdir /work/ce-bin
cp _build/default/src/main/Main.exe /work/ce-bin/semgrep-core
ln -s semgrep-core /work/ce-bin/osemgrep
export PATH=/work/ce-bin:/work/venv/bin:$PATH
semgrep --version > /work/evidence/semgrep-version.txt
opam list --installed --columns=name,version > /work/evidence/opam-installed.txt
/work/venv/bin/python -m pip inspect > /work/evidence/pip-inspect.json
apk info -vv > /work/evidence/apk-installed.txt
# Data only; installed distribution metadata includes license declarations, not clearance.
/work/venv/bin/python /input/ledger.py "$phase"
stage phase-complete
printf '%s\n' "$phase CE prototype complete; no final OCI image or scanner acceptance"
