
import json
import sys
from pathlib import Path
import runpy
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple


def main() -> int:
    data = json.load(sys.stdin)
    xml_items = data.get('xmlFiles') or []
    if not xml_items:
        print(json.dumps({'error': 'Missing xmlFiles'}))
        return 400

    # Load functions from fill_plan_data.py
    mod = runpy.run_path(str(Path.home() / 'Desktop' / 'Test Folder' / 'fill_plan_data.py'))
    parse_map_workbook = mod['parse_map_workbook']
    read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
    parse_lov = mod['parse_lov']
    parse_xml_linknames = mod['parse_xml_linknames']
    choose_value_for_map_entry = mod['choose_value_for_map_entry']
    _enforce_yes_no = mod['_enforce_yes_no']
    fallback_from_lov = mod['fallback_from_lov']
    pick_from_options_allowed = mod['pick_from_options_allowed']
    normalize_text = mod['normalize_text']

    # --- Vesting helpers ---
    def _is_vesting_schedule_prompt(pt: str) -> bool:
        p = (pt or '').strip().lower()
        return ('vesting schedule' in p) and ('describe' not in p)

    def _is_apply_schedule_prompt(pt: str) -> bool:
        p = (pt or '').strip().lower()
        return p.startswith('which vesting schedule will apply')

    def _is_vesting_describe_prompt(pt: str) -> bool:
        return normalize_text(pt).lower().startswith('please describe your vesting schedule')

    def _extract_vesting_other_text(flags: Dict[str, object]) -> Optional[str]:
        # Preferred holders observed in XMLs
        for k in ('OtherVestProvisions', 'VestOtherMatch'):
            lf = flags.get(k)
            if lf is not None:
                try:
                    t = (getattr(lf, 'text', None) or '').strip()
                except Exception:
                    t = ''
                if t:
                    return t
        # Any Vest*Other* with text
        for name, lf in flags.items():
            if ('Vest' in name or 'Vesting' in name) and 'Other' in name:
                try:
                    t = (getattr(lf, 'text', None) or '').strip()
                except Exception:
                    t = ''
                if t:
                    return t
        # Any Vest* with text as last resort
        for name, lf in flags.items():
            if ('Vest' in name or 'Vesting' in name):
                try:
                    t = (getattr(lf, 'text', None) or '').strip()
                except Exception:
                    t = ''
                if t:
                    return t
        return None

    def _is_immediate_for_money_type(flags: Dict[str, object], quick_text: str) -> bool:
        qt = (quick_text or '').lower()
        # Matching: Immediate when NAVestMatch is selected
        if 'match' in qt:
            lf = flags.get('NAVestMatch')
            try:
                if lf is not None and getattr(lf, 'selected', 0) == 1:
                    return True
            except Exception:
                pass
        # Matching: explicit 100% match vesting
        if 'match' in qt:
            lf = flags.get('Vest100Match')
            try:
                if lf is not None and getattr(lf, 'selected', 0) == 1:
                    return True
            except Exception:
                pass
        # Non-elective / Profit Sharing: treat explicit 100% vesting as Immediate
        if ('non elective' in qt) or ('non-elective' in qt) or ('profit' in qt):
            for name in ('100VestingNEContr', 'Vest100NEContr'):
                lf = flags.get(name)
                try:
                    if lf is not None and getattr(lf, 'selected', 0) == 1:
                        return True
                except Exception:
                    pass
        # Safe Harbor: QACA/Safe Harbor money types are normally fully vested
        if 'safe harbor' in qt or 'safeharbor' in qt or 'qaca' in qt:
            lf = flags.get('VestNAQACA')
            try:
                if lf is not None and getattr(lf, 'selected', 0) == 1:
                    return True
            except Exception:
                pass
        # Extend here for Safe Harbor / Profit Sharing immediate identifiers when known
        return False

    # --- Gate-aware helpers (for rows like: "If Y in page XXXX seq YY - enter ...") ---
    import re as _re
    _gate_re = _re.compile(r"if\s*y\s*in\s*page\s*(\d+)\s*seq\s*(\d+)", _re.IGNORECASE)

    def _parse_gate_ref(options_allowed: str) -> Optional[tuple]:
        if not options_allowed:
            return None
        m = _gate_re.search(options_allowed)
        if not m:
            return None
        return (m.group(1).strip(), m.group(2).strip())

    def _extract_numeric_for_prompt(prompt: str, flags: Dict[str, object]) -> Optional[str]:
        p = (prompt or '').lower()
        # Helper: first numeric
        def first_num(txt: str) -> Optional[str]:
            import re
            m = re.search(r"(\d{1,4}(?:[.,]\d{1,2})?)", txt)
            return m.group(1) if m else None
        # Candidate linknames by prompt type
        candidates: List[str] = []
        if 'minimum age' in p:
            candidates += ['InPlanRothDeemedAge']
        if 'minimum years of participation' in p:
            candidates += ['InPlanRothDeemedYearsPart', 'InPlanRothDeemedMonthsPart']
        if 'minimum years of accumulation' in p:
            candidates += ['InPlanRothDeemedYearsAccum', 'InPlanRothDeemedYearsDistr']
        if 'minimum amount' in p:
            candidates += ['InPlanRothOtherProvMinAmnt']
        if 'maximum number' in p:
            candidates += ['InPlanRothTransf_LimitsMaxPY', 'IPRT_LimitsMaxPYIRR', 'IPRT_LimitsMaxPYIRT']
        # Check specific candidates
        for n in candidates:
            lf = flags.get(n)
            if lf is not None:
                try:
                    txt = (getattr(lf, 'text', None) or '').strip()
                except Exception:
                    txt = ''
                if txt:
                    num = first_num(txt)
                    if num:
                        return num
        # Generic scan for any InPlanRoth* with numeric text and prompt keywords
        kws = []
        if 'age' in p:
            kws.append('age')
        if 'participation' in p:
            kws += ['years', 'part']
        if 'accumulation' in p:
            kws += ['accum', 'years', 'distr']
        if 'amount' in p:
            kws += ['amnt', 'amount', 'min']
        if 'maximum number' in p:
            kws += ['max', 'limits', 'py']
        for name, lf in flags.items():
            name_l = name.lower()
            if not name_l.startswith('inplanroth'):
                continue
            if not any(kw in name_l for kw in kws):
                continue
            try:
                txt = (getattr(lf, 'text', None) or '').strip()
            except Exception:
                txt = ''
            if txt:
                n = first_num(txt)
                if n:
                    return n
        return None

    # Auto-detect Map and Data Points if not provided
    map_path = Path.home() / 'Desktop' / 'Test Folder' / 'Map Updated 8152025.xlsx'
    datapoints_path = Path.home() / 'Desktop' / 'Test Folder' / 'TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx'

    # Read template rows and map data
    rows = read_xlsx_named_sheet_rows(datapoints_path, 'Plan Express Data Points')
    if not rows:
        raise SystemExit('Could not read Plan Express Data Points sheet')
    header = rows[0]
    header_norm = [h.strip() for h in header]
    try:
        i_prompt = header_norm.index('PROMPT')
    except ValueError:
        i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
        if i_prompt < 0:
            raise SystemExit("Couldn't find PROMPT column in template")
    i_options = header_norm.index('Options Allowed') if 'Options Allowed' in header_norm else -1
    i_page = header_norm.index('Page') if 'Page' in header_norm else -1
    i_seq = header_norm.index('Seq') if 'Seq' in header_norm else -1

    map_data = parse_map_workbook(map_path)
    lov = parse_lov(datapoints_path)

    # Pre-parse all XMLs
    xml_flags: Dict[str, Dict[str, object]] = {}
    for xml_item in xml_items:
        xml_flags[xml_item['name']] = parse_xml_linknames(ET.fromstring(xml_item['content']))

    # Build output header
    column_labels: List[str] = [item['name'] for item in xml_items]
    out_rows = []
    for r in rows[1:]:
        prompt = normalize_text(r[i_prompt] if 0 <= i_prompt < len(r) else '')
        if not prompt:
            continue
        options = (r[i_options] if (0 <= i_options < len(r)) else '').strip()
        page = (r[i_page] if (0 <= i_page < len(r)) else '').strip()
        seq = (r[i_seq] if (0 <= i_seq < len(r)) else '').strip()
        me = map_data.get(prompt)
        values = {}
        for file_name in column_labels:
            flags = xml_flags[file_name]
            val = None
            if me:
                val = choose_value_for_map_entry(me, options, flags, prompt)
                val = _enforce_yes_no(prompt, options, val, flags, me, strict=False)
            if val is None:
                val = fallback_from_lov(page, seq, options, lov)
            if val is None:
                pick = pick_from_options_allowed(options)
                if pick:
                    val = pick
            values[file_name] = val if val is not None else ''
        out_rows.append({'promptText': prompt, 'values': values})

    print(json.dumps({'fileNames': column_labels, 'rows': out_rows}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
