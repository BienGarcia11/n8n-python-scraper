import asyncio
import pandas as pd
from worker import run_scraper
from embedder import generate_embeddings # Import the new embedder

# --- POST PROCESSING LOGIC ---
def post_processing(file_path):
    """
    Runs after scraping. 
    1. Scrapes (already done).
    2. Generates Embeddings.
    """
    print(f"\nManager: Loading data from {file_path}...")
    
    try:
        df = pd.read_excel(file_path)
        
        # Stats
        total = len(df)
        success = len(df[df['status'] == 'Success'])
        print(f"Manager: Total Rows: {total}")
        print(f"Manager: Successful Scrapes: {success}")
        
        # --- RUN EMBEDDER ---
        if success > 0:
            print("Manager: Starting Embedding process...")
            generate_embeddings(input_file=file_path, output_file="embedded_data.xlsx")
        else:
            print("Manager: No data to embed.")
        
    except Exception as e:
        print(f"Manager: Error during processing: {e}")

# --- MAIN CONTROLLER ---
async def main():
    try:
        # 1. RUN SCRAPER
        output_file = await run_scraper()
        
        if output_file:
            # 2. RUN EMBEDDER
            post_processing(output_file)
        else:
            print("Manager: Worker returned no file. Exiting.")
            
    except KeyboardInterrupt:
        print("\nManager: Stopped by user.")

if __name__ == "__main__":
    asyncio.run(main())