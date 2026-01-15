# Plan Express Batch Filler GUI

A Flask-based web application for batch processing 401(k) plan XML files. This tool parses XML files and fills plan data using configurable mapping files, outputting results to CSV format.

## Features

- **Web-based GUI** - Modern interface built with Flask and HTMX for real-time updates
- **Batch Processing** - Process multiple XML files at once with progress tracking
- **Auto-detection** - Automatically detects Map and DataPoints files in the input directory
- **File Browser** - Built-in file browser for easy directory and file selection
- **History Tracking** - SQLite database tracks all batch runs with the ability to re-run previous jobs
- **CSV Preview** - Preview generated CSV data before downloading
- **Real-time Progress** - Server-Sent Events (SSE) for live progress updates during processing

## Requirements

- Python 3.10+
- Flask 3.0.0+

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/inSideos-designs/XML_Parser_401k.git
   cd XML_Parser_401k
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```bash
   python app.py
   ```
   Or use the launch script:
   ```bash
   ./launch.command
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:5001
   ```

3. Select an input directory containing XML files

4. Optionally specify:
   - **Map File** (.xlsx) - Mapping configuration file
   - **DataPoints File** (.xlsx) - TPA data points file
   - **Output CSV Path** - Custom output location

5. Click "Start Batch" to begin processing

## Project Structure

```
.
├── app.py              # Main Flask application
├── batch_wrapper.py    # Batch processing wrapper with progress callbacks
├── core/
│   ├── __init__.py
│   ├── batch_fill.py   # Core batch filling logic
│   └── fill_plan_data.py # XML parsing and data filling functions
├── static/
│   └── style.css       # Application styles
├── templates/
│   ├── index.html      # Main page template
│   ├── file_browser.html # File browser partial
│   └── history.html    # History list partial
├── requirements.txt    # Python dependencies
├── launch.command      # macOS launch script
└── history.db          # SQLite database for run history
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main application page |
| `/api/files/list` | GET | List directory contents |
| `/api/files/validate` | GET | Validate file/folder path |
| `/api/files/autodetect` | GET | Auto-detect Map and DataPoints files |
| `/api/batch/start` | POST | Start a new batch job |
| `/api/batch/progress/<job_id>` | GET | SSE endpoint for progress updates |
| `/api/batch/preview/<job_id>` | GET | Get CSV preview data |
| `/api/batch/download/<job_id>` | GET | Download generated CSV |
| `/api/history` | GET | Get batch run history |
| `/api/history/<run_id>` | DELETE | Delete history item |

## License

MIT License
