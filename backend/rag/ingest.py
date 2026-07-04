import os
import sys
import shutil

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)
from langchain_community.document_loaders import DirectoryLoader, UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

import config

FAISS_INDEX_PATH = "faiss_index"


def load_pdfs(data_dir: str):
    if not os.path.isdir(data_dir):
        print(f"[ERROR] DATA_DIR '{data_dir}' does not exist.")
        sys.exit(1)

    pdf_files = [f for f in os.listdir(data_dir) if f.endswith(".pdf")]
    if not pdf_files:
        print(f"[ERROR] No PDF files found in '{data_dir}'.")
        sys.exit(1)

    print(f"[1/4] Found {len(pdf_files)} PDF(s): {pdf_files}")
    loader = DirectoryLoader(data_dir, glob="*.pdf", loader_cls=UnstructuredPDFLoader, loader_kwargs={ "strategy": "hi_res"})
    docs = [d for d in loader.load() if d.page_content.strip()]
    print(f"      Loaded {len(docs)} non-empty pages.")
    return docs


def split_documents(docs):
    print(f"[2/4] Splitting into chunks (size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP})...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    print(f"      Created {len(chunks)} chunks.")
    return chunks


def build_embeddings():
    print(f"[3/4] Loading embedding model: {config.EMBEDDING_MODEL} ...")
    embeddings = HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    print("      Embedding model ready.")
    return embeddings


def save_to_faiss(chunks, embeddings):
    print(f"[4/4] Building FAISS index...")
    total = len(chunks)

    if os.path.exists(FAISS_INDEX_PATH):
        print("      Removing old FAISS index...")
        shutil.rmtree(FAISS_INDEX_PATH)

    print("      Creating new FAISS index...")

    vectorstore = FAISS.from_documents(
        chunks,
        embeddings
    )

    vectorstore.save_local(FAISS_INDEX_PATH)
    print(f"\n✅  Ingestion complete! {total} chunks saved to '{FAISS_INDEX_PATH}/'")


def main():
    docs   = load_pdfs(config.DATA_DIR)
    chunks = split_documents(docs)
    emb    = build_embeddings()
    save_to_faiss(chunks, emb)



if __name__ == "__main__":
    main()
