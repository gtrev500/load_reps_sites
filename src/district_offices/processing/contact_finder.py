#!/usr/bin/env python3

import argparse
import concurrent.futures
import logging
import sys
from urllib.parse import urljoin
import os
import psycopg2  # Database connector
import requests
from tqdm import tqdm

# Add parent directory to path for imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# --- Configuration ---

# Default number of concurrent workers
DEFAULT_WORKERS = 5
# Path to check for the contact page
CONTACT_PATH = "/contact"
# Timeout for requests in seconds
REQUEST_TIMEOUT = 10
# User-Agent string to use for requests
USER_AGENT = "Mozilla/5.0 (compatible; PythonContactPageFinder/1.0)"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


# --- Database Functions ---

def get_db_connection(database_uri):
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(database_uri)
        return conn
    except psycopg2.OperationalError as e:
        log.error(f"Database connection failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"An unexpected error occurred during DB connection: {e}")
        sys.exit(1)

def fetch_members_from_db(database_uri) -> list[tuple[str, str | None]]:
    """Fetches bioguideid and officialwebsiteurl for current members."""
    conn = get_db_connection(database_uri)
    members_data = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT bioguideid, officialwebsiteurl FROM members WHERE currentmember = true"
            )
            members_data = cur.fetchall()
        log.info(f"Fetched {len(members_data)} members from the database.")
    except psycopg2.Error as e:
        log.error(f"Database error during fetch: {e}")
    finally:
        if conn:
            conn.close()
    return members_data

