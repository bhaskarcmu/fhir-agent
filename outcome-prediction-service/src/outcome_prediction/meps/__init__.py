"""AHRQ Medical Expenditure Panel Survey (MEPS) public-use files.

Facts and reproduction targets: docs/phase8/prototype-baseline.md §3 and §5.
"""

# Panel -> two-year longitudinal file number (HC-nnn). Two-year files only:
# HC-245 is a Panel 24 *three-year* file that duplicates Panel 24 people — never add it.
LONGITUDINAL_PANELS: dict[int, int] = {
    21: 202,
    22: 210,
    23: 217,
    24: 225,
    25: 234,
    26: 244,
    27: 252,
}
