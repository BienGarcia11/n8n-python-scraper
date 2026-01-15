import threading
import sys
import os
import asyncio
from fastapi import FastAPI
from dotenv import load_dotenv

# Import your logic from manager.py
from manager import run_scraper, post_processing

# Load environment variables (Good for local dev, safe for Railway too)
load_dotenv()

app = FastAPI()

# Global flag to prevent double-starting
IS_RUNNING = False

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {"status": "ready", "message": "Call POST /start to begin scraping"}

@app.post("/start")
def start_scraping_job():
    """
    Starts the scraper in a background thread.
    Returns immediately so the HTTP request doesn't timeout.
    """
    global IS_RUNNING
    
    if IS_RUNNING:
        return {"status": "error", "message": "Job is already running"}
    
    IS_RUNNING = True
    
    # Define the function to run in the thread
    def run_job():
        try:
            # We run the full pipeline logic.
            # Because manager.py is async, and we are in a standard thread,
            # we need to run it in a new event loop using asyncio.run()
            asyncio.run(run_full_pipeline())
        except Exception as e:
            print(f"Job failed: {e}")
        finally:
            global IS_RUNNING
            IS_RUNNING = False
            
    # Start the thread
    thread = threading.Thread(target=run_job)
    thread.start()
    
    return {"status": "started", "message": "Scraping started in background."}

@app.get("/status")
def check_status():
    """Check if the job is currently running"""
    return {"status": "running" if IS_RUNNING else "idle"}

# --- PIPELINE WRAPPER ---
async def run_full_pipeline():
    """
    Wrapper that runs your Manager logic (Scraper -> Embedder -> Uploader).
    """
    try:
        # 1. Run Scraper
        output_csv = await run_scraper()
        
        if output_csv:
            # 2. Run Post-Processing (Embedder & Uploader)
            post_processing(csv_file=output_csv)
        else:
            print("Controller: Worker returned no file. Exiting.")
            
    except Exception as e:
        print(f"Controller: Error {e}")