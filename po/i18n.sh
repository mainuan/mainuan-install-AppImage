#!/usr/bin/env bash
# Mainuan i18n maintenance — one copy per repository, configured by i18n.conf
# next to this script.  Requires only GNU gettext and python3 (stdlib).
#
#   po/i18n.sh extract     regenerate the POT from POTFILES.in (idempotent)
#   po/i18n.sh update      merge the POT into every catalog listed in LINGUAS
#   po/i18n.sh add <lang>  create a new catalog with the verified Plural-Forms
#   po/i18n.sh validate    msgfmt --check + placeholder/markup checks (CI gate)
#   po/i18n.sh check-pot   fail if the committed POT is out of date (CI gate)
#   po/i18n.sh coverage    per-language statistics (--json for machines)
#   po/i18n.sh compile DIR build DIR/<lang>/LC_MESSAGES/<domain>.mo
#
# Source strings are English; the Portuguese interface lives in pt_BR.po.
set -euo pipefail

PODIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$PODIR/.." && pwd)
# shellcheck source=/dev/null
. "$PODIR/i18n.conf"

: "${DOMAIN:?i18n.conf must set DOMAIN}"
: "${PACKAGE_NAME:=$DOMAIN}"
: "${PACKAGE_VERSION:=}"
: "${BUGS_ADDRESS:=https://github.com/mainuan}"
: "${POT:=$PODIR/$DOMAIN.pot}"
: "${PO_NAME:=%s.po}"            # printf pattern, %s = language code
: "${POTFILES:=$PODIR/POTFILES.in}"
: "${LINGUAS_FILE:=$PODIR/LINGUAS}"
: "${COPYRIGHT_HOLDER:=Mainuan}"
# Keywords per xgettext language; override in i18n.conf when needed.
: "${KEYWORDS_C:=--keyword=i18n:1 --keyword=i18nc:1c,2 --keyword=i18np:1,2 --keyword=i18ncp:1c,2,3 --keyword=ki18n:1 --keyword=ki18nc:1c,2 --keyword=ki18np:1,2 --keyword=ki18ncp:1c,2,3 --keyword=kli18n:1 --keyword=kli18nc:1c,2 --keyword=tr2i18n:1 --keyword=tr2i18n:1,2c}"
: "${KEYWORDS_PYTHON:=--keyword=_ --keyword=N_ --keyword=ngettext:1,2 --keyword=pgettext:1c,2 --keyword=npgettext:1c,2,3}"
: "${KEYWORDS_JAVASCRIPT:=$KEYWORDS_C --keyword=qsTr:1 --keyword=qsTranslate:2 --keyword=QT_TR_NOOP:1}"
: "${KEYWORDS_SHELL:=--keyword=gettext --keyword=eval_gettext --keyword=ngettext:1,2 --keyword=eval_ngettext:1,2}"

po_path() { printf "%s/$PO_NAME" "$PODIR" "$1"; }
linguas() { [ -f "$LINGUAS_FILE" ] && grep -vE '^\s*(#|$)' "$LINGUAS_FILE" | tr ' ' '\n' | grep -v '^$' || true; }

# Plural-Forms verified from installed catalogs (KDE ki18n6.mo; GTK/Xfce for
# ur, blueman for sw) — see docs/data/plural-forms.tsv. Never from memory.
plural_forms() {
  case "$1" in
    pt_BR|fr|tr|fa)                 echo 'nplurals=2; plural=(n > 1);' ;;
    zh_CN|zh_TW|zh_HK|ja|ko|vi|th)  echo 'nplurals=1; plural=0;' ;;
    ru|uk) echo 'nplurals=4; plural=n==1 ? 3 : n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2;' ;;
    pl)    echo 'nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);' ;;
    cs)    echo 'nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;' ;;
    ro)    echo 'nplurals=3; plural=n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2;' ;;
    ar)    echo 'nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;' ;;
    he)    echo 'nplurals=4; plural=(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3));' ;;
    es|pt|de|it|hi|bn|id|nl|el|hu|sv|fi|da|nb|ur|sw|en_GB) echo 'nplurals=2; plural=(n != 1);' ;;
    *) echo "i18n.sh: no verified Plural-Forms for '$1'; take it from an installed KDE catalog:" >&2
       echo "  msgunfmt /usr/share/locale/$1/LC_MESSAGES/ki18n6.mo | grep -m1 Plural-Forms" >&2
       return 1 ;;
  esac
}

