"""
Visualization Module
====================
Interactive data visualization using Plotly Express.

This module creates interactive charts for analyzing:
- Price distributions
- Availability analysis
- Price category breakdowns

Author: Portfolio Project
Date: 2024
"""

import logging
import os
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Price Distribution Charts
# =============================================================================

def create_price_histogram(
    df: pd.DataFrame,
    price_col: str = 'price',
    title: str = "Price Distribution of Products",
    nbins: int = 30,
    color: str = "#636EFA"
) -> go.Figure:
    """
    Create an interactive histogram of price distribution.
    
    Args:
        df: DataFrame with price data
        price_col: Name of the price column
        title: Chart title
        nbins: Number of histogram bins
        color: Bar color
    
    Returns:
        Plotly Figure object
    
    Example:
        >>> fig = create_price_histogram(df)
        >>> fig.show()
    """
    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")
    
    # Filter out null prices
    valid_df = df[df[price_col].notna()].copy()
    
    fig = px.histogram(
        valid_df,
        x=price_col,
        nbins=nbins,
        title=title,
        labels={price_col: 'Price (€)'},
        color_discrete_sequence=[color]
    )
    
    fig.update_layout(
        xaxis_title="Price (€)",
        yaxis_title="Number of Products",
        bargap=0.1,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12, color="#f8fafc"),
        title_font=dict(size=16, color="#f8fafc"),
        hoverlabel=dict(bgcolor="#1e293b", font=dict(color="#f8fafc")),
        title=None, # Title is handled by HTML template
        margin=dict(t=20, l=20, r=20, b=20)
    )
    
    # Add statistics annotation
    mean_price = valid_df[price_col].mean()
    median_price = valid_df[price_col].median()
    
    fig.add_annotation(
        x=0.95, y=0.95,
        xref="paper", yref="paper",
        text=f"Mean: €{mean_price:.2f}<br>Median: €{median_price:.2f}",
        showarrow=False,
        bgcolor="white",
        bordercolor="gray",
        borderwidth=1,
        font=dict(size=11)
    )
    
    logger.info(f"Created price histogram with {len(valid_df)} data points")
    return fig


def create_price_box_by_availability(
    df: pd.DataFrame,
    price_col: str = 'price',
    availability_col: str = 'availability',
    title: str = "Price Distribution by Availability Status"
) -> go.Figure:
    """
    Create a box plot comparing prices by availability status.
    
    Args:
        df: DataFrame with price and availability data
        price_col: Name of the price column
        availability_col: Name of the availability column
        title: Chart title
    
    Returns:
        Plotly Figure object
    """
    if price_col not in df.columns or availability_col not in df.columns:
        raise ValueError("Required columns not found in DataFrame")
    
    # Filter valid data
    valid_df = df[df[price_col].notna()].copy()
    
    fig = px.box(
        valid_df,
        x=availability_col,
        y=price_col,
        title=title,
        labels={
            price_col: 'Price (€)',
            availability_col: 'Availability'
        },
        color=availability_col,
        color_discrete_map={
            "In Stock": "#00CC96",
            "Out of Stock": "#EF553B",
            "Unknown": "#AB63FA"
        }
    )
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12, color="#f8fafc"),
        title_font=dict(size=16, color="#f8fafc"),
        showlegend=False,
        title=None,
        margin=dict(t=20, l=20, r=20, b=20)
    )
    
    logger.info(f"Created availability box plot with {len(valid_df)} data points")
    return fig


# =============================================================================
# Category Analysis Charts
# =============================================================================

