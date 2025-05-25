#!/usr/bin/env python3
"""Main CLI entry point for district-offices tool."""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    """Main entry point for district-offices CLI."""
    parser = argparse.ArgumentParser(
        prog='district-offices',
        description='Extract and validate district office information from congressional representatives\' websites.'
    )
    
    subparsers = parser.add_subparsers(
        title='commands',
        dest='command',
        help='Available commands',
        required=True
    )
    
    # Scrape command
    scrape_parser = subparsers.add_parser(
        'scrape',
        help='Extract district office information from websites'
    )
    scrape_parser.add_argument(
        '--bioguide-id',
        type=str,
        help='Process a specific bioguide ID'
    )
    scrape_parser.add_argument(
        '--all',
        action='store_true',
        help='Process all bioguide IDs without district office information'
    )
    scrape_parser.add_argument(
        '--db-uri',
        type=str,
        help='Database URI (if not provided, uses DATABASE_URI environment variable)'
    )
    scrape_parser.add_argument(
        '--api-key',
        type=str,
        help='Anthropic API key (if not provided, uses ANTHROPIC_API_KEY environment variable)'
    )
    scrape_parser.add_argument(
        '--force',
        action='store_true',
        help='Force processing even if district office data already exists'
    )
    scrape_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Validate command
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate extracted district office data (uses browser-based validation by default)'
    )
    validate_parser.add_argument(
        '--bioguide-id',
        type=str,
        help='Validate a specific bioguide ID extraction'
    )
    validate_parser.add_argument(
        '--all-pending',
        action='store_true',
        help='Validate all pending extractions'
    )
    validate_parser.add_argument(
        '--db-uri',
        type=str,
        help='Database URI for storage (if not provided, uses DATABASE_URI environment variable)'
    )
    validate_parser.add_argument(
        '--batch-size',
        type=int,
        help='Maximum number of extractions to validate in this run'
    )
    validate_parser.add_argument(
        '--force',
        action='store_true',
        help='Re-validate previously processed extractions'
    )
    validate_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    # Find contacts command
    contacts_parser = subparsers.add_parser(
        'find-contacts',
        help='Find contact pages on representatives\' websites'
    )
    contacts_parser.add_argument(
        '-w', '--workers',
        type=int,
        default=5,
        help='Number of concurrent workers (default: 5)'
    )
    contacts_parser.add_argument(
        '--store-db',
        action='store_true',
        help='Store the results in the database'
    )
    contacts_parser.add_argument(
        '--db-uri',
        type=str,
        help='Database URI (if not provided, uses DATABASE_URI environment variable)'
    )
    contacts_parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output file to save results (if not storing in database)'
    )
    contacts_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Route to appropriate command handler
    if args.command == 'scrape':
        from cli.scrape import main as scrape_main
        # Convert args back to sys.argv format for scrape_main
        sys.argv = ['district-offices-scrape']
        if args.bioguide_id:
            sys.argv.extend(['--bioguide-id', args.bioguide_id])
        if args.all:
            sys.argv.append('--all')
        if args.db_uri:
            sys.argv.extend(['--db-uri', args.db_uri])
        if args.api_key:
            sys.argv.extend(['--api-key', args.api_key])
        if args.force:
            sys.argv.append('--force')
        if args.verbose:
            sys.argv.append('--verbose')
        scrape_main()
        
    elif args.command == 'validate':
        from cli.validate import main as validate_main
        # Convert args back to sys.argv format for validate_main
        sys.argv = ['district-offices-validate']
        if args.bioguide_id:
            sys.argv.extend(['--bioguide-id', args.bioguide_id])
        if args.all_pending:
            sys.argv.append('--all-pending')
        if args.db_uri:
            sys.argv.extend(['--db-uri', args.db_uri])
        if args.batch_size:
            sys.argv.extend(['--batch-size', str(args.batch_size)])
        if args.force:
            sys.argv.append('--force')
        if args.verbose:
            sys.argv.append('--verbose')
        validate_main()
        
    elif args.command == 'find-contacts':
        from cli.find_contacts import main as find_contacts_main
        # Convert args back to sys.argv format for find_contacts_main
        sys.argv = ['district-offices-find-contacts']
        if args.workers != 5:
            sys.argv.extend(['-w', str(args.workers)])
        if args.store_db:
            sys.argv.append('--store-db')
        if args.db_uri:
            sys.argv.extend(['--db-uri', args.db_uri])
        if args.output:
            sys.argv.extend(['-o', args.output])
        if args.verbose:
            sys.argv.append('--verbose')
        find_contacts_main()

if __name__ == '__main__':
    main()