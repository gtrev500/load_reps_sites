#!/usr/bin/env python3
"""CLI for finding contact pages on representatives' websites."""

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import contact finder main function
from district_offices.processing.contact_finder import main as contact_finder_main

def main():
    """Entry point for contact finder CLI."""
    contact_finder_main()

if __name__ == "__main__":
    main()