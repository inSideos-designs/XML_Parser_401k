#!/usr/bin/env python3
"""
Fill "Plan Express Data Points" Plan columns using LinkNames from an XML export
and mappings from the "Map Updated" workbook.

This script uses only the Python standard library (zipfile + ElementTree) to
read XLSX files (as they are ZIPs of XML files). It writes a CSV output with
filled values for Plan 1.

Inputs:
- XML file with <answers><LinkName value=... selected=... insert=.../></answers>
- Map Updated XLSX with headers: Prompt, Quick Text Data Point, Proposed LinkName, Reasoning
- Data Points XLSX (e.g., "TPA Data Points_...xlsx") containing a sheet named
  "Plan Express Data Points" with columns that include: "PROMPT", "Options Allowed",
  and plan columns (Plan 1..Plan 15). We fill only Plan 1 by default.

Outputs:
- CSV written next to the Data Points workbook: <base>_filled_plan1.csv
- XLSX copy with Plan 1 values filled inline: <base>_filled_plan1.xlsx

Usage:
  python3 scripts/fill_plan_data.py \
    --xml "Desktop/Test Folder/ASW_...xml" \
    --map "Desktop/Test Folder/Map Updated 8152025.xlsx" \
    --datapoints "Desktop/Test Folder/TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx"

Notes:
- If a mapping's Proposed LinkName includes multiple comma-separated names, we
  pick the one with selected==1 in the XML. For Y/N prompts, we write "Yes"/"No".
- For free-text prompts (e.g., emails, EIN), the XML provided does not include
  text values; such cells remain blank.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZipFile, ZipInfo


@dataclass
class LinkNameFlag:
    selected: int
    insert: int
    text: Optional[str] = None


def parse_xml_linknames(xml_path: Path) -> Dict[str, LinkNameFlag]:
    """Parse XML to a map of linkname-like flags.

    Supports two formats observed in exports:
    - <LinkName value="..." selected="0/1" insert="0/1">text</LinkName>
    - <PlanData FieldName="...">text?</PlanData> (presence implies selection)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    link_flags: Dict[str, LinkNameFlag] = {}
    # Classic LinkName flags
    for ln in root.findall('.//LinkName'):
        name = (ln.get('value') or '').strip()
        if not name:
            continue
        sel = ln.get('selected') or '0'
        ins = ln.get('insert') or '0'
        txt = (ln.text or '').strip() if ln.text else None
        try:
            link_flags[name] = LinkNameFlag(selected=int(sel), insert=int(ins), text=txt if txt else None)
        except ValueError:
            link_flags[name] = LinkNameFlag(selected=0, insert=0, text=txt if txt else None)
    # PlanData FieldName flags (treat presence as selected; text when present)
    for pd in root.findall('.//PlanData'):
        name = (pd.get('FieldName') or '').strip()
        if not name:
            continue
        txt = (pd.text or '').strip() if pd.text else None
        # If already populated via LinkName, prefer LinkName entry
        if name in link_flags:
            # But backfill text when LinkName had none
            if txt and not (link_flags[name].text or '').strip():
                link_flags[name] = LinkNameFlag(selected=link_flags[name].selected, insert=link_flags[name].insert, text=txt)
            continue
        # Presence implies selected; insert unknown for this format
        link_flags[name] = LinkNameFlag(selected=1, insert=0, text=txt if txt else None)
    return link_flags


def _xlsx_shared_strings(z: ZipFile) -> List[str]:
    strings: List[str] = []
    try:
        with z.open('xl/sharedStrings.xml') as f:
            root = ET.parse(f).getroot()
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for si in root.findall('./s:si', ns):
                # Concatenate possible multiple t nodes
                text_parts = []
                for node in si.findall('.//s:t', ns):
                    text_parts.append(node.text or '')
                strings.append(''.join(text_parts))
    except KeyError:
        pass
    return strings


def _xlsx_sheet_targets(z: ZipFile) -> List[Tuple[str, str]]:
    ns = {
        's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    }
    with z.open('xl/workbook.xml') as f:
        wb = ET.parse(f).getroot()
    with z.open('xl/_rels/workbook.xml.rels') as f:
        rels = ET.parse(f).getroot()
    rid_to_target = {
        rel.get('Id'): rel.get('Target') for rel in rels.findall('./{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
    }
    sheets = []
    for s in wb.findall('.//s:sheet', ns):
        name = s.get('name') or ''
        rid = s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        if not rid:
            continue
        target = rid_to_target.get(rid)
        if not target:
            continue
        sheets.append((name, 'xl/' + target))
    return sheets


def read_xlsx_first_sheet_rows(xlsx_path: Path) -> List[List[str]]:
    with ZipFile(xlsx_path) as z:
        strings = _xlsx_shared_strings(z)
        # Assume first sheet
        first_sheet = 'xl/worksheets/sheet1.xml'
        with z.open(first_sheet) as f:
            sh = ET.parse(f).getroot()
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rows_out: List[List[str]] = []
        for row in sh.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
            vals: List[str] = []
            for c in row.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                t = c.get('t')
                v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                if v is None:
                    vals.append('')
                elif t == 's':
                    try:
                        vals.append(strings[int(v.text)])
                    except Exception:
                        vals.append('')
                else:
                    vals.append(v.text or '')
            rows_out.append(vals)
        return rows_out


def read_xlsx_named_sheet_rows(xlsx_path: Path, sheet_name: str) -> List[List[str]]:
    with ZipFile(xlsx_path) as z:
        strings = _xlsx_shared_strings(z)
        targets = _xlsx_sheet_targets(z)
        target_path = None
        for name, target in targets:
            if name.strip() == sheet_name.strip():
                target_path = target
                break
        if not target_path:
            raise RuntimeError(f'Sheet {sheet_name!r} not found in {xlsx_path}')
        with z.open(target_path) as f:
            sh = ET.parse(f).getroot()
        rows_out: List[List[str]] = []
        for row in sh.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
            vals: List[str] = []
            for c in row.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                t = c.get('t')
                v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                if v is None:
                    vals.append('')
                elif t == 's':
                    try:
                        vals.append(strings[int(v.text)])
                    except Exception:
                        vals.append('')
                else:
                    vals.append(v.text or '')
            rows_out.append(vals)
        return rows_out


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or '').strip()).rstrip(':')


