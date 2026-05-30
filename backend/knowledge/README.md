# RUI AI Knowledge Base

Put your RAG documents in this folder.

Supported file types:
- `.txt`
- `.md`
- `.py`

The backend will chunk these files, use HyDE to improve retrieval, rerank the results with a cross-encoder style scorer, and pass the top context into the chat model.
