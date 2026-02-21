"""Main entry point for Futures Variation Margin Reconciliation"""
import sys
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import DataLoader
from reconciler import Reconciler
from report_generator import ReportGenerator
from transaction_api import MockTransactionAPI
from roll_forward_validator import RollForwardValidator


def merge_daily_results(all_results: list) -> dict:
    """Concatenate results across all days into single DataFrames"""
    combined = {}
    for key in all_results[0].keys():
        frames = [r[key] for r in all_results if key in r and not r[key].empty]
        combined[key] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined


def print_summary(recon_results: dict) -> None:
    """Print reconciliation summary to console"""
    print("=" * 60)
    print("RECONCILIATION SUMMARY")
    print("=" * 60)

    total_fa = len(recon_results['matched']) + len(recon_results['fund_admin_only']) + len(recon_results['amount_mismatches'])
    total_cust = len(recon_results['matched']) + len(recon_results['custody_only']) + len(recon_results['amount_mismatches'])
    matched = len(recon_results['matched'])
    fa_only = len(recon_results['fund_admin_only'])
    cust_only = len(recon_results['custody_only'])
    mismatches = len(recon_results['amount_mismatches'])

    match_rate = (matched / total_fa * 100) if total_fa > 0 else 0

    print(f"Total Fund Admin Records:    {total_fa}")
    print(f"Total Custody Records:       {total_cust}")
    print()
    print(f"[OK] Matched Records:        {matched}")
    print(f"[X]  Fund Admin Only:        {fa_only}")
    print(f"[X]  Custody Only:           {cust_only}")
    print(f"[!]  Amount Mismatches:      {mismatches}")

    # Fee adjustment breakdown for VM
    mismatches_df = recon_results['amount_mismatches']
    if not mismatches_df.empty and 'status' in mismatches_df.columns:
        explained = len(mismatches_df[mismatches_df['status'] == 'Explained by Fees'])
        unexplained = len(mismatches_df[mismatches_df['status'] != 'Explained by Fees'])
    else:
        explained = 0
        unexplained = mismatches
    print(f"     - Explained by Fees:    {explained}")
    print(f"     - Unexplained:          {unexplained}")

    print()
    print(f"Match Rate:                  {match_rate:.2f}%")

    # MV Reconciliation summary
    if 'mv_mismatches' in recon_results:
        print()
        print("-" * 60)
        print("MARKET VALUE RECONCILIATION")
        print("-" * 60)

        mv_df = recon_results['mv_mismatches']
        mv_total = len(mv_df)

        if not mv_df.empty and 'status' in mv_df.columns:
            mv_explained = len(mv_df[mv_df['status'] == 'Explained by Fees'])
            mv_unexplained = mv_total - mv_explained
        else:
            mv_explained = 0
            mv_unexplained = mv_total

        print(f"MV Mismatches (Total):       {mv_total}")
        print(f"     - Explained by Fees:    {mv_explained}")
        print(f"     - Unexplained:          {mv_unexplained}")

    # Roll-Forward summary
    if 'roll_forward_breaks' in recon_results:
        print()
        print("-" * 60)
        print("ROLL-FORWARD VALIDATION")
        print("-" * 60)

        rf_df = recon_results['roll_forward_breaks']
        rf_count = len(rf_df)

        if rf_count == 0:
            print("[OK] All balances validated - no roll-forward breaks")
        else:
            print(f"[X]  Roll-Forward Breaks:    {rf_count}")

    print()
    has_issues = (fa_only > 0 or cust_only > 0 or mismatches > 0)
    if has_issues:
        print("[!] Exceptions found - please review the Excel report")
    else:
        print("[OK] All records matched successfully!")

    print("=" * 60)


def main():
    """Main reconciliation workflow"""
    parser = argparse.ArgumentParser(description='Futures VM/MV Reconciliation')
    parser.add_argument('--fund-admin', nargs='+',
                        default=['data/input/fund_admin_sample.csv'],
                        help='Fund admin CSV file(s), one per day, in date order')
    parser.add_argument('--custody', nargs='+',
                        default=['data/input/custody_sample.csv'],
                        help='Custody CSV file(s), one per day, in date order')
    parser.add_argument('--output-dir', default='data/output',
                        help='Output directory for Excel report')
    args = parser.parse_args()

    print("=" * 60)
    print("Futures Variation Margin Reconciliation")
    print("=" * 60)
    print()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"recon_report_{timestamp}.xlsx"

    if len(args.fund_admin) != len(args.custody):
        print("ERROR: Number of fund admin files must match number of custody files")
        return 1

    try:
        # Step 1: Load data
        print("Step 1: Loading data...")
        loader = DataLoader()
        transaction_api = MockTransactionAPI()

        daily_data = []
        for fa_file, cust_file in zip(args.fund_admin, args.custody):
            print(f"  - Loading fund admin: {fa_file}")
            fa_df = loader.load_csv(fa_file, 'fund_admin')
            print(f"    Loaded {len(fa_df)} records")

            print(f"  - Loading custody:    {cust_file}")
            cust_df = loader.load_csv(cust_file, 'custody')
            print(f"    Loaded {len(cust_df)} records")

            daily_data.append({'fund_admin': fa_df, 'custody': cust_df})
        print()

        # Step 2: Reconcile each day
        print("Step 2: Performing reconciliation...")
        all_results = []
        for day_pair in daily_data:
            reconciler = Reconciler(transaction_api=transaction_api)
            results = reconciler.reconcile(day_pair['fund_admin'], day_pair['custody'])
            all_results.append(results)
        print("  - Reconciliation complete")
        print("  - Fee/commission adjustments checked for all mismatches")

        # Merge results across days
        if len(all_results) == 1:
            combined_results = all_results[0]
        else:
            combined_results = merge_daily_results(all_results)
            print(f"  - Merged results across {len(all_results)} days")

        # Step 3: Roll-forward validation (multi-day + MV columns)
        has_mv = DataLoader.has_mv_columns(daily_data[0]['fund_admin'])
        if len(daily_data) > 1 and has_mv:
            print()
            print("Step 3: Running roll-forward validation...")
            rf_validator = RollForwardValidator()
            rf_breaks = rf_validator.validate(daily_data)
            combined_results['roll_forward_breaks'] = rf_breaks
            print(f"  - Validated {len(daily_data)} days")
        print()

        # Step 4: Generate report
        step_num = 4 if (len(daily_data) > 1 and has_mv) else 3
        print(f"Step {step_num}: Generating Excel report...")
        report_gen = ReportGenerator()
        report_path = report_gen.generate_excel_report(combined_results, str(output_file))
        print(f"  - Report saved to: {report_path}")
        print()

        # Step 5: Display summary
        print_summary(combined_results)

    except FileNotFoundError as e:
        print(f"ERROR: File not found - {e}")
        return 1

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