def parse_map_workbook(map_xlsx: Path) -> Dict[str, Dict[str, object]]:
    """Return mapping per prompt with aggregated option rows.

    Structure per prompt:
      {
        'linknames': 'csv of last row (for backward compat)',
        'quick': 'last quick text',
        'options': [
           {'quick': str, 'label': str|None, 'linknames': [str,...]},
        ]
      }
    """
    # Allow CSV maps for auto-derived mappings
    if str(map_xlsx).lower().endswith('.csv'):
        import csv as _csv
        rows: List[List[str]] = []
        with map_xlsx.open(encoding='utf-8') as f:
            for r in _csv.reader(f):
                rows.append(r)
    else:
        rows = read_xlsx_first_sheet_rows(map_xlsx)
    if not rows:
        return {}
    header = [h.strip() for h in rows[0]]
    try:
        i_prompt = header.index('Prompt')
        i_quick = header.index('Quick Text Data Point')
        i_link = header.index('Proposed LinkName')
    except ValueError as e:
        raise RuntimeError(f'Unexpected Map header: {header}') from e

    mapping: Dict[str, Dict[str, object]] = {}
    current_prompt: Optional[str] = None

    def extract_label(quick_text: str) -> Optional[str]:
        if not quick_text:
            return None
        if ',' in quick_text:
            # Take only the first line after the comma as the option label
            after = quick_text.split(',', 1)[1]
            # Normalize escaped newlines
            after = after.replace('\\n', '\n')
            first_line = after.splitlines()[0].strip().strip('"')
            return first_line or None
        return None

    for r in rows[1:]:
        if not any((x or '').strip() for x in r):
            continue
        prompt_cell = r[i_prompt] if i_prompt < len(r) else ''
        prompt = normalize_text(prompt_cell)
        if prompt:
            current_prompt = prompt
        elif not current_prompt:
            continue
        quick = (r[i_quick] if i_quick < len(r) else '').strip()
        linkcsv = (r[i_link] if i_link < len(r) else '').strip()
        entry = mapping.setdefault(current_prompt, {'linknames': '', 'quick': '', 'options': []})
        # Preserve prior non-empty linknames; only update when we have a value
        if linkcsv:
            entry['linknames'] = linkcsv
        # Keep the first non-empty quick as the prompt-level quick
        if quick and not entry['quick']:
            entry['quick'] = quick
        if linkcsv:
            names = [n.strip() for n in linkcsv.split(',') if n.strip()]
            entry['options'].append({'quick': quick, 'label': extract_label(quick), 'linknames': names})
    return mapping

