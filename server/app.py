#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import runpy
import tempfile
from pathlib import Path
from typing import List

from flask import Flask, request, jsonify, make_response

app = Flask(__name__)


HERE = Path(__file__).resolve().parent
DEFAULT_WORKING_LOGIC = Path.home() / 'Desktop' / 'Working Logic '
FALLBACK_WORKING_LOGIC = Path.home() / 'Desktop' / 'Test Folder'


def load_working_logic_module():
    candidates = [DEFAULT_WORKING_LOGIC, FALLBACK_WORKING_LOGIC]
    for base in candidates:
        fp = base / 'fill_plan_data.py'
        if fp.exists():
            return runpy.run_path(str(fp))
    raise RuntimeError('Could not find fill_plan_data.py in Working Logic or Test Folder')


@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'ok': True})


@app.route('/process', methods=['POST'])
def process():
    try:
        map_file = request.files.get('map_file')
        datapoints_file = request.files.get('datapoints_file')
        xml_files = request.files.getlist('xml_files') or []
        # Allow using default Map/DataPoints on server when not provided
        use_defaults = not (map_file and datapoints_file)
        if not xml_files:
            # Help debug what we received
            return make_response(jsonify({
                'error': 'Missing required files: xml_files[]',
                'received_form_keys': list(request.form.keys()),
                'received_file_keys': list(request.files.keys()),
            }), 400)

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            if use_defaults:
                # Find default files on Desktop/Test Folder
                default_map = (Path.home() / 'Desktop' / 'Test Folder' / 'Map Updated 8152025.xlsx')
                if not default_map.exists():
                    # Try auto-derived CSV
                    default_map = Path.home() / 'Desktop' / 'Test Folder' / 'Map_AutoDerived.csv'
                default_dp = Path.home() / 'Desktop' / 'Test Folder' / 'TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx'
                if not (default_map.exists() and default_dp.exists()):
                    return make_response(jsonify({'error': 'Default Map/Data Points not found on server. Provide files or place them in Desktop/Test Folder.'}), 400)
                map_path = default_map
                datapoints_path = default_dp
            else:
                map_path = td_path / (map_file.filename or 'map.xlsx')
                datapoints_path = td_path / (datapoints_file.filename or 'datapoints.xlsx')
                map_file.save(str(map_path))
                datapoints_file.save(str(datapoints_path))
            xml_paths: List[Path] = []
            for xf in xml_files:
                p = td_path / (xf.filename or 'file.xml')
                xf.save(str(p))
                xml_paths.append(p)

            mod = load_working_logic_module()
            parse_map_workbook = mod['parse_map_workbook']
            read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
            parse_lov = mod['parse_lov']
            parse_xml_linknames = mod['parse_xml_linknames']
            choose_value_for_map_entry = mod['choose_value_for_map_entry']
            _enforce_yes_no = mod['_enforce_yes_no']
            fallback_from_lov = mod['fallback_from_lov']
            pick_from_options_allowed = mod['pick_from_options_allowed']
            normalize_text = mod['normalize_text']

            rows = read_xlsx_named_sheet_rows(datapoints_path, 'Plan Express Data Points')
            if not rows:
                return make_response(jsonify({'error': 'Could not read Plan Express Data Points sheet'}), 400)
            header = rows[0]
            header_norm = [h.strip() for h in header]
            try:
                i_prompt = header_norm.index('PROMPT')
            except ValueError:
                i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
            i_options = header_norm.index('Options Allowed') if 'Options Allowed' in header_norm else -1
            i_page = header_norm.index('Page') if 'Page' in header_norm else -1
            i_seq = header_norm.index('Seq') if 'Seq' in header_norm else -1

            map_data = parse_map_workbook(map_path)
            lov = parse_lov(datapoints_path)

            file_names = [p.name for p in xml_paths]
            flags_per_file = [parse_xml_linknames(p) for p in xml_paths]

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
                for fname, flags in zip(file_names, flags_per_file):
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
                    values[fname] = val if val is not None else ''
                out_rows.append({'promptText': prompt, 'values': values})

            return jsonify({'fileNames': file_names, 'rows': out_rows})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)


