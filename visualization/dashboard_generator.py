"""
Dashboard Generator Module
==========================
Generates the HTML dashboard by injecting data and charts into the template.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any

import pandas as pd
import plotly.offline as pyo
from jinja2 import Environment, FileSystemLoader

# Import chart creators
from visualization.charts import (
    create_price_histogram,
    create_price_box_by_availability,
    create_price_category_bar,
    create_availability_pie
)

# Configure logging
logger = logging.getLogger(__name__)

def generate_dashboard_html(df: pd.DataFrame, output_path: str = "data/dashboard.html") -> str:
    """
    Generate the complete HTML dashboard.
    
    Args:
        df: Cleaned product DataFrame
        output_path: Path to save the HTML file
        
    Returns:
        Path to the saved file
    """
    logger.info("Generating dashboard HTML...")
    
    # 1. Calculate Metrics
    total_products = len(df)
    avg_price = df['price'].mean() if 'price' in df.columns else 0
    in_stock_count = len(df[df['availability'] == 'In Stock']) if 'availability' in df.columns else 0
    
    # Simple data quality score (percentage of rows with no missing essential values)
    # penalize unknown availability
    quality_score = 100
    if total_products > 0:
        unknown_availability = len(df[df['availability'] == 'Unknown'])
        quality_score = 100 - (unknown_availability / total_products * 20) # Max 20% penalty
        quality_score = round(quality_score, 1)

    # 2. Generate Charts (as HTML fragments)
    # Config to remove the modebar for cleaner look
    config = {'displayModeBar': False}
    
    fig_hist = create_price_histogram(df)
    plot_price_hist = pyo.plot(fig_hist, output_type='div', include_plotlyjs=False, config=config)
    
    fig_avail = create_availability_pie(df)
    plot_availability = pyo.plot(fig_avail, output_type='div', include_plotlyjs=False, config=config)
    
    fig_cat = create_price_category_bar(df)
    plot_category_bar = pyo.plot(fig_cat, output_type='div', include_plotlyjs=False, config=config)

    # 3. Render Template
    # Setup Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('dashboard_template.html')
    
    # Context data for the template
    context = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'total_products': total_products,
        'avg_price': f"{avg_price:.2f}",
        'in_stock_count': in_stock_count,
        'data_quality_score': quality_score,
        'plot_price_hist': plot_price_hist,
        'plot_availability': plot_availability,
        'plot_category_bar': plot_category_bar
    }
    
    # Render
    html_content = template.render(context)
    
    # 4. Save to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    logger.info(f"Dashboard saved to {output_path}")
    return output_path