def choose_value_for_map_entry(map_entry: Dict[str, object], options_allowed: str, link_flags: Dict[str, LinkNameFlag], prompt_text: str) -> Optional[str]:
    # Vesting schedule mapping: infer canonical labels (Immediate, 1-25, 1-20, 2-20, Cliff2)
    def _is_vesting_schedule_prompt(pt: str) -> bool:
        p = (pt or '').strip().lower()
        return ('vesting schedule' in p) and ('describe' not in p)

    def _derive_vesting_label(flags: Dict[str, LinkNameFlag], quick_text: str) -> Optional[str]:
        """Map a wide set of vesting indicators to canonical labels.

        Supports Match, Non-Elective/Profit Sharing, and Safe Harbor/QACA.
        """
        # Graded schedules (map known flags to canonical labels used in template/LOV)
        graded_map = {
            # Match money type graded schedules
            'Vest6YRGradeMatch': '2-20',  # 0,0,20,40,60,80,100
            'Vest5YRGradeMatch': '1-20',  # 0,20,40,60,80,100
            'Vest4YRGradeMatch': '1-25',  # 0,25,50,75,100
            # Non-elective/profit sharing graded schedules (PlanData FieldName variants)
            '6YRGradedNEContr': '2-20',
            '5YRGradedNEContr': '1-20',
            '4YRGradedNEContr': '1-25',
        }
        for nm, label in graded_map.items():
            lf = flags.get(nm)
            if lf and lf.selected == 1:
                return label
        # Cliff schedules
        cliff_map = {
            'Vest3YRClifMatch': 'Cliff 3',
            '3YRCliffNEContr': 'Cliff 3',
            '2YRCliffNEContr': 'Cliff 2',
        }
        for nm, label in cliff_map.items():
            lf = flags.get(nm)
            if lf and lf.selected == 1:
                return label
        # Immediate indicators across money types (context-aware by quick_text if available)
        qt = (quick_text or '').lower()
        match_immediate = ('match' in qt)
        ne_immediate = any(k in qt for k in ('non elective', 'non-elective', 'profit'))
        if match_immediate:
            for nm in ('NAVestMatch', 'Vest100Match'):
                lf = flags.get(nm)
                if lf and lf.selected == 1:
                    return 'Immediate'
        if ne_immediate:
            for nm in ('100VestingNEContr', 'Vest100NEContr'):
                lf = flags.get(nm)
                if lf and lf.selected == 1:
                    return 'Immediate'
        # Safe Harbor/QACA fully vested
        for nm in ('VestNAQACA', 'VestNAQACAMatch', 'VestNAQACANE'):
            lf = flags.get(nm)
            if lf and lf.selected == 1:
                return 'Immediate'
        return None

    def _expand_vesting_label_from_options(short_label: str, options_allowed: str) -> Optional[str]:
        if not short_label or not options_allowed:
            return None
        # Prepare candidate starts for matching
        s = short_label.strip().lower().replace(' ', '')
        cand_prefixes = {s}
        # Handle synonyms
        if s in ('cliff2', 'cliff3'):
            cand_prefixes.add(s.replace('cliff', 'cliff '))  # 'cliff 2'
        if s == '1-20':
            cand_prefixes.add('20/yr')
        if s == '1yr/50' or s == '1yr50' or s == '1=50':
            cand_prefixes |= {'1yr/50', '1 yr/50', '1yr50'}
        # Scan lines and pick first that matches any candidate
        txt = options_allowed.replace('\\n', '\n')
        for line in txt.splitlines():
            raw = line.strip().strip('"')
            low = raw.lower()
            low_cmp = low.replace(' ', '')
            for pref in cand_prefixes:
                if low_cmp.startswith(pref):
                    return raw
        # As a fallback, if '20/Yr' is present and short is 1-20, prefer that
        if s == '1-20':
            for line in txt.splitlines():
                raw = line.strip().strip('"')
                if raw.lower().startswith('20/yr'):
                    return raw
        return None

    if _is_vesting_schedule_prompt(prompt_text):
        vlabel = _derive_vesting_label(link_flags, str(map_entry.get('quick') or ''))
        if vlabel is not None:
            # Canonical verbose mapping regardless of current row options
            def _canonical_verbose(label: str) -> Optional[str]:
                s = (label or '').strip().lower().replace(' ', '')
                if s in ('1-25',):
                    return '1-25 (0=0, 1=25, 2=50, 3=75, 4=100)'
                if s in ('1-20', '20/yr', '20yr'):
                    return '20/Yr (0=0, 1=20, 2=40, 3=60, 4=80, 5=100)'
                if s in ('2-20',):
                    return '2-20 (0=0, 1=0, 2=20, 3=40, 4=60, 5=80, 6=100)'
                if s in ('1yr/50', '1yr50', '1=50'):
                    return '1 Yr/50 (0=0, 1=50, 2=100)'
                if s in ('1yr33.3', '1yr/33.3', '33.3'):
                    return '1Yr 33.3 (0=0, 1=33.3, 2=66.6, 3=100)'
                if s in ('cliff2', 'cliff 2'):
                    return 'Cliff 2 (0=0, 1=0, 2=100)'
                if s in ('cliff3', 'cliff 3'):
                    return 'Cliff 3 (0=0, 1=0, 2=0, 3=100)'
                if s.startswith('immediate') or s == 'immediate':
                    return 'Immediate (100% immediate vesting)'
                return None
            canon = _canonical_verbose(vlabel)
            if canon:
                return canon
            # Otherwise try expanding from the row's Options Allowed for a full line
            expanded = _expand_vesting_label_from_options(vlabel, options_allowed)
            return expanded or vlabel
    # Prompt-specific heuristics first
    def _is_service_req_prompt(pt: str, oa: str) -> bool:
        pt_n = (pt or '').strip().lower()
        if 'service requirement for eligibility' in pt_n:
            return True
        oa_n = (oa or '').strip().lower()
        return oa_n.startswith('if day is selected') and 'if month is selected' in oa_n

    def _extract_numeric_service_req(flags: Dict[str, LinkNameFlag], oa: str) -> Optional[str]:
        # 1) Explicit "OtherServReq" free-text like "Sixty Days (60)" -> extract number in parentheses or digits
        for k in ['OtherServReq']:
            lf = flags.get(k)
            if lf and lf.text:
                import re as _re
                txt = lf.text.strip()
                m = _re.search(r'(\d{1,3})', txt)
                if m:
                    return m.group(1)
        # 2) Numeric text values on known fields
        for k in ['ConsecMonthsServReq', 'APPMCEligMonthsServ', 'MCEligMonthsServ']:
            lf = flags.get(k)
            if lf and lf.text and (lf.text.strip().isdigit()):
                return lf.text.strip()
        # 3) Generic scan: any numeric text on keys that look relevant
        for name, lf in flags.items():
            if not lf or not lf.text:
                continue
            n = lf.text.strip()
            if not n.isdigit():
                continue
            name_l = name.lower()
            if any(tok in name_l for tok in ['serv', 'elig', 'month', 'day', 'year']):
                return n
        return None

    def _is_vesting_describe_prompt(pt: str) -> bool:
        pt_n = normalize_text(pt).lower()
        return pt_n.startswith('please describe your vesting schedule')

    def _extract_vesting_other_text(flags: Dict[str, LinkNameFlag]) -> Optional[str]:
        # Common free-text holders seen in ASW XMLs
        preferred = [
            'OtherVestProvisions',
            'VestOtherMatch',
        ]
        for k in preferred:
            lf = flags.get(k)
            if lf and (lf.text or '').strip():
                return lf.text.strip()
        # Fallback: any linkname containing Vest and Other with text
        for name, lf in flags.items():
            if ('Vest' in name or 'Vesting' in name) and 'Other' in name and (lf.text or '').strip():
                return lf.text.strip()
        return None

    # Handle service requirement prompt early to avoid falling back to Options Allowed blurb
    if _is_service_req_prompt(prompt_text, options_allowed):
        num = _extract_numeric_service_req(link_flags, options_allowed)
        # Return empty string to explicitly suppress downstream fallbacks if unknown
        return num if num is not None else ''

    # Handle vesting "describe" prompt by pulling any "Other" free-text
    if _is_vesting_describe_prompt(prompt_text):
        txt = _extract_vesting_other_text(link_flags)
        # Return empty string to prevent leaking mapping "quick"/instruction text
        return txt if txt is not None else ''

    options: List[Dict[str, object]] = map_entry.get('options') or []
    if options:
        # 1) Prefer concrete text values from XML
        for opt in options:
            for n in opt.get('linknames', []):
                lf = link_flags.get(n)
                if lf and lf.text:
                    return lf.text
        # 2) Otherwise, use selected linkname and return label or Yes/No
        for opt in options:
            chosen_name = None
            for n in opt.get('linknames', []):
                lf = link_flags.get(n)
                if lf and lf.selected == 1:
                    chosen_name = n
                    break
            if chosen_name:
                label = opt.get('label')
                if label:
                    return str(label)
                # If no label, but a related text value exists (e.g., strip 'Main'), prefer that
                lf = link_flags.get(chosen_name)
                if lf and (lf.text or '').strip():
                    return lf.text
                if chosen_name.endswith('Main'):
                    base = chosen_name[:-4]
                    lf2 = link_flags.get(base)
                    if lf2 and (lf2.text or '').strip():
                        return lf2.text
                # Special-case mappings to a canonical label
                if chosen_name in ('HrdshipDistrAll','YSafeHarbHrdshipDistrAll'):
                    return 'All'
                if chosen_name == 'ERAllocReqDis' and prompt_text.startswith('Eligible Money Types available for Disability'):
                    return 'All'
                if chosen_name == 'EntryDateSameContrTypeYes':
                    # If the prompt asks for Prospective/Retroactive entry date without options, choose a clear phrase
                    if 'Prospective or Retroactive entry date' in prompt_text:
                        return 'Next following'
                    # If the prompt mentions 'All others except immediate', prefer the common phrase
                    if 'All others except immediate' in prompt_text or 'Next following' in prompt_text:
                        return 'Coinciding with or next following'
                # Fallback: use the option's quick text (single line) if present
                q = (opt.get('quick') or '').strip().strip('"')
                if q:
                    q = q.replace('\\n', '\n').splitlines()[0].strip()
                    if q:
                        return q
                if _looks_yes_no_prompt(prompt_text, options_allowed):
                    if re.search(r'yes', chosen_name, re.IGNORECASE):
                        return 'Yes'
                    if re.search(r'no', chosen_name, re.IGNORECASE):
                        return 'No'
                    return 'Yes'
                # Avoid leaking internal linkname to the sheet
                return None
    # Y/N special-case: If options include Yes/No-style linknames but none selected in options,
    # attempt to infer from global Yes*/No* pairs.
    if _looks_yes_no_prompt(prompt_text, options_allowed):
        # Look through option linknames and try alternate Yes/No name
        for opt in options:
            for n in opt.get('linknames', []):
                if n.startswith('Yes'):
                    lf = link_flags.get(n)
                    if lf and lf.selected == 1:
                        return 'Yes'
                    alt = 'No' + n[3:]
                    lf2 = link_flags.get(alt)
                    if lf2 and lf2.selected == 1:
                        return 'No'
                if n.startswith('No'):
                    lf = link_flags.get(n)
                    if lf and lf.selected == 1:
                        return 'No'
                    alt = 'Yes' + n[2:]
                    lf2 = link_flags.get(alt)
                    if lf2 and lf2.selected == 1:
                        return 'Yes'
    # Heuristic mapping using Options Allowed tokens when map options incomplete
    tokens_text = (options_allowed or '').replace('\\n', '\n').strip()
    if tokens_text:
        # Collect unique linknames referenced by this map entry
        all_names: List[str] = []
        seen = set()
        for opt in (map_entry.get('options') or []):
            for n in opt.get('linknames', []):
                if n not in seen:
                    all_names.append(n)
                    seen.add(n)
        for n in [x.strip() for x in str(map_entry.get('linknames') or '').split(',') if x.strip()]:
            if n not in seen:
                all_names.append(n); seen.add(n)

        # Which of these are selected?
        selected_names = [n for n in all_names if (link_flags.get(n) and link_flags[n].selected == 1)]
        def normalize_word(w: str) -> str:
            w = w.lower()
            w = w.replace('%',' percent ')
            w = w.replace('percents','percent').replace('percentages','percent').replace('perc','percent')
            w = w.replace('dollars','dollar')
            w = w.replace('semi-monthly','semi monthly')
            w = re.sub(r'[^a-z0-9]+',' ', w)
            return w.strip()
        def option_tokens(line: str) -> set:
            n = normalize_word(line)
            return set(t for t in n.split() if len(t) >= 2)
        def linkname_keywords(name: str) -> set:
            n = name.lower()
            kws = set()
            if 'dollar' in n:
                kws.add('dollar')
            if 'perc' in n or 'percent' in n:
                kws.add('percent')
            for k in ['eaca','qaca','aca','eqac']:
                if k in n:
                    kws.add(k)
            for k in ['match','profit','non elective','nonelective','immediate','monthly','quarterly','semi','semi annual','annual','weekly','cliff','graded','retire','disability','death','early','vesting','vest']:
                if k in n:
                    kws.add(k)
            # numbers like 1,2,3,4,5,7,10 etc
            import re as _re
            nums = set(_re.findall(r'(\d+)', n))
            for num in nums:
                kws.add(num)
            if 'yr' in n or 'year' in n:
                kws.add('yr')
            return kws
        token_lines = [t.strip().strip('"') for t in tokens_text.splitlines() if t.strip()]
        token_sets = [(t, option_tokens(t)) for t in token_lines]
        sel_kw = set()
        for n in selected_names:
            sel_kw |= linkname_keywords(n)
        # If no map-referenced names selected, fall back to global selected linknames to infer tokens
        if (not selected_names) or (not sel_kw):
            for name, lf in link_flags.items():
                if lf.selected == 1:
                    sel_kw |= linkname_keywords(name)
        # Domain-specific quick rules for common options
        tok_all = tokens_text.lower()
        # Safe harbor: Match vs Profit Sharing
        if ('match' in tok_all or 'profit' in tok_all) and sel_kw:
            if 'match' in sel_kw:
                return 'Match'
            if 'profit' in sel_kw or 'non elective' in sel_kw or 'nonelective' in sel_kw:
                # prefer standard label if present
                for line in token_lines:
                    if 'profit' in line.lower():
                        return line
                return 'Profit Sharing'
        # Frequencies: Immediate/Monthly/Quarterly/Semi-Annual/Annual
        for freq in ['immediate','monthly','quarterly','semi-annual','semi annual','annual','weekly']:
            if freq in tok_all and freq.split()[0] in sel_kw:
                for line in token_lines:
                    if freq.replace('semi-','semi ') in line.lower():
                        return line
                return freq.title().replace('Semi annual','Semi-Annual')
        # Vesting schedules: if graded detected but no direct token, prefer 'Other' option
        if 'graded' in sel_kw:
            for line in token_lines:
                if line.strip().lower().startswith('other') or 'other' in line.lower():
                    return line

        if selected_names and sel_kw:
            # Prefer an option whose tokens cover all selected keywords (e.g., Dollars and Percents)
            for tok, toks in token_sets:
                if sel_kw.issubset(toks):
                    return tok
            # Otherwise choose option with highest overlap
            best = None; best_score = 0
            for tok, toks in token_sets:
                score = len(sel_kw & toks)
                if score > best_score:
                    best = tok; best_score = score
            if best and best_score > 0:
                return best

    # Static keyword mapping for certain linknames when labels/options are absent
    ln_raw = str(map_entry.get('linknames') or '')
    names = [n.strip() for n in ln_raw.split(',') if n.strip()]
    for n in names:
        if link_flags.get(n) and link_flags[n].selected == 1:
            if n in ('HrdshipDistrAll','YSafeHarbHrdshipDistrAll'):
                return 'All'

    # Legacy fallback
    return choose_value_for_prompt(
        linkcsv=str(map_entry.get('linknames') or ''),
        options_allowed=options_allowed,
        link_flags=link_flags,
        quick_text=str(map_entry.get('quick') or ''),
        prompt_text=prompt_text,
    )


