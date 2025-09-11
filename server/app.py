#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import tempfile
from io import TextIOWrapper
from pathlib import Path
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify, make_response
from .logic import (
    normalize_text,
    parse_xml_flags_from_string,
    choose_value_for_map_entry,
    enforce_yes_no,
    pick_from_options_allowed,
)

app = Flask(__name__)


HERE = Path(__file__).resolve().parent


def load_map_entries() -> Optional[List[Dict[str, Any]]]:
    """Load map entries from user store (~/.xml-prompt-filler) or bundled maps."""
    user_path = Path.home() / '.xml-prompt-filler' / 'defaultMap.json'
    for json_path in (user_path, HERE.parent / 'maps' / 'defaultMap.json'):
        try:
            if json_path.exists():
                data = json.loads(json_path.read_text())
                if isinstance(data, list):
                    out: List[Dict[str, Any]] = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        out.append({
                            'prompt': str(item.get('prompt', '')),
                            'linknames': str(item.get('linknames', '')),
                            'quick': str(item.get('quick', '')),
                        })
                    return out
        except Exception:
            continue
    return None


def load_options_by_prompt() -> Optional[Dict[str, str]]:
    """Load options mapping from user store or bundled maps."""
    user_path = Path.home() / '.xml-prompt-filler' / 'optionsByPrompt.json'
    for json_path in (user_path, HERE.parent / 'maps' / 'optionsByPrompt.json'):
        try:
            if json_path.exists():
                data = json.loads(json_path.read_text())
                if isinstance(data, dict):
                    return {str(k): str(v or '') for k, v in data.items()}
                if isinstance(data, list):
                    out: Dict[str, str] = {}
                    for item in data:
                        if isinstance(item, dict) and 'key' in item:
                            out[str(item.get('key') or '')] = str(item.get('value') or '')
                    return out
        except Exception:
            continue
    return None


def _parse_csv_map(file_storage) -> List[Dict[str, str]]:
    """Parse an uploaded Map CSV into entries: [{prompt, linknames, quick}].
    Expects headers including Prompt and Proposed LinkName. Quick is optional.
    """
    # Decode with utf-8-sig to drop BOM if present
    text = file_storage.read().decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(text.splitlines())
    # Normalize header keys
    def get_row_val(row: Dict[str, str], *candidates: str) -> str:
        for k in row.keys():
            for cand in candidates:
                if k.strip().lower() == cand.strip().lower():
                    return str(row.get(k) or '').strip()
        return ''
    out: List[Dict[str, str]] = []
    for row in reader:
        prompt = get_row_val(row, 'Prompt')
        linknames = get_row_val(row, 'Proposed LinkName', 'Proposed Linkname', 'LinkNames', 'Linknames')
        quick = get_row_val(row, 'Quick', 'Quick Text')
        if not prompt:
            continue
        out.append({'prompt': prompt, 'linknames': linknames, 'quick': quick})
    return out


