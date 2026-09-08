from pathlib import Path
from typing import List, Optional, Union

from jinja2 import Environment, FileSystemLoader

from config import TERMINAL_DASHBOARD_HTML_PATH, TEMPLATES_DIR
from logger import get_logger
from models import Product
from visualization.report_data import ReportSnapshot, report_link

logger = get_logger(__name__)


def generate_terminal_dashboard(
    products: Union[List[Product], ReportSnapshot],
    output_path: Optional[str] = None,
    *,
    dashboard_path: Optional[str] = None,
) -> str:
    """Generate the terminal-style HTML dashboard."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("dashboard_terminal_template.html")
    snapshot = (
        products
        if isinstance(products, ReportSnapshot)
        else ReportSnapshot.from_products(products)
    )
    destination = Path(output_path) if output_path else TERMINAL_DASHBOARD_HTML_PATH
    sibling = (
        Path(dashboard_path)
        if dashboard_path
        else destination.with_name("dashboard.html")
    )
    html_content = template.render(
        **snapshot.context, dashboard_href=report_link(destination, sibling)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_content, encoding="utf-8")

    logger.info(f"Terminal dashboard saved to {destination}")
    return str(destination)
