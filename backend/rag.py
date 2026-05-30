import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ai import generate_text


KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".py"}
CHUNK_SIZE = 900
CHUNK_OVERLAP = 160
RETRIEVE_TOP_K = 12
RERANK_TOP_K = 5
MIN_CONFIDENCE = float(os.getenv("RAG_MIN_CONFIDENCE", "1.2"))


@dataclass
class Chunk:
    source: str
    index: int
    content: str


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


_chunks = []
_chunk_terms = []
_idf = {}
_mtime_signature = None


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())


def chunk_text(text: str) -> list[str]:
    clean = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not clean:
        return []

    chunks = []
    start = 0
    while start < len(clean):
        end = min(start + CHUNK_SIZE, len(clean))
        chunks.append(clean[start:end].strip())
        if end == len(clean):
            break
        start = max(0, end - CHUNK_OVERLAP)

    return [chunk for chunk in chunks if chunk]


def knowledge_signature():
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    files = [
        path
        for path in KNOWLEDGE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return tuple(sorted((str(path), path.stat().st_mtime_ns) for path in files))


def rebuild_index(force: bool = False):
    global _chunks, _chunk_terms, _idf, _mtime_signature

    signature = knowledge_signature()
    if not force and signature == _mtime_signature:
        return

    _mtime_signature = signature
    _chunks = []
    _chunk_terms = []
    document_frequency = {}

    for file_path, _ in signature:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative_source = str(path.relative_to(KNOWLEDGE_DIR))

        for index, content in enumerate(chunk_text(text), start=1):
            chunk = Chunk(source=relative_source, index=index, content=content)
            terms = tokenize(content)
            _chunks.append(chunk)
            _chunk_terms.append(terms)

            for term in set(terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1

    total = max(len(_chunks), 1)
    _idf = {
        term: math.log((total + 1) / (count + 0.5)) + 1
        for term, count in document_frequency.items()
    }


def bm25_score(query_terms: list[str], doc_terms: list[str], avg_len: float) -> float:
    if not query_terms or not doc_terms:
        return 0.0

    k1 = 1.5
    b = 0.75
    doc_len = len(doc_terms)
    term_counts = {}
    for term in doc_terms:
        term_counts[term] = term_counts.get(term, 0) + 1

    score = 0.0
    for term in query_terms:
        freq = term_counts.get(term, 0)
        if not freq:
            continue
        idf = _idf.get(term, 0.0)
        denominator = freq + k1 * (1 - b + b * doc_len / max(avg_len, 1))
        score += idf * (freq * (k1 + 1)) / denominator

    return score


def generate_hypothetical_answer(question: str) -> str:
    prompt = f"""
Write a likely answer that could appear in a Traditional Chinese knowledge base.
This text is only for HyDE retrieval. Do not add a title or disclaimer.

Question:
{question}
""".strip()
    return generate_text(prompt)


def retrieve(question: str, hyde_answer: str) -> list[ScoredChunk]:
    rebuild_index()
    if not _chunks:
        return []

    query = f"{question}\n{hyde_answer}"
    query_terms = tokenize(query)
    avg_len = sum(len(terms) for terms in _chunk_terms) / max(len(_chunk_terms), 1)

    scored = [
        ScoredChunk(chunk=chunk, score=bm25_score(query_terms, terms, avg_len))
        for chunk, terms in zip(_chunks, _chunk_terms)
    ]
    scored.sort(key=lambda item: item.score, reverse=True)
    return [item for item in scored[:RETRIEVE_TOP_K] if item.score > 0]


def cross_encoder_score(question: str, content: str) -> float:
    question_terms = set(tokenize(question))
    content_terms = tokenize(content)
    if not question_terms or not content_terms:
        return 0.0

    content_set = set(content_terms)
    overlap = len(question_terms & content_set) / len(question_terms)
    density = sum(1 for term in content_terms if term in question_terms) / len(content_terms)
    return overlap * 0.8 + density * 0.2


def rerank(question: str, candidates: list[ScoredChunk]) -> list[ScoredChunk]:
    reranked = []
    for candidate in candidates:
        ce_score = cross_encoder_score(question, candidate.chunk.content)
        final_score = candidate.score * 0.35 + ce_score * 10 * 0.65
        reranked.append(ScoredChunk(chunk=candidate.chunk, score=final_score))

    reranked.sort(key=lambda item: item.score, reverse=True)
    return reranked[:RERANK_TOP_K]


def build_context(scored_chunks: list[ScoredChunk]) -> str:
    blocks = []
    for item in scored_chunks:
        chunk = item.chunk
        blocks.append(
            f"[source: {chunk.source}#{chunk.index}, score: {item.score:.2f}]\n"
            f"{chunk.content}"
        )
    return "\n\n---\n\n".join(blocks)


def rag_context(question: str) -> dict:
    hyde_answer = generate_hypothetical_answer(question)
    candidates = retrieve(question, hyde_answer)
    reranked = rerank(question, candidates)
    confidence = reranked[0].score if reranked else 0.0

    return {
        "hyde_answer": hyde_answer,
        "context": build_context(reranked),
        "confidence": round(confidence, 4),
        "min_confidence": MIN_CONFIDENCE,
        "passed": confidence >= MIN_CONFIDENCE,
        "sources": [
            {
                "source": item.chunk.source,
                "chunk": item.chunk.index,
                "score": round(item.score, 4),
            }
            for item in reranked
        ],
    }