def _parse_csv_options(file_storage) -> Dict[str, str]:
    """Parse uploaded Data Points CSV into a mapping: { PROMPT -> Options Allowed }"""
    text = file_storage.read().decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(text.splitlines())
    # Identify columns by case-insensitive names
    fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
    def key_for(names: List[str]) -> Optional[str]:
        for want in names:
            for fn in fieldnames:
                if fn.lower() == want.lower():
                    return fn
        return None
    k_prompt = key_for(['PROMPT', 'Prompt'])
    k_options = key_for(['Options Allowed', 'Options'])
    if not k_prompt or not k_options:
        raise ValueError('CSV missing required columns: PROMPT and Options Allowed')
    out: Dict[str, str] = {}
    for row in reader:
        p = str(row.get(k_prompt) or '').strip()
        if not p:
            continue
        oa = str(row.get(k_options) or '').strip()
        out[p] = oa
    return out


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

        # Build flags from uploaded XMLs
        file_names: List[str] = []
        flags_per_file: List[Dict[str, Any]] = []
        for xf in xml_files:
            name = xf.filename or 'file.xml'
            try:
                content = xf.read().decode('utf-8')
            except UnicodeDecodeError:
                content = xf.read().decode('latin1', errors='ignore')
            file_names.append(name)
            flags_per_file.append(parse_xml_flags_from_string(content))

        # Decide data source
        if use_defaults:
            packaged_map = load_map_entries()
            packaged_opts = load_options_by_prompt()
            if not (packaged_map and packaged_opts):
                return make_response(jsonify({'error': 'No packaged Map/Options found. Upload CSVs for map_file and datapoints_file.'}), 400)
            entries = packaged_map
            options_by_prompt = packaged_opts
        else:
            try:
                entries = _parse_csv_map(map_file)
                options_by_prompt = _parse_csv_options(datapoints_file)
            except Exception as e:
                return make_response(jsonify({'error': f'Failed to parse uploaded CSV files: {e}. Please upload CSV, not Excel.'}), 400)

        # Build normalized map
        map_data: Dict[str, Dict[str, Any]] = {}
        for e in entries:
            ptxt = normalize_text(str(e.get('prompt') or ''))
            if ptxt:
                map_data[ptxt] = e

        out_rows: List[Dict[str, Any]] = []
        for e in entries:
            orig_prompt = str(e.get('prompt') or '')
            prompt = normalize_text(orig_prompt)
            options = options_by_prompt.get(orig_prompt, '')
            me = map_data.get(prompt)
            values = {}
            for fname, flags in zip(file_names, flags_per_file):
                val = None
                if me:
                    val = choose_value_for_map_entry(me, options, flags, prompt)
                    val = enforce_yes_no(prompt, options, val, flags, me, strict=False)
                if val is None:
                    pick = pick_from_options_allowed(options)
                    if pick:
                        val = pick
                values[fname] = val if val is not None else ''
            out_rows.append({'promptText': orig_prompt, 'values': values})

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

        # Prefer packaged/user assets
        packaged_map = load_map_entries()
        packaged_opts = load_options_by_prompt()
        if not (packaged_map and packaged_opts):
            return make_response(jsonify({'error': 'No packaged Map/Options found. Use /process with CSV uploads.'}), 400)

        file_names = [item.get('name') or f'file_{i}.xml' for i, item in enumerate(xml_items)]
        flags_per_file = [parse_xml_flags_from_string(item.get('content') or '') for item in xml_items]

        map_data = {}
        for e in packaged_map:
            ptxt = normalize_text(str(e.get('prompt') or ''))
            if ptxt:
                map_data[ptxt] = e

        out_rows: List[Dict[str, Any]] = []
        for e in packaged_map:
            orig_prompt = str(e.get('prompt') or '')
            prompt = normalize_text(orig_prompt)
            options = packaged_opts.get(orig_prompt, '')
            me = map_data.get(prompt)
            values = {}
            for fname, flags in zip(file_names, flags_per_file):
                val = None
                if me:
                    val = choose_value_for_map_entry(me, options, flags, prompt)
                    val = enforce_yes_no(prompt, options, val, flags, me, strict=False)
                if val is None:
                    pick = pick_from_options_allowed(options)
                    if pick:
                        val = pick
                values[fname] = val if val is not None else ''
            out_rows.append({'promptText': orig_prompt, 'values': values})

        return jsonify({'fileNames': file_names, 'rows': out_rows})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)


@app.route('/admin/import-json', methods=['POST'])
def import_json():
    """Persist Map/Options JSON to user store (~/.xml-prompt-filler). Body: { map: [...], options: {...} }"""
    try:
        data = request.get_json(silent=True) or {}
        entries = data.get('map')
        options = data.get('options')
        if not isinstance(entries, list) or not isinstance(options, dict):
            return make_response(jsonify({'error': 'Body must include map: [] and options: {}'}), 400)
        store_dir = Path.home() / '.xml-prompt-filler'
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / 'defaultMap.json').write_text(json.dumps(entries, indent=2))
        (store_dir / 'optionsByPrompt.json').write_text(json.dumps(options, indent=2))
        return jsonify({'ok': True, 'saved': str(store_dir)})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)


@app.route('/admin/import-csv', methods=['POST'])
def import_csv():
    """Persist uploaded CSVs (map_csv, datapoints_csv) as JSON in user store."""
    try:
        map_csv = request.files.get('map_csv')
        dp_csv = request.files.get('datapoints_csv')
        if not (map_csv and dp_csv):
            return make_response(jsonify({'error': 'Upload map_csv and datapoints_csv files (CSV only)'}), 400)
        entries = _parse_csv_map(map_csv)
        options = _parse_csv_options(dp_csv)
        store_dir = Path.home() / '.xml-prompt-filler'
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / 'defaultMap.json').write_text(json.dumps(entries, indent=2))
        (store_dir / 'optionsByPrompt.json').write_text(json.dumps(options, indent=2))
        return jsonify({'ok': True, 'saved': str(store_dir), 'entries': len(entries), 'options': len(options)})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)


if __name__ == '__main__':
    port = int(os.environ.get('PLAN_EXPRESS_PORT', '8787'))
    app.run(host='127.0.0.1', port=port)
