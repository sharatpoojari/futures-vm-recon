"""Streamlit UI for Futures Variation Margin Reconciliation"""
import sys
from pathlib import Path
from io import BytesIO
from datetime import date

import streamlit as st
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import DataLoader
from reconciler import Reconciler
from report_generator import ReportGenerator
from transaction_api import MockTransactionAPI

# Page config
st.set_page_config(
    page_title="Futures VM Reconciliation",
    page_icon="📊",
    layout="wide"
)

st.title("Futures Variation Margin Reconciliation")

# --- Sidebar: Inputs ---
with st.sidebar:
    st.header("Upload Files")

    fund_admin_file = st.file_uploader(
        "Fund Administrator CSV",
        type="csv",
        key="fund_admin"
    )

    custody_file = st.file_uploader(
        "Custody CSV",
        type="csv",
        key="custody"
    )

    st.divider()
    st.header("Options")

    filter_by_date = st.checkbox("Filter by date")
    recon_date = None
    if filter_by_date:
        recon_date = st.date_input("Reconciliation Date", value=date.today())

    st.divider()
    run_button = st.button("Run Reconciliation", type="primary", use_container_width=True)


# --- Main Area ---
if run_button:
    # Validate uploads
    if fund_admin_file is None or custody_file is None:
        st.error("Please upload both Fund Administrator and Custody CSV files.")
        st.stop()

    try:
        # Load and normalize data
        loader = DataLoader()

        fund_admin_raw = pd.read_csv(fund_admin_file)
        custody_raw = pd.read_csv(custody_file)

        fund_admin_df = loader.load_dataframe(fund_admin_raw, 'fund_admin')
        custody_df = loader.load_dataframe(custody_raw, 'custody')

        # Apply date filter if selected
        if recon_date is not None:
            recon_date_ts = pd.Timestamp(recon_date)
            fund_admin_df = fund_admin_df[fund_admin_df['trade_date'] == recon_date_ts]
            custody_df = custody_df[custody_df['trade_date'] == recon_date_ts]

            if fund_admin_df.empty and custody_df.empty:
                st.warning(f"No records found for date {recon_date}.")
                st.stop()

        # Reconcile
        transaction_api = MockTransactionAPI()
        reconciler = Reconciler(transaction_api=transaction_api)
        results = reconciler.reconcile(fund_admin_df, custody_df)

        # Generate Excel report to memory buffer
        report_gen = ReportGenerator()
        buffer = BytesIO()
        report_gen.generate_excel_report(results, buffer)
        buffer.seek(0)

        # --- Summary Metrics ---
        st.header("Summary")

        matched = len(results['matched'])
        fa_only = len(results['fund_admin_only'])
        cust_only = len(results['custody_only'])
        mismatches = len(results['amount_mismatches'])
        total_fa = matched + fa_only + mismatches
        total_cust = matched + cust_only + mismatches
        match_rate = (matched / total_fa * 100) if total_fa > 0 else 0

        mismatches_df = results['amount_mismatches']
        if not mismatches_df.empty and 'status' in mismatches_df.columns:
            explained = len(mismatches_df[mismatches_df['status'] == 'Explained by Fees'])
            unexplained = len(mismatches_df[mismatches_df['status'] != 'Explained by Fees'])
        else:
            explained = 0
            unexplained = mismatches

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Matched", matched)
        col2.metric("Fund Admin Only", fa_only)
        col3.metric("Custody Only", cust_only)
        col4.metric("Mismatches", mismatches, help=f"Explained: {explained} | Unexplained: {unexplained}")
        col5.metric("Match Rate", f"{match_rate:.1f}%")

        if mismatches > 0:
            info_col1, info_col2 = st.columns(2)
            info_col1.info(f"Explained by Fees: **{explained}**")
            info_col2.warning(f"Unexplained: **{unexplained}**")

        st.divider()

        # --- Download Button ---
        st.download_button(
            label="Download Excel Report",
            data=buffer,
            file_name="recon_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        st.divider()

        # --- Tabbed Data View ---
        tab1, tab2, tab3, tab4 = st.tabs([
            f"Matched ({matched})",
            f"Fund Admin Only ({fa_only})",
            f"Custody Only ({cust_only})",
            f"Amount Mismatches ({mismatches})"
        ])

        with tab1:
            if results['matched'].empty:
                st.info("No matched records.")
            else:
                st.dataframe(results['matched'], use_container_width=True, hide_index=True)

        with tab2:
            if results['fund_admin_only'].empty:
                st.info("No fund admin only records.")
            else:
                st.dataframe(results['fund_admin_only'], use_container_width=True, hide_index=True)

        with tab3:
            if results['custody_only'].empty:
                st.info("No custody only records.")
            else:
                st.dataframe(results['custody_only'], use_container_width=True, hide_index=True)

        with tab4:
            if results['amount_mismatches'].empty:
                st.info("No amount mismatches.")
            else:
                st.dataframe(results['amount_mismatches'], use_container_width=True, hide_index=True)

    except ValueError as e:
        st.error(f"Data validation error: {e}")
    except Exception as e:
        st.error(f"Error: {e}")

else:
    # Landing state
    st.info("Upload your Fund Administrator and Custody CSV files in the sidebar, then click **Run Reconciliation**.")

    with st.expander("Expected CSV Format"):
        st.markdown("""
**Fund Administrator CSV** should contain columns:
- `Portfolio_ID` - Account/portfolio identifier
- `TradeDate` - Trade date
- `FuturesContract` - Contract identifier (e.g., ESH26)
- `VM_Amount` - Variation margin amount

**Custody CSV** should contain columns:
- `Account` - Account identifier
- `Date` - Trade date
- `Contract_Symbol` - Contract identifier
- `Variation_Margin` - Variation margin amount

Column names can be customized in `config/column_mapping.json`.
        """)