lang_name() {  # Language-Team label only
  case "$1" in
    pt_BR) echo "Brazilian Portuguese";; pt) echo "Portuguese";; es) echo "Spanish";;
    fr) echo "French";; de) echo "German";; it) echo "Italian";; zh_CN) echo "Chinese (Simplified)";;
    zh_TW) echo "Chinese (Traditional)";; ja) echo "Japanese";; ko) echo "Korean";; ru) echo "Russian";;
    hi) echo "Hindi";; ar) echo "Arabic";; bn) echo "Bengali";; *) echo "$1";;
  esac
}

xgettext_group() {  # $1 language, $2 output, rest: files
  local lang=$1 out=$2; shift 2
  local kw=()
  case "$lang" in
    C++|C)       read -r -a kw <<<"$KEYWORDS_C --kde" ;;
    Python)      read -r -a kw <<<"$KEYWORDS_PYTHON" ;;
    JavaScript)  read -r -a kw <<<"$KEYWORDS_JAVASCRIPT" ;;
    Shell)       read -r -a kw <<<"$KEYWORDS_SHELL" ;;
    *)           kw=() ;;   # Desktop, Glade, ITS-based XML: no keywords
  esac
  local langarg=()
  case "$lang" in auto) ;; ITS) ;; *) langarg=(--language="$lang") ;; esac
  # xgettext honours only the last --add-comments tag, so extract once per tag
  # (GNU "Translators:" and KDE "i18n:"); --join-existing unions the notes.
  local tag join=()
  rm -f "$out"
  for tag in ${COMMENT_TAGS:-Translators: i18n:}; do
    (cd "$ROOT" && xgettext --from-code=UTF-8 --add-comments="$tag" "${join[@]}" \
        --sort-by-file --package-name="$PACKAGE_NAME" ${PACKAGE_VERSION:+--package-version="$PACKAGE_VERSION"} \
        --msgid-bugs-address="$BUGS_ADDRESS" --copyright-holder="$COPYRIGHT_HOLDER" \
        "${langarg[@]}" "${kw[@]}" -o "$out" "$@")
    [ -f "$out" ] && join=(--join-existing)
  done
  [ -f "$out" ] && sed -i 's/charset=CHARSET/charset=UTF-8/' "$out"
  # QML strings (qsTr/i18n) use Qt/KDE %1 placeholders, not JavaScript printf
  # formats; xgettext's heuristic javascript-format flag would make msgfmt
  # reject correct translations such as "%1 %" (fr/de). Placeholders are
  # still checked by "validate".
  if [ -f "$out" ] && [ "$lang" = JavaScript ]; then
    sed -i -e '/^#, javascript-format$/d' -e 's/^\(#,.*\), javascript-format/\1/' -e 's/^#, javascript-format, /#, /' "$out"
  fi
  return 0
}

