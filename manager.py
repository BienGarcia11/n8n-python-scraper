import asyncio
import pandas as pd
from dotenv import load_dotenv
from worker import run_scraper
from embedder import generate_embeddings
from uploader import upload_to_supabase
from logger_config import setup_logger

# --- LOGGER SETUP ---
logger = setup_logger("Manager")

# Load environment variables at the very start
load_dotenv()

# --- POST PROCESSING LOGIC ---
def post_processing(csv_file):
    """
    Runs after scraping. 
    1. Reads stats from CSV.
    2. Generates Embeddings.
    3. Uploads to Supabase.
    """
    logger.info(f"Loading stats from {csv_file}...")
    
    try:
        # Read CSV for stats
        df = pd.read_csv(csv_file)
        
        total = len(df)
        success = len(df[df['status'] == 'Success'])
        fail = total - success
        logger.info(f"Total Rows: {total}")
        logger.info(f"Successful Scrapes: {success}")
        logger.info(f"Failed Scrapes: {fail}")
        
        # --- RUN EMBEDDER ---
        if success > 0:
            logger.info("Starting Embedding process...")
            # Input is CSV, Output is CSV
            generate_embeddings(input_file=csv_file, output_file="embedded_data.csv")
            
            # --- RUN UPLOADER ---
            logger.info("Starting Upload process...")
            upload_to_supabase("embedded_data.csv")
        else:
            logger.warning("No data to embed or upload.")
        
    except Exception as e:
        logger.exception(f"Error during processing: {e}")

# --- NEW WRAPPER FOR API ---
async def main_controller():
    """
    This is the function main.py calls. 
    It mimics what the __main__ block did.
    """
    try:
        output_csv = await run_scraper()
        
        if output_csv:
            post_processing(csv_file=output_csv)
        else:
            logger.error("Worker returned no file. Exiting.")
            
    except Exception as e:
        logger.exception(f"Controller Error: {e}")

# Keep this for local testing
if __name__ == "__main__":
    asyncio.run(main_controller())