#!/usr/bin/env python3
"""CLI for validating extracted district office data.

The validation interface now uses browser-based validation by default,
allowing human review with Accept/Reject buttons for each office.
"""

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import validation runner main function
from district_offices.validation.runner import main as validation_main

def main():
    """Entry point for validation CLI."""
    validation_main()

if __name__ == "__main__":
    main()