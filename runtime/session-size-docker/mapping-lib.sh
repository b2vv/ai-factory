# Local, trusted shell functions; never source a mapping or payload.
canonical() {
 case "$1" in /*) ;;*) return 1;;esac
 case "$1" in *','*|*'|'*) return 1;;esac
 printf '%s' "$1" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null && return 1
 q=$1;while [ "$q" != / ];do [ ! -L "$q" ] || return 1;q=${q%/*};[ -n "$q" ] || q=/;done
 [ "$(CDPATH= cd -- "$1" && pwd -P)" = "$1" ]
}
metadata() {
 case $(uname -s) in Darwin) stat -f '%u %Lp %l' "$1";;Linux) stat -c '%u %a %h' "$1";;*) return 1;;esac
}
private_dir() { canonical "$1" && [ -d "$1" ] && [ "$(metadata "$1" | cut -d ' ' -f 1,2)" = "$(id -u) 700" ]; }
private_file() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(metadata "$1")" = "$(id -u) 600 1" ]; }
clean_text() { [ -n "$1" ] && [ "${#1}" -le 256 ] && ! printf '%s' "$1" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null; }
hash_key() { if command -v shasum >/dev/null 2>&1;then shasum -a 256;else sha256sum;fi; }
