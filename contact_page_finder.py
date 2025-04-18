#!/usr/bin/env python3

import argparse
import concurrent.futures
import logging
import sys
from urllib.parse import urljoin, urlparse

import requests
from tqdm import tqdm

# --- Configuration ---

# Input file containing base URLs
DEFAULT_INPUT_FILE = "website_members.txt"
# Output file for URLs with contact pages
DEFAULT_OUTPUT_FILE = "contact_pages.txt"
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

# --- Functions ---

def read_urls(filename: str) -> list[str]:
    """Reads URLs from a file, one per line."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        log.info(f"Read {len(urls)} URLs from {filename}")
        return urls
    except FileNotFoundError:
        log.error(f"Error: Input file not found: {filename}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Error reading file {filename}: {e}")
        sys.exit(1)


def check_contact_page(base_url: str) -> str | None:
    """
    Checks if a /contact page exists for the given base URL.

    Args:
        base_url: The base URL of the website (e.g., https://example.com).

    Returns:
        The base_url if the contact page exists and returns HTTP 200,
        otherwise None.
    """
    if not base_url.startswith(("http://", "https://")):
        log.warning(f"Skipping invalid URL scheme: {base_url}")
        return None

    contact_url = urljoin(base_url, CONTACT_PATH)
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
            # Further checks could be added here (e.g., checking Location header for redirects)
            # content_type = response.headers.get('Content-Type', '').lower() # Example check
            # if 'html' in content_type: # Example check
            return base_url
        else:
            # log.debug(f"Contact page not found for {base_url} (URL: {contact_url}, Status: {response.status_code})")
            return None
    except requests.exceptions.Timeout:
        # log.debug(f"Timeout checking {contact_url}")
        return None
    except requests.exceptions.RequestException as e:
        # log.debug(f"Error checking {contact_url}: {e}")
        return None
    except Exception as e:
        # Catch any other unexpected errors during the check
        log.error(f"Unexpected error checking {contact_url}: {e}")
        return None


def write_urls(filename: str, urls: list[str]):
    """Writes URLs to a file, one per line."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for url in sorted(urls): # Sort for consistent output
                f.write(url + "\n")
        log.info(f"Wrote {len(urls)} URLs to {filename}")
    except Exception as e:
        log.error(f"Error writing file {filename}: {e}")
        sys.exit(1)


# --- Main Execution ---

def main():
    """Main function to coordinate the process."""
    parser = argparse.ArgumentParser(
        description="Check websites for a /contact page."
    )
    parser.add_argument(
        "-i",
        "--input",
        default=DEFAULT_INPUT_FILE,
        help=f"Input file with base URLs (default: {DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_FILE,
        help=f"Output file for URLs with contact pages (default: {DEFAULT_OUTPUT_FILE})",
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

    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG) # Adjust root logger too if needed
        log.debug("Verbose logging enabled.")


    base_urls = read_urls(args.input)
    if not base_urls:
        log.warning("No URLs found in the input file. Exiting.")
        return

    found_urls = []
    not_found_count = 0
    total_urls = len(base_urls)

    # Initialize tqdm progress bar
    progress_bar = tqdm(total=total_urls, desc="Checking URLs", unit="url")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(check_contact_page, url): url for url in base_urls
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result()
            if result:
                found_urls.append(result)
            else:
                not_found_count += 1

            # Update progress bar postfix with current counts
            progress_bar.set_postfix(
                found=len(found_urls), not_found=not_found_count, refresh=True
            )
            progress_bar.update(1) # Increment progress bar

    progress_bar.close() # Close the progress bar

    log.info(f"Finished checking {total_urls} URLs.")
    log.info(f"Found {len(found_urls)} URLs with contact pages.")
    log.info(f"{not_found_count} URLs without accessible contact pages.")

    if found_urls:
        write_urls(args.output, found_urls)
    else:
        log.info("No URLs with contact pages found, output file will be empty or not created.")
        # Optionally create an empty file if desired
        # write_urls(args.output, [])


if __name__ == "__main__":
    main()
