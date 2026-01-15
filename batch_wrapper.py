"""
Wrapper around batch_fill.py for GUI integration.
Provides progress callbacks and returns CSV data for preview.
"""
from __future__ import annotations

import csv
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
import runpy


@dataclass
class BatchProgress:
    """Progress information for GUI updates."""
    phase: str           # 'init', 'parsing_xml', 'processing_rows', 'writing_csv', 'complete', 'error'
    current: int         # Current item number
    total: int           # Total items
    message: str         # Human-readable status
    xml_name: Optional[str] = None  # Current XML being processed


ProgressCallback = Callable[[BatchProgress], None]


@dataclass
class BatchResult:
    """Result from batch processing."""
    success: bool
    message: str
    csv_path: Optional[Path] = None
    rows: Optional[List[List[str]]] = None  # For preview
    xml_count: int = 0
    row_count: int = 0


def auto_detect_files(input_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Auto-detect Map and DataPoints files in the input directory."""
    map_file = None
    datapoints_file = None

    for p in input_dir.iterdir():
        if p.suffix.lower() != '.xlsx':
            continue
        name_lower = p.name.lower()
        if 'map' in name_lower and map_file is None:
            map_file = p
        if ('data points' in name_lower or 'tpa' in name_lower) and datapoints_file is None:
            datapoints_file = p

    return map_file, datapoints_file


def count_xml_files(input_dir: Path) -> int:
    """Count XML files in the input directory."""
    return len([p for p in input_dir.iterdir() if p.suffix.lower() == '.xml'])


def run_batch(
    input_dir: Path,
    map_path: Optional[Path] = None,
    datapoints_path: Optional[Path] = None,
    out_csv_path: Optional[Path] = None,
    progress_callback: Optional[ProgressCallback] = None
) -> BatchResult:
    """
    Run the batch fill process with progress reporting.

    Args:
        input_dir: Directory containing XML files
        map_path: Path to Map XLSX (auto-detected if None)
        datapoints_path: Path to Data Points XLSX (auto-detected if None)
        out_csv_path: Output CSV path (defaults to input_dir/plan_express_filled_batch.csv)
        progress_callback: Function to call with progress updates

    Returns:
        BatchResult with success status, message, and CSV data
    """
    def report(phase: str, current: int, total: int, message: str, xml_name: str = None):
        if progress_callback:
            progress_callback(BatchProgress(phase, current, total, message, xml_name))

    try:
        report('init', 0, 100, 'Initializing...')

        # Load functions from fill_plan_data.py
        core_dir = Path(__file__).parent / 'core'
        mod = runpy.run_path(str(core_dir / 'fill_plan_data.py'))
        parse_map_workbook = mod['parse_map_workbook']
        read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
        parse_lov = mod['parse_lov']
        parse_xml_linknames = mod['parse_xml_linknames']
        choose_value_for_map_entry = mod['choose_value_for_map_entry']
        _enforce_yes_no = mod['_enforce_yes_no']
        fallback_from_lov = mod['fallback_from_lov']
        pick_from_options_allowed = mod['pick_from_options_allowed']
        normalize_text = mod['normalize_text']

        # Auto-detect files if not provided
        if not map_path:
            cands = sorted([p for p in input_dir.iterdir() if p.suffix.lower()=='.xlsx' and 'map' in p.name.lower()])
            if not cands:
                return BatchResult(False, 'Map workbook not found. Please select a Map file.')
            map_path = cands[0]

        if not datapoints_path:
            cands = sorted([p for p in input_dir.iterdir() if p.suffix.lower()=='.xlsx' and ('data points' in p.name.lower() or 'tpa' in p.name.lower())])
            if not cands:
                return BatchResult(False, 'Data Points workbook not found. Please select a Data Points file.')
            datapoints_path = cands[0]

        report('init', 10, 100, f'Loading template from {datapoints_path.name}...')

        # Read template rows and map data
        rows = read_xlsx_named_sheet_rows(datapoints_path, 'Plan Express Data Points')
        if not rows:
            return BatchResult(False, 'Could not read Plan Express Data Points sheet')

        header = rows[0]
        header_norm = [h.strip() for h in header]
        try:
            i_prompt = header_norm.index('PROMPT')
        except ValueError:
            i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
            if i_prompt < 0:
                return BatchResult(False, "Couldn't find PROMPT column in template")

        i_options = header_norm.index('Options Allowed') if 'Options Allowed' in header_norm else -1
        i_page = header_norm.index('Page') if 'Page' in header_norm else -1
        i_seq = header_norm.index('Seq') if 'Seq' in header_norm else -1

        report('init', 20, 100, f'Loading map from {map_path.name}...')
        map_data = parse_map_workbook(map_path)
        lov = parse_lov(datapoints_path)

        # Collect XML files
        xml_files = sorted([p for p in input_dir.iterdir() if p.suffix.lower() == '.xml'])
        if not xml_files:
            return BatchResult(False, f'No XML files found in {input_dir}')

        total_xml = len(xml_files)
        report('parsing_xml', 0, total_xml, f'Found {total_xml} XML files. Parsing...')

        # Pre-parse all XMLs with progress
        xml_flags: Dict[str, Dict[str, object]] = {}
        for idx, xml in enumerate(xml_files):
            report('parsing_xml', idx + 1, total_xml, f'Parsing XML {idx + 1}/{total_xml}', xml.name)
            xml_flags[xml.stem] = parse_xml_linknames(xml)

        # Build output header with de-duplication
        column_labels: List[str] = []
        xmls_dedup: List[Path] = []
        rids_for_cols: List[str] = []
        seen_rids: set = set()

        for xml in xml_files:
            flags = xml_flags.get(xml.stem, {})
            rid_flag = flags.get('ReportingID') if isinstance(flags, dict) else None
            rid_text = None
            if rid_flag is not None:
                try:
                    rid_text = (getattr(rid_flag, 'text', None) or '').strip()
                except Exception:
                    rid_text = None

            # Get friendly name
            friendly = None
            if isinstance(flags, dict):
                name_flag = flags.get('1stAdoptERName')
                if name_flag is not None:
                    try:
                        friendly = (getattr(name_flag, 'text', None) or '').strip()
                    except Exception:
                        friendly = None
            if not friendly:
                try:
                    root = ET.parse(xml).getroot()
                    pn = root.find('.//ProjectName')
                    if pn is not None and pn.text:
                        friendly = pn.text.strip()
                except Exception:
                    friendly = None

            # Compose label
            if friendly and rid_text:
                label = f"{friendly} [{rid_text}]"
            else:
                label = friendly or rid_text or xml.stem

            # De-dupe
            dedupe_key = rid_text or xml.stem
            if dedupe_key in seen_rids:
                continue
            seen_rids.add(dedupe_key)
            xmls_dedup.append(xml)
            column_labels.append(label)
            rids_for_cols.append(rid_text or '')

        # Define helper functions (same as original)
        def _is_vesting_schedule_prompt(pt: str) -> bool:
            p = (pt or '').strip().lower()
            return ('vesting schedule' in p) and ('describe' not in p)

        def _is_apply_schedule_prompt(pt: str) -> bool:
            p = (pt or '').strip().lower()
            return p.startswith('which vesting schedule will apply')

        def _is_vesting_describe_prompt(pt: str) -> bool:
            return normalize_text(pt).lower().startswith('please describe your vesting schedule')

        def _extract_vesting_other_text(flags: Dict[str, object]) -> Optional[str]:
            for k in ('OtherVestProvisions', 'VestOtherMatch'):
                lf = flags.get(k)
                if lf is not None:
                    try:
                        t = (getattr(lf, 'text', None) or '').strip()
                    except Exception:
                        t = ''
                    if t:
                        return t
            for name, lf in flags.items():
                if ('Vest' in name or 'Vesting' in name) and 'Other' in name:
                    try:
                        t = (getattr(lf, 'text', None) or '').strip()
                    except Exception:
                        t = ''
                    if t:
                        return t
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
            if 'match' in qt:
                lf = flags.get('NAVestMatch')
                try:
                    if lf is not None and getattr(lf, 'selected', 0) == 1:
                        return True
                except Exception:
                    pass
                lf = flags.get('Vest100Match')
                try:
                    if lf is not None and getattr(lf, 'selected', 0) == 1:
                        return True
                except Exception:
                    pass
            if ('non elective' in qt) or ('non-elective' in qt) or ('profit' in qt):
                for name in ('100VestingNEContr', 'Vest100NEContr'):
                    lf = flags.get(name)
                    try:
                        if lf is not None and getattr(lf, 'selected', 0) == 1:
                            return True
                    except Exception:
                        pass
            if 'safe harbor' in qt or 'safeharbor' in qt or 'qaca' in qt:
                lf = flags.get('VestNAQACA')
                try:
                    if lf is not None and getattr(lf, 'selected', 0) == 1:
                        return True
                except Exception:
                    pass
            return False

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
            def first_num(txt: str) -> Optional[str]:
                import re
                m = re.search(r"(\d{1,4}(?:[.,]\d{1,2})?)", txt)
                return m.group(1) if m else None
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

        # Build output
        out_header = ['Page', 'Seq', 'PROMPT', 'Quick Text Data Point', 'Options Allowed'] + column_labels + ['Comments']
        out_rows: List[List[str]] = [out_header]

        # Tracking dictionaries
        prior_vesting_choice: Dict[tuple, str] = {}
        prior_base_vest_choice: Dict[tuple, str] = {}
        prior_base_vest_quick: Dict[tuple, str] = {}
        filled_values: Dict[tuple, str] = {}
        elig_method_by_page: Dict[tuple, str] = {}

        # Pre-pass for vesting
        for r in rows[1:]:
            prompt = normalize_text(r[i_prompt] if 0 <= i_prompt < len(r) else '')
            if not _is_vesting_schedule_prompt(prompt) or _is_apply_schedule_prompt(prompt) or _is_vesting_describe_prompt(prompt):
                continue
            options = (r[i_options] if (0 <= i_options < len(r)) else '').strip()
            page = (r[i_page] if (0 <= i_page < len(r)) else '').strip()
            pnorm = (prompt or '').lower()
            if 'pensionpal id' in pnorm:
                continue
            me = map_data.get(prompt) if prompt else None
            for xml in xml_files:
                flags = xml_flags[xml.stem]
                val: Optional[str] = None
                if me:
                    val = choose_value_for_map_entry(me, options, flags, prompt)
                    val = _enforce_yes_no(prompt, options, val, flags, me, True)
                if val is None:
                    seq = (r[i_seq] if (0 <= i_seq < len(r)) else '').strip()
                    val = fallback_from_lov(page, seq, options, lov)
                if val is None:
                    pick = pick_from_options_allowed(options)
                    if pick:
                        val = pick
                choice = (val or '').strip()
                me_quick = (me.get('quick') if isinstance(me, dict) else '') or ''
                if choice.lower() == 'other' and _is_immediate_for_money_type(flags, me_quick):
                    choice = 'Immediate'
                prior_base_vest_choice[(page, xml.stem)] = choice
                prior_base_vest_quick[(page, xml.stem)] = me_quick

        # Main processing loop with progress
        total_rows = len(rows) - 1
        report('processing_rows', 0, total_rows, f'Processing {total_rows} template rows...')

        for row_idx in range(1, len(rows)):
            if row_idx % 50 == 0:  # Report every 50 rows to avoid too many updates
                report('processing_rows', row_idx, total_rows, f'Processing row {row_idx}/{total_rows}')

            r = rows[row_idx]
            prompt = normalize_text(r[i_prompt] if 0 <= i_prompt < len(r) else '')
            options = (r[i_options] if (0 <= i_options < len(r)) else '').strip()
            page = (r[i_page] if (0 <= i_page < len(r)) else '').strip()
            seq = (r[i_seq] if (0 <= i_seq < len(r)) else '').strip()

            me = map_data.get(prompt) if prompt else None
            quick_text = ''
            if me and isinstance(me, dict):
                quick_text = str(me.get('quick') or '')

            row_out = [page, seq, prompt, quick_text, options]

            for col_idx, xml in enumerate(xmls_dedup):
                flags = xml_flags[xml.stem]
                val: Optional[str] = None
                source: str = 'none'

                if me:
                    val_from_map = choose_value_for_map_entry(me, options, flags, prompt)
                    val = _enforce_yes_no(prompt, options, val_from_map, flags, me, True)
                    if val is not None:
                        source = 'strict'

                if val is None:
                    v2 = fallback_from_lov(page, seq, options, lov)
                    if v2 is not None:
                        val = v2
                        source = 'lov'

                if val is None:
                    pick = pick_from_options_allowed(options)
                    if pick:
                        val = pick
                        source = 'options'

                gate_ref = _parse_gate_ref(options)
                if gate_ref is not None:
                    g_page, g_seq = gate_ref
                    gate = filled_values.get((g_page, g_seq, xml.stem), '').strip().lower()
                    if gate == 'yes' and (not val or val.strip().lower().startswith('if y')):
                        num = _extract_numeric_for_prompt(prompt, flags)
                        if num is not None:
                            val = num
                            if source != 'strict':
                                source = 'xml_infer'

                if _is_vesting_schedule_prompt(prompt):
                    me_quick = (me.get('quick') if isinstance(me, dict) else '') or ''
                    choice = (val or '').strip()
                    if choice.lower() == 'other' and _is_immediate_for_money_type(flags, me_quick):
                        choice = 'Immediate'
                        if source != 'strict':
                            source = 'xml_infer'
                        val = choice or val
                    prior_vesting_choice[(page, xml.stem)] = choice
                    if not _is_apply_schedule_prompt(prompt):
                        prior_base_vest_choice[(page, xml.stem)] = choice
                        prior_base_vest_quick[(page, xml.stem)] = me_quick
                elif _is_vesting_describe_prompt(prompt):
                    prev = prior_vesting_choice.get((page, xml.stem), '').strip().lower()
                    if prev == 'other' or prev.startswith('other '):
                        txt = _extract_vesting_other_text(flags)
                        if txt is not None and txt != '':
                            val = txt
                        else:
                            ref_page = None
                            try:
                                me_quick = (me.get('quick') if isinstance(me, dict) else '') or ''
                                import re as _re
                                m = _re.search(r'page\s+(\d+)\s+seq\s+(\d+)', me_quick, _re.IGNORECASE)
                                if m:
                                    ref_page = m.group(1).strip()
                            except Exception:
                                ref_page = None
                            base = ''
                            if ref_page:
                                base = prior_base_vest_choice.get((ref_page, xml.stem), '').strip()
                            if not base:
                                base = prior_base_vest_choice.get((page, xml.stem), '').strip()
                            if (not base or base.lower() == 'other'):
                                q = prior_base_vest_quick.get((page, xml.stem), '')
                                if _is_immediate_for_money_type(flags, q):
                                    base = 'Immediate'
                            if not base:
                                k = row_idx - 1
                                while k >= 1 and not base:
                                    r_prev = rows[k]
                                    pr_prev = normalize_text(r_prev[i_prompt] if 0 <= i_prompt < len(r_prev) else '')
                                    if _is_vesting_schedule_prompt(pr_prev) and not _is_apply_schedule_prompt(pr_prev):
                                        prev_page = (r_prev[i_page] if (0 <= i_page < len(r_prev)) else '').strip()
                                        base = prior_base_vest_choice.get((prev_page, xml.stem), '').strip()
                                        if not base or base.lower() == 'other':
                                            q = prior_base_vest_quick.get((prev_page, xml.stem), '')
                                            if _is_immediate_for_money_type(flags, q):
                                                base = 'Immediate'
                                        break
                                    k -= 1
                            val = base
                            if source != 'strict' and base:
                                source = 'xml_infer'
                    else:
                        val = ''

                try:
                    pnorm = (prompt or '').strip().lower()
                except Exception:
                    pnorm = ''
                if 'eligibility computation method' in pnorm:
                    elig_method_by_page[(page, xml.stem)] = (val or '').strip()
                if ('minimum service hours required to become eligible' in pnorm) and (val or '').strip():
                    meth = elig_method_by_page.get((page, xml.stem), '')
                    if isinstance(meth, str) and ('elapsed' in meth.lower()):
                        val = 'Elapsed'

                filled_values[(page, seq, xml.stem)] = (val or '').strip()
                row_out.append(val or '')

            row_out.append('')  # Comments column
            out_rows.append(row_out)

        # Write CSV
        report('writing_csv', 0, 1, 'Writing CSV file...')

        if not out_csv_path:
            out_csv_path = input_dir / 'plan_express_filled_batch.csv'

        out_csv_path.parent.mkdir(parents=True, exist_ok=True)
        with out_csv_path.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            for r in out_rows:
                w.writerow(r)

        report('complete', 100, 100, f'Complete! Wrote {len(xmls_dedup)} plans, {len(out_rows)-1} rows.')

        return BatchResult(
            success=True,
            message=f'Successfully processed {len(xmls_dedup)} XML files with {len(out_rows)-1} template rows.',
            csv_path=out_csv_path,
            rows=out_rows,
            xml_count=len(xmls_dedup),
            row_count=len(out_rows) - 1
        )

    except SystemExit as e:
        msg = str(e) if str(e) else 'Unknown error'
        report('error', 0, 0, msg)
        return BatchResult(False, msg)
    except Exception as e:
        msg = f'Error: {str(e)}'
        report('error', 0, 0, msg)
        return BatchResult(False, msg)
