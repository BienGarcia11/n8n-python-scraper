#!/usr/bin/env python3
"""Test script to trigger bulk scrape on Railway"""
import requests
import json

url = "http://n8n-python-scraper-production.up.railway.app/scrape/bulk"

print("Sending POST request to bulk scrape endpoint...")
print(f"URL: {url}")

try:
    response = requests.post(url, headers={"Content-Type": "application/json"})
    
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        print("\n✅ Bulk scrape started successfully!")
    else:
        print(f"\n❌ Failed to start bulk scrape: {response.text}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