@app.route('/process-json', methods=['POST'])
def process_json():
    """Accepts JSON: { xmlFiles: [{name, content}, ...] } and uses default Map/Data Points on server."""
    try:
        data = request.get_json(silent=True) or {}
        xml_items = data.get('xmlFiles') or []
        if not xml_items:
            return make_response(jsonify({'error': 'Missing xmlFiles'}), 400)

        # Resolve default files
        default_map = (Path.home() / 'Desktop' / 'Test Folder' / 'Map Updated 8152025.xlsx')
        if not default_map.exists():
            default_map = Path.home() / 'Desktop' / 'Test Folder' / 'Map_AutoDerived.csv'
        default_dp = Path.home() / 'Desktop' / 'Test Folder' / 'TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx'
        if not (default_map.exists() and default_dp.exists()):
            return make_response(jsonify({'error': 'Default Map/Data Points not found on server. Place them in Desktop/Test Folder.'}), 400)

        mod = load_working_logic_module()
        parse_map_workbook = mod['parse_map_workbook']
        read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
        parse_lov = mod['parse_lov']
        choose_value_for_map_entry = mod['choose_value_for_map_entry']
        _enforce_yes_no = mod['_enforce_yes_no']
        fallback_from_lov = mod['fallback_from_lov']
        pick_from_options_allowed = mod['pick_from_options_allowed']
        normalize_text = mod['normalize_text']

        # Read template rows
        rows = read_xlsx_named_sheet_rows(default_dp, 'Plan Express Data Points')
        header = rows[0]
        header_norm = [h.strip() for h in header]
        try:
            i_prompt = header_norm.index('PROMPT')
        except ValueError:
            i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
        i_options = header_norm.index('Options Allowed') if 'Options Allowed' in header_norm else -1
        i_page = header_norm.index('Page') if 'Page' in header_norm else -1
        i_seq = header_norm.index('Seq') if 'Seq' in header_norm else -1

        map_data = parse_map_workbook(default_map)
        lov = parse_lov(default_dp)

        # Parse XML contents using the Working Logic helper (requires a temp file path)
        # We will inline a simple XML parser for LinkName/PlanData here to avoid temp files
        import xml.etree.ElementTree as ET
        from dataclasses import dataclass

        @dataclass
        class LinkNameFlag:
            selected: int
            insert: int
            text: str | None = None

        def parse_xml_flags_from_string(xml_str: str):
            flags = {}
            root = ET.fromstring(xml_str)
            for ln in root.findall('.//LinkName'):
                name = (ln.get('value') or '').strip()
                if not name: continue
                sel = int(ln.get('selected') or '0') if (ln.get('selected') or '0').isdigit() else 0
                ins = int(ln.get('insert') or '0') if (ln.get('insert') or '0').isdigit() else 0
                txt = (ln.text or '').strip() or None
                flags[name] = LinkNameFlag(sel, ins, txt)
            for pd in root.findall('.//PlanData'):
                name = (pd.get('FieldName') or '').strip()
                if not name: continue
                txt = (pd.text or '').strip() or None
                if name not in flags:
                    flags[name] = LinkNameFlag(1, 0, txt)
                elif txt and not flags[name].text:
                    flags[name].text = txt
            return flags

        file_names = [item.get('name') or f'file_{i}.xml' for i, item in enumerate(xml_items)]
        flags_per_file = [parse_xml_flags_from_string(item.get('content') or '') for item in xml_items]

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
            for fname, flags in zip(file_names, flags_per_file):
                val = None
                if me:
                    val = mod['choose_value_for_map_entry'](me, options, flags, prompt)
                    val = mod['_enforce_yes_no'](prompt, options, val, flags, me, strict=False)
                if val is None:
                    val = mod['fallback_from_lov'](page, seq, options, lov)
                if val is None:
                    pick = mod['pick_from_options_allowed'](options)
                    if pick:
                        val = pick
                values[fname] = val if val is not None else ''
            out_rows.append({'promptText': prompt, 'values': values})

        return jsonify({'fileNames': file_names, 'rows': out_rows})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)


if __name__ == '__main__':
    port = int(os.environ.get('PLAN_EXPRESS_PORT', '8787'))
    app.run(host='127.0.0.1', port=port)
