import json
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from typing import List
from models import Product
from config import TEMPLATES_DIR, DATA_DIR


def generate_terminal_dashboard(products: List[Product]):
    """
    Generates the retro terminal-style HTML dashboard.
    """
    if not products:
        print("No products to display in terminal dashboard.")
        return

    # Helper function to serializing objects (handle datetime)
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    # Prepare data for template
    products_data = [p.dict() for p in products]
    products_json = json.dumps(products_data, default=json_serial)

    # Setup Jinja2 environment
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("dashboard_terminal_template.html")

    # Render template
    context = {
        "products_json": products_json,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    html_content = template.render(context)

    # Write output
    output_path = DATA_DIR / "dashboard_terminal.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Terminal Dashboard generated at: {output_path}")
