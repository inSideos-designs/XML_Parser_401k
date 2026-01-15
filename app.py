"""
Plan Express Batch Filler - Web GUI
Flask application with HTMX for real-time progress and file management.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import Optional

from flask import Flask, render_template, request, jsonify, Response, send_file

from batch_wrapper import run_batch, BatchProgress, BatchResult, auto_detect_files, count_xml_files

app = Flask(__name__)

# Configuration
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'history.db'
DEFAULT_MAP_PATH = BASE_DIR / 'Map Updated 8152025.xlsx'
ALLOWED_ROOTS = [Path.home() / 'Desktop', Path.home() / 'Documents', Path.home()]

# Global state for progress tracking
progress_queues: dict[str, Queue] = {}
job_results: dict[str, BatchResult] = {}


# Database setup
def init_db():
    """Initialize SQLite database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS batch_runs (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT CHECK(status IN ('pending', 'running', 'completed', 'failed')),
                input_dir TEXT NOT NULL,
                map_path TEXT,
                datapoints_path TEXT,
                out_csv_path TEXT,
                xml_count INTEGER,
                row_count INTEGER,
                error_message TEXT
            )
        ''')
        conn.commit()


def save_run(run_id: str, input_dir: str, map_path: str = None, datapoints_path: str = None,
             out_csv_path: str = None, status: str = 'pending'):
    """Save a batch run to history."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO batch_runs (id, input_dir, map_path, datapoints_path, out_csv_path, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (run_id, input_dir, map_path, datapoints_path, out_csv_path, status))
        conn.commit()


def update_run(run_id: str, status: str, xml_count: int = None, row_count: int = None,
               error_message: str = None):
    """Update a batch run status."""
    with sqlite3.connect(DB_PATH) as conn:
        if status in ('completed', 'failed'):
            conn.execute('''
                UPDATE batch_runs SET status=?, completed_at=?, xml_count=?, row_count=?, error_message=?
                WHERE id=?
            ''', (status, datetime.now().isoformat(), xml_count, row_count, error_message, run_id))
        else:
            conn.execute('UPDATE batch_runs SET status=? WHERE id=?', (status, run_id))
        conn.commit()


def get_recent_runs(limit: int = 20) -> list[dict]:
    """Get recent batch runs."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT * FROM batch_runs ORDER BY created_at DESC LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(row) for row in rows]


def get_run(run_id: str) -> Optional[dict]:
    """Get a specific batch run."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM batch_runs WHERE id=?', (run_id,)).fetchone()
        return dict(row) if row else None


# Initialize database on startup
init_db()


# Routes
@app.route('/')
def index():
    """Main page with batch form."""
    default_map = str(DEFAULT_MAP_PATH) if DEFAULT_MAP_PATH.exists() else ''
    return render_template('index.html', default_map=default_map)


@app.route('/api/files/list')
def list_files():
    """List directory contents for file browser."""
    path_str = request.args.get('path', str(Path.home() / 'Desktop'))
    path = Path(path_str)

    # Security check
    if not any(path == root or (path.exists() and root in path.parents) for root in ALLOWED_ROOTS):
        if path != Path.home() and path not in ALLOWED_ROOTS:
            return jsonify({'error': 'Access denied'}), 403

    if not path.exists():
        return jsonify({'error': 'Path not found'}), 404

    if not path.is_dir():
        return jsonify({'error': 'Not a directory'}), 400

    items = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith('.'):
                continue  # Skip hidden files
            items.append({
                'name': item.name,
                'path': str(item),
                'is_dir': item.is_dir(),
                'extension': item.suffix.lower() if item.is_file() else None,
            })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403

    return jsonify({
        'current_path': str(path),
        'parent_path': str(path.parent) if path.parent != path else None,
        'items': items
    })


@app.route('/api/files/validate')
def validate_path():
    """Validate a file/folder path."""
    path_str = request.args.get('path', '')
    path = Path(path_str)
    return jsonify({
        'exists': path.exists(),
        'is_dir': path.is_dir() if path.exists() else False,
        'is_file': path.is_file() if path.exists() else False,
        'xml_count': count_xml_files(path) if path.is_dir() else 0
    })


@app.route('/api/files/autodetect')
def autodetect_files():
    """Auto-detect Map and DataPoints files in a directory."""
    path_str = request.args.get('path', '')
    path = Path(path_str)

    if not path.exists() or not path.is_dir():
        return jsonify({'error': 'Invalid directory'}), 400

    map_file, datapoints_file = auto_detect_files(path)

    # Use default map if none found in folder
    if not map_file and DEFAULT_MAP_PATH.exists():
        map_file = DEFAULT_MAP_PATH

    return jsonify({
        'map_path': str(map_file) if map_file else None,
        'datapoints_path': str(datapoints_file) if datapoints_file else None,
        'xml_count': count_xml_files(path)
    })


@app.route('/api/batch/start', methods=['POST'])
def start_batch():
    """Start a new batch processing job."""
    data = request.json or {}

    input_dir = data.get('input_dir', '').strip()
    if not input_dir:
        return jsonify({'error': 'Input directory is required'}), 400

    input_path = Path(input_dir)
    if not input_path.exists() or not input_path.is_dir():
        return jsonify({'error': 'Invalid input directory'}), 400

    job_id = str(uuid.uuid4())[:8]
    map_path = data.get('map_path', '').strip() or None
    datapoints_path = data.get('datapoints_path', '').strip() or None
    out_csv_path = data.get('out_csv_path', '').strip() or None

    # Save to history
    save_run(job_id, input_dir, map_path, datapoints_path, out_csv_path, 'running')

    # Create progress queue
    progress_queues[job_id] = Queue()

    def run_in_background():
        def on_progress(p: BatchProgress):
            progress_queues[job_id].put({
                'type': 'progress',
                'phase': p.phase,
                'current': p.current,
                'total': p.total,
                'message': p.message,
                'xml_name': p.xml_name
            })

        result = run_batch(
            input_dir=input_path,
            map_path=Path(map_path) if map_path else None,
            datapoints_path=Path(datapoints_path) if datapoints_path else None,
            out_csv_path=Path(out_csv_path) if out_csv_path else None,
            progress_callback=on_progress
        )

        job_results[job_id] = result

        if result.success:
            update_run(job_id, 'completed', result.xml_count, result.row_count)
            progress_queues[job_id].put({
                'type': 'complete',
                'success': True,
                'message': result.message,
                'csv_path': str(result.csv_path) if result.csv_path else None,
                'xml_count': result.xml_count,
                'row_count': result.row_count
            })
        else:
            update_run(job_id, 'failed', error_message=result.message)
            progress_queues[job_id].put({
                'type': 'complete',
                'success': False,
                'message': result.message
            })

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/api/batch/progress/<job_id>')
def batch_progress(job_id):
    """SSE endpoint for batch progress."""
    def generate():
        q = progress_queues.get(job_id)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown job'})}\n\n"
            return

        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get('type') == 'complete':
                    break
            except Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/batch/preview/<job_id>')
def batch_preview(job_id):
    """Get CSV preview for a completed job."""
    result = job_results.get(job_id)
    if not result or not result.rows:
        return jsonify({'error': 'No preview available'}), 404

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    start = (page - 1) * per_page + 1  # Skip header
    end = start + per_page

    return jsonify({
        'headers': result.rows[0] if result.rows else [],
        'rows': result.rows[start:end] if result.rows else [],
        'total_rows': len(result.rows) - 1 if result.rows else 0,
        'page': page,
        'per_page': per_page,
        'has_more': end < len(result.rows) if result.rows else False
    })


@app.route('/api/batch/download/<job_id>')
def download_csv(job_id):
    """Download the generated CSV file."""
    result = job_results.get(job_id)
    if not result or not result.csv_path:
        return jsonify({'error': 'No file available'}), 404

    return send_file(result.csv_path, as_attachment=True, download_name=result.csv_path.name)


@app.route('/api/history')
def get_history():
    """Get batch run history."""
    runs = get_recent_runs()
    return jsonify(runs)


@app.route('/api/history/<run_id>')
def get_history_item(run_id):
    """Get a specific history item."""
    run = get_run(run_id)
    if not run:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(run)


@app.route('/api/history/<run_id>/rerun', methods=['POST'])
def rerun_batch(run_id):
    """Re-run a previous batch with the same settings."""
    run = get_run(run_id)
    if not run:
        return jsonify({'error': 'Not found'}), 404

    # Create a new job with the same settings
    return start_batch()


@app.route('/api/history/<run_id>', methods=['DELETE'])
def delete_history_item(run_id):
    """Delete a history item."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM batch_runs WHERE id=?', (run_id,))
        conn.commit()
    return jsonify({'success': True})


# Template partials for HTMX
@app.route('/partials/history')
def history_partial():
    """Render history list partial."""
    runs = get_recent_runs()
    return render_template('history.html', runs=runs)


@app.route('/partials/file-browser')
def file_browser_partial():
    """Render file browser partial."""
    path_str = request.args.get('path', str(Path.home() / 'Desktop'))
    target = request.args.get('target', '')
    mode = request.args.get('mode', 'folder')  # folder, file
    filter_ext = request.args.get('filter', '')

    path = Path(path_str)
    if not path.exists():
        path = Path.home() / 'Desktop'

    items = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith('.'):
                continue
            if mode == 'file' and item.is_file():
                if filter_ext and item.suffix.lower() != filter_ext:
                    continue
            items.append({
                'name': item.name,
                'path': str(item),
                'is_dir': item.is_dir(),
                'extension': item.suffix.lower() if item.is_file() else None,
            })
    except PermissionError:
        pass

    return render_template('file_browser.html',
                           current_path=str(path),
                           parent_path=str(path.parent) if path.parent != path else None,
                           items=items,
                           target=target,
                           mode=mode,
                           filter=filter_ext)


if __name__ == '__main__':
    print("Starting Plan Express Batch Filler GUI...")
    print("Open http://localhost:5001 in your browser")
    app.run(debug=True, port=5001, threaded=True)
