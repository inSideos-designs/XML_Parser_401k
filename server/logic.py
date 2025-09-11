from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET


@dataclass
class LinkNameFlag:
    selected: int
    insert: int
    text: Optional[str] = None


def normalize_text(s: str) -> str:
    s = (s or '').strip()
    # Collapse internal whitespace and drop trailing colon
    s = re.sub(r"\s+", " ", s)
    if s.endswith(":"):
        s = s[:-1]
    return s


def parse_xml_flags_from_string(xml_str: str) -> Dict[str, LinkNameFlag]:
    flags: Dict[str, LinkNameFlag] = {}
    root = ET.fromstring(xml_str)
    for ln in root.findall('.//LinkName'):
        name = (ln.get('value') or '').strip()
        if not name:
            continue
        sel = int(ln.get('selected') or '0') if (ln.get('selected') or '0').isdigit() else 0
        ins = int(ln.get('insert') or '0') if (ln.get('insert') or '0').isdigit() else 0
        txt = (ln.text or '').strip() or None
        flags[name] = LinkNameFlag(sel, ins, txt)
    for pd in root.findall('.//PlanData'):
        name = (pd.get('FieldName') or '').strip()
        if not name:
            continue
        txt = (pd.text or '').strip() or None
        if name not in flags:
            flags[name] = LinkNameFlag(1, 0, txt)
        elif txt and not flags[name].text:
            flags[name].text = txt
    return flags


def _looks_yes_no_prompt(prompt_text: str) -> bool:
    p = (prompt_text or '').strip().lower()
    return p.endswith('?') and bool(re.match(r'^(is|does|will|are|has|have)\b', p))


def _clean_name(n: str) -> str:
    return (n or '').strip().strip('"').strip()


def _related_text(name: str, flags: Dict[str, LinkNameFlag]) -> Optional[str]:
    lf = flags.get(name)
    if lf and lf.text:
        t = lf.text.strip()
        if t:
            return t
    if name.endswith('Main'):
        base = name[:-4]
        lf2 = flags.get(base)
        if lf2 and lf2.text and lf2.text.strip():
            return lf2.text
    for suf in ('Age','Amt','Amount','Perc','Percent','Dollar','Dollars'):
        lf3 = flags.get(f'{name}{suf}')
        if lf3 and lf3.text and lf3.text.strip():
            return lf3.text
    return None


def _selected_names(names: List[str], flags: Dict[str, LinkNameFlag]) -> List[str]:
    out = []
    for n in names:
        lf = flags.get(n)
        if lf and lf.selected == 1:
            out.append(n)
    return out


def _yes_no_from_name(name: str, lf: LinkNameFlag) -> Optional[str]:
    if re.match(r'^yes', name, re.IGNORECASE):
        return 'Yes' if lf.selected == 1 else 'No'
    if re.match(r'^no', name, re.IGNORECASE):
        return 'No' if lf.selected == 1 else 'Yes'
    return None


def pick_from_options_allowed(options_allowed: str) -> Optional[str]:
    txt = (options_allowed or '').replace('\\n', '\n')
    lines = [ln.strip() for ln in re.split(r'\n+', txt) if ln.strip()]
    if not lines:
        return None
    # Prefer explicit defaults when present
    for pref in ('N/A', 'All', 'None'):
        for ln in lines:
            if ln.lower().startswith(pref.lower()):
                return ln
    # Single option => take it
    if len(lines) == 1:
        return lines[0]
    return None


def _derive_label_from_quick(quick: Optional[str]) -> Optional[str]:
    if not quick:
        return None
    q = quick.strip()
    if not q:
        return None
    if ',' in q:
        label = q.split(',')[-1].strip().strip('"')
        return label or None
    return None


def _is_vesting_schedule_prompt(prompt_text: str) -> bool:
    p = (prompt_text or '').strip().lower()
    return ('vesting schedule' in p) and ('describe' not in p)


def choose_value_for_map_entry(me: Dict[str, str], options_allowed: str, flags: Dict[str, LinkNameFlag], prompt_text: str) -> Optional[str]:
    linkcsv = (me.get('linknames') or '').strip()
    names = [_clean_name(s) for s in linkcsv.split(',') if _clean_name(s)]
    quick = me.get('quick') or ''

    if not names:
        return None

    # Fast path: single name
    if len(names) == 1:
        nm = names[0]
        lf = flags.get(nm)
        if not lf:
            return None
        if _looks_yes_no_prompt(prompt_text):
            return 'Yes' if lf.selected == 1 else 'No'
        txt = _related_text(nm, flags)
        if txt:
            return txt
        yn = _yes_no_from_name(nm, lf)
        if yn is not None:
            return yn
        return None

    # Multi-name: pick the selected one
    sel = _selected_names(names, flags)
    if sel:
        chosen = sel[0]
        if _looks_yes_no_prompt(prompt_text):
            if re.search(r'\byes\b', chosen, re.IGNORECASE):
                return 'Yes'
            if re.search(r'\bno\b', chosen, re.IGNORECASE):
                return 'No'
            return 'Yes'  # when some choice is selected for Y/N format
        txt = _related_text(chosen, flags)
        if txt:
            return txt
        # Last resort: try label from quick text
        lab = _derive_label_from_quick(quick)
        if lab:
            return lab
    return None


def enforce_yes_no(prompt_text: str, options_allowed: str, value: Optional[str], flags: Dict[str, LinkNameFlag], me: Dict[str, str], strict: bool = False) -> Optional[str]:
    if value is None and not _looks_yes_no_prompt(prompt_text):
        return None
    if value in ('Yes', 'No'):
        return value
    if _looks_yes_no_prompt(prompt_text):
        # Infer from mapped linknames
        names = [_clean_name(s) for s in (me.get('linknames') or '').split(',') if _clean_name(s)]
        for n in names:
            lf = flags.get(n)
            if not lf:
                continue
            yn = _yes_no_from_name(n, lf)
            if yn is not None:
                return yn
        # Fallback to selected any => Yes
        if any(f.selected == 1 for f in flags.values()):
            return 'Yes'
        return 'No' if strict else None
    return value

