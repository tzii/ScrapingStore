from pathlib import Path
from typing import Optional, Union

from jinja2 import Environment, FileSystemLoader

from config import DASHBOARD_HTML_PATH, TEMPLATES_DIR
from database import DatabaseManager
from logger import get_logger
from visualization.report_data import ReportSnapshot, report_link

logger = get_logger(__name__)


def generate_dashboard(
    db: Union[DatabaseManager, ReportSnapshot],
    output_path: Optional[str] = None,
    *,
    terminal_path: Optional[str] = None,
) -> str:
    """Generate the modern dashboard from a shared snapshot or a database."""
    logger.info("Generating dashboard...")
    if isinstance(db, ReportSnapshot):
        snapshot = db
    else:
        products, run = db.get_catalog_snapshot()
        snapshot = ReportSnapshot.from_products(products, run=run)
    destination = Path(output_path) if output_path else DASHBOARD_HTML_PATH
    sibling = (
        Path(terminal_path)
        if terminal_path
        else destination.with_name("dashboard_terminal.html")
    )
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("dashboard_modern_template.html")
    html_content = template.render(
        **snapshot.context, terminal_href=report_link(destination, sibling)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_content, encoding="utf-8")
    logger.info(f"Dashboard saved to {destination}")
    return str(destination)
