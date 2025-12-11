"""
Main Pipeline Orchestrator
==========================
Main entry point for the web scraping portfolio project.

This script orchestrates the complete data pipeline:
1. Scrape product data from Oxylabs sandbox
2. Clean and transform the data
3. Generate interactive visualizations
4. Export Power BI-ready CSV

Usage:
    python main.py              # Default: scrape 10 pages
    python main.py --pages 5    # Scrape specific number of pages
    python main.py --all        # Scrape all pages (~94 pages)

Author: Portfolio Project
Date: 2024
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pandas as pd

# Import project modules
from scraper.product_scraper_browser import scrape_products_browser as scrape_products
from cleaning.data_cleaner import clean_product_data
from visualization.charts import (
    create_price_histogram,
    create_price_box_by_availability,
    create_price_category_bar,
    create_availability_pie,
    save_all_charts
)
from visualization.dashboard_generator import generate_dashboard_html
from visualization.terminal_dashboard_generator import generate_terminal_dashboard

# Ensure data directory exists before configuring logging
os.makedirs('data', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data/pipeline.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Power BI Export Function
# =============================================================================

def export_for_powerbi(
    df: pd.DataFrame,
    output_path: str = "data/products_powerbi.csv"
) -> str:
    """
    Export DataFrame to Power BI-compatible CSV format.
    
    Power BI requirements:
    - UTF-8 encoding with BOM (for proper character handling)
    - Standard comma separator
    - Clean column headers (no special characters)
    - Consistent data types
    - ISO format for dates
    
    Args:
        df: Cleaned DataFrame to export
        output_path: Path for output CSV file
    
    Returns:
        Path to the exported file
    """
    logger.info("Preparing data for Power BI export...")
    
    # Create a copy for Power BI specific transformations
    powerbi_df = df.copy()
    
    # Clean column names (remove spaces, special chars)
    powerbi_df.columns = [
        col.strip()
        .replace(' ', '_')
        .replace('-', '_')
        .lower()
        for col in powerbi_df.columns
    ]
    
    # Convert datetime columns to ISO format string
    for col in powerbi_df.columns:
        if pd.api.types.is_datetime64_any_dtype(powerbi_df[col]):
            powerbi_df[col] = powerbi_df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Convert categorical to string for Power BI compatibility
    for col in powerbi_df.columns:
        if powerbi_df[col].dtype.name == 'category':
            powerbi_df[col] = powerbi_df[col].astype(str)
    
    # Handle boolean columns (convert to Yes/No for Power BI)
    bool_cols = powerbi_df.select_dtypes(include=['bool']).columns
    for col in bool_cols:
        powerbi_df[col] = powerbi_df[col].map({True: 'Yes', False: 'No'})
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Export with UTF-8 BOM encoding (recommended for Power BI)
    powerbi_df.to_csv(
        output_path,
        index=False,
        encoding='utf-8-sig',  # UTF-8 with BOM
        sep=',',
        date_format='%Y-%m-%d'
    )
    
    logger.info(f"Power BI export complete: {output_path}")
    logger.info(f"  - Rows: {len(powerbi_df)}")
    logger.info(f"  - Columns: {list(powerbi_df.columns)}")
    
    return output_path


# =============================================================================
# Pipeline Execution
# =============================================================================

def run_pipeline(
    max_pages: int = 10,
    delay: float = 1.0,
    output_dir: str = "data"
) -> dict:
    """
    Run the complete data pipeline.
    
    Args:
        max_pages: Maximum pages to scrape (None for all)
        delay: Delay between page requests in seconds
        output_dir: Base directory for output files
    
    Returns:
        Dictionary with pipeline results and file paths
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("STARTING DATA PIPELINE")
    logger.info(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Max pages: {max_pages}, Delay: {delay}s")
    logger.info("=" * 60)
    
    results = {
        'success': False,
        'files': {},
        'statistics': {},
        'errors': []
    }
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # =====================================================================
        # Step 1: Scrape Data
        # =====================================================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: WEB SCRAPING")
        logger.info("=" * 60)
        
        raw_path = os.path.join(output_dir, "products_raw.csv")
        
        raw_df = scrape_products(
            max_pages=max_pages,
            delay_seconds=delay,
            save_raw=True,
            output_path=raw_path
        )
        
        results['files']['raw_csv'] = raw_path
        results['statistics']['raw_count'] = len(raw_df)
        logger.info(f"Scraped {len(raw_df)} products")
        
        if raw_df.empty:
            logger.warning("No products scraped. Pipeline stopped.")
            results['errors'].append("No products scraped")
            return results
        
        # =====================================================================
        # Step 2: Clean Data
        # =====================================================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2: DATA CLEANING")
        logger.info("=" * 60)
        
        cleaned_path = os.path.join(output_dir, "products_cleaned.csv")
        
        cleaned_df = clean_product_data(
            raw_df,
            save_cleaned=True,
            output_path=cleaned_path
        )
        
        results['files']['cleaned_csv'] = cleaned_path
        results['statistics']['cleaned_count'] = len(cleaned_df)
        results['statistics']['duplicates_removed'] = len(raw_df) - len(cleaned_df)
        logger.info(f"Cleaned data: {len(cleaned_df)} products")
        
        # =====================================================================
        # Step 3: Generate Visualizations
        # =====================================================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 3: VISUALIZATION")
        logger.info("=" * 60)
        
        # Generate new HTML dashboard
        dashboard_path = os.path.join(output_dir, "dashboard.html")
        generate_dashboard_html(cleaned_df, dashboard_path)
        results['files']['dashboard'] = dashboard_path

        # Generate Terminal Dashboard
        terminal_path = os.path.join(output_dir, "dashboard_terminal.html")
        generate_terminal_dashboard(cleaned_df, terminal_path)
        results['files']['dashboard_terminal'] = terminal_path
        
        # Save individual charts
        charts_dir = os.path.join(output_dir, "charts")
        chart_paths = save_all_charts(cleaned_df, output_dir=charts_dir)
        results['files']['charts'] = chart_paths
        
        logger.info(f"Created {len(chart_paths)} individual charts")
        
        # =====================================================================
        # Step 4: Power BI Export
        # =====================================================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 4: POWER BI EXPORT")
        logger.info("=" * 60)
        
        powerbi_path = os.path.join(output_dir, "products_powerbi.csv")
        export_for_powerbi(cleaned_df, output_path=powerbi_path)
        results['files']['powerbi_csv'] = powerbi_path
        
        # =====================================================================
        # Pipeline Complete
        # =====================================================================
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        results['success'] = True
        results['statistics']['duration_seconds'] = duration
        
        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Products scraped: {results['statistics']['raw_count']}")
        logger.info(f"Products after cleaning: {results['statistics']['cleaned_count']}")
        logger.info(f"\nOutput files:")
        for key, path in results['files'].items():
            if isinstance(path, dict):
                logger.info(f"  {key}:")
                for name, chart_path in path.items():
                    logger.info(f"    - {name}: {chart_path}")
            else:
                logger.info(f"  {key}: {path}")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        results['errors'].append(str(e))
        raise
    
    return results


# =============================================================================
# Command Line Interface
# =============================================================================

def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Web Scraping Portfolio Project Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Scrape 10 pages (default)
  python main.py --pages 5          # Scrape 5 pages
  python main.py --pages 20         # Scrape 20 pages
  python main.py --all              # Scrape all pages (~94)
  python main.py --delay 2.0        # Set 2 second delay between requests
        """
    )
    
    parser.add_argument(
        '--pages', '-p',
        type=int,
        default=10,
        help='Number of pages to scrape (default: 10)'
    )
    
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Scrape all pages (approximately 94 pages)'
    )
    
    parser.add_argument(
        '--delay', '-d',
        type=float,
        default=1.0,
        help='Delay between page requests in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data',
        help='Output directory for all files (default: data)'
    )
    
    args = parser.parse_args()
    
    # Determine max pages
    max_pages = None if args.all else args.pages
    
    # Run pipeline
    try:
        results = run_pipeline(
            max_pages=max_pages,
            delay=args.delay,
            output_dir=args.output
        )
        
        if results['success']:
            print("\n✓ Pipeline completed successfully!")
            print(f"  Output directory: {args.output}/")
        else:
            print("\n✗ Pipeline completed with errors:")
            for error in results['errors']:
                print(f"  - {error}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
