"""
Database Manager
================
Handles database connections and operations using SQLModel.
"""

from typing import List, Optional
import pandas as pd
from sqlmodel import Session, SQLModel, create_engine, select

from config import DB_URL, CSV_POWERBI_PATH
from models import Product
from logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, db_url: str = DB_URL):
        self.engine = create_engine(db_url)

    def init_db(self):
        """Create database tables."""
        SQLModel.metadata.create_all(self.engine)
        logger.info("Database initialized.")

    def save_products(self, products: List[Product]):
        """
        Save a list of products to the database with Upsert logic.
        Updates existing products (matched by source_url) and inserts new ones.
        """
        if not products:
            return
        
        with Session(self.engine) as session:
            for product in products:
                # Upsert Logic: Check if product exists by name (unique identifier)
                # Note: source_url is the same for all products on a page, so we use name.
                existing_product = session.exec(
                    select(Product).where(Product.name == product.name)
                ).first()

                if existing_product:
                    # Update fields
                    existing_product.name = product.name
                    existing_product.price = product.price
                    existing_product.availability = product.availability
                    existing_product.image_url = product.image_url
                    existing_product.scraped_at = product.scraped_at
                    # Add simple log if prices changed? (Optional)
                    session.add(existing_product)
                else:
                    session.add(product)
            
            session.commit()
            logger.info(f"Processed {len(products)} products (Upsert).")

    def get_all_products(self) -> List[Product]:
        """Retrieve all products from the database."""
        with Session(self.engine) as session:
            statement = select(Product)
            results = session.exec(statement).all()
            return list(results)
    
    def get_products_df(self) -> pd.DataFrame:
        """Retrieve all products as a Pandas DataFrame."""
        products = self.get_all_products()
        return pd.DataFrame([p.model_dump() for p in products])

    def export_for_powerbi(self, output_path: str = str(CSV_POWERBI_PATH)):
        """
        Export database content to a Power BI-compatible CSV.
        """
        logger.info("Exporting data for Power BI...")
        df = self.get_products_df()
        
        if df.empty:
            logger.warning("No data to export.")
            return

        # Power BI Transformations
        # 1. Clean column names
        df.columns = [
            col.strip().replace(' ', '_').replace('-', '_').lower()
            for col in df.columns
        ]
        
        # 2. ISO Dates
        if 'scraped_at' in df.columns:
            df['scraped_at'] = pd.to_datetime(df['scraped_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

        # 3. Export with BOM for Excel/Power BI compatibility
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logger.info(f"Power BI export saved to {output_path}")