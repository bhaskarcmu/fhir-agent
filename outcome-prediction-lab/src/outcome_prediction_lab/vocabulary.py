"""Plain-language names for every code the lab uses — taken from AHRQ's own MEPS documentation
pages, which the committed manifest already pins (so no extra sources, no extra licences).

  ICD-10 3-character categories  "ICD10CDX VALUE / LABEL" table in each Medical Conditions doc page
  CCSR categories                "CCSR1X VALUE / LABEL" table in the same pages
  Multum therapeutic classes     "Therapeutic Class Code / Definition" table in each Prescribed
                                 Medicines doc page (one code space for TC1, TC1S1, TC1S1_1)

Labels are merged across all years (2016–2022): a code present in any year's documentation is
named. Where years disagree (e.g. a label truncated in one release), the longest label wins.
AHRQ prints labels in capitals; they're converted to sentence case for reading.

Gaps: MEPS's tables list frequency combinations, not full code sets, so ~180 ICD-10 categories that
occur in the data have no MEPS label. Those come from the CDC/NCHS ICD-10-CM release (US government,
public domain), pinned below by SHA-256 and fetched through the same verified path as MEPS files.
A CCSR group still without a label is described by its body system (the code's first 3 letters).
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from outcome_prediction.etl.codelists import ICD10CM   # CDC ICD-10-CM FY2026: one pin, in the service
from outcome_prediction.meps.download import ensure_archive
from outcome_prediction.meps.manifest import archive_dir, load_manifest
from outcome_prediction.settings import processed_dir

from outcome_prediction_lab.data import CONDITIONS, PRESCRIBED

VOCAB = "vocabulary.json"
CCSR_LABEL_WIDTH = 57      # measured: 26 CCSR labels stop at exactly this length, mid-word
# Acronyms that must stay upper case after sentence-casing AHRQ's capitals.
KEEP_UPPER = {"HIV", "AIDS", "COPD", "ADHD", "HMG-COA", "NSAID", "NSAIDS", "ACE", "ARB", "SGLT-2",
              "GLP-1", "DPP-4", "COVID-19", "CNS", "GI", "ENT", "UTI", "MRSA", "TB"}

# CCSR body systems: the first three letters of every CCSR code (AHRQ CCSR documentation).
BODY_SYSTEMS = {
    "BLD": "blood and immune system", "CIR": "circulatory system (heart and blood vessels)",
    "DEN": "dental", "DIG": "digestive system", "EAR": "ear", "END": "endocrine, nutritional and metabolic",
    "EXT": "external causes of injury", "EYE": "eye", "FAC": "factors influencing health care use",
    "GEN": "genitourinary system (kidneys, bladder, reproductive organs)", "INF": "infections",
    "INJ": "injuries and poisonings", "MAL": "congenital conditions", "MBD": "mental and behavioural health",
    "MUS": "musculoskeletal system (bones, joints, muscles)", "NEO": "cancers and other growths",
    "NVS": "nervous system", "PNL": "newborn and perinatal", "PRG": "pregnancy and childbirth",
    "RSP": "respiratory system (lungs and airways)", "SKN": "skin", "SYM": "symptoms and abnormal findings",
}


class _Tables(HTMLParser):
    """Every <table> as rows of cell text — the stdlib parser, no lxml dependency."""

    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_tables(html: str) -> list[list[list[str]]]:
    p = _Tables()
    p.feed(html)
    return p.tables


def sentence_case(label: str) -> str:
    words = label.strip().split()
    out = []
    for i, w in enumerate(words):
        core = w.strip(",.;:()").upper()
        if core in KEEP_UPPER:
            out.append(w.upper())
        else:
            out.append(w.lower() if i else w[:1].upper() + w[1:].lower())
    return " ".join(out)


def _merge(target: dict, code: str, label: str) -> None:
    if label and (code not in target or len(label) > len(target[code])):
        target[code] = label


def parse_conditions_doc(html: str, icd: dict, ccsr: dict) -> None:
    for table in html_tables(html):
        if not table or not table[0]:
            continue
        head = [c.upper() for c in table[0]]
        if head[:2] == ["ICD10CDX VALUE", "ICD10CDX LABEL"]:
            for row in table[1:]:
                if len(row) >= 2 and re.fullmatch(r"[A-Z]\d{2}", row[0]):
                    _merge(icd, row[0], sentence_case(row[1]))
        elif head[:2] == ["CCSR1X VALUE", "CCSR1X LABEL"]:
            for row in table[1:]:                  # pairs of (value, label) columns: CCSR1X..CCSR4X
                for v, lab in zip(row[0:8:2], row[1:8:2]):
                    if re.fullmatch(r"[A-Z]{3}\d{3}", v):
                        _merge(ccsr, v, sentence_case(lab))


def parse_prescribed_doc(html: str, classes: dict) -> None:
    for table in html_tables(html):
        if table and table[0] and table[0][0].lower().startswith("therapeutic class code"):
            for row in table[1:]:
                if len(row) >= 2 and row[0].isdigit():
                    _merge(classes, row[0], row[1].strip())


# Category titles that only make sense to a coder. U07 is the WHO/CDC emergency-use category whose
# code U07.1 is COVID-19; both MEPS and CDC title it "Emergency use of U07".
OVERRIDES = {"U07": "COVID-19 (emergency-use diagnosis category U07)"}


def describe_tokens(tokens: str, vocab: dict) -> str:
    """A patient's code document rewritten as plain words, for word-level TF-IDF: each code becomes
    its name ('Heart failure', 'insulin', …), separated so names don't run together."""
    return " . ".join(name_token(t, vocab)[1] for t in dict.fromkeys(tokens.split()))


