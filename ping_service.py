#!/usr/bin/env python3
import requests
import logging
from datetime import datetime
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ping_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)

def ping_service(url):
    """
    Ping the web service to keep it alive
    """
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            logging.info(f"✅ Successfully pinged {url} - Status: {response.status_code}")
            return True
        else:
            logging.warning(f"⚠️ Ping returned status {response.status_code} for {url}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Failed to ping {url}: {str(e)}")
        return False

if __name__ == "__main__":
    # Replace with your actual Render service URL
    SERVICE_URL = "https://barterex.onrender.com"
    
    # You can also add a health check endpoint if you have one
    # SERVICE_URL = "https://your-service-name.onrender.com/health"
    
    logging.info(f"Starting ping job for {SERVICE_URL}")
    ping_service(SERVICE_URL)
    logging.info("Ping job completed")