def create_contact_table(database_uri):
    """Creates the members_contact table if it doesn't exist."""
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS members_contact (
                    bioguideid VARCHAR(20) PRIMARY KEY,
                    contact_page VARCHAR(2048) NOT NULL
                );
            """)
            conn.commit()
        log.info("Ensured members_contact table exists.")
    except psycopg2.Error as e:
        log.error(f"Database error creating table: {e}")
        conn.rollback()  # Rollback changes on error
    finally:
        if conn:
            conn.close()

def store_contact_pages_in_db(contact_data: list[tuple[str, str]], database_uri):
    """Stores found contact page URLs in the database."""
    if not contact_data:
        log.info("No contact pages found to store.")
        return

    conn = get_db_connection(database_uri)
    inserted_count = 0
    try:
        with conn.cursor() as cur:
            # Use INSERT ... ON CONFLICT to handle existing entries (upsert)
            upsert_sql = """
                INSERT INTO members_contact (bioguideid, contact_page)
                VALUES (%s, %s)
                ON CONFLICT (bioguideid) DO UPDATE SET
                    contact_page = EXCLUDED.contact_page;
            """
            for bioguideid, url in contact_data:
                 cur.execute(upsert_sql, (bioguideid, url))
                 # Check if insert or update occurred
                 if cur.rowcount > 0:
                     inserted_count += 1  # Count all successful upserts

            conn.commit()
        log.info(f"Successfully stored/updated {inserted_count} contact page entries in the database.")
    except psycopg2.Error as e:
        log.error(f"Database error during storage: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()


# --- Core Logic Functions ---

def check_contact_page(member_data: tuple[str, str | None]) -> tuple[str, str] | None:
    """
    Checks if a /contact page exists for the given member's base URL.

    Args:
        member_data: A tuple containing (bioguideid, base_url).

    Returns:
        A tuple (bioguideid, contact_url) if the contact page exists,
        otherwise None.
    """
    bioguideid, base_url = member_data

    if not base_url or not isinstance(base_url, str):
        return None
    if not base_url.startswith(("http://", "https://")):
        log.warning(f"Skipping invalid URL scheme for member {bioguideid}: {base_url}")
        return None

    # Ensure base_url ends with '/' for urljoin to work correctly if path is relative
    if not base_url.endswith('/'):
        base_url += '/'

    contact_url = urljoin(base_url, CONTACT_PATH.lstrip('/'))  # Ensure CONTACT_PATH joins correctly
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.head(
            contact_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,  # Check the status code directly, don't follow redirects
        )
        # Accept 200 OK, or 301/302 Redirects as indicators of a contact page
        if response.status_code in [200, 301, 302]:
            # We assume a 200 or a redirect from /contact means a contact page exists
            # Return the actual contact URL checked
            return (bioguideid, contact_url)
        else:
            return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.RequestException:
        return None
    except Exception as e:
        # Catch any other unexpected errors during the check
        log.error(f"Unexpected error checking {contact_url} for {bioguideid}: {e}")
        return None

def find_contact_pages(members_data, num_workers=DEFAULT_WORKERS):
    """
    Finds contact pages for a list of members using parallel execution.
    
    Args:
        members_data: List of (bioguideid, url) tuples
        num_workers: Number of parallel workers
        
    Returns:
        Tuple containing (found_contacts, not_found_count, skipped_count)
    """
    found_contacts = []
    not_found_count = 0
    skipped_count = 0
    total_members = len(members_data)

    # Initialize tqdm progress bar
    progress_bar = tqdm(total=total_members, desc="Checking Member URLs", unit="member")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks, passing the (bioguideid, url) tuple
        future_to_member = {
            executor.submit(check_contact_page, member_info): member_info
            for member_info in members_data
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_member):
            member_info = future_to_member[future]  # Get original input tuple
            bioguideid, base_url = member_info

            if base_url is None:  # Track members skipped due to no URL initially
                skipped_count += 1
                progress_bar.update(1)
                continue  # Skip processing if URL was None

            try:
                result = future.result()  # result is (bioguideid, contact_url) or None
                if result:
                    found_contacts.append(result)  # Append the (bioguideid, contact_url) tuple
                else:
                    not_found_count += 1
            except Exception as exc:
                log.error(f"Member {bioguideid} generated an exception: {exc}")
                not_found_count += 1  # Count exceptions as not found

            # Update progress bar postfix with current counts
            progress_bar.set_postfix(
                found=len(found_contacts), not_found=not_found_count, skipped=skipped_count, refresh=True
            )
            progress_bar.update(1)  # Increment progress bar

    progress_bar.close()  # Close the progress bar

    log.info(f"Finished checking {total_members} members.")
    log.info(f"Found {len(found_contacts)} members with contact pages.")
    log.info(f"{not_found_count} members without accessible contact pages.")
    if skipped_count > 0:
        log.info(f"{skipped_count} members skipped due to missing website URL in database.")
        
    return found_contacts, not_found_count, skipped_count


# --- Main Execution ---

def main():
    """Main function to coordinate the process."""
    parser = argparse.ArgumentParser(
        description="Check member websites for a /contact page and optionally store results in DB."
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of concurrent workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--store-db",
        action="store_true",
        help="Store the results in the database",
    )
    parser.add_argument(
        "--db-uri",
        type=str,
        help="Database URI (if not provided, uses DATABASE_URI environment variable)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file to save results (if not storing in database)",
    )

    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)  # Adjust root logger too if needed
        log.debug("Verbose logging enabled.")
    
    # Determine database URI
    database_uri = None
    if args.store_db or args.db_uri:
        database_uri = args.db_uri or os.environ.get("DATABASE_URI")
        if not database_uri:
            log.error("Database URI not provided and DATABASE_URI environment variable not set.")
            sys.exit(1)
    
    # Ensure the target table exists if storing in DB
    if args.store_db:
        create_contact_table(database_uri)

    # Fetch member data (bioguideid, url) from the database
    if database_uri:
        members_data = fetch_members_from_db(database_uri)
        if not members_data:
            log.warning("No member data fetched from the database. Exiting.")
            return
    else:
        log.error("Database connection required to fetch members. Please provide --db-uri or set DATABASE_URI environment variable.")
        sys.exit(1)

    # Find contact pages
    found_contacts, not_found_count, skipped_count = find_contact_pages(
        members_data, num_workers=args.workers
    )

    # Store the found contact data in the database if requested
    if args.store_db and found_contacts:
        log.info("Storing contact pages in database...")
        store_contact_pages_in_db(found_contacts, database_uri)
    elif found_contacts and args.output:
        # Write results to output file if specified
        log.info(f"Writing {len(found_contacts)} contact pages to {args.output}...")
        with open(args.output, 'w') as f:
            for bioguideid, url in found_contacts:
                f.write(f"{bioguideid}\t{url}\n")
        log.info(f"Results written to {args.output}")
    elif found_contacts:
        # Print results to stdout if not storing in DB and no output file specified
        log.info("Contact pages found (not storing in database):")
        for bioguideid, url in found_contacts:
            print(f"{bioguideid}\t{url}")


if __name__ == "__main__":
    main()