def _enforce_yes_no(prompt_text: str, options_allowed: str, value: Optional[str], link_flags: Dict[str, LinkNameFlag], map_entry: Optional[Dict[str, object]], strict: bool) -> Optional[str]:
    """Ensure Y/N prompts resolve to explicit 'Yes' or 'No' (or blank if strict and unknown)."""
    if not _looks_yes_no_prompt(prompt_text, options_allowed):
        return value
    v = (value or '').strip().lower()
    if v in ('yes', 'no'):
        return 'Yes' if v == 'yes' else 'No'
    if v in ('y/n', 'y / n') or ('yes' in v and 'no' in v):
        # ambiguous value came through; recompute via selection
        pass
    # Try recomputing directly from map options
    if map_entry:
        recomputed = choose_value_for_map_entry(map_entry, options_allowed, link_flags, prompt_text)
        if recomputed and recomputed.strip().lower() in ('yes', 'no'):
            return 'Yes' if recomputed.strip().lower() == 'yes' else 'No'
        # If any mapped linkname is selected, treat as Yes
        names = []
        for opt in (map_entry.get('options') or []):
            names.extend(opt.get('linknames', []))
        for n in [x.strip() for x in str(map_entry.get('linknames') or '').split(',') if x.strip()]:
            names.append(n)
        if any((link_flags.get(n) and link_flags[n].selected == 1) for n in names):
            return 'Yes'
        # None selected
        return None if strict else 'No'
    return None if strict else 'No'


