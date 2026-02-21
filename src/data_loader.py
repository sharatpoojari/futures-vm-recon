"""Data Loader Module for loading and normalizing CSV files"""
import pandas as pd
import json
from pathlib import Path
from typing import Dict, Optional


class DataLoader:
    """Handles loading and normalizing CSV data from different sources"""

    def __init__(self, config_path: str = "config/column_mapping.json"):
        """
        Initialize DataLoader with column mapping configuration

        Args:
            config_path: Path to the column mapping JSON file
        """
        self.config_path = config_path
        self.column_mapping = self._load_config()

    def _load_config(self) -> Dict:
        """Load column mapping configuration from JSON file"""
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def load_csv(self, file_path: str, source_type: str) -> pd.DataFrame:
        """
        Load CSV file and normalize it to standard format

        Args:
            file_path: Path to the CSV file
            source_type: Either 'fund_admin' or 'custody'

        Returns:
            Normalized pandas DataFrame
        """
        if source_type not in ['fund_admin', 'custody']:
            raise ValueError(f"Invalid source_type: {source_type}. Must be 'fund_admin' or 'custody'")

        # Load CSV
        df = pd.read_csv(file_path)

        # Apply column mapping
        df = self._apply_column_mapping(df, source_type)

        # Validate data
        self._validate_data(df)

        # Clean data
        df = self._clean_data(df)

        return df

    def load_dataframe(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        """
        Normalize an already-loaded DataFrame to standard format.
        Useful when data comes from file uploads (e.g. Streamlit).

        Args:
            df: Raw DataFrame with original column names
            source_type: Either 'fund_admin' or 'custody'

        Returns:
            Normalized pandas DataFrame
        """
        if source_type not in ['fund_admin', 'custody']:
            raise ValueError(f"Invalid source_type: {source_type}. Must be 'fund_admin' or 'custody'")

        df = self._apply_column_mapping(df, source_type)
        self._validate_data(df)
        df = self._clean_data(df)
        return df

    def _apply_column_mapping(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        """
        Rename columns based on the mapping configuration

        Args:
            df: DataFrame to rename
            source_type: Either 'fund_admin' or 'custody'

        Returns:
            DataFrame with standardized column names
        """
        mapping = self.column_mapping[source_type]

        # Create reverse mapping (original column name -> standard name)
        reverse_mapping = {v: k for k, v in mapping.items()}

        # Rename columns
        df = df.rename(columns=reverse_mapping)

        return df

    def _validate_data(self, df: pd.DataFrame) -> None:
        """
        Validate that required fields are present

        Args:
            df: DataFrame to validate

        Raises:
            ValueError: If required columns are missing
        """
        required_columns = ['account_id', 'trade_date', 'contract_id', 'variation_margin']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and prepare data for reconciliation

        Args:
            df: DataFrame to clean

        Returns:
            Cleaned DataFrame
        """
        # Make a copy to avoid modifying original
        df = df.copy()

        # Strip whitespace from string columns
        string_columns = ['account_id', 'contract_id']
        for col in string_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()

        # Convert trade_date to datetime
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # Convert variation_margin to float
        df['variation_margin'] = pd.to_numeric(df['variation_margin'], errors='coerce')

        # Convert market value columns to float if present
        for mv_col in ['beginning_market_value', 'ending_market_value']:
            if mv_col in df.columns:
                df[mv_col] = pd.to_numeric(df[mv_col], errors='coerce')

        # Remove rows with missing critical data
        df = df.dropna(subset=['account_id', 'trade_date', 'contract_id', 'variation_margin'])

        # Add source column for tracking
        return df

    @staticmethod
    def has_mv_columns(df: pd.DataFrame) -> bool:
        """Check if DataFrame has market value columns for MV reconciliation"""
        mv_columns = ['beginning_market_value', 'ending_market_value']
        return all(col in df.columns for col in mv_columns)
