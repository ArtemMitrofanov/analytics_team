import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.utils import secure_filename

from src.config import (
    DATA_DIR, OUTPUT_DIR, TEMPLATES_DIR, STATIC_DIR,
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS
)
from src.data_loader import load_and_parse_csv
from src.processors.timeline_builder import build_timelines, build_flow_data
from src.processors.metrics_calculator import (
    calculate_all_metrics,
    calculate_worklog_metrics,
    calculate_distributions,
    calculate_trends,
)
from src.processors.report_generator import generate_report, load_html_template

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def process_csv_file(file_path: str) -> dict:
    df = load_and_parse_csv(file_path)
    timelines = build_timelines(df)
    metrics = calculate_all_metrics(timelines)
    worklog = calculate_worklog_metrics(timelines)
    distributions = calculate_distributions(timelines, df)
    trends = calculate_trends(timelines)
    flow_nodes, flow_links = build_flow_data(timelines)

    report_path = generate_report(
        timelines=timelines,
        metrics=metrics,
        worklog=worklog,
        flow_nodes=flow_nodes,
        flow_links=flow_links,
        distributions=distributions,
        trends=trends,
    )

    return {
        "success": True,
        "report_path": str(report_path),
        "total_issues": len(timelines),
        "message": "Report generated successfully",
    }


@app.route("/")
def index():
    template = load_html_template()
    return render_template_string(template, DATA={})


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Empty filename"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid file type. Only CSV allowed"}), 400

    filename = secure_filename(file.filename)
    file_path = DATA_DIR / filename
    file.save(file_path)

    try:
        result = process_csv_file(str(file_path))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Processing error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate_report_endpoint():
    data = request.get_json() or {}
    input_file = data.get("input_file")

    if not input_file:
        return jsonify({"success": False, "error": "input_file required"}), 400

    file_path = Path(input_file)
    if not file_path.exists():
        file_path = DATA_DIR / input_file

    if not file_path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        result = process_csv_file(str(file_path))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Generation error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/download/<filename>")
def download_report(filename: str):
    file_path = OUTPUT_DIR / secure_filename(filename)
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)