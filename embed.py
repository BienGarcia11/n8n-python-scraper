import sys
import argparse
import requests
import json
from fastembed import TextEmbedding

def generate_embedding(text):
    # Load model (downloads ~50MB on first run, cached thereafter)
    print("Loading model...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    
    print("Generating embedding...")
    embedding = list(model.embed([text]))[0]
    return embedding.tolist()

def main():
    parser = argparse.ArgumentParser(description="Generate embeddings using fastembed and return via callback.")
    parser.add_argument("--text", required=True, help="The text to embed.")
    parser.add_argument("--callback_url", required=True, help="The n8n webhook URL to send the result to.")
    
    args = parser.parse_args()
    
    try:
        vector = generate_embedding(args.text)
        
        payload = {
            "text": args.text,
            "embedding": vector,
            "status": "success"
        }
        
        print(f"Sending result to callback URL: {args.callback_url}")
        # Use a timeout to prevent hanging
        response = requests.post(args.callback_url, json=payload, timeout=30)
        print(f"Callback response: {response.status_code} {response.text}")
        
    except Exception as e:
        print(f"Error: {e}")
        # Try to report error to callback if possible
        error_payload = {
            "text": args.text,
            "status": "error",
            "error": str(e)
        }
        try:
            requests.post(args.callback_url, json=error_payload, timeout=30)
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
