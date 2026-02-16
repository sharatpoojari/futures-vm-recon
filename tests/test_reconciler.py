"""Unit tests for reconciliation logic"""
import sys
from pathlib import Path
import pandas as pd
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from reconciler import Reconciler


class TestReconciler:
    """Test cases for Reconciler class"""

    def test_create_recon_key(self):
        """Test composite key creation"""
        reconciler = Reconciler()

        df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-15']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2000.0]
        })

        keys = reconciler._create_recon_key(df)

        assert keys[0] == 'ACC001|2026-02-14|ESH26'
        assert keys[1] == 'ACC002|2026-02-15|NQH26'

    def test_reconcile_perfect_match(self):
        """Test reconciliation with perfect matches"""
        reconciler = Reconciler()

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2000.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['matched']) == 2
        assert len(results['fund_admin_only']) == 0
        assert len(results['custody_only']) == 0
        assert len(results['amount_mismatches']) == 0

    def test_reconcile_with_breaks(self):
        """Test reconciliation with breaks (records in one source only)"""
        reconciler = Reconciler()

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002', 'ACC003'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26', 'GCJ26'],
            'variation_margin': [1000.0, 2000.0, 3000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002', 'ACC004'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26', 'CLJ26'],
            'variation_margin': [1000.0, 2000.0, 4000.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['matched']) == 2
        assert len(results['fund_admin_only']) == 1
        assert len(results['custody_only']) == 1
        assert len(results['amount_mismatches']) == 0

        # Verify the breaks are correct
        assert results['fund_admin_only']['account_id'].values[0] == 'ACC003'
        assert results['custody_only']['account_id'].values[0] == 'ACC004'

    def test_reconcile_with_amount_mismatches(self):
        """Test reconciliation with amount mismatches"""
        reconciler = Reconciler()

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2100.0]  # Mismatch on ACC002
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['matched']) == 1
        assert len(results['fund_admin_only']) == 0
        assert len(results['custody_only']) == 0
        assert len(results['amount_mismatches']) == 1

        # Verify the mismatch details
        mismatch = results['amount_mismatches'].iloc[0]
        assert mismatch['account_id'] == 'ACC002'
        assert mismatch['variation_margin_fa'] == 2000.0
        assert mismatch['variation_margin_cust'] == 2100.0
        assert mismatch['difference'] == -100.0

    def test_reconcile_empty_dataframes(self):
        """Test reconciliation with empty dataframes"""
        reconciler = Reconciler()

        fund_admin_df = pd.DataFrame({
            'account_id': [],
            'trade_date': pd.to_datetime([]),
            'contract_id': [],
            'variation_margin': []
        })

        custody_df = pd.DataFrame({
            'account_id': [],
            'trade_date': pd.to_datetime([]),
            'contract_id': [],
            'variation_margin': []
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['matched']) == 0
        assert len(results['fund_admin_only']) == 0
        assert len(results['custody_only']) == 0
        assert len(results['amount_mismatches']) == 0


class TestFeeAdjustment:
    """Test cases for fee/commission adjustment logic"""

    def test_mismatch_explained_by_fees(self):
        """Test that mismatches explained by fees are properly categorized"""
        from transaction_api import TransactionAPIBase, FeeCommissionData

        class TestFeeAPI(TransactionAPIBase):
            def get_fees_and_commissions(self, account_id, trade_date, contract_id):
                if account_id == 'ACC002' and contract_id == 'NQH26':
                    return FeeCommissionData(
                        account_id=account_id,
                        trade_date=trade_date,
                        contract_id=contract_id,
                        fees=60.0,
                        commissions=40.0
                    )
                return None

        reconciler = Reconciler(transaction_api=TestFeeAPI())

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001', 'ACC002'],
            'trade_date': pd.to_datetime(['2026-02-14', '2026-02-14']),
            'contract_id': ['ESH26', 'NQH26'],
            'variation_margin': [1000.0, 2100.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['matched']) == 1
        assert len(results['amount_mismatches']) == 1

        mismatch = results['amount_mismatches'].iloc[0]
        assert mismatch['status'] == 'Explained by Fees'
        assert mismatch['fees'] == 60.0
        assert mismatch['commissions'] == 40.0
        assert mismatch['total_fees_commissions'] == 100.0

    def test_mismatch_unexplained_no_api_data(self):
        """Test that mismatches without API data remain unexplained"""
        from transaction_api import TransactionAPIBase

        class EmptyFeeAPI(TransactionAPIBase):
            def get_fees_and_commissions(self, account_id, trade_date, contract_id):
                return None

        reconciler = Reconciler(transaction_api=EmptyFeeAPI())

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1100.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['amount_mismatches']) == 1
        mismatch = results['amount_mismatches'].iloc[0]
        assert mismatch['status'] == 'Unexplained Mismatch'
        assert mismatch['fees'] == 0.0
        assert mismatch['commissions'] == 0.0

    def test_backward_compatibility_without_api(self):
        """Test that reconciler works without transaction API (original behavior)"""
        reconciler = Reconciler()

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1100.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        assert len(results['amount_mismatches']) == 1
        mismatch = results['amount_mismatches'].iloc[0]
        assert mismatch['status'] == 'Amount Mismatch'
        assert 'fees' not in results['amount_mismatches'].columns

    def test_fees_dont_match_difference(self):
        """Test that fees not matching the difference keep mismatch as unexplained"""
        from transaction_api import TransactionAPIBase, FeeCommissionData

        class PartialFeeAPI(TransactionAPIBase):
            def get_fees_and_commissions(self, account_id, trade_date, contract_id):
                return FeeCommissionData(
                    account_id=account_id,
                    trade_date=trade_date,
                    contract_id=contract_id,
                    fees=10.0,
                    commissions=5.0
                )

        reconciler = Reconciler(transaction_api=PartialFeeAPI())

        fund_admin_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1000.0]
        })

        custody_df = pd.DataFrame({
            'account_id': ['ACC001'],
            'trade_date': pd.to_datetime(['2026-02-14']),
            'contract_id': ['ESH26'],
            'variation_margin': [1100.0]
        })

        results = reconciler.reconcile(fund_admin_df, custody_df)

        mismatch = results['amount_mismatches'].iloc[0]
        assert mismatch['status'] == 'Unexplained Mismatch'
        assert mismatch['fees'] == 10.0
        assert mismatch['commissions'] == 5.0
        assert mismatch['total_fees_commissions'] == 15.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
