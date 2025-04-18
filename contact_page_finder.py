#!/usr/bin/env python3

import argparse
import argparse
import concurrent.futures
import logging
import sys
from urllib.parse import urljoin, urlparse

import psycopg2 # Database connector
import requests
from tqdm import tqdm

# --- Configuration ---

# Database connection URI
DATABASE_URI = "postgresql://postgres:postgres@localhost/gov"
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

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URI)
        return conn
    except psycopg2.OperationalError as e:
        log.error(f"Database connection failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"An unexpected error occurred during DB connection: {e}")
        sys.exit(1)

def fetch_members_from_db() -> list[tuple[str, str | None]]:
    """Fetches bioguideid and officialwebsiteurl for current members."""
    conn = get_db_connection()
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

def create_contact_table():
    """Creates the members_contact table if it doesn't exist."""
    conn = get_db_connection()
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
        conn.rollback() # Rollback changes on error
    finally:
        if conn:
            conn.close()

def store_contact_pages_in_db(contact_data: list[tuple[str, str]]):
    """Stores found contact page URLs in the database."""
    if not contact_data:
        log.info("No contact pages found to store.")
        return

    conn = get_db_connection()
    inserted_count = 0
    updated_count = 0
    try:
        with conn.cursor() as cur:
            # Use INSERT ... ON CONFLICT to handle existing entries (upsert)
            upsert_sql = """
                INSERT INTO members_contact (bioguideid, contact_page)
                VALUES (%s, %s)
                ON CONFLICT (bioguideid) DO UPDATE SET
                    contact_page = EXCLUDED.contact_page;
            """
            # Execute many for efficiency, though we need to track results
            # psycopg2 doesn't directly return counts per row for execute_batch or executemany easily
            # So we iterate and check rowcount for simplicity here
            for bioguideid, url in contact_data:
                 cur.execute(upsert_sql, (bioguideid, url))
                 # Check if insert or update occurred (rowcount is 1 for both in upsert)
                 # A more precise way would involve checking if the value changed,
                 # but for this use case, just knowing it was processed is likely sufficient.
                 # We'll just count successful executions.
                 if cur.rowcount > 0:
                     inserted_count += 1 # Count all successful upserts

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
        A tuple (bioguideid, base_url) if the contact page exists,
        otherwise None.
    """
    bioguideid, base_url = member_data

    if not base_url or not isinstance(base_url, str):
        # log.debug(f"Skipping member {bioguideid} due to missing or invalid URL.")
        return None
    if not base_url.startswith(("http://", "https://")):
        log.warning(f"Skipping invalid URL scheme for member {bioguideid}: {base_url}")
        return None

    # Ensure base_url ends with '/' for urljoin to work correctly if path is relative
    if not base_url.endswith('/'):
        base_url += '/'

    contact_url = urljoin(base_url, CONTACT_PATH.lstrip('/')) # Ensure CONTACT_PATH joins correctly
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.head(
            contact_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False, # Check the status code directly, don't follow redirects
        )
        # Accept 200 OK, or 301/302 Redirects as indicators of a contact page
        if response.status_code in [200, 301, 302]:
            # We assume a 200 or a redirect from /contact means a contact page exists
            return (bioguideid, base_url)
        else:
            # log.debug(f"Contact page not found for {bioguideid} (URL: {contact_url}, Status: {response.status_code})")
            return None
    except requests.exceptions.Timeout:
        # log.debug(f"Timeout checking {contact_url} for {bioguideid}")
        return None
    except requests.exceptions.RequestException as e:
        # log.debug(f"Error checking {contact_url} for {bioguideid}: {e}")
        return None
    except Exception as e:
        # Catch any other unexpected errors during the check
        log.error(f"Unexpected error checking {contact_url} for {bioguideid}: {e}")
        return None


# --- Main Execution ---

def main():
    """Main function to coordinate the process."""
    """Main function to coordinate the process."""
    parser = argparse.ArgumentParser(
        description="Check member websites for a /contact page and store results in DB."
    )
    # Removed input/output file arguments
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

    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG) # Adjust root logger too if needed
        log.debug("Verbose logging enabled.")

    # Ensure the target table exists
    create_contact_table()

    # Fetch member data (bioguideid, url) from the database
    members_data = fetch_members_from_db()
    if not members_data:
        log.warning("No member data fetched from the database. Exiting.")
        return

    found_contacts = []
    not_found_count = 0
    skipped_count = 0
    total_members = len(members_data)

    # Initialize tqdm progress bar
    progress_bar = tqdm(total=total_members, desc="Checking Member URLs", unit="member")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks, passing the (bioguideid, url) tuple
        future_to_member = {
            executor.submit(check_contact_page, member_info): member_info
            for member_info in members_data
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_member):
            member_info = future_to_member[future] # Get original input tuple
            bioguideid, base_url = member_info

            if base_url is None: # Track members skipped due to no URL initially
                skipped_count += 1
                progress_bar.update(1)
                continue # Skip processing if URL was None

            try:
                result = future.result() # result is (bioguideid, base_url) or None
                if result:
                    found_contacts.append(result)
                else:
                    not_found_count += 1
            except Exception as exc:
                log.error(f"Member {bioguideid} generated an exception: {exc}")
                not_found_count += 1 # Count exceptions as not found

            # Update progress bar postfix with current counts
            progress_bar.set_postfix(
                found=len(found_contacts), not_found=not_found_count, skipped=skipped_count, refresh=True
            )
            progress_bar.update(1) # Increment progress bar

    progress_bar.close() # Close the progress bar

    log.info(f"Finished checking {total_members} members.")
    log.info(f"Found {len(found_contacts)} members with contact pages.")
    log.info(f"{not_found_count} members without accessible contact pages.")
    if skipped_count > 0:
        log.info(f"{skipped_count} members skipped due to missing website URL in database.")

    # Store the found contact data in the database
    if found_contacts:
        store_contact_pages_in_db(found_contacts)
    else:
        log.info("No new contact pages found to store in the database.")


if __name__ == "__main__":
    main()
