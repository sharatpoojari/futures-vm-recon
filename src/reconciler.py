"""Reconciliation Engine for comparing variation margin and market value data"""
import pandas as pd
from typing import Dict, Optional
from transaction_api import TransactionAPIBase


class Reconciler:
    """Handles reconciliation logic between fund admin and custody data"""

    def __init__(self, transaction_api: Optional[TransactionAPIBase] = None):
        """
        Initialize Reconciler

        Args:
            transaction_api: Optional transaction API for fee/commission lookups.
                           If None, fee adjustment is skipped.
        """
        self.transaction_api = transaction_api
        self._mv_enabled = False

    def reconcile(self, fund_admin_df: pd.DataFrame, custody_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Main reconciliation function that compares two datasets

        Args:
            fund_admin_df: Fund administrator DataFrame
            custody_df: Custody DataFrame

        Returns:
            Dictionary containing:
                - matched: Successfully matched records
                - fund_admin_only: Records only in fund admin
                - custody_only: Records only in custody
                - amount_mismatches: Records with matching keys but different VM amounts
                - mv_mismatches: (optional) Records with matching keys but different MV
        """
        # Add source identifiers
        fund_admin_df = fund_admin_df.copy()
        custody_df = custody_df.copy()
        fund_admin_df['source'] = 'fund_admin'
        custody_df['source'] = 'custody'

        # Detect MV capability
        self._mv_enabled = (
            'beginning_market_value' in fund_admin_df.columns and
            'ending_market_value' in fund_admin_df.columns and
            'beginning_market_value' in custody_df.columns and
            'ending_market_value' in custody_df.columns
        )

        # Create composite key for matching
        fund_admin_df['recon_key'] = self._create_recon_key(fund_admin_df)
        custody_df['recon_key'] = self._create_recon_key(custody_df)

        # Find matches and breaks
        matched_df, fund_admin_only_df, custody_only_df, amount_mismatches_df, mv_mismatches_df = (
            self._perform_matching(fund_admin_df, custody_df)
        )

        results = {
            'matched': matched_df,
            'fund_admin_only': fund_admin_only_df,
            'custody_only': custody_only_df,
            'amount_mismatches': amount_mismatches_df
        }

        if self._mv_enabled:
            results['mv_mismatches'] = mv_mismatches_df

        return results

    def _create_recon_key(self, df: pd.DataFrame) -> pd.Series:
        """
        Create composite key for matching

        Args:
            df: DataFrame to create key for

        Returns:
            Series containing composite keys
        """
        if df.empty:
            return pd.Series(dtype=str)

        # Convert date to string format for consistent key creation
        date_str = df['trade_date'].dt.strftime('%Y-%m-%d')

        # Create composite key: account_id|trade_date|contract_id
        return df['account_id'] + '|' + date_str + '|' + df['contract_id']

    def _perform_matching(self, fund_admin_df: pd.DataFrame, custody_df: pd.DataFrame) -> tuple:
        """
        Perform the actual matching logic

        Args:
            fund_admin_df: Fund admin DataFrame with recon_key
            custody_df: Custody DataFrame with recon_key

        Returns:
            Tuple of (matched, fund_admin_only, custody_only, amount_mismatches, mv_mismatches)
        """
        # Get unique keys from both sources
        fund_admin_keys = set(fund_admin_df['recon_key'])
        custody_keys = set(custody_df['recon_key'])

        # Find common keys and unique keys
        common_keys = fund_admin_keys & custody_keys
        fund_admin_only_keys = fund_admin_keys - custody_keys
        custody_only_keys = custody_keys - fund_admin_keys

        # Extract records
        fund_admin_only_df = fund_admin_df[fund_admin_df['recon_key'].isin(fund_admin_only_keys)].copy()
        custody_only_df = custody_df[custody_df['recon_key'].isin(custody_only_keys)].copy()

        # For common keys, merge and compare amounts
        fund_admin_common = fund_admin_df[fund_admin_df['recon_key'].isin(common_keys)].copy()
        custody_common = custody_df[custody_df['recon_key'].isin(common_keys)].copy()

        # Merge on recon_key
        merged_df = pd.merge(
            fund_admin_common,
            custody_common,
            on='recon_key',
            suffixes=('_fa', '_cust')
        )

        # Identify VM amount mismatches
        merged_df['amount_diff'] = merged_df['variation_margin_fa'] - merged_df['variation_margin_cust']
        merged_df['amounts_match'] = merged_df['amount_diff'].abs() < 0.01

        matched_df = merged_df[merged_df['amounts_match']].copy()
        amount_mismatches_df = merged_df[~merged_df['amounts_match']].copy()

        # MV comparison (separate from VM matching)
        mv_mismatches_df = pd.DataFrame()
        if self._mv_enabled:
            merged_df['ending_mv_diff'] = (
                merged_df['ending_market_value_fa'] - merged_df['ending_market_value_cust']
            )
            merged_df['beginning_mv_diff'] = (
                merged_df['beginning_market_value_fa'] - merged_df['beginning_market_value_cust']
            )
            merged_df['mv_match'] = merged_df['ending_mv_diff'].abs() < 0.01

            mv_mismatch_rows = merged_df[~merged_df['mv_match']]
            if not mv_mismatch_rows.empty:
                mv_mismatches_df = self._format_mv_mismatch_df(mv_mismatch_rows)
                if self.transaction_api is not None and not mv_mismatches_df.empty:
                    mv_mismatches_df = self._check_fee_adjustments_mv(mv_mismatches_df)

        # Clean up the matched DataFrame
        matched_df = self._format_matched_df(matched_df, merged_df if self._mv_enabled else None)

        # Clean up amount mismatches DataFrame
        amount_mismatches_df = self._format_mismatch_df(amount_mismatches_df)

        # Check if VM mismatches are explained by fees/commissions
        if self.transaction_api is not None and not amount_mismatches_df.empty:
            amount_mismatches_df = self._check_fee_adjustments(amount_mismatches_df)

        # Remove recon_key from output DataFrames
        for df in [matched_df, fund_admin_only_df, custody_only_df, amount_mismatches_df, mv_mismatches_df]:
            if 'recon_key' in df.columns:
                df.drop('recon_key', axis=1, inplace=True)

        return matched_df, fund_admin_only_df, custody_only_df, amount_mismatches_df, mv_mismatches_df

    def _format_matched_df(self, df: pd.DataFrame, full_merged_df: pd.DataFrame = None) -> pd.DataFrame:
        """Format matched records DataFrame"""
        if df.empty:
            return pd.DataFrame()

        result = {
            'account_id': df['account_id_fa'],
            'trade_date': df['trade_date_fa'],
            'contract_id': df['contract_id_fa'],
            'variation_margin_fa': df['variation_margin_fa'],
            'variation_margin_cust': df['variation_margin_cust'],
            'difference': df['amount_diff'],
            'status': 'Matched'
        }

        if self._mv_enabled:
            result['beginning_mv_fa'] = df['beginning_market_value_fa']
            result['ending_mv_fa'] = df['ending_market_value_fa']
            result['beginning_mv_cust'] = df['beginning_market_value_cust']
            result['ending_mv_cust'] = df['ending_market_value_cust']

        return pd.DataFrame(result)

    def _format_mismatch_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Format amount mismatch records DataFrame"""
        if df.empty:
            return pd.DataFrame()

        result_df = pd.DataFrame({
            'account_id': df['account_id_fa'],
            'trade_date': df['trade_date_fa'],
            'contract_id': df['contract_id_fa'],
            'variation_margin_fa': df['variation_margin_fa'],
            'variation_margin_cust': df['variation_margin_cust'],
            'difference': df['amount_diff'],
            'status': 'Amount Mismatch'
        })

        return result_df

    def _format_mv_mismatch_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Format MV mismatch records DataFrame"""
        if df.empty:
            return pd.DataFrame()

        result_df = pd.DataFrame({
            'account_id': df['account_id_fa'],
            'trade_date': df['trade_date_fa'],
            'contract_id': df['contract_id_fa'],
            'beginning_mv_fa': df['beginning_market_value_fa'],
            'beginning_mv_cust': df['beginning_market_value_cust'],
            'beginning_mv_diff': df['beginning_mv_diff'],
            'ending_mv_fa': df['ending_market_value_fa'],
            'ending_mv_cust': df['ending_market_value_cust'],
            'ending_mv_diff': df['ending_mv_diff'],
            'vm_fa': df['variation_margin_fa'],
            'vm_cust': df['variation_margin_cust'],
            'status': 'MV Mismatch'
        })

        return result_df

    def _check_fee_adjustments(self, mismatches_df: pd.DataFrame) -> pd.DataFrame:
        """
        Check if amount mismatches can be explained by fees and commissions.

        For each mismatch, queries the transaction API and compares the total
        fees/commissions against the absolute difference.

        Args:
            mismatches_df: DataFrame of amount mismatches from _format_mismatch_df

        Returns:
            Updated DataFrame with fee columns and refined status
        """
        fees_list = []
        commissions_list = []
        statuses = []

        for _, row in mismatches_df.iterrows():
            trade_date = row['trade_date']
            if hasattr(trade_date, 'strftime'):
                trade_date_str = trade_date.strftime('%Y-%m-%d')
            else:
                trade_date_str = str(trade_date)

            fee_data = self.transaction_api.get_fees_and_commissions(
                row['account_id'], trade_date_str, row['contract_id']
            )

            if fee_data is not None:
                fees_list.append(fee_data.fees)
                commissions_list.append(fee_data.commissions)

                if abs(abs(row['difference']) - abs(fee_data.total)) < 0.01:
                    statuses.append('Explained by Fees')
                else:
                    statuses.append('Unexplained Mismatch')
            else:
                fees_list.append(0.0)
                commissions_list.append(0.0)
                statuses.append('Unexplained Mismatch')

        mismatches_df = mismatches_df.copy()
        mismatches_df['fees'] = fees_list
        mismatches_df['commissions'] = commissions_list
        mismatches_df['total_fees_commissions'] = mismatches_df['fees'] + mismatches_df['commissions']
        mismatches_df['status'] = statuses

        return mismatches_df

    def _check_fee_adjustments_mv(self, mv_mismatches_df: pd.DataFrame) -> pd.DataFrame:
        """
        Check if MV mismatches can be explained by fees and commissions.

        The MV difference is cumulative across days. Beginning MV may already
        differ due to prior days' fees. The incremental MV difference
        (ending_mv_diff - beginning_mv_diff) should match today's daily fees.

        Args:
            mv_mismatches_df: DataFrame of MV mismatches

        Returns:
            Updated DataFrame with fee columns and refined status
        """
        fees_list = []
        commissions_list = []
        statuses = []

        for _, row in mv_mismatches_df.iterrows():
            trade_date = row['trade_date']
            if hasattr(trade_date, 'strftime'):
                trade_date_str = trade_date.strftime('%Y-%m-%d')
            else:
                trade_date_str = str(trade_date)

            fee_data = self.transaction_api.get_fees_and_commissions(
                row['account_id'], trade_date_str, row['contract_id']
            )

            if fee_data is not None:
                fees_list.append(fee_data.fees)
                commissions_list.append(fee_data.commissions)

                # Incremental MV difference = today's fee impact only
                incremental_mv_diff = row['ending_mv_diff'] - row['beginning_mv_diff']
                if abs(abs(incremental_mv_diff) - abs(fee_data.total)) < 0.01:
                    statuses.append('Explained by Fees')
                else:
                    statuses.append('Unexplained MV Mismatch')
            else:
                fees_list.append(0.0)
                commissions_list.append(0.0)
                statuses.append('Unexplained MV Mismatch')

        mv_mismatches_df = mv_mismatches_df.copy()
        mv_mismatches_df['fees'] = fees_list
        mv_mismatches_df['commissions'] = commissions_list
        mv_mismatches_df['total_fees_commissions'] = mv_mismatches_df['fees'] + mv_mismatches_df['commissions']
        mv_mismatches_df['status'] = statuses

        return mv_mismatches_df
