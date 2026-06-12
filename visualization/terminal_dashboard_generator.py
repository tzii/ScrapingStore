from datetime import datetime
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader

from config import TERMINAL_DASHBOARD_HTML_PATH, TEMPLATES_DIR
from logger import get_logger
from models import Product

logger = get_logger(__name__)


def generate_terminal_dashboard(
    products: List[Product], output_path: Optional[str] = None
) -> str:
    """Generate the terminal-style HTML dashboard."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("dashboard_terminal_template.html")
    context = {
        "products": [product.model_dump(mode="json") for product in products],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    html_content = template.render(context)

    destination = Path(output_path) if output_path else TERMINAL_DASHBOARD_HTML_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_content, encoding="utf-8")

    logger.info(f"Terminal dashboard saved to {destination}")
    return str(destination)
