import threading
import sys
import os
from fastapi import FastAPI
from dotenv import load_dotenv

# Import your logic
# We need to import the 'main' function or 'run_scraper' logic from your manager/worker
# Since manager.py runs 'run_scraper', we can import that or just the main function.
from manager import run_scraper, post_processing

# Load env vars locally (Railway handles this automatically in production)
load_dotenv()

app = FastAPI()

# Global flag to prevent double-starting
IS_RUNNING = False

@app.get("/")
def read_root():
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
    
    # Define the function to run in thread
    def run_job():
        try:
            # We call the manager logic. 
            # Note: We need to adapt manager.py slightly to be async-friendly 
            # or just call it as is.
            
            # Because manager.py is async, and FastAPI is async, 
            # we run it in a new event loop in this thread.
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

async def run_full_pipeline():
    """
    Wrapper that runs your Manager logic.
    """
    # 1. Run Scraper
    output_csv = await run_scraper()
    
    if output_csv:
        # 2. Run Post-Processing (Embedder & Uploader)
        # We need to pass the csv file path
        post_processing(csv_file=output_csv)
    else:
        print("No data to process.")

# Optional: Status check endpoint
@app.get("/status")
def check_status():
    return {"status": "running" if IS_RUNNING else "idle"}