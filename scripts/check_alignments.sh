#!/usr/bin/env bash
# Reason over the OWP vocabulary and each alignment package with HermiT (via ROBOT), against the pinned
# upstream ontologies that `ontle fetch` downloads and verifies by digest. Needs Java 11+ and network access.
#
#   ./scripts/check_alignments.sh
#
# Passes when the vocabulary and every alignment are consistent with no unsatisfiable classes, with and without
# the sample data, when each deliberately wrong input (alignments/tests/invalid-*, wrong-*) is inconsistent, and
# when the vocabulary and the BFO, DUL, and schema.org alignments are in the OWL 2 DL profile.
set -euo pipefail
cd "$(dirname "$0")/.."
ROBOT_VERSION=1.9.11
WORK="${OWP_ALIGN_WORK:-$(mktemp -d)}"
ROBOT="$WORK/robot.jar"
[ -f "$ROBOT" ] || curl -sSL -o "$ROBOT" "https://github.com/ontodev/robot/releases/download/v$ROBOT_VERSION/robot.jar"

# Upstream ontologies, verified against the digests pinned in each owp.yaml.
for pkg in owp-align-prov owp-align-bfo owp-align-dul; do
  python -m ontle.cli fetch "alignments/$pkg" --into "$WORK/$pkg" > "$WORK/$pkg.files"
done
file_in() {  # the fetched file of a package whose path contains $2; fails when there is none
  local f; f=$(grep "$2" "$WORK/$1.files" | head -1)
  [ -n "$f" ] || { echo "no fetched file matching $2 in $1" >&2; exit 2; }
  echo "$f"
}
PROV_O=$(file_in owp-align-prov prov-o)
BFO_CORE=$(file_in owp-align-bfo bfo-core)
IAO=$(file_in owp-align-bfo iao.owl)
DUL=$(file_in owp-align-dul DUL.owl)
cat > "$WORK/catalog-v001.xml" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<catalog prefer="public" xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
  <uri name="https://w3id.org/owp/ns" uri="$PWD/vocab/owp/ns.ttl"/>
  <uri name="https://w3id.org/owp/align/prov" uri="$PWD/alignments/owp-align-prov/align.ttl"/>
  <uri name="https://w3id.org/owp/align/bfo" uri="$PWD/alignments/owp-align-bfo/align.ttl"/>
  <uri name="https://w3id.org/owp/align/dul" uri="$PWD/alignments/owp-align-dul/align.ttl"/>
  <uri name="http://www.w3.org/ns/prov-o-20130430" uri="$PROV_O"/>
  <uri name="http://purl.obolibrary.org/obo/bfo/2020/bfo-core.ttl" uri="$BFO_CORE"/>
  <uri name="http://purl.obolibrary.org/obo/iao/2026-03-30/iao.owl" uri="$IAO"/>
  <uri name="http://www.ontologydesignpatterns.org/ont/dul/DUL.owl" uri="$DUL"/>
</catalog>
XML

reason() {  # prints "consistent" or "inconsistent"
  if java -Xmx4g -jar "$ROBOT" merge --catalog "$WORK/catalog-v001.xml" "$@" reason --reasoner hermit > "$WORK/out.log" 2>&1; then
    echo consistent
  elif grep -q "inconsistent\|unsatisfiable" "$WORK/out.log"; then
    echo inconsistent
  else
    cat "$WORK/out.log" >&2; exit 2
  fi
}
with_import() {  # the sample, importing one module, so its data is checked against that module's axioms
  sed "s#owl:imports <https://w3id.org/owp/ns>#owl:imports <$1>#" alignments/tests/sample.ttl > "$WORK/sample-$2.ttl"
  echo "$WORK/sample-$2.ttl"
}
bad=0
expect() {  # expect <consistent|inconsistent> <label> <robot inputs...>
  want=$1 label=$2; shift 2
  got=$(reason "$@")
  if [ "$got" = "$want" ]; then echo "PASS $label: $got"; else echo "FAIL $label: expected $want, got $got"; bad=1; fi
}
# The sample's PROV terms carry no axioms here (they are undeclared without PROV-O); the PROV-O case checks them.
expect consistent "vocabulary + sample (OWP axioms)" --input "$(with_import https://w3id.org/owp/ns core)"
expect consistent "PROV-O + sample" --input "$(with_import https://w3id.org/owp/align/prov prov)"
expect consistent "BFO 2020 + IAO + sample" --input "$(with_import https://w3id.org/owp/align/bfo bfo)"
expect consistent "DUL + sample" --input "$(with_import https://w3id.org/owp/align/dul dul)"
expect consistent "all alignments together (classes)" --input alignments/owp-align-prov/align.ttl --input alignments/owp-align-bfo/align.ttl --input alignments/owp-align-dul/align.ttl
for f in alignments/tests/invalid-*.ttl; do expect inconsistent "$(basename "$f" .ttl)" --input "$f"; done
expect inconsistent "wrong-bfo" --input alignments/owp-align-bfo/align.ttl --input alignments/tests/wrong-bfo.ttl
expect inconsistent "wrong-dul" --input alignments/owp-align-dul/align.ttl --input alignments/tests/wrong-dul.ttl
# OWL 2 DL profile of each imports closure. The PROV alignment is not checked: the pinned PROV-O itself is outside
# OWL 2 DL (prov:wasRevisionOf is punned between an object and an annotation property).
profile() {
  if java -jar "$ROBOT" validate-profile --catalog "$WORK/catalog-v001.xml" --input "$2" --profile DL > "$WORK/profile.log" 2>&1; then
    echo "PASS OWL 2 DL: $1"
  else
    echo "FAIL OWL 2 DL: $1"; grep -v "^$" "$WORK/profile.log" | head -5; bad=1
  fi
}
profile vocabulary vocab/owp/ns.ttl
profile owp-align-bfo alignments/owp-align-bfo/align.ttl
profile owp-align-dul alignments/owp-align-dul/align.ttl
profile owp-align-schemaorg alignments/owp-align-schemaorg/align.ttl  # SKOS matches only: no reasoning case
exit $bad
