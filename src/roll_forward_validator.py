"""Roll-Forward Validation for multi-day market value continuity"""
import pandas as pd
from typing import Dict, List


class RollForwardValidator:
    """
    Validates that ending MV on day N equals beginning MV on day N+1.

    Operates on a sequence of daily DataFrames, sorted by date.
    Validates for each source independently (fund_admin and custody).
    """

    def __init__(self, tolerance: float = 0.01):
        self.tolerance = tolerance

    def validate(self, daily_data: List[Dict[str, pd.DataFrame]]) -> pd.DataFrame:
        """
        Validate roll-forward across consecutive days.

        Args:
            daily_data: List of dicts, each with keys 'fund_admin' and 'custody',
                       ordered by date. Each value is a normalized DataFrame.

        Returns:
            DataFrame of roll-forward breaks with columns:
            source, account_id, contract_id, day_n_date, day_n1_date,
            ending_mv_day_n, beginning_mv_day_n1, difference, status
        """
        if len(daily_data) < 2:
            return pd.DataFrame(columns=[
                'source', 'account_id', 'contract_id',
                'day_n_date', 'day_n1_date',
                'ending_mv_day_n', 'beginning_mv_day_n1',
                'difference', 'status'
            ])

        breaks = []

        for i in range(len(daily_data) - 1):
            day_n = daily_data[i]
            day_n1 = daily_data[i + 1]

            for source in ['fund_admin', 'custody']:
                if source in day_n and source in day_n1:
                    source_breaks = self._compare_consecutive_days(
                        day_n[source], day_n1[source], source
                    )
                    breaks.extend(source_breaks)

        if not breaks:
            return pd.DataFrame(columns=[
                'source', 'account_id', 'contract_id',
                'day_n_date', 'day_n1_date',
                'ending_mv_day_n', 'beginning_mv_day_n1',
                'difference', 'status'
            ])

        return pd.DataFrame(breaks)

    def _compare_consecutive_days(
        self, day_n_df: pd.DataFrame, day_n1_df: pd.DataFrame, source: str
    ) -> List[Dict]:
        """Compare ending MV of day N with beginning MV of day N+1"""
        breaks = []

        if 'ending_market_value' not in day_n_df.columns:
            return breaks
        if 'beginning_market_value' not in day_n1_df.columns:
            return breaks

        # Create a key for joining: account_id + contract_id (no date)
        day_n_df = day_n_df.copy()
        day_n1_df = day_n1_df.copy()
        day_n_df['rf_key'] = day_n_df['account_id'] + '|' + day_n_df['contract_id']
        day_n1_df['rf_key'] = day_n1_df['account_id'] + '|' + day_n1_df['contract_id']

        common_keys = set(day_n_df['rf_key']) & set(day_n1_df['rf_key'])

        for key in common_keys:
            n_row = day_n_df[day_n_df['rf_key'] == key].iloc[0]
            n1_row = day_n1_df[day_n1_df['rf_key'] == key].iloc[0]

            ending_mv = n_row['ending_market_value']
            beginning_mv = n1_row['beginning_market_value']
            diff = ending_mv - beginning_mv

            if abs(diff) > self.tolerance:
                breaks.append({
                    'source': source,
                    'account_id': n_row['account_id'],
                    'contract_id': n_row['contract_id'],
                    'day_n_date': n_row['trade_date'],
                    'day_n1_date': n1_row['trade_date'],
                    'ending_mv_day_n': ending_mv,
                    'beginning_mv_day_n1': beginning_mv,
                    'difference': diff,
                    'status': 'Roll-Forward Break'
                })

        # Flag positions in day N that disappear in day N+1 (non-zero ending MV)
        missing_in_n1 = set(day_n_df['rf_key']) - set(day_n1_df['rf_key'])
        for key in missing_in_n1:
            n_row = day_n_df[day_n_df['rf_key'] == key].iloc[0]
            if abs(n_row['ending_market_value']) > self.tolerance:
                breaks.append({
                    'source': source,
                    'account_id': n_row['account_id'],
                    'contract_id': n_row['contract_id'],
                    'day_n_date': n_row['trade_date'],
                    'day_n1_date': None,
                    'ending_mv_day_n': n_row['ending_market_value'],
                    'beginning_mv_day_n1': None,
                    'difference': n_row['ending_market_value'],
                    'status': 'Position Closed/Missing Next Day'
                })

        return breaks