def _looks_yes_no_prompt(prompt_text: str, options_allowed: str) -> bool:
    p = (prompt_text or '').strip().lower()
    if 'y/n' in (options_allowed or '').lower():
        return True
    # Heuristic: questions starting with is/does/will/are/has/have
    return bool(p.endswith('?') and re.match(r'^(is|does|will|are|has|have)\b', p))


def choose_value_for_prompt(linkcsv: str, options_allowed: str, link_flags: Dict[str, LinkNameFlag], quick_text: str, prompt_text: str = '') -> Optional[str]:
    def related_text(name: str) -> Optional[str]:
        lf = link_flags.get(name)
        if lf and (lf.text or '').strip():
            return lf.text
        # Heuristic: strip 'Main' suffix to find actual numeric/text value
        if name.endswith('Main'):
            base = name[:-4]
            lf2 = link_flags.get(base)
            if lf2 and (lf2.text or '').strip():
                return lf2.text
        # Try common suffix variants
        for suf in ['Age','Amt','Amount','Perc','Percent','Dollar','Dollars']:
            lf3 = link_flags.get(f"{name}{suf}")
            if lf3 and (lf3.text or '').strip():
                return lf3.text
        return None
    names = [n.strip() for n in (linkcsv or '').split(',') if n.strip()]
    if not names:
        return None

    # If single linkname and it's a Y/N type, use selected flag as Yes/No
    if len(names) == 1:
        lf = link_flags.get(names[0])
        if lf is None:
            return None
        if _looks_yes_no_prompt(prompt_text, options_allowed):
            return 'Yes' if lf.selected == 1 else 'No'
        # Non Y/N: return text value if present
        txt = related_text(names[0])
        if txt:
            return txt
        # Heuristic: if linkname itself starts with Yes/No and selected signifies choose that
        nm = names[0].lower()
        if nm.startswith('yes'):
            return 'Yes' if lf.selected == 1 else 'No'
        if nm.startswith('no'):
            return 'No' if lf.selected == 1 else 'Yes'
        return None

    # Multiple linknames: pick the one that is selected
    chosen: Optional[str] = None
    chosen_info: Optional[LinkNameFlag] = None
    for n in names:
        lf = link_flags.get(n)
        if lf and lf.selected == 1:
            chosen = n
            chosen_info = lf
            break

    if not chosen:
        return None

    # If Y/N, infer from name if possible
    if _looks_yes_no_prompt(prompt_text, options_allowed):
        if re.search(r'yes', chosen, re.IGNORECASE):
            return 'Yes'
        if re.search(r'no', chosen, re.IGNORECASE):
            return 'No'
        # Fallback: selected implies Yes
        return 'Yes'

    # If selected link has a concrete text value, use it
    if chosen_info:
        txt = related_text(chosen)
        if txt:
            return txt

    # Try to derive a friendly label from quick_text if it looks like "...,Label"
    if quick_text and ',' in quick_text:
        label = quick_text.split(',')[-1].strip()
        if label:
            return label

    # Do not leak internal linkname; no unambiguous value
    return None


