import threading
import sys
import os
import asyncio
from fastapi import FastAPI
from dotenv import load_dotenv

# Import your logic
from manager import run_scraper, post_processing

# Load env vars
load_dotenv()

app = FastAPI()

# --- THREAD MANAGEMENT ---
IS_RUNNING = False
JOB_THREAD = None # Track the actual thread object

@app.get("/")
def read_root():
    return {"status": "ready", "message": "Call POST /start to begin scraping"}

@app.post("/start")
def start_scraping_job():
    global IS_RUNNING, JOB_THREAD
    
    if IS_RUNNING:
        return {"status": "error", "message": "Job is already running"}
    
    IS_RUNNING = True
    
    # Define the function to run in thread
    def run_job():
        try:
            # We run the full pipeline logic.
            asyncio.run(run_full_pipeline())
        except Exception as e:
            print(f"Job failed: {e}")
        finally:
            global IS_RUNNING
            IS_RUNNING = False
            
    # Start the thread and save reference
    JOB_THREAD = threading.Thread(target=run_job)
    JOB_THREAD.start()
    
    return {"status": "started", "message": "Scraping started in background."}

@app.get("/status")
def check_status():
    """
    Checks if the specific thread is alive.
    More reliable than just checking a boolean.
    """
    if JOB_THREAD and JOB_THREAD.is_alive():
        return {"status": "running", "thread_id": str(JOB_THREAD.ident)}
    else:
        return {"status": "idle"}

# --- PIPELINE WRAPPER ---
async def run_full_pipeline():
    """
    Wrapper that runs your Manager logic.
    """
    try:
        output_csv = await run_scraper()
        
        if output_csv:
            post_processing(csv_file=output_csv)
        else:
            print("Controller: Worker returned no file. Exiting.")
            
    except Exception as e:
        print(f"Controller: Error {e}")