# Futures Variation Margin Reconciliation

A Python-based reconciliation tool to compare futures variation margin data between fund administrator and custody sources.

## Features

- **CSV Data Loading**: Load variation margin data from CSV files with different column structures
- **Flexible Column Mapping**: JSON-based configuration for mapping different column names
- **Comprehensive Reconciliation**: Identifies matched records, breaks, and amount mismatches
- **Excel Reporting**: Generates formatted Excel reports with multiple sheets and conditional formatting
- **Automated Workflow**: Simple command-line execution

## Project Structure

```
futures-vm-recon/
├── config/
│   └── column_mapping.json          # Column name mappings
├── data/
│   ├── input/                        # Input CSV files
│   │   ├── fund_admin_sample.csv
│   │   └── custody_sample.csv
│   └── output/                       # Generated Excel reports
├── src/
│   ├── __init__.py
│   ├── data_loader.py               # Data loading and normalization
│   ├── reconciler.py                # Reconciliation logic
│   └── report_generator.py          # Excel report generation
├── tests/
│   ├── __init__.py
│   └── test_reconciler.py           # Unit tests
├── main.py                          # Main entry point
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## Installation

1. **Navigate to the project directory**:
   ```bash
   cd Desktop/futures-vm-recon
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The `config/column_mapping.json` file maps the different column names from your data sources to standardized field names:

```json
{
  "fund_admin": {
    "account_id": "Portfolio_ID",
    "trade_date": "TradeDate",
    "contract_id": "FuturesContract",
    "variation_margin": "VM_Amount"
  },
  "custody": {
    "account_id": "Account",
    "trade_date": "Date",
    "contract_id": "Contract_Symbol",
    "variation_margin": "Variation_Margin"
  }
}
```

**To use with your own data**: Update the values (right side) to match your actual column names.

## Usage

### Running with Sample Data

The project includes sample CSV files for testing:

```bash
python main.py
```

This will:
1. Load sample data from `data/input/`
2. Perform reconciliation
3. Generate an Excel report in `data/output/`
4. Display summary statistics

### Running with Your Own Data

1. **Prepare your CSV files**:
   - Place your fund administrator CSV file in `data/input/`
   - Place your custody CSV file in `data/input/`

2. **Update column mappings** in `config/column_mapping.json` to match your column names

3. **Update file paths** in `main.py` (lines 18-19):
   ```python
   fund_admin_file = "data/input/your_fund_admin_file.csv"
   custody_file = "data/input/your_custody_file.csv"
   ```

4. **Run the reconciliation**:
   ```bash
   python main.py
   ```

## Expected Data Format

Both CSV files should contain the following information (column names can vary):

- **Account/Portfolio ID**: Unique identifier for the fund or portfolio
- **Trade Date**: Date of the variation margin
- **Contract/Instrument ID**: Futures contract identifier (e.g., ESH26, NQH26)
- **Variation Margin Amount**: The margin amount to reconcile

## Output Report

The generated Excel report contains 5 sheets:

1. **Summary**: High-level statistics including:
   - Total records from each source
   - Match count and rate
   - Exception counts

2. **Matched**: Successfully matched records with amounts from both sources

3. **Fund Admin Only**: Records present only in the fund administrator file (highlighted in red)

4. **Custody Only**: Records present only in the custody file (highlighted in red)

5. **Amount Mismatches**: Records that matched on key fields but have different variation margin amounts (highlighted in yellow)

## Reconciliation Logic

The tool performs reconciliation by:

1. **Loading Data**: Reads CSV files and normalizes column names
2. **Creating Composite Keys**: Combines account_id + trade_date + contract_id
3. **Matching**: Identifies records present in both sources
4. **Amount Comparison**: For matched keys, compares variation margin amounts (allows ±$0.01 tolerance for rounding)
5. **Categorizing Results**:
   - Matched (key match + amount match)
   - Fund Admin Only (key only in fund admin)
   - Custody Only (key only in custody)
   - Amount Mismatches (key match but amount difference > $0.01)

## Testing

Run unit tests:

```bash
pytest tests/ -v
```

Or run a specific test file:

```bash
python tests/test_reconciler.py
```

## Sample Data Scenarios

The included sample data demonstrates various reconciliation scenarios:

- **Perfect Matches**: Records that match on all fields
- **Amount Mismatches**: Records with same key but different amounts (e.g., ACC002 ESH26: $8,750.25 vs $8,750.30)
- **Fund Admin Only**: Record in fund admin but not in custody (e.g., ACC004 ZBH26)
- **Custody Only**: Record in custody but not in fund admin (e.g., ACC003 NQH26 on 2026-02-15)

## Troubleshooting

### File Not Found Error
- Ensure CSV files are in the `data/input/` directory
- Check file names match those specified in `main.py`

### Column Name Errors
- Verify column names in your CSV files
- Update `config/column_mapping.json` to match your actual column names

### Date Format Issues
- Dates should be in a standard format (YYYY-MM-DD, MM/DD/YYYY, etc.)
- pandas will attempt to parse most common date formats automatically

## Future Enhancements

Potential improvements for future versions:

- Support for additional file formats (Excel, JSON, database)
- Configurable tolerance thresholds for amount matching
- Historical tracking and trend analysis
- Email notifications for exceptions
- API integration for automated data retrieval
- Dashboard visualization

## Requirements

- Python 3.7+
- pandas >= 2.0.0
- openpyxl >= 3.1.0
- pytest >= 7.0.0 (for testing)

## License

This project is intended for internal use.

## Support

For issues or questions, please contact your development team.
