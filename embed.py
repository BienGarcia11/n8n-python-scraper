import sys
import argparse
import requests
import json
import base64
from fastembed import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter

def process_document(text, metadata=None, chunk_size=500, chunk_overlap=50):
    print("Loading model...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    print(f"Splitting document ({len(text)} chars)...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len
    )
    chunks = splitter.split_text(text)
    print(f"Created {len(chunks)} chunks.")

    print("Generating embeddings...")
    embeddings_generator = model.embed(chunks)
    embeddings_list = list(embeddings_generator)

    results = []
    for i, chunk in enumerate(chunks):
        item = {
            "content": chunk,
            "embedding": embeddings_list[i].tolist(),
            "chunk_index": i
        }
        if metadata:
            item["metadata"] = metadata
        results.append(item)

    return results

def main():
    parser = argparse.ArgumentParser(description="Split and embed text, returning JSON to n8n.")
    parser.add_argument("--text", required=True, help="Base64-encoded text to embed.")
    parser.add_argument("--callback_url", required=True, help="The n8n webhook URL to send the result to.")
    parser.add_argument("--metadata", required=False, help="JSON string of metadata to pass through.")
    parser.add_argument("--chunk_size", type=int, default=500, help="Chars per chunk")
    parser.add_argument("--chunk_overlap", type=int, default=50, help="Overlap chars")

    args = parser.parse_args()

    try:
        # Decode base64 text
        try:
            text = base64.b64decode(args.text).decode('utf-8')
            print(f"Decoded {len(text)} characters from base64 input")
        except Exception as decode_error:
            print(f"Base64 decode failed, treating as plain text: {decode_error}")
            text = args.text

        metadata = None
        if args.metadata:
            metadata = json.loads(args.metadata)

        results = process_document(text, metadata, args.chunk_size, args.chunk_overlap)

        payload = {
            "results": results,
            "status": "success",
            "total_chunks": len(results)
        }

        print(f"Sending {len(results)} embeddings to callback: {args.callback_url}")
        response = requests.post(args.callback_url, json=payload, timeout=60)
        print(f"Callback response: {response.status_code} {response.text}")

    except Exception as e:
        print(f"Error: {e}")
        error_payload = {
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