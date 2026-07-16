"""Create an Access-style HTML diagram from the configured database."""

import argparse

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.visualizers.schema_visualizer import SchemaVisualizer


def main() -> None:
    """Inspect the configured database and write a browser-ready diagram."""
    parser = argparse.ArgumentParser(description="Generate an HTML database diagram.")
    parser.add_argument("--output", default="schema_visualization.html", help="HTML output path")
    args = parser.parse_args()

    schema = SchemaInspector.from_connection_provider(get_connection).inspect()
    output_path = SchemaVisualizer().save_html(schema, args.output)
    print(f"Schema visualization written to {output_path}")


if __name__ == "__main__":
    main()
