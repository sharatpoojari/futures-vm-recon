"""Transaction API Module for fetching fee/commission data from fund admin system"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class FeeCommissionData:
    """Fee and commission information for a trade"""
    account_id: str
    trade_date: str
    contract_id: str
    fees: float
    commissions: float

    @property
    def total(self) -> float:
        """Total fees and commissions"""
        return self.fees + self.commissions


class TransactionAPIBase(ABC):
    """Abstract base class for transaction API implementations"""

    @abstractmethod
    def get_fees_and_commissions(
        self, account_id: str, trade_date: str, contract_id: str
    ) -> Optional[FeeCommissionData]:
        """
        Fetch fee and commission data for a specific trade.

        Args:
            account_id: Account/portfolio identifier
            trade_date: Trade date as string (YYYY-MM-DD)
            contract_id: Futures contract identifier

        Returns:
            FeeCommissionData if found, None if no data available
        """
        pass


class MockTransactionAPI(TransactionAPIBase):
    """
    Mock implementation of the Transaction API.
    Returns sample fee/commission data for testing and development.
    Replace with a real API client (subclass TransactionAPIBase) for production.
    """

    def __init__(self):
        """Initialize with sample fee/commission data"""
        self._mock_data = {
            "ACC002|2026-02-14|ESH26": FeeCommissionData(
                account_id="ACC002",
                trade_date="2026-02-14",
                contract_id="ESH26",
                fees=0.03,
                commissions=0.02
            ),
            "ACC001|2026-02-14|ESH26": FeeCommissionData(
                account_id="ACC001",
                trade_date="2026-02-14",
                contract_id="ESH26",
                fees=1.50,
                commissions=0.75
            ),
            "ACC001|2026-02-14|NQH26": FeeCommissionData(
                account_id="ACC001",
                trade_date="2026-02-14",
                contract_id="NQH26",
                fees=1.25,
                commissions=0.50
            ),
            "ACC011|2026-02-16|ABC": FeeCommissionData(
                account_id="ACC011",
                trade_date="2026-02-16",
                contract_id="ABC",
                fees=3.00,
                commissions=2.00
            ),
        }

    def get_fees_and_commissions(
        self, account_id: str, trade_date: str, contract_id: str
    ) -> Optional[FeeCommissionData]:
        """Look up fees/commissions from mock data store"""
        key = f"{account_id}|{trade_date}|{contract_id}"
        return self._mock_data.get(key)