def create_price_category_bar(
    df: pd.DataFrame,
    category_col: str = 'price_category',
    title: str = "Products by Price Category"
) -> go.Figure:
    """
    Create a bar chart showing product counts by price category.
    
    Args:
        df: DataFrame with price category data
        category_col: Name of the price category column
        title: Chart title
    
    Returns:
        Plotly Figure object
    """
    if category_col not in df.columns:
        raise ValueError(f"Column '{category_col}' not found in DataFrame")
    
    # Count products in each category
    category_counts = df[category_col].value_counts().reset_index()
    category_counts.columns = ['Category', 'Count']
    
    # Sort by category order
    category_order = ['Budget', 'Mid-Range', 'Premium', 'Luxury']
    category_counts['sort_order'] = category_counts['Category'].apply(
        lambda x: category_order.index(x) if x in category_order else 999
    )
    category_counts = category_counts.sort_values('sort_order')
    
    fig = px.bar(
        category_counts,
        x='Category',
        y='Count',
        title=title,
        color='Category',
        color_discrete_map={
            'Budget': '#00CC96',
            'Mid-Range': '#636EFA',
            'Premium': '#FFA15A',
            'Luxury': '#EF553B'
        },
        text='Count'
    )
    
    fig.update_traces(textposition='outside')
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12, color="#f8fafc"),
        title_font=dict(size=16, color="#f8fafc"),
        showlegend=False,
        xaxis_title="Price Category",
        yaxis_title="Number of Products",
        title=None,
        margin=dict(t=20, l=20, r=20, b=20)
    )
    
    logger.info(f"Created price category bar chart")
    return fig


def create_availability_pie(
    df: pd.DataFrame,
    availability_col: str = 'availability',
    title: str = "Product Availability Distribution"
) -> go.Figure:
    """
    Create a pie chart showing availability distribution.
    
    Args:
        df: DataFrame with availability data
        availability_col: Name of the availability column
        title: Chart title
    
    Returns:
        Plotly Figure object
    """
    if availability_col not in df.columns:
        raise ValueError(f"Column '{availability_col}' not found in DataFrame")
    
    availability_counts = df[availability_col].value_counts().reset_index()
    availability_counts.columns = ['Status', 'Count']
    
    fig = px.pie(
        availability_counts,
        values='Count',
        names='Status',
        title=title,
        color='Status',
        color_discrete_map={
            "In Stock": "#00CC96",
            "Out of Stock": "#EF553B",
            "Unknown": "#AB63FA"
        },
        hole=0.3  # Creates a donut chart
    )
    
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label'
    )
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12, color="#f8fafc"),
        title_font=dict(size=16, color="#f8fafc"),
        title=None,
        margin=dict(t=20, l=20, r=20, b=20)
    )
    
    logger.info(f"Created availability pie chart")
    return fig


# =============================================================================
# Dashboard Creation
# =============================================================================

def create_dashboard(
    df: pd.DataFrame,
    output_path: str = "data/dashboard.html"
) -> go.Figure:
    """
    Create a comprehensive dashboard with multiple charts.
    
    Args:
        df: Cleaned DataFrame
        output_path: Path to save the dashboard HTML
    
    Returns:
        Combined Plotly Figure object
    """
    # Create subplot layout
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Price Distribution",
            "Price by Availability",
            "Products by Price Category",
            "Availability Distribution"
        ),
        specs=[
            [{"type": "histogram"}, {"type": "box"}],
            [{"type": "bar"}, {"type": "pie"}]
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.1
    )
    
    # Filter valid price data
    valid_df = df[df['price'].notna()].copy() if 'price' in df.columns else df
    
    # 1. Price Histogram (top-left)
    if 'price' in valid_df.columns:
        fig.add_trace(
            go.Histogram(
                x=valid_df['price'],
                nbinsx=30,
                name="Price",
                marker_color="#636EFA"
            ),
            row=1, col=1
        )
    
    # 2. Box Plot by Availability (top-right)
    if 'price' in valid_df.columns and 'availability' in valid_df.columns:
        for status in valid_df['availability'].unique():
            subset = valid_df[valid_df['availability'] == status]
            color_map = {"In Stock": "#00CC96", "Out of Stock": "#EF553B", "Unknown": "#AB63FA"}
            fig.add_trace(
                go.Box(
                    y=subset['price'],
                    name=str(status),
                    marker_color=color_map.get(str(status), "#636EFA")
                ),
                row=1, col=2
            )
    
    # 3. Price Category Bar (bottom-left)
    if 'price_category' in valid_df.columns:
        category_counts = valid_df['price_category'].value_counts()
        category_order = ['Budget', 'Mid-Range', 'Premium', 'Luxury']
        ordered_counts = [(cat, category_counts.get(cat, 0)) for cat in category_order if cat in category_counts.index]
        
        fig.add_trace(
            go.Bar(
                x=[c[0] for c in ordered_counts],
                y=[c[1] for c in ordered_counts],
                name="Categories",
                marker_color=['#00CC96', '#636EFA', '#FFA15A', '#EF553B'][:len(ordered_counts)],
                text=[c[1] for c in ordered_counts],
                textposition='outside'
            ),
            row=2, col=1
        )
    
    # 4. Availability Pie (bottom-right)
    if 'availability' in valid_df.columns:
        availability_counts = valid_df['availability'].value_counts()
        color_map = {"In Stock": "#00CC96", "Out of Stock": "#EF553B", "Unknown": "#AB63FA"}
        colors = [color_map.get(str(status), "#636EFA") for status in availability_counts.index]
        
        fig.add_trace(
            go.Pie(
                labels=availability_counts.index.tolist(),
                values=availability_counts.values.tolist(),
                hole=0.3,
                marker_colors=colors
            ),
            row=2, col=2
        )
    
    # Update layout
    fig.update_layout(
        title_text="Product Data Analysis Dashboard",
        title_font=dict(size=20),
        template="plotly_white",
        height=800,
        showlegend=False,
        font=dict(size=11)
    )
    
    # Update axes labels
    fig.update_xaxes(title_text="Price (€)", row=1, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1)
    fig.update_yaxes(title_text="Price (€)", row=1, col=2)
    fig.update_xaxes(title_text="Category", row=2, col=1)
    fig.update_yaxes(title_text="Count", row=2, col=1)
    
    # Save dashboard
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_html(output_path)
    logger.info(f"Dashboard saved to {output_path}")
    
    return fig


