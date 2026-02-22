import json
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from typing import List
from models import Product
from config import TEMPLATES_DIR, DATA_DIR
from logger import get_logger

logger = get_logger(__name__)


def generate_terminal_dashboard(products: List[Product]):
    """
    Generates the retro terminal-style HTML dashboard.
    """
    if not products:
        logger.warning("No products to display in terminal dashboard.")
        return

    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    products_data = [p.model_dump() for p in products]
    products_json = json.dumps(products_data, default=json_serial)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    try:
        template = env.get_template("dashboard_terminal_template.html")
    except Exception as e:
        logger.error(f"Terminal dashboard template not found: {e}")
        raise

    context = {
        "products_json": products_json,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    html_content = template.render(context)

    output_path = DATA_DIR / "dashboard_terminal.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Terminal dashboard saved to {output_path}")
