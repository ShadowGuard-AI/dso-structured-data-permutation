import argparse
import csv
import logging
import os
import random
import sys
from chardet.universaldetector import UniversalDetector


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.
    """
    parser = argparse.ArgumentParser(description='Randomly permutes columns or rows in a structured data file (CSV/TSV).')
    parser.add_argument('input_file', type=str, help='Path to the input CSV/TSV file.')
    parser.add_argument('output_file', type=str, help='Path to the output file.')
    parser.add_argument('--delimiter', type=str, default=',', help='Delimiter used in the input file (default: ,).')
    parser.add_argument('--quotechar', type=str, default='"', help='Quote character used in the input file (default: ").')
    parser.add_argument('--exclude_columns', type=str, default='', help='Comma-separated list of column names/indices to exclude from permutation (e.g., "id,name,0").')
    parser.add_argument('--permute_rows', action='store_true', help='Permute rows instead of columns.')
    parser.add_argument('--encoding', type=str, default=None, help='Encoding of the input file (e.g., utf-8, latin-1). If not provided, attempts to auto-detect.')

    return parser.parse_args()


def detect_encoding(file_path):
    """
    Detects the encoding of a file.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The detected encoding, or None if detection fails.
    """
    # I feed the detector line by line and stop as soon as it decides. Reading
    # the whole file first would give the same answer for most inputs, and
    # this way a large file costs one pass over its opening lines.
    detector = UniversalDetector()
    try:
        with open(file_path, 'rb') as f:
            for line in f:
                detector.feed(line)
                if detector.done:
                    break
            detector.close()
            return detector.result['encoding']
    except Exception as e:
        logging.error(f"Error detecting encoding: {e}")
        return None


def validate_input(args):
    """
    Validates the input arguments.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        bool: True if the input is valid, False otherwise.
    """
    try:
        with open(args.input_file, 'r', encoding=args.encoding or 'utf-8') as f: # Use detected or default encoding here to check file exists
            pass
    except FileNotFoundError:
        logging.error(f"Input file not found: {args.input_file}")
        return False
    except Exception as e:
         logging.error(f"Error opening input file: {e}")
         return False

    return True


def _resolve_exclude_indices(header, exclude_columns):
    indices = set()
    if exclude_columns:
        for col in exclude_columns:
            try:
                # A token that parses as an integer is always treated as an index, never
                # as a name. A column literally named 0 cannot be excluded by name, and
                # with duplicate header names, index() below finds only the first one.
                index = int(col)
                if 0 <= index < len(header):
                    indices.add(index)
                else:
                    logging.warning(f"Invalid column index in exclude_columns: {col}.  Skipping.")
            except ValueError:
                if col in header:
                    indices.add(header.index(col))
                else:
                    logging.warning(f"Column name not found in header: {col}. Skipping.")
    return indices


def _read_all(input_file, delimiter, quotechar, encoding):
    if encoding is None:
        encoding = 'utf-8'
    with open(input_file, 'r', encoding=encoding, newline='') as infile:
        reader = csv.reader(infile, delimiter=delimiter, quotechar=quotechar)
        rows = list(reader)
    if not rows:
        raise ValueError("Input file is empty; nothing to permute.")
    header = rows[0]
    data_rows = rows[1:]
    if not data_rows:
        raise ValueError("Input file has a header only; nothing to permute.")
    for i, row in enumerate(data_rows):
        # Ragged rows are refused outright. Permuting a row with the wrong number
        # of fields would shift values into the wrong columns, which is exactly
        # the kind of silent corruption this check exists to prevent. The row
        # number in the message counts the header as row 1.
        if len(row) != len(header):
            raise ValueError(f"Row {i + 2} has {len(row)} field(s), expected {len(header)}.")
    return header, data_rows


def _write_all(output_file, header, rows, delimiter, quotechar, encoding):
    if encoding is None:
        encoding = 'utf-8'
    with open(output_file, 'w', newline='', encoding=encoding) as outfile:
        writer = csv.writer(outfile, delimiter=delimiter, quotechar=quotechar)
        writer.writerow(header)
        writer.writerows(rows)


def permute_columns(input_file, output_file, delimiter=',', quotechar='"', exclude_columns=None, encoding=None):
    """
    Permutes the order of columns. The same column order is applied to the
    header and to every row, so a column and its values move as a unit.
    Excluded columns stay at their original indices. Errors propagate.
    """
    if os.path.realpath(input_file) == os.path.realpath(output_file):
        raise ValueError("Output file resolves to the input file; refusing to overwrite it.")
    header, data_rows = _read_all(input_file, delimiter, quotechar, encoding)
    num_columns = len(header)
    exclude_indices = _resolve_exclude_indices(header, exclude_columns)
    permute_indices = [i for i in range(num_columns) if i not in exclude_indices]
    if len(permute_indices) < 2:
        raise ValueError("Fewer than two columns are available to permute; nothing would change.")
    shuffled = list(permute_indices)
    # I retry the shuffle rather than accept an identity result. A permutation
    # that changes nothing would still write a file and log success, so after
    # 100 identical draws the rotate below forces at least a positional
    # change. It cannot help when every row is identical; then the output
    # equals the input no matter what, and nothing here can detect that.
    for _attempt in range(100):
        random.shuffle(shuffled)
        if shuffled != permute_indices:
            break
    if shuffled == permute_indices:
        shuffled = shuffled[1:] + shuffled[:1]
    # Excluded columns stay pinned at their original index. The shuffled list
    # fills only the remaining slots, in order, so a column and its values
    # always move together as one unit.
    new_order = []
    it = iter(shuffled)
    for i in range(num_columns):
        if i in exclude_indices:
            new_order.append(i)
        else:
            new_order.append(next(it))
    permuted_header = [header[i] for i in new_order]
    permuted_rows = [[row[i] for i in new_order] for row in data_rows]
    _write_all(output_file, permuted_header, permuted_rows, delimiter, quotechar, encoding)
    logging.info(f"Columns permuted successfully from {input_file} to {output_file}")
    return True


def permute_rows(input_file, output_file, delimiter=',', quotechar='"', exclude_columns=None, encoding=None):
    """
    Permutes the order of rows. When columns are excluded, those columns keep
    their original row order while the remaining columns are permuted as a
    block. Errors propagate.
    """
    if os.path.realpath(input_file) == os.path.realpath(output_file):
        raise ValueError("Output file resolves to the input file; refusing to overwrite it.")
    header, data_rows = _read_all(input_file, delimiter, quotechar, encoding)
    if len(data_rows) < 2:
        raise ValueError("Fewer than two data rows; nothing would change.")
    exclude_indices = _resolve_exclude_indices(header, exclude_columns)
    shuffled_rows = [list(r) for r in data_rows]
    for _attempt in range(100):
        random.shuffle(shuffled_rows)
        if shuffled_rows != data_rows:
            break
    if shuffled_rows == data_rows:
        shuffled_rows = shuffled_rows[1:] + shuffled_rows[:1]
    # With exclusions, the excluded columns keep their original row order
    # while the rest of each row comes from the shuffled copy. That breaks
    # the link between an excluded identifier column and the values it used
    # to sit beside, which is the point of permuting for release.
    if exclude_indices:
        out_rows = []
        for i, original in enumerate(data_rows):
            row = []
            for c in range(len(header)):
                if c in exclude_indices:
                    row.append(original[c])
                else:
                    row.append(shuffled_rows[i][c])
            out_rows.append(row)
    else:
        out_rows = shuffled_rows
    _write_all(output_file, header, out_rows, delimiter, quotechar, encoding)
    logging.info(f"Rows permuted successfully from {input_file} to {output_file}")
    return True


def main():
    """
    Main function to parse arguments and execute the permutation.
    """
    args = setup_argparse()

    # Detect encoding if not specified
    if not args.encoding:
        args.encoding = detect_encoding(args.input_file)
        if args.encoding:
            logging.info(f"Detected encoding: {args.encoding}")
        else:
            logging.warning("Failed to detect encoding, using utf-8 as default.")
            args.encoding = 'utf-8'


    # validate_input only proves the file opens. Shape problems, ragged rows,
    # and too little data are caught later in _read_all, inside the try.
    if not validate_input(args):
        sys.exit(1)

    exclude_columns = [col.strip() for col in args.exclude_columns.split(',') if col.strip()] if args.exclude_columns else None


    if os.path.realpath(args.input_file) == os.path.realpath(args.output_file):
        logging.error("Output file resolves to the input file; refusing to overwrite it.")
        sys.exit(1)

    try:
        if args.permute_rows:
            permute_rows(args.input_file, args.output_file, args.delimiter, args.quotechar, exclude_columns, args.encoding)
        else:
            permute_columns(args.input_file, args.output_file, args.delimiter, args.quotechar, exclude_columns, args.encoding)
    except Exception as e:
        logging.error(f"Permutation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()