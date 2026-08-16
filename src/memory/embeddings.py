"""Local embeddings for case-memory vectors.

Deliberately not Amazon Bedrock Titan embeddings or an external embeddings
API: this project's only AWS footprint is the AgentCore runtime host, so
embedding stays a local ONNX model (fastembed) with no extra network
dependency or API key. It runs the same way in a laptop dev loop and inside
the AgentCore container.
"""

import os
from functools import lru_cache

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM = 384


@lru_cache(maxsize=1)
def get_embeddings():
    from langchain_community.embeddings import FastEmbedEmbeddings

    model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    return FastEmbedEmbeddings(model_name=model_name)


def get_embedding_dimension() -> int:
    return int(os.getenv("EMBEDDING_DIM", str(DEFAULT_DIM)))
