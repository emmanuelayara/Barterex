#!/usr/bin/env python3
import requests
import logging
from datetime import datetime
import sys

# Configure logging with UTF-8 encoding for Windows
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ping_log.txt', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def ping_service(url):
    """
    Ping the web service to keep it alive
    """
    try:
        # Increase timeout for sleeping services (first request might be slow)
        response = requests.get(url, timeout=90)
        if response.status_code == 200:
            logging.info(f"SUCCESS: Pinged {url} - Status: {response.status_code}")
            return True
        else:
            logging.warning(f"WARNING: Ping returned status {response.status_code} for {url}")
            return False
    except requests.exceptions.Timeout:
        logging.error(f"TIMEOUT: Service took too long to respond - {url} (This is normal if service was sleeping)")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"ERROR: Failed to ping {url}: {str(e)}")
        return False

if __name__ == "__main__":
    # Replace with your actual Render service URL
    SERVICE_URL = "https://barterex.onrender.com"
    
    # You can also add a health check endpoint if you have one
    # SERVICE_URL = "https://barterex.onrender.com/health"
    
    logging.info(f"Starting ping job for {SERVICE_URL}")
    success = ping_service(SERVICE_URL)
    if success:
        logging.info("Ping job completed successfully")
    else:
        logging.info("Ping job completed with issues (check logs above)")