def cdc_icd10_categories() -> dict[str, str]:
    """3-character ICD-10-CM codes -> descriptions, from the pinned CDC order file (fixed-width:
    code in columns 7–13, long description from column 78)."""
    import io
    import zipfile
    from outcome_prediction.meps.download import obtain_original
    data = obtain_original(ICD10CM["name"], ICD10CM["sha256"], ICD10CM["url"],
                           archive_dir() / "reference", mirrors=[])
    lines = zipfile.ZipFile(io.BytesIO(data)).read(ICD10CM["member"]).decode("latin1").splitlines()
    return {ln[6:13].strip(): ln[77:].strip() for ln in lines if len(ln[6:13].strip()) == 3}


def build_vocabulary(rebuild: bool = False) -> dict:
    """{'icd': {...}, 'ccsr': {...}, 'rx_class': {...}, 'body_system': {...}} — cached as JSON."""
    path = processed_dir() / VOCAB
    if path.exists() and not rebuild:
        return json.loads(path.read_text())
    manifest = load_manifest()
    keys = {f"h{n}" for n in list(CONDITIONS.values()) + list(PRESCRIBED.values())}
    ensure_archive(manifest, archive_dir(), include_docs=True, keys=keys)   # pinned doc pages
    icd, ccsr, classes = {}, {}, {}
    for n in CONDITIONS.values():
        parse_conditions_doc((archive_dir() / f"h{n}doc.shtml").read_text(encoding="latin1"), icd, ccsr)
    for n in PRESCRIBED.values():
        parse_prescribed_doc((archive_dir() / f"h{n}doc.shtml").read_text(encoding="latin1"), classes)
    for code, label in cdc_icd10_categories().items():      # MEPS labels win; CDC fills gaps
        icd.setdefault(code, label)
    icd.update(OVERRIDES)
    # AHRQ cuts CCSR labels at 57 characters ("…immune mechanis"); mark the cut instead of hiding it.
    ccsr = {k: (v + "…" if len(v) >= CCSR_LABEL_WIDTH else v) for k, v in ccsr.items()}
    vocab = {"icd": icd, "ccsr": ccsr, "rx_class": classes, "body_system": BODY_SYSTEMS}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vocab, indent=1, sort_keys=True) + "\n")
    return vocab


def name_token(token: str, vocab: dict) -> tuple[str, str]:
    """('diagnosis' | 'condition group' | 'medicine class', plain-language name) for a code token."""
    if token.startswith("icd"):
        code = token[3:]
        return "diagnosis", vocab["icd"].get(code, f"diagnosis code {code}")
    if token.startswith("rx"):
        code = token[2:]
        return "medicine class", vocab["rx_class"].get(code, f"medicine class {code}")
    if token in vocab["ccsr"]:
        return "condition group", vocab["ccsr"][token]
    system = vocab["body_system"].get(token[:3], "other")
    return "condition group", f"a {system} condition group"