# =============================================================================
# Chart Export Functions
# =============================================================================

def save_all_charts(
    df: pd.DataFrame,
    output_dir: str = "data/charts"
) -> dict:
    """
    Generate and save all individual charts.
    
    Args:
        df: Cleaned DataFrame
        output_dir: Directory to save chart HTML files
    
    Returns:
        Dictionary mapping chart names to file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    saved_charts = {}
    
    try:
        # Price Histogram
        fig1 = create_price_histogram(df)
        path1 = os.path.join(output_dir, "price_histogram.html")
        fig1.write_html(path1)
        saved_charts['price_histogram'] = path1
        
        # Box Plot by Availability
        fig2 = create_price_box_by_availability(df)
        path2 = os.path.join(output_dir, "price_by_availability.html")
        fig2.write_html(path2)
        saved_charts['price_by_availability'] = path2
        
        # Price Category Bar
        if 'price_category' in df.columns:
            fig3 = create_price_category_bar(df)
            path3 = os.path.join(output_dir, "price_categories.html")
            fig3.write_html(path3)
            saved_charts['price_categories'] = path3
        
        # Availability Pie
        fig4 = create_availability_pie(df)
        path4 = os.path.join(output_dir, "availability_distribution.html")
        fig4.write_html(path4)
        saved_charts['availability_distribution'] = path4
        
        logger.info(f"Saved {len(saved_charts)} charts to {output_dir}")
        
    except Exception as e:
        logger.error(f"Error saving charts: {e}")
        raise
    
    return saved_charts


# =============================================================================
# Module Entry Point
# =============================================================================

if __name__ == "__main__":
    # Example usage with sample data
    print("Visualization Module")
    print("=" * 50)
    
    # Create sample data
    import numpy as np
    np.random.seed(42)
    
    sample_df = pd.DataFrame({
        'name': [f'Product {i}' for i in range(100)],
        'price': np.random.uniform(10, 150, 100),
        'availability': np.random.choice(['In Stock', 'Out of Stock', 'Unknown'], 100, p=[0.6, 0.3, 0.1]),
        'price_category': pd.cut(
            np.random.uniform(10, 150, 100),
            bins=[0, 20, 50, 100, float('inf')],
            labels=['Budget', 'Mid-Range', 'Premium', 'Luxury']
        )
    })
    
    print(f"\nSample data shape: {sample_df.shape}")
    print("\nGenerating charts...")
    
    # Create and display a chart
    fig = create_price_histogram(sample_df)
    print("\nPrice histogram created successfully!")
    print("Call fig.show() to display in browser")
