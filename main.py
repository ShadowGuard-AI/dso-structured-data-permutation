import argparse
import csv
import logging
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


def permute_columns(input_file, output_file, delimiter=',', quotechar='"', exclude_columns=None, encoding=None):
    """
    Permutes the order of columns in a CSV/TSV file.

    Args:
        input_file (str): Path to the input file.
        output_file (str): Path to the output file.
        delimiter (str): Delimiter used in the file (default: ,).
        quotechar (str): Quote character used in the file (default: ").
        exclude_columns (list): List of column names/indices to exclude from permutation (default: None).
        encoding (str): Encoding of the file (default: None).
    """
    try:
        with open(input_file, 'r', encoding=encoding) as infile, open(output_file, 'w', newline='', encoding=encoding) as outfile:
            reader = csv.reader(infile, delimiter=delimiter, quotechar=quotechar)
            writer = csv.writer(outfile, delimiter=delimiter, quotechar=quotechar)

            header = next(reader)
            num_columns = len(header)

            if exclude_columns:
                # Convert exclude_columns to a set for faster lookup
                exclude_indices = set()
                for col in exclude_columns:
                    try:
                        # Attempt to convert to integer (index)
                        index = int(col)
                        if 0 <= index < num_columns:
                            exclude_indices.add(index)
                        else:
                            logging.warning(f"Invalid column index in exclude_columns: {col}.  Skipping.")

                    except ValueError:
                        # Handle as column name
                        try:
                            index = header.index(col)  # Safer lookup with header index
                            exclude_indices.add(index)
                        except ValueError:
                            logging.warning(f"Column name not found in header: {col}. Skipping.")
                            continue


                # Create a list of columns to permute, excluding the specified ones
                permute_indices = [i for i in range(num_columns) if i not in exclude_indices]

                # Create a new header, putting excluded columns in their original positions and permuting the rest
                permuted_header = [None] * num_columns
                permuted_columns = [header[i] for i in permute_indices]
                random.shuffle(permuted_columns)

                permute_index = 0
                for i in range(num_columns):
                    if i in exclude_indices:
                        permuted_header[i] = header[i]
                    else:
                        permuted_header[i] = permuted_columns[permute_index]
                        permute_index += 1


            else:
                 # Simple permutation when no columns are excluded
                permute_indices = list(range(num_columns))
                random.shuffle(permute_indices)
                permuted_header = [header[i] for i in permute_indices]

            writer.writerow(permuted_header)


            for row in reader:
                if len(row) != num_columns:
                    logging.warning(f"Skipping row with incorrect number of columns: {len(row)} != {num_columns}")
                    continue

                permuted_row = [None] * num_columns
                if exclude_columns: # More complex approach necessary if columns are to be skipped
                     row_values = [row[i] for i in permute_indices]
                     permuted_row_values = []

                     permute_index = 0

                     for i in range(num_columns):

                        if i in exclude_indices:
                            permuted_row[i] = row[i] # Add back the skipped columns
                        else:
                            permuted_row[i] = row_values[permute_index]
                            permute_index +=1

                else:
                     permuted_row = [row[i] for i in permute_indices]


                writer.writerow(permuted_row)


        logging.info(f"Columns permuted successfully from {input_file} to {output_file}")

    except Exception as e:
        logging.error(f"Error permuting columns: {e}")



def permute_rows(input_file, output_file, delimiter=',', quotechar='"', exclude_columns=None, encoding=None):
    """
    Permutes the order of rows in a CSV/TSV file.
    """
    try:
        with open(input_file, 'r', encoding=encoding) as infile, open(output_file, 'w', newline='', encoding=encoding) as outfile:
            reader = csv.reader(infile, delimiter=delimiter, quotechar=quotechar)
            writer = csv.writer(outfile, delimiter=delimiter, quotechar=quotechar)

            header = next(reader)
            writer.writerow(header)

            rows = list(reader)
            random.shuffle(rows)

            writer.writerows(rows)

        logging.info(f"Rows permuted successfully from {input_file} to {output_file}")

    except Exception as e:
        logging.error(f"Error permuting rows: {e}")


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


    if not validate_input(args):
        sys.exit(1)

    exclude_columns = [col.strip() for col in args.exclude_columns.split(',') if col.strip()] if args.exclude_columns else None


    if args.permute_rows:
        permute_rows(args.input_file, args.output_file, args.delimiter, args.quotechar, exclude_columns, args.encoding)
    else:
        permute_columns(args.input_file, args.output_file, args.delimiter, args.quotechar, exclude_columns, args.encoding)


if __name__ == "__main__":
    main()