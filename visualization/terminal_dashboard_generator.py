
import os
import logging
import json
from datetime import datetime
import pandas as pd
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

def generate_terminal_dashboard(df: pd.DataFrame, output_path: str = "data/dashboard_terminal.html") -> str:
    """
    Generate the Terminal Dashboard HTML.
    
    Args:
        df: Cleaned product DataFrame
        output_path: Path to save the HTML file
        
    Returns:
        Path to the saved file
    """
    logger.info("Generating Terminal Dashboard HTML...")
    
    # Convert Data to JSON
    records = df.to_dict(orient='records')
    products_json = json.dumps(records, default=str)

    # Setup Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template('dashboard_terminal_template.html')
    except Exception as e:
        logger.error(f"Terminal template not found: {e}")
        raise

    # Context data
    context = {
        'timestamp': datetime.now().strftime("%a %b %d %H:%M:%S"),
        'products_json': products_json
    }
    
    # Render
    html_content = template.render(context)
    
    # Save to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    logger.info(f"Terminal Dashboard saved to {output_path}")
    return output_path