cmd_extract() {
  # POTFILES.in: one path per line, optionally prefixed with [Language]
  # ([C++] [Python] [JavaScript] [Shell] [Desktop] [ITS]); default: by extension.
  local tmp; tmp=$(mktemp -d)
  declare -A groups=()
  local line lang file
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%%#*}; line=$(echo "$line" | xargs); [ -z "$line" ] && continue
    if [[ $line =~ ^\[([A-Za-z+]+)\][[:space:]]+(.+)$ ]]; then lang=${BASH_REMATCH[1]}; file=${BASH_REMATCH[2]}
    else
      file=$line
      case "$file" in
        *.cpp|*.h|*.hpp|*.cc) lang=C++;; *.py) lang=Python;; *.qml|*.js) lang=JavaScript;;
        *.sh) lang=Shell;; *.desktop|*.desktop.in) lang=Desktop;; *.ui) lang=Glade;; *) lang=ITS;;
      esac
    fi
    [ -f "$ROOT/$file" ] || { echo "i18n.sh: POTFILES entry missing: $file" >&2; exit 1; }
    groups[$lang]+="$file"$'\n'
  done < "$POTFILES"
  local parts=() n=0
  for lang in "${!groups[@]}"; do
    n=$((n+1)); local out="$tmp/part$n.pot"
    mapfile -t files < <(printf '%s' "${groups[$lang]}")
    if [ "$lang" = Glade ]; then
      # Qt Designer .ui: <string> elements; notr="true" ones are skipped,
      # including items of a <stringlist notr="true">. comment= becomes msgctxt
      # (uic -tr tr2i18n passes it to i18nc), extracomment= a "#." note.
      python3 - "$out" "$ROOT" "${files[@]}" <<'PY'
import sys, xml.etree.ElementTree as ET
out, root, files = sys.argv[1], sys.argv[2], sys.argv[3:]
seen, notes = {}, {}
def esc(s): return s.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
for f in files:
    tree = ET.parse(f"{root}/{f}")
    skip = set()
    for lst in tree.iter('stringlist'):
        if lst.get('notr') == 'true': skip.update(id(c) for c in lst.iter('string'))
    for el in tree.iter('string'):
        if id(el) in skip or el.get('notr') == 'true' or not (el.text or '').strip(): continue
        key = (el.get('comment') or None, el.text)
        seen.setdefault(key, []).append(f)
        if el.get('extracomment'): notes.setdefault(key, set()).add(el.get('extracomment'))
with open(out, 'w', encoding='utf-8') as fh:
    fh.write('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n')
    for (ctx, s), where in seen.items():
        fh.write(''.join(f"#. {n}\n" for n in sorted(notes.get((ctx, s), ()))))
        fh.write(''.join(f"#: {w}\n" for w in sorted(set(where))))
        if ctx: fh.write(f'msgctxt "{esc(ctx)}"\n')
        fh.write(f'msgid "{esc(s)}"\nmsgstr ""\n\n')
