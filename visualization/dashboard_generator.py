import os
import logging
import json
from datetime import datetime
import pandas as pd
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

def generate_dashboard_html(df: pd.DataFrame, output_path: str = "data/dashboard.html") -> str:
    """
    Generate the Modern HTML dashboard (Chart.js version).
    
    Args:
        df: Cleaned product DataFrame
        output_path: Path to save the HTML file
        
    Returns:
        Path to the saved file
    """
    logger.info("Generating Modern Dashboard HTML...")
    
    # 1. Convert Data to JSON for Injection
    # We want a list of dicts: [{name: "...", price: 12.34}, ...]
    # Handle NaN values and date serialization if needed
    records = df.to_dict(orient='records')
    
    # Custom serializer implementation if needed, but default json.dumps might work 
    # if simple types. Adding 'default=str' handles dates safely.
    products_json = json.dumps(records, default=str)

    # 2. Render Template
    # Setup Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template('dashboard_modern_template.html')
    except Exception as e:
        logger.error(f"Template not found: {e}")
        # Fallback to default if modern template missing (should not happen in this flow)
        raise

    # Context data for the template
    context = {
        'timestamp': datetime.now().strftime("%b %d, %Y • %H:%M"),
        'products_json': products_json
    }
    
    # Render
    html_content = template.render(context)
    
    # 3. Save to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    logger.info(f"Modern Dashboard saved to {output_path}")
    return output_path

