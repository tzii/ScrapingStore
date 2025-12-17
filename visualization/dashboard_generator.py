import os
import json
from datetime import datetime
import pandas as pd
from jinja2 import Environment, FileSystemLoader

from config import DASHBOARD_HTML_PATH, TEMPLATES_DIR
from logger import get_logger
from database import DatabaseManager

logger = get_logger(__name__)


def generate_dashboard(
    db: DatabaseManager, output_path: str = str(DASHBOARD_HTML_PATH)
) -> str:
    """
    Generate the Modern HTML dashboard with Tailwind/Alpine/Grid.js.
    """
    logger.info("Generating Sleek Dashboard...")

    # Get Data
    df = db.get_products_df()

    if df.empty:
        logger.warning("No data to generate dashboard.")
        return output_path

    # --- Backend Logic (KPIs & Stats) ---

    # 1. KPIs
    total_products = len(df)
    avg_price = df["price"].mean() if not df.empty else 0
    premium_count = len(df[df["price"] > 85])

    # Dynamic Availability
    # Assuming 'availability' column has "In Stock" / "Out of Stock" from cleaner
    in_stock_count = 0
    availability_pct = "0%"
    availability_label = "No Data"

    if "availability" in df.columns:
        in_stock_count = len(
            df[df["availability"].str.contains("In Stock", case=False, na=False)]
        )
        if total_products > 0:
            pct = (in_stock_count / total_products) * 100
            availability_pct = f"{int(pct)}%"
            if pct > 80:
                availability_label = "Stock Level Healthy"
            elif pct > 50:
                availability_label = "Stock Level Moderate"
            else:
                availability_label = "Stock Level Low"

    # 2. Franchise Stats (Simple heuristic)
    keywords = [
        "Zelda",
        "Mario",
        "Metal Gear",
        "Gran Turismo",
        "Halo",
        "Persona",
        "Pokemon",
        "Final Fantasy",
    ]
    from typing import Dict, Any, List
    franchise_data: List[Dict[str, Any]] = []
    for key in keywords:
        count = len(df[df["name"].str.contains(key, case=False)])
        if count > 0:
            franchise_data.append({"name": key, "count": count})
    franchise_data.sort(key=lambda x: int(x["count"]), reverse=True)

    # 3. Price Distribution (Dynamic Bins)
    # create ~8 bins based on min-max
    hist_labels = []
    hist_counts = []

    if not df.empty and total_products > 0:
        min_p = int(df["price"].min())
        max_p = int(df["price"].max())
        if max_p > min_p:
            # Create 8 bins
            step = max(5, (max_p - min_p) // 8)
            # Round step to nice number (5, 10, 20 etc)
            if step > 10:
                step = (step // 10) * 10

            for i in range(min_p, max_p + step, step):
                end = i + step
                count = len(df[(df["price"] >= i) & (df["price"] < end)])
                if count > 0:  # Only add if has data or keep all? Keep all for range
                    hist_labels.append(f"{i}-{end}")
                    hist_counts.append(count)
        else:
            hist_labels = [f"{min_p}-{min_p+10}"]
            hist_counts = [total_products]
    else:
        hist_labels = ["No Data"]
        hist_counts = [0]

    chart_json = json.dumps({"labels": hist_labels, "counts": hist_counts})

    # 4. JSON Serialization
    # Convert DataFrame to list of dicts for Grid.js
    products_list = df.to_dict(orient="records")
    products_json = json.dumps(products_list, default=str)
    franchise_json = json.dumps(franchise_data)

    # --- Render Template ---
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    try:
        template = env.get_template("dashboard_modern_template.html")
    except Exception as e:
        logger.error(f"Template not found: {e}")
        raise

    context = {
        "timestamp": datetime.now().strftime("%b %d, %Y • %H:%M"),
        "products_json": products_json,
        "franchise_json": franchise_json,
        "kpi_total": total_products,
        "kpi_avg": f"{avg_price:.2f}",
        "kpi_premium": premium_count,
        "kpi_availability_pct": availability_pct,
        "kpi_availability_label": availability_label,
        "chart_data_json": chart_json,
    }

    html_content = template.render(context)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Dashboard saved to {output_path}")
    return output_path