PY
    else
      xgettext_group "$lang" "$out" "${files[@]}"
    fi
    [ -f "$out" ] && parts+=("$out")
  done
  [ ${#parts[@]} -gt 0 ] || { echo "i18n.sh: nothing extracted" >&2; exit 1; }
  # Combine; first part provides the header (xgettext header, charset UTF-8).
  xgettext --from-code=UTF-8 --sort-by-file --package-name="$PACKAGE_NAME" \
    ${PACKAGE_VERSION:+--package-version="$PACKAGE_VERSION"} --msgid-bugs-address="$BUGS_ADDRESS" \
    --copyright-holder="$COPYRIGHT_HOLDER" --language=PO -o "$tmp/new.pot" "${parts[@]}" 2>/dev/null \
    || msgcat --use-first -o "$tmp/new.pot" "${parts[@]}"
  sed -i 's/charset=CHARSET/charset=UTF-8/' "$tmp/new.pot"
  if [ -f "$POT" ] && diff -q <(grep -v '^"POT-Creation-Date:' "$POT") <(grep -v '^"POT-Creation-Date:' "$tmp/new.pot") >/dev/null; then
    echo "POT unchanged: ${POT#"$ROOT"/}"
  else
    cp "$tmp/new.pot" "$POT"
    echo "POT updated: ${POT#"$ROOT"/} ($(grep -c '^msgid ' "$POT") entries incl. header)"
  fi
  rm -rf "$tmp"
}

cmd_check_pot() {
  local saved; saved=$(mktemp); cp "$POT" "$saved"
  cmd_extract >/dev/null
  if ! diff -q <(grep -v '^"POT-Creation-Date:' "$saved") <(grep -v '^"POT-Creation-Date:' "$POT") >/dev/null; then
    diff -u <(grep -v '^"POT-Creation-Date:' "$saved") <(grep -v '^"POT-Creation-Date:' "$POT") | head -40 >&2
    cp "$saved" "$POT"; rm -f "$saved"
    echo "i18n.sh: POT is out of date — run po/i18n.sh extract && po/i18n.sh update" >&2; exit 1
  fi
  cp "$saved" "$POT"; rm -f "$saved"; echo "POT is up to date"
}

cmd_add() {
  local lang=${1:?usage: i18n.sh add <lang>} po; po=$(po_path "$lang")
  [ -e "$po" ] && { echo "exists: $po" >&2; exit 1; }
  local pf; pf=$(plural_forms "$lang")
  msginit --no-translator --no-wrap --locale="$lang.UTF-8" -i "$POT" -o "$po" >/dev/null 2>&1
  PF="$pf" LT="$(lang_name "$lang")" LG="$lang" python3 - "$po" <<'PY'
import os, re, sys
p = sys.argv[1]; s = open(p, encoding='utf-8').read()
for key, val in (('Plural-Forms', os.environ['PF']), ('Language-Team', os.environ['LT']), ('Language', os.environ['LG'])):
    s = re.sub(r'^"%s: .*\\n"$' % key, lambda m: '"%s: %s\\n"' % (key, val), s, count=1, flags=re.M)
open(p, 'w', encoding='utf-8').write(s)
PY
  msgcat -o "$po" "$po"   # normalize wrapping to the project default
  grep -qx "$lang" "$LINGUAS_FILE" 2>/dev/null || { echo "$lang" >> "$LINGUAS_FILE"; sort -u -o "$LINGUAS_FILE" "$LINGUAS_FILE"; }
  echo "created ${po#"$ROOT"/}"
}

cmd_update() {
  local lang po
  for lang in $(linguas); do
    po=$(po_path "$lang")
    [ -f "$po" ] || { echo "i18n.sh: $lang listed in LINGUAS but ${po#"$ROOT"/} is missing" >&2; exit 1; }
    msgmerge --quiet --update --backup=none --previous "$po" "$POT"
  done
  echo "merged $(linguas | wc -l) catalogs"
}

cmd_validate() {
  local rc=0 lang po
  for lang in $(linguas); do
    po=$(po_path "$lang")
    [ -f "$po" ] || { echo "MISSING $lang"; rc=1; continue; }
    if ! msgfmt --check --check-accelerators=\& -o /dev/null "$po" 2>/tmp/i18n-msgfmt.$$; then
      echo "FAIL msgfmt $lang"; cat /tmp/i18n-msgfmt.$$; rc=1
    fi
    rm -f /tmp/i18n-msgfmt.$$
  done
  python3 - "$PODIR" "$PO_NAME" $(linguas) <<'PY' || rc=1
import re, sys, pathlib
podir, pattern, langs = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
PH = [re.compile(p) for p in (r"%\d+", r"%\([A-Za-z_]+\)[sdif]", r"%[sdif]", r"\{[A-Za-z_0-9]*\}",
                               r"\$\{?[A-Za-z_][A-Za-z_0-9]*\}?", r"</?[A-Za-z][^>]*>", r"&[a-z]+;")]
def unq(s): return bytes(s[1:-1], 'utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
def parse(path):
    entries, cur, key, flags = [], {}, None, set()
    for raw in path.read_text(encoding='utf-8').splitlines() + ['']:
        line = raw.strip()
        if not line:
            if cur: cur['flags'] = flags; entries.append(cur)
            cur, key, flags = {}, None, set(); continue
        if line.startswith('#,'): flags |= {f.strip() for f in line[2:].split(',')}; continue
        if line.startswith('#'): continue
        m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(".*")$', line)
        if m: key = m.group(1); cur[key] = unq(m.group(2)); continue
        if line.startswith('"') and key: cur[key] += unq(line)
    return entries
def toks(s): return sorted(t for p in PH for t in p.findall(s))
bad = 0
for lang in langs:
    for e in parse(podir / (pattern % lang)):
        if not e.get('msgid') or 'fuzzy' in e['flags']: continue
        src = [e['msgid']] + ([e['msgid_plural']] if 'msgid_plural' in e else [])
        outs = [(k, v) for k, v in e.items() if k.startswith('msgstr') and v]
        for k, v in outs:
            if 'msgid_plural' in e:
                # every form may only use the source's placeholders and must keep the
                # non-count ones; the count itself may be spelled out in a singular form
                allowed = set(toks(e['msgid'])) | set(toks(e['msgid_plural'])); got = toks(v)
                # the count may be spelled out in a form (ar: zero/one/two): numeric
                # placeholders of the source are optional, the others are required
                numeric = {t for t in allowed if re.fullmatch(r"%\d+|%n|%d|%\(\w+\)d|\{(count|n|num|number)\}", t)}
                needed = set(toks(e['msgid_plural'])) - numeric
                if set(got) - allowed or needed - set(got):
                    print(f"PLACEHOLDER {lang} {k}: {e['msgid_plural']!r} -> {v!r}"); bad += 1
                continue
            if toks(v) != toks(e['msgid']):
                print(f"PLACEHOLDER {lang}: {e['msgid']!r} -> {v!r}"); bad += 1
            for edge in ('startswith', 'endswith'):
                for ws in ('\n', ' '):
                    if getattr(e['msgid'], edge)(ws) != getattr(v, edge)(ws):
                        print(f"WHITESPACE {lang}: {e['msgid']!r} -> {v!r}"); bad += 1
sys.exit(1 if bad else 0)
PY
  [ $rc -eq 0 ] && echo "all catalogs valid ($(linguas | wc -l) languages)"
  return $rc
}

cmd_coverage() {
  local json=${1:-} lang po total out
  total=$(msgattrib --no-obsolete "$POT" 2>/dev/null | grep -c '^msgid ' || true); total=$((total-1))
  [ "$json" = --json ] && printf '{"domain":"%s","total":%d,"languages":{' "$DOMAIN" "$total" || printf '%-8s %6s %6s %6s %6s\n' lang trans fuzzy untr pct
  local first=1
  for lang in $(linguas); do
    po=$(po_path "$lang")
    out=$(LC_ALL=C msgfmt --statistics -o /dev/null "$po" 2>&1)
    local t f u
    t=$(grep -oE '^[0-9]+ translated' <<<"$out" | grep -oE '[0-9]+' || echo 0)
    f=$(grep -oE '[0-9]+ fuzzy' <<<"$out" | grep -oE '[0-9]+' || echo 0)
    u=$(grep -oE '[0-9]+ untranslated' <<<"$out" | grep -oE '[0-9]+' || echo 0)
    local pct=0; [ "$total" -gt 0 ] && pct=$((100*t/total))
    if [ "$json" = --json ]; then
      [ $first -eq 1 ] || printf ','; first=0
      printf '"%s":{"translated":%d,"fuzzy":%d,"untranslated":%d,"percent":%d}' "$lang" "$t" "$f" "$u" "$pct"
    else printf '%-8s %6d %6d %6d %5d%%\n' "$lang" "$t" "$f" "$u" "$pct"; fi
  done
  [ "$json" = --json ] && echo '}}' || true
}

cmd_compile() {
  local dest=${1:?usage: i18n.sh compile <destdir>} lang po
  for lang in $(linguas); do
    po=$(po_path "$lang"); mkdir -p "$dest/$lang/LC_MESSAGES"
    msgfmt --check -o "$dest/$lang/LC_MESSAGES/$DOMAIN.mo" "$po"
  done
}

case "${1:-}" in
  extract) cmd_extract ;; update) cmd_update ;; add) shift; cmd_add "$@" ;;
  validate) cmd_validate ;; check-pot) cmd_check_pot ;; coverage) shift; cmd_coverage "${1:-}" ;;
  compile) shift; cmd_compile "$@" ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
