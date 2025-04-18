import requests
import argparse
from urllib.parse import urlparse, urlunparse, urljoin
import sys

# --- Configuration ---
# Standard locations to check if not found in robots.txt
SITEMAP_LOCATIONS = ["/sitemap_index.xml", "/sitemap.xml"]
# Timeout for requests in seconds
REQUEST_TIMEOUT = 10
# User-Agent string to use for requests
USER_AGENT = ("Mozilla/5.0 (compatible; PythonSitemapChecker/1.0")
              # Optional: Replace with your contact info/repo
# --- End Configuration ---

def get_normalized_url(url_str):
    """Normalizes a URL string, ensuring it has a scheme (defaults to https)."""
    url_str = url_str.strip()
    if not url_str:
        return None

    # Add scheme if missing, default to https
    if not url_str.startswith(('http://', 'https://')):
        url_str = 'https://' + url_str

    try:
        parsed = urlparse(url_str)
        # Reconstruct with just scheme and netloc (domain)
        base_url = urlunparse((parsed.scheme, parsed.netloc, '', '', '', ''))
        return base_url
    except ValueError:
        print(f"    [Error] Invalid URL format: {url_str}", file=sys.stderr)
        return None

def check_url_exists(url):
    """Checks if a URL exists using a HEAD request."""
    try:
        response = requests.head(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': USER_AGENT},
            allow_redirects=True # Follow redirects to find the final location
        )
        # Consider any 2xx status code as success
        if 200 <= response.status_code < 300:
            return True, url # Return the final URL after redirects
        else:
            # print(f"    [Debug] HEAD {url} status: {response.status_code}") # Uncomment for debug
            return False, None
    except requests.exceptions.Timeout:
        print(f"    [Error] Timeout checking {url}", file=sys.stderr)
        return False, None
    except requests.exceptions.ConnectionError:
        print(f"    [Error] Connection error checking {url}", file=sys.stderr)
        return False, None
    except requests.exceptions.RequestException as e:
        print(f"    [Error] Request error checking {url}: {e}", file=sys.stderr)
        return False, None

def find_sitemap_in_robots(base_url):
    """Checks robots.txt for Sitemap directives."""
    robots_url = urljoin(base_url, "/robots.txt")
    sitemap_urls_from_robots = []
    try:
        response = requests.get(
            robots_url,
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': USER_AGENT}
        )
        if response.status_code == 200:
            lines = response.text.splitlines()
            for line in lines:
                line = line.strip()
                if line.lower().startswith('sitemap:'):
                    # Extract the URL part after "Sitemap:"
                    sitemap_url = line[len('sitemap:'):].strip()
                    if sitemap_url:
                        sitemap_urls_from_robots.append(sitemap_url)
                        # print(f"    [Debug] Found Sitemap directive in robots.txt: {sitemap_url}") # Uncomment for debug
            return sitemap_urls_from_robots
        else:
            # print(f"    [Debug] robots.txt not found or accessible (Status: {response.status_code})") # Uncomment for debug
            return []
    except requests.exceptions.Timeout:
        print(f"    [Error] Timeout fetching {robots_url}", file=sys.stderr)
        return []
    except requests.exceptions.ConnectionError:
        print(f"    [Error] Connection error fetching {robots_url}", file=sys.stderr)
        return []
    except requests.exceptions.RequestException as e:
        print(f"    [Error] Request error fetching {robots_url}: {e}", file=sys.stderr)
        return []

def check_website_for_sitemap(url_str):
    """Checks a website for a sitemap (robots.txt then common locations)."""
    base_url = get_normalized_url(url_str)
    if not base_url:
        return f"{url_str}: Invalid URL"

    print(f"Checking: {base_url}")

    # 1. Check robots.txt
    sitemaps_in_robots = find_sitemap_in_robots(base_url)
    for sitemap_url in sitemaps_in_robots:
        # Validate the sitemap URL found in robots.txt
        exists, final_sitemap_url = check_url_exists(sitemap_url)
        if exists:
            return f"{base_url}: Sitemap Found (from robots.txt): {final_sitemap_url}"
        else:
             print(f"    [Warning] Sitemap listed in robots.txt ({sitemap_url}) not found or inaccessible.")

    # 2. Check standard locations if not found via robots.txt
    print(f"    Sitemap not found via robots.txt, checking standard locations...")
    for location in SITEMAP_LOCATIONS:
        potential_sitemap_url = urljoin(base_url, location)
        exists, final_sitemap_url = check_url_exists(potential_sitemap_url)
        if exists:
            return f"{base_url}: Sitemap Found (standard location): {final_sitemap_url}"

    # 3. If nothing found
    return f"{base_url}: Sitemap NOT Found"

def main():
    parser = argparse.ArgumentParser(description="Check websites listed in a file for sitemaps.")
    parser.add_argument("filename", help="Path to the text file containing URLs (one per line).")
    args = parser.parse_args()

    try:
        with open(args.filename, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print(f"Error: File not found '{args.filename}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{args.filename}': {e}", file=sys.stderr)
        sys.exit(1)

    if not urls:
        print(f"No valid URLs found in '{args.filename}'. Ensure the file is not empty and URLs are one per line.")
        sys.exit(0)

    print(f"--- Starting Sitemap Check ({len(urls)} URLs from {args.filename}) ---")
    results = []
    for url in urls:
        result = check_website_for_sitemap(url)
        results.append(result)
        print(f"    -> Result: {result.split(': ', 1)[1]}\n") # Print result clearly

    print("--- Sitemap Check Complete ---")
    # Optional: Print summary again if needed
    # print("\n--- Summary ---")
    # for res in results:
    #     print(res)

if __name__ == "__main__":
    main()
