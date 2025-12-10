# Web Scraping Portfolio Project

A complete end-to-end data engineering portfolio project demonstrating web scraping, data cleaning, visualization, and Power BI integration.

## 🎯 Project Overview

This project scrapes product data from the [Oxylabs Sandbox E-commerce](https://sandbox.oxylabs.io/products) website and processes it through a complete data pipeline:

1. **Web Scraping** - Extract product data using BeautifulSoup
2. **Data Cleaning** - Process and transform raw data with Pandas
3. **Visualization** - Create interactive charts with Plotly Express
4. **Power BI Export** - Generate analysis-ready CSV files

## 📁 Project Structure

```
ScrapingStore/
├── scraper/
│   ├── __init__.py
│   └── product_scraper.py      # Web scraping module
├── cleaning/
│   ├── __init__.py
│   └── data_cleaner.py         # Data cleaning module
├── visualization/
│   ├── __init__.py
│   └── charts.py               # Plotly visualization module
├── data/                        # Output directory
│   ├── products_raw.csv
│   ├── products_cleaned.csv
│   ├── products_powerbi.csv
│   ├── dashboard.html
│   └── charts/
├── main.py                      # Pipeline orchestrator
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### Installation

```bash
# Navigate to project directory
cd ScrapingStore

# Install dependencies
pip install -r requirements.txt
```

### Running the Pipeline

```bash
# Default: scrape 10 pages (~320 products)
python main.py

# Scrape specific number of pages
python main.py --pages 5

# Scrape all pages (~3000 products)
python main.py --all

# Custom delay between requests
python main.py --pages 10 --delay 2.0
```

## 📊 Output Files

| File | Description |
|------|-------------|
| `products_raw.csv` | Raw scraped data |
| `products_cleaned.csv` | Cleaned and transformed data |
| `products_powerbi.csv` | Power BI-ready export (UTF-8 BOM) |
| `dashboard.html` | Interactive dashboard with all charts |
| `charts/*.html` | Individual chart files |

## 🔧 Modules

### Web Scraper (`scraper/product_scraper.py`)

- HTTP session with retry logic
- User-Agent headers for browser simulation
- Rate limiting to respect server resources
- Pagination handling
- Comprehensive error handling

### Data Cleaner (`cleaning/data_cleaner.py`)

- Price conversion (€ format to float)
- Availability standardization
- Missing value handling
- Duplicate removal
- Price categorization

### Visualization (`visualization/charts.py`)

- Price distribution histogram
- Price by availability box plot
- Price category bar chart
- Availability pie chart
- Combined dashboard

## 📈 Power BI Integration

The `products_powerbi.csv` file is formatted for seamless Power BI import:

1. Open Power BI Desktop
2. Click "Get Data" → "Text/CSV"
3. Select `data/products_powerbi.csv`
4. Data types will be auto-detected

## 🛠️ Technologies

- **Python 3.9+**
- **BeautifulSoup4** - HTML parsing
- **Requests** - HTTP client
- **Pandas** - Data manipulation
- **Plotly Express** - Interactive visualizations

## 📝 License

MIT License - feel free to use for your portfolio!
