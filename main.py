"""Main entry point for Futures Variation Margin Reconciliation"""
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_loader import DataLoader
from reconciler import Reconciler
from report_generator import ReportGenerator
from transaction_api import MockTransactionAPI


def main():
    """Main reconciliation workflow"""
    print("=" * 60)
    print("Futures Variation Margin Reconciliation")
    print("=" * 60)
    print()

    # Configuration
    fund_admin_file = "data/input/fund_admin_sample.csv"
    custody_file = "data/input/custody_sample.csv"
    output_dir = Path("data/output")
    output_dir.mkdir(exist_ok=True)

    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"recon_report_{timestamp}.xlsx"

    try:
        # Step 1: Load data
        print("Step 1: Loading data...")
        loader = DataLoader()

        print(f"  - Loading fund administrator file: {fund_admin_file}")
        fund_admin_df = loader.load_csv(fund_admin_file, 'fund_admin')
        print(f"    Loaded {len(fund_admin_df)} records")

        print(f"  - Loading custody file: {custody_file}")
        custody_df = loader.load_csv(custody_file, 'custody')
        print(f"    Loaded {len(custody_df)} records")
        print()

        # Step 2: Reconcile
        print("Step 2: Performing reconciliation...")
        transaction_api = MockTransactionAPI()
        reconciler = Reconciler(transaction_api=transaction_api)
        recon_results = reconciler.reconcile(fund_admin_df, custody_df)
        print("  - Reconciliation complete")
        print("  - Fee/commission adjustments checked for all mismatches")
        print()

        # Step 3: Generate report
        print("Step 3: Generating Excel report...")
        report_gen = ReportGenerator()
        report_path = report_gen.generate_excel_report(recon_results, str(output_file))
        print(f"  - Report saved to: {report_path}")
        print()

        # Step 4: Display summary
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

        # Fee adjustment breakdown
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
        print()

        if fa_only > 0 or cust_only > 0 or mismatches > 0:
            print("[!] Exceptions found - please review the Excel report")
        else:
            print("[OK] All records matched successfully!")

        print("=" * 60)

    except FileNotFoundError as e:
        print(f"ERROR: File not found - {e}")
        print()
        print("Please ensure the following files exist:")
        print(f"  - {fund_admin_file}")
        print(f"  - {custody_file}")
        return 1

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
