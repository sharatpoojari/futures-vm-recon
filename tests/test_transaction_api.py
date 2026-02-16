"""Unit tests for transaction API module"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from transaction_api import MockTransactionAPI, FeeCommissionData


class TestFeeCommissionData:
    """Tests for the FeeCommissionData dataclass"""

    def test_total_property(self):
        """Test that total correctly sums fees and commissions"""
        data = FeeCommissionData(
            account_id="ACC001",
            trade_date="2026-02-14",
            contract_id="ESH26",
            fees=1.50,
            commissions=0.75
        )
        assert data.total == 2.25

    def test_total_zero(self):
        """Test total when both fees and commissions are zero"""
        data = FeeCommissionData(
            account_id="ACC001",
            trade_date="2026-02-14",
            contract_id="ESH26",
            fees=0.0,
            commissions=0.0
        )
        assert data.total == 0.0


class TestMockTransactionAPI:
    """Tests for the MockTransactionAPI"""

    def test_known_key_returns_data(self):
        """Test that a known key returns fee/commission data"""
        api = MockTransactionAPI()
        result = api.get_fees_and_commissions("ACC002", "2026-02-14", "ESH26")
        assert result is not None
        assert result.fees == 0.03
        assert result.commissions == 0.02
        assert result.total == 0.05

    def test_unknown_key_returns_none(self):
        """Test that an unknown key returns None"""
        api = MockTransactionAPI()
        result = api.get_fees_and_commissions("UNKNOWN", "2026-01-01", "XXX")
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
