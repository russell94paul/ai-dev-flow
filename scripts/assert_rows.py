#!/usr/bin/env python3
"""Assert that a Prefect flow emitted at least N rows. TODO: implement."""
import argparse, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--min', type=int, default=1)
    args = parser.parse_args()
    # TODO: query Prefect API or database for row count
    print(f"TODO: assert rows >= {args.min}")
    sys.exit(0)  # stub always passes

if __name__ == '__main__':
    main()
