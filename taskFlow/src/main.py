import argparse
import logging
import sys
from pathlib import Path

from src.config import DATA_DIR, OUTPUT_DIR
from src.data_loader import load_and_parse_csv
from src.processors.timeline_builder import build_timelines, build_flow_data
from src.processors.metrics_calculator import (
    calculate_all_metrics,
    calculate_worklog_metrics,
    calculate_distributions,
    calculate_trends,
)
from src.processors.report_generator import generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_analysis(input_file: str, output_file: str = None) -> Path:
    logger.info(f"Starting analysis for: {input_file}")

    df = load_and_parse_csv(input_file)

    logger.info("Building timelines...")
    timelines = build_timelines(df)

    logger.info("Calculating metrics...")
    metrics = calculate_all_metrics(timelines)

    logger.info("Analyzing worklog...")
    worklog = calculate_worklog_metrics(timelines)

    logger.info("Calculating distributions...")
    distributions = calculate_distributions(timelines, df)

    logger.info("Calculating trends...")
    trends = calculate_trends(timelines)

    logger.info("Building flow data...")
    flow_nodes, flow_links = build_flow_data(timelines)

    logger.info("Generating report...")
    report_path = generate_report(
        timelines=timelines,
        metrics=metrics,
        worklog=worklog,
        flow_nodes=flow_nodes,
        flow_links=flow_links,
        distributions=distributions,
        trends=trends,
        output_path=Path(output_file) if output_file else None,
    )

    logger.info(f"Report generated: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="TaskFlow Analytics - Task analytics service")
    parser.add_argument("--mode", choices=["generate", "server"], default="generate", help="Mode to run")
    parser.add_argument("--input", "-i", help="Input CSV file path")
    parser.add_argument("--output", "-o", help="Output HTML file path")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    if args.mode == "generate":
        input_file = args.input or str(DATA_DIR / "input.csv")
        output_file = args.output

        try:
            report_path = run_analysis(input_file, output_file)
            print(f"✅ Report generated: {report_path}")
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            sys.exit(1)

    elif args.mode == "server":
        from src.app import app
        app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()