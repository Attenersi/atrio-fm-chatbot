from __future__ import annotations

import re
import uuid
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CHROMA_DIR, DOCS_DIR
from .llm import embed


def _infer_doc_title(source_name: str, text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("#"):
            return cleaned.lstrip("#").strip()[:120]
        if cleaned:
            return cleaned[:120]
    stem = Path(source_name).stem.replace("_", " ").replace("-", " ")
    return stem[:120]


def _keywords(text: str, limit: int = 12) -> str:
    words = re.findall(r"[a-zA-Z0-9]{4,}", text.lower())
    seen: list[str] = []
    for word in words:
        if word in seen:
            continue
        seen.append(word)
        if len(seen) >= limit:
            break
    return ",".join(seen)


def _load_docs(docs_dir: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for path in docs_dir.glob("*"):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        docs.append(
            {
                "source": path.name,
                "text": text,
                "title": _infer_doc_title(path.name, text),
            }
        )
    return docs


def run_ingest() -> int:
    docs_dir = Path(DOCS_DIR)
    chroma_dir = Path(CHROMA_DIR)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    raw_docs = _load_docs(docs_dir)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
    )

    chunks: list[str] = []
    metas: list[dict[str, str]] = []
    for doc in raw_docs:
        split = splitter.split_text(doc["text"])
        for idx, chunk in enumerate(split):
            chunks.append(chunk)
            metas.append(
                {
                    "source": doc["source"],
                    "title": doc["title"],
                    "chunk_index": str(idx),
                    "chunk_chars": str(len(chunk)),
                    "keywords": _keywords(chunk),
                }
            )

    if not chunks:
        return 0

    vectors = embed(chunks, input_type="passage")
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection("fm_docs")
    # Rebuild index deterministically on each ingest.
    existing = collection.get(include=[])
    existing_ids = existing.get("ids", [])
    if existing_ids:
        collection.delete(ids=existing_ids)

    ids = [str(uuid.uuid4()) for _ in chunks]
    collection.add(ids=ids, documents=chunks, embeddings=vectors, metadatas=metas)
    return len(chunks)


if __name__ == "__main__":
    count = run_ingest()
    print(f"Ingested {count} chunks.")