def parse_lov(datapoints_xlsx: Path) -> Dict[Tuple[str, str], List[str]]:
    try:
        rows = read_xlsx_named_sheet_rows(datapoints_xlsx, 'LOV')
    except Exception:
        return {}
    lov: Dict[Tuple[str, str], List[str]] = {}
    for r in rows:
        if not r:
            continue
        # Last two cells should be page, seq
        if len(r) < 2:
            continue
        page = (r[-2] or '').strip()
        seq = (r[-1] or '').strip()
        if not page or not seq:
            continue
        opts = [x for x in r[:-2] if (x or '').strip()]
        if not opts:
            continue
        lov[(page, seq)] = opts
    return lov


def fallback_from_lov(page: str, seq: str, options_allowed: str, lov: Dict[Tuple[str, str], List[str]]) -> Optional[str]:
    # If explicit Y/N declared, default to 'No'
    if 'y/n' in (options_allowed or '').lower():
        return 'No'
    opts = lov.get((page.strip(), seq.strip()))
    if not opts:
        return None
    # Prefer 'None' if offered, else first option
    for o in opts:
        if o.strip().lower() == 'none':
            return 'None'
    return opts[0]


def smart_default(prompt_text: str, options_allowed: str) -> str:
    p = (prompt_text or '').lower()
    oa = (options_allowed or '').lower()
    if _looks_yes_no_prompt(prompt_text, options_allowed):
        return 'No'
    if '%' in p or 'percent' in p or 'percentage' in p:
        return '0%'
    if any(k in p for k in ['amount', 'dollar', '$']):
        return '0'
    if 'date' in p:
        return '01/01/1900'
    if 'email' in p or 'phone' in p or 'name' in p:
        return 'N/A'
    # If options are listed inline, pick first
    if oa:
        first = (options_allowed.split(',')[0] or '').strip()
        if first:
            return first
    return 'None'


def pick_from_options_allowed(options_allowed: str) -> Optional[str]:
    if not options_allowed:
        return None
    txt = options_allowed.replace('\\n', '\n')
    def _is_instruction(s: str) -> bool:
        s_low = s.lower()
        # Common instruction patterns we should never paste into the sheet
        if s_low.startswith('if y') and ('page' in s_low and 'seq' in s_low):
            return True
        if s_low.startswith('enter '):
            return True
        if 'this information will not be loaded' in s_low:
            return True
        if 'if day is selected' in s_low and 'if month is selected' in s_low:
            return True
        return False
    for line in txt.splitlines():
        line = line.strip().strip('"')
        if not line:
            continue
        if _is_instruction(line):
            continue
        return line
    return None


def fill_plan1(datapoints_xlsx: Path, map_xlsx: Path, link_flags: Dict[str, LinkNameFlag], strict: bool = False) -> List[List[str]]:
    rows = read_xlsx_named_sheet_rows(datapoints_xlsx, 'Plan Express Data Points')
    if not rows:
        return []
    header = rows[0]
    # Normalize headers by stripping spaces
    header_norm = [h.strip() for h in header]
    try:
        i_prompt = header_norm.index('PROMPT')
    except ValueError:
        # Some files may include extra spaces around PROMPT
        # Try fuzzy locate the column that contains PROMPT keyword
        i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
        if i_prompt < 0:
            raise RuntimeError(f"Couldn't find PROMPT column in header: {header}")
    try:
        i_options = header_norm.index('Options Allowed')
    except ValueError:
        i_options = -1

    # Additional columns
    try:
        i_page = header_norm.index('Page')
    except ValueError:
        i_page = -1
    try:
        i_seq = header_norm.index('Seq')
    except ValueError:
        i_seq = -1

    # Plan 1 column index (create if missing in output CSV)
    try:
        i_plan1 = header_norm.index('Plan 1')
    except ValueError:
        i_plan1 = -1

    # Build prompt -> linknames mapping
    map_data = parse_map_workbook(map_xlsx)
    lov = parse_lov(datapoints_xlsx)

    out_rows: List[List[str]] = []
    out_header = header.copy()
    if i_plan1 < 0:
        out_header.append('Plan 1')
    out_rows.append(out_header)

    misses = 0
    hits = 0

    for r in rows[1:]:
        # Make a working copy for output
        r_out = r.copy()
        # Normalize length
        if len(r_out) < len(out_header):
            r_out += [''] * (len(out_header) - len(r_out))

        prompt = normalize_text(r[i_prompt] if i_prompt < len(r) else '')
        if not prompt:
            out_rows.append(r_out)
            continue

        options = (r[i_options] if (0 <= i_options < len(r)) else '').strip()

        map_entry = map_data.get(prompt)
        value: Optional[str] = None
        if map_entry:
            value = choose_value_for_map_entry(map_entry, options, link_flags, prompt)
            value = _enforce_yes_no(prompt, options, value, link_flags, map_entry, strict)

        # Deterministic fallbacks to ensure a single valid option
        if value is None:
            page = (r[i_page] if (0 <= i_page < len(r)) else '').strip()
            seq = (r[i_seq] if (0 <= i_seq < len(r)) else '').strip()
            value = fallback_from_lov(page, seq, options, lov)
        if value is None:
            pick = pick_from_options_allowed(options)
            if pick:
                value = pick
        if not strict and value is None:
            value = smart_default(prompt, options)

        if i_plan1 >= 0:
            if i_plan1 >= len(r_out):
                r_out += [''] * (i_plan1 - len(r_out) + 1)
            r_out[i_plan1] = value or ''
        else:
            r_out[-1] = value or ''

        if value is None:
            misses += 1
        else:
            hits += 1

        out_rows.append(r_out)

    sys.stderr.write(f"Mapping complete. Hits: {hits}, Misses: {misses}\n")
    return out_rows


