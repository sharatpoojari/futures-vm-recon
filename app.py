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
from roll_forward_validator import RollForwardValidator

# Page config
st.set_page_config(
    page_title="Futures VM/MV Reconciliation",
    page_icon="📊",
    layout="wide"
)

st.title("Futures Variation Margin & Market Value Reconciliation")

# --- Sidebar: Inputs ---
with st.sidebar:
    st.header("Upload Files")

    recon_mode = st.radio("Mode", ["Single Day", "Multi-Day (Roll-Forward)"])

    if recon_mode == "Single Day":
        fund_admin_file = st.file_uploader(
            "Fund Administrator CSV",
            type="csv",
            key="fund_admin_single"
        )

        custody_file = st.file_uploader(
            "Custody CSV",
            type="csv",
            key="custody_single"
        )

        st.divider()
        st.header("Options")

        filter_by_date = st.checkbox("Filter by date")
        recon_date = None
        if filter_by_date:
            recon_date = st.date_input("Reconciliation Date", value=date.today())

    else:  # Multi-Day mode
        fund_admin_files = st.file_uploader(
            "Fund Administrator CSVs (one per day, in date order)",
            type="csv",
            key="fund_admin_multi",
            accept_multiple_files=True
        )

        custody_files = st.file_uploader(
            "Custody CSVs (one per day, in date order)",
            type="csv",
            key="custody_multi",
            accept_multiple_files=True
        )

        recon_date = None

    st.divider()
    run_button = st.button("Run Reconciliation", type="primary", use_container_width=True)


