"""Render inspected database schemas as Access-style table diagrams."""

from collections import defaultdict
from html import escape
import json
from pathlib import Path
import re

from src.models.schema.schema_model import DatabaseSchema


class SchemaVisualizer:
    """Convert :class:`DatabaseSchema` metadata into database-table diagrams."""

    _IDENTIFIER_PATTERN = re.compile(r"[^A-Za-z0-9_]")

    def render_html(self, schema: DatabaseSchema) -> str:
        """Return a standalone interactive HTML diagram styled like Access.

        The output contains table cards with their fields and PK/FK indicators.
        Relationship connectors are drawn in the browser, so the diagram remains
        readable when cards flow to a different row on smaller displays.
        """
        primary_keys = {(key.table_name, key.column_name) for key in schema.primary_keys}
        foreign_keys = {(key.source_table, key.source_column) for key in schema.foreign_keys}
        columns_by_table = defaultdict(list)
        for column in schema.columns:
            columns_by_table[column.table_name].append(column)

        table_names = {table.table_name for table in schema.tables}
        table_names.update(columns_by_table)
        table_names.update(relation.parent_table for relation in schema.relations)
        table_names.update(relation.child_table for relation in schema.relations)
        schema_names = {table.table_name: table.schema_name for table in schema.tables}

        cards = []
        for table_name in sorted(table_names):
            fields = []
            for column in sorted(columns_by_table[table_name], key=lambda item: item.ordinal_position):
                badges = ""
                if (table_name, column.column_name) in primary_keys:
                    badges += '<span class="badge pk">PK</span>'
                if (table_name, column.column_name) in foreign_keys:
                    badges += '<span class="badge fk">FK</span>'
                nullable = "NULL" if column.is_nullable else "NOT NULL"
                fields.append(
                    '<div class="field">'
                    f'<span class="field-name">{escape(column.column_name)}</span>'
                    f'<span class="field-type">{escape(column.data_type)} · {nullable}</span>'
                    f'<span class="badges">{badges}</span>'
                    "</div>"
                )
            cards.append(
                f'<section class="table-card" data-table="{escape(table_name, quote=True)}">'
                '<header class="table-title">'
                f'<span>{escape(table_name)}</span>'
                f'<small>{escape(schema_names.get(table_name, "database"))}</small>'
                "</header>"
                f'<div class="fields">{"".join(fields) or "<div class=\"field empty\">No columns found</div>"}</div>'
                "</section>"
            )

        relations = [
            {
                "parent": relation.parent_table,
                "child": relation.child_table,
                "label": f"{relation.parent_column} → {relation.child_column}",
            }
            for relation in schema.relations
        ]
        relations_json = json.dumps(relations).replace("</", "<\\/")
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Database schema</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: #1c2b3a; background: #eaf0f5; font: 14px/1.35 Arial, sans-serif; }}
.toolbar {{ position: sticky; top: 0; z-index: 2; padding: 14px 22px; background: #fff; border-bottom: 1px solid #becbd7; box-shadow: 0 1px 3px #8ca0b533; }}
.toolbar h1 {{ margin: 0; font-size: 20px; }} .toolbar p {{ margin: 3px 0 0; color: #526878; }}
#workspace {{ position: relative; min-height: calc(100vh - 77px); padding: 28px; }}
#relations {{ position: absolute; inset: 0; pointer-events: none; overflow: visible; }}
#cards {{ position: relative; display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 32px 46px; align-items: start; }}
.table-card {{ position: relative; background: #fff; border: 1px solid #8094a6; border-radius: 3px; box-shadow: 2px 3px 7px #8295a855; overflow: hidden; }}
.table-title {{ display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px; color: #fff; background: #255b87; font-weight: bold; }}
.table-title small {{ font-weight: normal; opacity: .85; }} .fields {{ padding: 2px 0; }}
.field {{ display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; align-items: center; min-height: 29px; padding: 4px 9px; border-top: 1px solid #d6e0e8; }}
.field:first-child {{ border-top: 0; }} .field-name {{ overflow-wrap: anywhere; font-weight: 600; }}
.field-type {{ color: #607482; font-size: 12px; white-space: nowrap; }}
.badges {{ display: flex; gap: 3px; }} .badge {{ padding: 1px 4px; border-radius: 2px; color: #473500; background: #ffe38a; font-size: 10px; font-weight: bold; }}
.badge.fk {{ color: #184a69; background: #a9d7ee; }} .empty {{ color: #718390; font-style: italic; }}
@media (max-width: 620px) {{ #workspace {{ padding: 16px; }} #cards {{ grid-template-columns: 1fr; }} #relations {{ display: none; }} }}
</style>
</head>
<body>
<header class="toolbar"><h1>Database Relationships</h1><p>Table cards show fields and keys. Lines represent foreign-key relationships.</p></header>
<main id="workspace"><svg id="relations" aria-hidden="true"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#527e9e" /></marker></defs></svg><div id="cards">{"".join(cards)}</div></main>
<script>
const relationships = {relations_json};
const workspace = document.getElementById('workspace'), svg = document.getElementById('relations');
function drawRelationships() {{
  svg.querySelectorAll('.relationship').forEach(line => line.remove());
  const area = workspace.getBoundingClientRect();
  relationships.forEach(relation => {{
    const parent = document.querySelector(`[data-table="${{CSS.escape(relation.parent)}}"]`), child = document.querySelector(`[data-table="${{CSS.escape(relation.child)}}"]`);
    if (!parent || !child) return;
    const a = parent.getBoundingClientRect(), b = child.getBoundingClientRect();
    const x1 = a.left - area.left + a.width / 2, y1 = a.top - area.top + a.height / 2, x2 = b.left - area.left + b.width / 2, y2 = b.top - area.top + b.height / 2;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('class', 'relationship'); line.setAttribute('x1', x1); line.setAttribute('y1', y1); line.setAttribute('x2', x2); line.setAttribute('y2', y2); line.setAttribute('stroke', '#527e9e'); line.setAttribute('stroke-width', '1.5'); line.setAttribute('marker-end', 'url(#arrow)');
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title'); title.textContent = relation.label; line.appendChild(title); svg.appendChild(line);
  }});
}}
addEventListener('load', drawRelationships); addEventListener('resize', drawRelationships);
</script>
</body>
</html>"""

    def save_html(self, schema: DatabaseSchema, output_path: str | Path) -> Path:
        """Write an Access-style HTML diagram and return its resolved path."""
        path = Path(output_path)
        path.write_text(self.render_html(schema), encoding="utf-8")
        return path.resolve()

    def render_mermaid(self, schema: DatabaseSchema) -> str:
        """Return a deterministic Mermaid ``erDiagram`` for ``schema``.

        Mermaid entity names cannot contain punctuation, so database identifiers are
        normalized while their original names remain visible in comments.
        """
        primary_keys = {(key.table_name, key.column_name) for key in schema.primary_keys}
        foreign_keys = {(key.source_table, key.source_column) for key in schema.foreign_keys}
        columns_by_table = defaultdict(list)
        for column in schema.columns:
            columns_by_table[column.table_name].append(column)

        table_names = {table.table_name for table in schema.tables}
        table_names.update(columns_by_table)
        table_names.update(relation.parent_table for relation in schema.relations)
        table_names.update(relation.child_table for relation in schema.relations)

        lines = ["erDiagram"]
        for table_name in sorted(table_names):
            entity_name = self._entity_name(table_name)
            lines.append(f"    %% {entity_name} represents {table_name}")
            lines.append(f"    {entity_name} {{")
            for column in sorted(
                columns_by_table[table_name], key=lambda item: item.ordinal_position
            ):
                markers = []
                if (table_name, column.column_name) in primary_keys:
                    markers.append("PK")
                if (table_name, column.column_name) in foreign_keys:
                    markers.append("FK")
                marker = f" {' '.join(markers)}" if markers else ""
                lines.append(
                    f"        {self._data_type(column.data_type)} "
                    f"{self._entity_name(column.column_name)}{marker}"
                )
            lines.append("    }")

        for relation in sorted(
            schema.relations,
            key=lambda item: (
                item.parent_table,
                item.parent_column,
                item.child_table,
                item.child_column,
            ),
        ):
            lines.append(
                f"    {self._entity_name(relation.parent_table)} ||--o{{ "
                f"{self._entity_name(relation.child_table)} : "
                f'"{relation.parent_column} to {relation.child_column}"'
            )

        return "\n".join(lines) + "\n"

    def _entity_name(self, identifier: str) -> str:
        """Return a Mermaid-safe identifier without losing determinism."""
        normalized = self._IDENTIFIER_PATTERN.sub("_", identifier).strip("_")
        return normalized.upper() or "UNNAMED"

    def _data_type(self, data_type: str) -> str:
        """Return a Mermaid-safe representation of a PostgreSQL type name."""
        return self._IDENTIFIER_PATTERN.sub("_", data_type).upper()