def write_csv(rows: List[List[str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for r in rows:
            writer.writerow(r)


def _col_letter_to_num(col: str) -> int:
    n = 0
    for ch in col:
        if 'A' <= ch <= 'Z':
            n = n * 26 + (ord(ch) - 64)
    return n


def _col_num_to_letter(n: int) -> str:
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell_ref(col_letter: str, row_num: int) -> str:
    return f"{col_letter}{row_num}"


def _get_cell_value_text(c: ET.Element, shared_strings: List[str]) -> str:
    t = c.get('t')
    v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
    if t == 's' and v is not None and v.text is not None:
        try:
            return shared_strings[int(v.text)]
        except Exception:
            return ''
    # inline string
    if t == 'inlineStr':
        is_el = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is')
        if is_el is not None:
            tnode = is_el.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
            return (tnode.text or '') if tnode is not None else ''
    # number or blank
    if v is not None and v.text is not None:
        return v.text
    return ''


def _set_cell_inline_str(c: ET.Element, text: str) -> None:
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    # Clear children v/f
    for child in list(c):
        c.remove(child)
    c.set('t', 'inlineStr')
    is_el = ET.Element(f'{{{ns}}}is')
    t_el = ET.SubElement(is_el, f'{{{ns}}}t')
    t_el.text = text
    c.append(is_el)


def fill_plan1_in_xlsx(datapoints_xlsx: Path, map_xlsx: Path, link_flags: Dict[str, LinkNameFlag], out_xlsx: Path, strict: bool = False) -> None:
    # Read shared strings and locate target sheet
    with ZipFile(datapoints_xlsx, 'r') as zin:
        strings = _xlsx_shared_strings(zin)
        targets = _xlsx_sheet_targets(zin)
        sheet_target = None
        for name, target in targets:
            if name.strip() == 'Plan Express Data Points':
                sheet_target = target
                break
        if not sheet_target:
            raise RuntimeError('Plan Express Data Points sheet not found')
        with zin.open(sheet_target) as f:
            sheet_root = ET.parse(f).getroot()

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    # Find header row (look for one containing PROMPT)
    rows = sheet_root.findall(f'.//{{{ns}}}row')
    header_row_el: Optional[ET.Element] = None
    for row in rows[:5]:
        texts = [_get_cell_value_text(c, strings).strip() for c in row.findall(f'{{{ns}}}c')]
        if any(normalize_text(t).upper() == 'PROMPT' for t in texts):
            header_row_el = row
            break
    if header_row_el is None:
        raise RuntimeError('Header row with PROMPT not found')

    # Map header text -> column letter
    header_map: Dict[str, str] = {}
    prompt_col_letter = None
    options_col_letter = None
    plan1_col_letter = None
    page_col_letter = None
    seq_col_letter = None
    for c in header_row_el.findall(f'{{{ns}}}c'):
        rref = c.get('r') or ''
        # Extract column letters
        m = re.match(r'([A-Z]+)(\d+)', rref)
        if not m:
            continue
        col_letter = m.group(1)
        text = normalize_text(_get_cell_value_text(c, strings))
        if not text:
            continue
        key = text
        header_map[key] = col_letter
        if key.upper() == 'PROMPT':
            prompt_col_letter = col_letter
        elif key.lower() == 'options allowed':
            options_col_letter = col_letter
        elif key.lower() == 'plan 1':
            plan1_col_letter = col_letter
        elif key.lower() == 'page':
            page_col_letter = col_letter
        elif key.lower() == 'seq':
            seq_col_letter = col_letter

    if not prompt_col_letter:
        raise RuntimeError('PROMPT column letter not identified')
    if not plan1_col_letter:
        # If "Plan 1" header missing, create it at the end of header row
        # Determine max column used
        used_cols = [_col_letter_to_num(m.group(1)) for m in (re.match(r'([A-Z]+)\d+', (c.get('r') or '')) for c in header_row_el.findall(f'{{{ns}}}c')) if m]
        next_col_num = max(used_cols) + 1 if used_cols else 1
        plan1_col_letter = _col_num_to_letter(next_col_num)
        # Create header cell
        hcell = ET.Element(f'{{{ns}}}c', {'r': _cell_ref(plan1_col_letter, int(header_row_el.get('r') or '1'))})
        _set_cell_inline_str(hcell, 'Plan 1')
        header_row_el.append(hcell)

    # Build map data from Map workbook
    map_data = parse_map_workbook(map_xlsx)
    lov = parse_lov(datapoints_xlsx)

    # Prepare loop over data rows
    for row in rows:
        rnum = int(row.get('r') or '0')
        if row is header_row_el or rnum <= int(header_row_el.get('r') or '1'):
            continue
        # Locate prompt cell and options cell
        prompt_cell = None
        options_cell = None
        plan1_cell = None
        for c in row.findall(f'{{{ns}}}c'):
            rref = c.get('r') or ''
            m = re.match(r'([A-Z]+)(\d+)', rref)
            if not m:
                continue
            col_letter = m.group(1)
            if col_letter == prompt_col_letter:
                prompt_cell = c
            elif options_col_letter and col_letter == options_col_letter:
                options_cell = c
            elif col_letter == plan1_col_letter:
                plan1_cell = c
            elif page_col_letter and col_letter == page_col_letter:
                page_cell = c
            elif seq_col_letter and col_letter == seq_col_letter:
                seq_cell = c

        # Read prompt text
        prompt_text = normalize_text(_get_cell_value_text(prompt_cell, strings) if prompt_cell is not None else '')
        if not prompt_text:
            continue
        options_text = (_get_cell_value_text(options_cell, strings) if options_cell is not None else '').strip()
        page_text = (_get_cell_value_text(locals().get('page_cell'), strings) if 'page_cell' in locals() else '').strip()
        seq_text = (_get_cell_value_text(locals().get('seq_cell'), strings) if 'seq_cell' in locals() else '').strip()

        map_entry = map_data.get(prompt_text)
        value = None
        if map_entry:
            value = choose_value_for_map_entry(map_entry, options_text, link_flags, prompt_text)
            value = _enforce_yes_no(prompt_text, options_text, value, link_flags, map_entry, strict)
        # Deterministic fallbacks to ensure a single valid option
        if value is None:
            value = fallback_from_lov(page_text, seq_text, options_text, lov)
        if value is None:
            pick = pick_from_options_allowed(options_text)
            if pick:
                value = pick
        if not strict and value is None:
            value = smart_default(prompt_text, options_text)

        # Ensure plan1 cell exists
        if plan1_cell is None:
            plan1_cell = ET.Element(f'{{{ns}}}c', {'r': _cell_ref(plan1_col_letter, rnum)})
            row.append(plan1_cell)
        _set_cell_inline_str(plan1_cell, value)

    # Write out the modified workbook as a new zip
    with ZipFile(datapoints_xlsx, 'r') as zin, ZipFile(out_xlsx, 'w') as zout:
        for info in zin.infolist():
            name = info.filename
            if name == sheet_target:
                # Write modified sheet
                data = ET.tostring(sheet_root, encoding='utf-8', xml_declaration=True)
                zi = ZipInfo(filename=name, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zout.writestr(zi, data)
            else:
                zout.writestr(info, zin.read(name))


def build_strict_qa(datapoints_xlsx: Path, map_xlsx: Path, link_flags: Dict[str, LinkNameFlag]) -> List[List[str]]:
    """Build a QA table under strict logic without defaults.

    Columns:
    - Page, Seq, Prompt, Options Allowed,
    - Map LinkNames (csv), XML Selected (csv), XML Text Values (csv), Strict Value
    """
    rows = read_xlsx_named_sheet_rows(datapoints_xlsx, 'Plan Express Data Points')
    header = rows[0]
    header_norm = [h.strip() for h in header]
    try:
        i_prompt = header_norm.index('PROMPT')
    except ValueError:
        i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
    i_options = header_norm.index('Options Allowed') if 'Options Allowed' in header_norm else -1
    i_page = header_norm.index('Page') if 'Page' in header_norm else -1
    i_seq = header_norm.index('Seq') if 'Seq' in header_norm else -1

    map_data = parse_map_workbook(map_xlsx)

    out: List[List[str]] = []
    out.append(['Page','Seq','Prompt','Options Allowed','Map LinkNames','XML Selected','XML Text Values','Strict Value'])

    def summarize_selected(names: List[str]) -> str:
        sels = []
        for n in names:
            lf = link_flags.get(n)
            if lf and lf.selected == 1:
                sels.append(n)
        return ', '.join(sels)

    def summarize_text(names: List[str]) -> str:
        vals = []
        for n in names:
            lf = link_flags.get(n)
            if lf and (lf.text or '').strip():
                vals.append(f"{n}={lf.text}")
        return ', '.join(vals)

    for r in rows[1:]:
        prompt = normalize_text(r[i_prompt] if i_prompt >= 0 and i_prompt < len(r) else '')
        if not prompt:
            continue
        options = (r[i_options] if (0 <= i_options < len(r)) else '').strip()
        page = (r[i_page] if (0 <= i_page < len(r)) else '').strip()
        seq = (r[i_seq] if (0 <= i_seq < len(r)) else '').strip()

        me = map_data.get(prompt)
        linkcsv = ''
        all_names: List[str] = []
        if me:
            linkcsv = str(me.get('linknames') or '')
            # collect unique linknames from options aggregation as well
            seen = set()
            for opt in (me.get('options') or []):
                for n in opt.get('linknames', []):
                    if n not in seen:
                        all_names.append(n)
                        seen.add(n)
            # also include raw csv list
            for n in [x.strip() for x in linkcsv.split(',') if x.strip()]:
                if n not in set(all_names):
                    all_names.append(n)

        # strict value
        val = None
        if me:
            val = choose_value_for_map_entry(me, options, link_flags, prompt)
            val = _enforce_yes_no(prompt, options, val, link_flags, me, True)

        out.append([
            page,
            seq,
            prompt,
            options,
            linkcsv,
            summarize_selected(all_names),
            summarize_text(all_names),
            val or ''
        ])
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='Fill Plan 1 values using XML linknames + map workbook')
    ap.add_argument('--xml', required=True, type=Path, help='Path to XML export file')
    ap.add_argument('--map', required=True, type=Path, help='Path to Map Updated XLSX')
    ap.add_argument('--datapoints', required=True, type=Path, help='Path to Data Points XLSX')
    ap.add_argument('--out', type=Path, help='Output CSV path (default next to Data Points)')
    ap.add_argument('--write-xlsx', action='store_true', help='Also write a filled XLSX copy with Plan 1 values')
    ap.add_argument('--qa-csv', type=Path, help='Write a strict QA CSV (no defaults) for Plan 1 analysis')
    ap.add_argument('--strict', action='store_true', help='Fill only when directly mapped from XML+Map. No LOV/defaults.')
    args = ap.parse_args(argv)

    link_flags = parse_xml_linknames(args.xml)
    rows = fill_plan1(args.datapoints, args.map, link_flags, strict=args.strict)
    if rows:
        out_path = args.out
        if not out_path:
            base = args.datapoints.with_suffix('').name
            out_path = args.datapoints.parent / f'{base}_filled_plan1.csv'
        write_csv(rows, out_path)
        print(f'Wrote {out_path}')

    if args.write_xlsx:
        x_out = args.out.with_suffix('.xlsx') if args.out and args.out.suffix.lower() == '.xlsx' else None
        if not x_out:
            base = args.datapoints.with_suffix('').name
            x_out = args.datapoints.parent / f'{base}_filled_plan1.xlsx'
        fill_plan1_in_xlsx(args.datapoints, args.map, link_flags, x_out, strict=args.strict)
        print(f'Wrote {x_out}')

    if args.qa_csv:
        qa_rows = build_strict_qa(args.datapoints, args.map, link_flags)
        write_csv(qa_rows, args.qa_csv)
        print(f'Wrote QA CSV {args.qa_csv}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