# --- Main Area ---
if run_button:
    # Validate uploads based on mode
    if recon_mode == "Single Day":
        if fund_admin_file is None or custody_file is None:
            st.error("Please upload both Fund Administrator and Custody CSV files.")
            st.stop()

        fund_admin_files_list = [fund_admin_file]
        custody_files_list = [custody_file]

    else:  # Multi-Day
        if not fund_admin_files or not custody_files:
            st.error("Please upload Fund Administrator and Custody CSV files for each day.")
            st.stop()

        if len(fund_admin_files) != len(custody_files):
            st.error(f"Number of fund admin files ({len(fund_admin_files)}) must match custody files ({len(custody_files)}).")
            st.stop()

        fund_admin_files_list = fund_admin_files
        custody_files_list = custody_files

    try:
        # Load and normalize data
        loader = DataLoader()
        transaction_api = MockTransactionAPI()

        daily_data = []
        all_results = []

        # Store column info for debugging
        uploaded_columns = {'fund_admin': [], 'custody': []}

        for fa_file, cust_file in zip(fund_admin_files_list, custody_files_list):
            fund_admin_raw = pd.read_csv(fa_file)
            custody_raw = pd.read_csv(cust_file)

            # Store columns for error reporting
            uploaded_columns['fund_admin'] = list(fund_admin_raw.columns)
            uploaded_columns['custody'] = list(custody_raw.columns)

            fund_admin_df = loader.load_dataframe(fund_admin_raw, 'fund_admin')
            custody_df = loader.load_dataframe(custody_raw, 'custody')

            # Apply date filter if selected (single-day mode only)
            if recon_date is not None:
                recon_date_ts = pd.Timestamp(recon_date)
                fund_admin_df = fund_admin_df[fund_admin_df['trade_date'] == recon_date_ts]
                custody_df = custody_df[custody_df['trade_date'] == recon_date_ts]

                if fund_admin_df.empty and custody_df.empty:
                    st.warning(f"No records found for date {recon_date}.")
                    st.stop()

            # Store for roll-forward validation
            daily_data.append({'fund_admin': fund_admin_df, 'custody': custody_df})

            # Reconcile this day
            reconciler = Reconciler(transaction_api=transaction_api)
            day_results = reconciler.reconcile(fund_admin_df, custody_df)
            all_results.append(day_results)

        # Merge results if multi-day
        if len(all_results) == 1:
            results = all_results[0]
        else:
            # Merge across days
            results = {}
            for key in all_results[0].keys():
                frames = [r[key] for r in all_results if key in r and not r[key].empty]
                results[key] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        # Roll-forward validation (multi-day + MV columns)
        has_mv = DataLoader.has_mv_columns(daily_data[0]['fund_admin'])
        if len(daily_data) > 1 and has_mv:
            rf_validator = RollForwardValidator()
            rf_breaks = rf_validator.validate(daily_data)
            results['roll_forward_breaks'] = rf_breaks

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

        # VM breakdown
        mismatches_df = results['amount_mismatches']
        if not mismatches_df.empty and 'status' in mismatches_df.columns:
            vm_explained = len(mismatches_df[mismatches_df['status'] == 'Explained by Fees'])
            vm_unexplained = len(mismatches_df[mismatches_df['status'] != 'Explained by Fees'])
        else:
            vm_explained = 0
            vm_unexplained = mismatches

        # Display VM metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Matched", matched)
        col2.metric("Fund Admin Only", fa_only)
        col3.metric("Custody Only", cust_only)
        col4.metric("VM Mismatches", mismatches, help=f"Explained: {vm_explained} | Unexplained: {vm_unexplained}")
        col5.metric("Match Rate", f"{match_rate:.1f}%")

        if mismatches > 0:
            info_col1, info_col2 = st.columns(2)
            info_col1.info(f"VM Explained by Fees: **{vm_explained}**")
            info_col2.warning(f"VM Unexplained: **{vm_unexplained}**")

        # MV metrics (if present)
        if 'mv_mismatches' in results:
            st.subheader("Market Value Reconciliation")
            mv_df = results['mv_mismatches']
            mv_total = len(mv_df)

            if not mv_df.empty and 'status' in mv_df.columns:
                mv_explained = len(mv_df[mv_df['status'] == 'Explained by Fees'])
                mv_unexplained = mv_total - mv_explained
            else:
                mv_explained = 0
                mv_unexplained = mv_total

            mv_col1, mv_col2, mv_col3 = st.columns(3)
            mv_col1.metric("MV Mismatches", mv_total)
            mv_col2.metric("MV Explained by Fees", mv_explained)
            mv_col3.metric("MV Unexplained", mv_unexplained)

        # Roll-Forward metrics (if present)
        if 'roll_forward_breaks' in results:
            st.subheader("Roll-Forward Validation")
            rf_df = results['roll_forward_breaks']
            rf_count = len(rf_df)

            if rf_count == 0:
                st.success(f"✓ All balances validated across {len(daily_data)} days - no roll-forward breaks")
            else:
                st.error(f"✗ {rf_count} roll-forward breaks detected")

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
        tabs = [
            f"Matched ({matched})",
            f"Fund Admin Only ({fa_only})",
            f"Custody Only ({cust_only})",
            f"VM Mismatches ({mismatches})"
        ]

        if 'mv_mismatches' in results:
            mv_count = len(results['mv_mismatches'])
            tabs.append(f"MV Mismatches ({mv_count})")

        if 'roll_forward_breaks' in results:
            rf_count = len(results['roll_forward_breaks'])
            tabs.append(f"Roll-Forward ({rf_count})")

        all_tabs = st.tabs(tabs)
        tab_idx = 0

        with all_tabs[tab_idx]:
            if results['matched'].empty:
                st.info("No matched records.")
            else:
                st.dataframe(results['matched'], use_container_width=True, hide_index=True)
        tab_idx += 1

        with all_tabs[tab_idx]:
            if results['fund_admin_only'].empty:
                st.info("No fund admin only records.")
            else:
                st.dataframe(results['fund_admin_only'], use_container_width=True, hide_index=True)
        tab_idx += 1

        with all_tabs[tab_idx]:
            if results['custody_only'].empty:
                st.info("No custody only records.")
            else:
                st.dataframe(results['custody_only'], use_container_width=True, hide_index=True)
        tab_idx += 1

        with all_tabs[tab_idx]:
            if results['amount_mismatches'].empty:
                st.info("No VM mismatches.")
            else:
                st.dataframe(results['amount_mismatches'], use_container_width=True, hide_index=True)
        tab_idx += 1

        if 'mv_mismatches' in results:
            with all_tabs[tab_idx]:
                if results['mv_mismatches'].empty:
                    st.info("No MV mismatches.")
                else:
                    st.dataframe(results['mv_mismatches'], use_container_width=True, hide_index=True)
            tab_idx += 1

        if 'roll_forward_breaks' in results:
            with all_tabs[tab_idx]:
                if results['roll_forward_breaks'].empty:
                    st.success("No roll-forward breaks - all balances validated.")
                else:
                    st.dataframe(results['roll_forward_breaks'], use_container_width=True, hide_index=True)

    except ValueError as e:
        st.error(f"Data validation error: {e}")

        # Show column debugging info
        if "Missing required columns" in str(e):
            st.warning("**Debugging Information:**")

            if 'uploaded_columns' in locals():
                if uploaded_columns['fund_admin']:
                    st.info(f"**Fund Admin CSV columns found:** {uploaded_columns['fund_admin']}")
                if uploaded_columns['custody']:
                    st.info(f"**Custody CSV columns found:** {uploaded_columns['custody']}")

            st.markdown("""
**Expected column names (must match exactly, including case):**

**Fund Admin CSV:**
- `Portfolio_ID` (not portfolio_id or PortfolioID)
- `TradeDate`
- `FuturesContract`
- `VM_Amount`
- *(Optional)* `Beginning_MV`, `Ending_MV`

**Custody CSV:**
- `Account`
- `Date`
- `Contract_Symbol`
- `Variation_Margin`
- *(Optional)* `Begin_Market_Value`, `End_Market_Value`

**Common issues:**
- Column names are case-sensitive
- Remove any leading/trailing spaces in column headers
- Make sure you're uploading the right file to the right uploader (Fund Admin vs Custody)
            """)

    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    # Landing state
    st.info("Upload your CSV files in the sidebar, then click **Run Reconciliation**.")

    with st.expander("Expected CSV Format"):
        st.markdown("""
**Required Columns:**

**Fund Administrator CSV:**
- `Portfolio_ID` - Account/portfolio identifier
- `TradeDate` - Trade date
- `FuturesContract` - Contract identifier (e.g., ESH26)
- `VM_Amount` - Variation margin amount

**Custody CSV:**
- `Account` - Account identifier
- `Date` - Trade date
- `Contract_Symbol` - Contract identifier
- `Variation_Margin` - Variation margin amount

**Optional Columns (for Market Value reconciliation):**

**Fund Administrator CSV:**
- `Beginning_MV` - Beginning market value
- `Ending_MV` - Ending market value

**Custody CSV:**
- `Begin_Market_Value` - Beginning market value
- `End_Market_Value` - Ending market value

Column names can be customized in `config/column_mapping.json`.

**Multi-Day Mode:**
- Upload one file pair per day, in chronological order
- MV columns are required for roll-forward validation
- Tool validates ending MV on day N = beginning MV on day N+1
        """)
