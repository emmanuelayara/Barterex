#!/usr/bin/env python3
"""
Simple test to verify the valuation system is working
"""

import requests
import json

BASE_URL = "http://127.0.0.1:5000"
HEADERS = {"Content-Type": "application/json"}

def test_valuation():
    """Test the price estimation API"""
    
    print("\n" + "="*60)
    print("TESTING BARTEREX PRICE ESTIMATION API")
    print("="*60 + "\n")
    
    # Test data
    payload = {
        "item_name": "Samsung Galaxy A23",
        "description": "Samsung Galaxy A23 in good condition, used for 1 year",
        "condition": "good",
        "category": "Phones & Gadgets",
        "images": []
    }
    
    print(f"📤 Sending request to: {BASE_URL}/api/estimate-price")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}\n")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/estimate-price",
            json=payload,
            headers=HEADERS,
            timeout=30
        )
        
        print(f"✓ Response Status: {response.status_code}\n")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ SUCCESS! API returned data:")
            print(json.dumps(data, indent=2))
            
            if data.get('success'):
                price = data.get('price_estimate', {})
                credit = data.get('credit_value', {})
                
                print(f"\n✨ ESTIMATION RESULTS:")
                print(f"   Estimated Price: ${price.get('estimated_price', 'N/A')}")
                print(f"   Confidence: {price.get('confidence', 'N/A')}")
                print(f"   Price Range: ${price.get('price_range', {}).get('min', 'N/A')} - ${price.get('price_range', {}).get('max', 'N/A')}")
                print(f"   Credit Value: ${credit.get('credit_value', 'N/A')}")
                print(f"   Data Points: {price.get('data_points', 0)}")
            else:
                print(f"\n❌ API returned error: {data.get('error', 'Unknown error')}")
        else:
            print(f"❌ API Error! Status: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {type(e).__name__}: {str(e)}")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    test_valuation()
