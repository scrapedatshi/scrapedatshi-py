"""
scrapedatshi CLI — project scaffolding and quick-query tool.

Usage:
    scrapedatshi init [project-name]
    scrapedatshi query  QUERY  [options]
    scrapedatshi rag-chat QUERY [options]
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from scrapedatshi._templates import (
    ENV_TEMPLATE,
    GITIGNORE_TEMPLATE,
    README_TEMPLATE,
    EXAMPLES,
)

# ── CLI implementation ────────────────────────────────────────────────────────


def _write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def cmd_init(args: list[str]) -> None:
    project_name = args[0] if args else "scrapedatshi-project"
    target = os.path.abspath(project_name)

    if os.path.exists(target):
        print(f"Error: '{project_name}' already exists.", file=sys.stderr)
        sys.exit(1)

    print(f"\n🚀 Creating scrapedatshi project: {project_name}/\n")

    # Prompt for API key
    api_key = ""
    try:
        api_key = input(
            "Enter your scrapedatshi API key (press Enter to skip): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        pass

    # Write .env
    env_content = ENV_TEMPLATE
    if api_key:
        env_content = env_content.replace(
            "SCRAPEDATSHI_API_KEY=sds_...", f"SCRAPEDATSHI_API_KEY={api_key}"
        )
    _write_file(os.path.join(target, ".env"), env_content)

    # Write .gitignore
    _write_file(os.path.join(target, ".gitignore"), GITIGNORE_TEMPLATE)

    # Write README
    _write_file(os.path.join(target, "README.md"), README_TEMPLATE)

    # Write example scripts
    examples_dir = os.path.join(target, "examples")
    for filename, content in EXAMPLES.items():
        _write_file(os.path.join(examples_dir, filename), content)

    # Summary
    files_written = 3 + len(EXAMPLES)  # .env + .gitignore + README + examples
    print(f"  ✓ .env")
    print(f"  ✓ .gitignore")
    print(f"  ✓ README.md")
    for filename in EXAMPLES:
        print(f"  ✓ examples/{filename}")

    print(f"\n✅ Project created ({files_written} files)\n")
    print(textwrap.dedent(f"""\
        Next steps:
          1. cd {project_name}
          2. Edit .env — add your API keys
          3. python examples/00_discover_providers.py
          4. python examples/01_scrape_url.py

        Docs: https://scrapedatshi.com/dev
    """))


# ── Argument parsing helpers ──────────────────────────────────────────────────


def _parse_flags(args: list[str]) -> tuple[list[str], dict[str, str | bool]]:
    """
    Minimal flag parser for CLI commands.

    Supports:
      --flag value    → {"flag": "value"}
      --flag          → {"flag": True}   (boolean flag)

    Returns (positional_args, flags_dict).
    """
    positional: list[str] = []
    flags: dict[str, str | bool] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[key] = args[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            positional.append(arg)
            i += 1
    return positional, flags


def _resolve_key(env_var: str, flag_value: str | bool | None) -> str | None:
    """Resolve an API key from a CLI flag or environment variable."""
    if flag_value and isinstance(flag_value, str):
        return flag_value
    return os.environ.get(env_var)


def _build_vdb_config(flags: dict, vector_db: str) -> dict:
    """
    Build vector_db_config from --config JSON flag + env var fallbacks.

    --config '{"index_host": "https://..."}' merges with env var defaults.
    """
    config: dict = {}

    # Parse --config JSON if provided
    raw_config = flags.get("config", "{}")
    if isinstance(raw_config, str):
        try:
            config = json.loads(raw_config)
        except json.JSONDecodeError:
            print(
                f"Error: --config must be valid JSON. Got: {raw_config}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Env var fallbacks per provider
    if vector_db == "pinecone":
        if not config.get("api_key"):
            config["api_key"] = os.environ.get("PINECONE_API_KEY", "")
        if not config.get("index_host"):
            config["index_host"] = os.environ.get("PINECONE_INDEX_HOST", "")
    elif vector_db == "qdrant":
        if not config.get("url"):
            config["url"] = os.environ.get("QDRANT_URL", "")
        if not config.get("api_key"):
            config["api_key"] = os.environ.get("QDRANT_API_KEY", "")
        if not config.get("collection_name"):
            config["collection_name"] = os.environ.get("QDRANT_COLLECTION_NAME", "")
    elif vector_db == "supabase":
        if not config.get("connection_string"):
            config["connection_string"] = os.environ.get(
                "SUPABASE_CONNECTION_STRING", ""
            )
        if not config.get("table_name"):
            config["table_name"] = os.environ.get("SUPABASE_TABLE_NAME", "documents")
    elif vector_db == "chroma":
        if not config.get("host"):
            config["host"] = os.environ.get("CHROMA_HOST", "localhost")
        if not config.get("port"):
            port_str = os.environ.get("CHROMA_PORT", "8000")
            config["port"] = int(port_str) if port_str.isdigit() else 8000
        if not config.get("collection_name"):
            config["collection_name"] = os.environ.get("CHROMA_COLLECTION_NAME", "")
    elif vector_db == "lancedb":
        if not config.get("db_path"):
            config["db_path"] = os.environ.get("LANCEDB_PATH", "./lancedb")
        if not config.get("table_name"):
            config["table_name"] = os.environ.get("LANCEDB_TABLE_NAME", "documents")
    elif vector_db in ("mongodb", "azure_cosmos_mongo"):
        if not config.get("connection_string"):
            config["connection_string"] = os.environ.get(
                "MONGODB_CONNECTION_STRING", ""
            )
        if not config.get("database_name"):
            config["database_name"] = os.environ.get("MONGODB_DATABASE_NAME", "")
        if not config.get("collection_name"):
            config["collection_name"] = os.environ.get("MONGODB_COLLECTION_NAME", "")
    elif vector_db == "weaviate":
        if not config.get("url"):
            config["url"] = os.environ.get("WEAVIATE_URL", "")
        if not config.get("api_key"):
            config["api_key"] = os.environ.get("WEAVIATE_API_KEY", "")

    return config


# ── query command ─────────────────────────────────────────────────────────────


def cmd_query(args: list[str]) -> None:
    """
    Semantic search against your vector database.

    Usage:
      scrapedatshi query QUERY [options]

    Options:
      --embedding-provider  openai|cohere|gemini|mistral|voyage  (default: openai)
      --embedding-model     model name (default: text-embedding-3-small)
      --embedding-api-key   API key (default: OPENAI_API_KEY env var)
      --vector-db           pinecone|qdrant|chroma|supabase|weaviate|mongodb|lancedb
      --config              JSON string of provider-specific config fields
      --top-k               number of results (default: 5)
      --hybrid              enable hybrid search (vector + BM25 + RRF)
      --rewrite-provider    LLM provider for query rewriting (openai|anthropic|gemini)
      --rewrite-model       LLM model for query rewriting (e.g. gpt-4o-mini)
      --rewrite-api-key     API key for rewrite LLM (default: same as embedding key env)
    """
    positional, flags = _parse_flags(args)

    if not positional:
        print("Error: QUERY is required.", file=sys.stderr)
        print("Usage: scrapedatshi query QUERY [options]", file=sys.stderr)
        sys.exit(1)

    query = positional[0]
    embedding_provider = str(flags.get("embedding_provider", "openai"))
    embedding_model = str(flags.get("embedding_model", "text-embedding-3-small"))
    vector_db = str(flags.get("vector_db", ""))
    top_k = int(str(flags.get("top_k", "5")))
    hybrid = bool(flags.get("hybrid", False))

    if not vector_db:
        print("Error: --vector-db is required.", file=sys.stderr)
        print("Example: --vector-db pinecone", file=sys.stderr)
        sys.exit(1)

    # Resolve embedding API key
    env_map = {
        "openai": "OPENAI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "voyage": "VOYAGE_API_KEY",
    }
    embedding_api_key = _resolve_key(
        env_map.get(embedding_provider, "OPENAI_API_KEY"),
        flags.get("embedding_api_key"),
    )
    if not embedding_api_key and embedding_provider != "ollama":
        print(
            f"Error: No API key for embedding provider '{embedding_provider}'. "
            f"Set {env_map.get(embedding_provider, 'OPENAI_API_KEY')} or pass --embedding-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    vector_db_config = _build_vdb_config(flags, vector_db)

    # Build optional query_rewrite config
    query_rewrite = None
    rewrite_provider = flags.get("rewrite_provider")
    rewrite_model = flags.get("rewrite_model")
    if rewrite_provider and rewrite_model:
        llm_env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        rewrite_api_key = _resolve_key(
            llm_env_map.get(str(rewrite_provider), "OPENAI_API_KEY"),
            flags.get("rewrite_api_key"),
        )
        if rewrite_api_key:
            query_rewrite = {
                "llm_provider": str(rewrite_provider),
                "llm_api_key": rewrite_api_key,
                "llm_model": str(rewrite_model),
            }

    from scrapedatshi import ScrapedatshiClient

    client = ScrapedatshiClient()
    try:
        result = client.pipeline.query_vectordb(
            query=query,
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key or "",
            embedding_model=embedding_model,
            vector_db=vector_db,
            vector_db_config=vector_db_config,
            top_k=top_k,
            hybrid_search=hybrid,
            query_rewrite=query_rewrite,
        )
    finally:
        client.close()

    print(f"Query:    {query}")
    if result.rewritten_query:
        print(f"Rewritten: {result.rewritten_query}")
    print(f"Results:  {result.chunks_retrieved}")
    if result.hybrid_search:
        print(f"Hybrid:   True (vector + BM25 + RRF)")
    print(
        f"Cost:     ${result.credits_used:.4f}  |  Remaining: ${result.credits_remaining:.4f}"
    )
    print()

    for i, r in enumerate(result.results, 1):
        score = r.rrf_score if r.rrf_score is not None else r.score
        print(f"── [{i}] score={score:.4f} ──")
        print(r.text[:500])
        if r.metadata:
            url = r.metadata.get("url") or r.metadata.get("source", "")
            if url:
                print(f"   source: {url}")
        print()


# ── rag-chat command ──────────────────────────────────────────────────────────


def cmd_rag_chat(args: list[str]) -> None:
    """
    Retrieve relevant chunks and generate a grounded LLM answer.

    Usage:
      scrapedatshi rag-chat QUERY [options]

    Options:
      --embedding-provider  openai|cohere|gemini|mistral|voyage  (default: openai)
      --embedding-model     model name (default: text-embedding-3-small)
      --embedding-api-key   API key (default: OPENAI_API_KEY env var)
      --vector-db           pinecone|qdrant|chroma|supabase|weaviate|mongodb|lancedb
      --config              JSON string of provider-specific config fields
      --llm-provider        openai|anthropic|gemini  (default: openai)
      --llm-model           LLM model name (default: gpt-4o-mini)
      --llm-api-key         LLM API key (default: OPENAI_API_KEY env var)
      --top-k               number of chunks to retrieve (default: 5)
      --hybrid              enable hybrid search (vector + BM25 + RRF)
      --query-rewrite       rewrite query before embedding using the answer LLM
    """
    positional, flags = _parse_flags(args)

    if not positional:
        print("Error: QUERY is required.", file=sys.stderr)
        print("Usage: scrapedatshi rag-chat QUERY [options]", file=sys.stderr)
        sys.exit(1)

    query = positional[0]
    embedding_provider = str(flags.get("embedding_provider", "openai"))
    embedding_model = str(flags.get("embedding_model", "text-embedding-3-small"))
    vector_db = str(flags.get("vector_db", ""))
    llm_provider = str(flags.get("llm_provider", "openai"))
    llm_model = str(flags.get("llm_model", "gpt-4o-mini"))
    top_k = int(str(flags.get("top_k", "5")))
    hybrid = bool(flags.get("hybrid", False))
    query_rewrite = bool(flags.get("query_rewrite", False))

    if not vector_db:
        print("Error: --vector-db is required.", file=sys.stderr)
        print("Example: --vector-db pinecone", file=sys.stderr)
        sys.exit(1)

    # Resolve embedding API key
    embed_env_map = {
        "openai": "OPENAI_API_KEY",
        "cohere": "COHERE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "voyage": "VOYAGE_API_KEY",
    }
    embedding_api_key = _resolve_key(
        embed_env_map.get(embedding_provider, "OPENAI_API_KEY"),
        flags.get("embedding_api_key"),
    )
    if not embedding_api_key and embedding_provider != "ollama":
        print(
            f"Error: No API key for embedding provider '{embedding_provider}'. "
            f"Set {embed_env_map.get(embedding_provider, 'OPENAI_API_KEY')} or pass --embedding-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve LLM API key
    llm_env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    llm_api_key = _resolve_key(
        llm_env_map.get(llm_provider, "OPENAI_API_KEY"),
        flags.get("llm_api_key"),
    )
    if not llm_api_key:
        print(
            f"Error: No API key for LLM provider '{llm_provider}'. "
            f"Set {llm_env_map.get(llm_provider, 'OPENAI_API_KEY')} or pass --llm-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    vector_db_config = _build_vdb_config(flags, vector_db)

    from scrapedatshi import ScrapedatshiClient

    client = ScrapedatshiClient()
    try:
        result = client.pipeline.rag_chat(
            query=query,
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key or "",
            embedding_model=embedding_model,
            vector_db=vector_db,
            vector_db_config=vector_db_config,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            top_k=top_k,
            hybrid_search=hybrid,
            query_rewrite=query_rewrite,
        )
    finally:
        client.close()

    print(f"Question:  {query}")
    if result.rewritten_query:
        print(f"Rewritten: {result.rewritten_query}")
    if result.hybrid_search:
        print(f"Hybrid:    True (vector + BM25 + RRF)")
    print(
        f"Chunks:    {result.chunks_retrieved}  |  Cost: ${result.credits_used:.4f}  |  Remaining: ${result.credits_remaining:.4f}"
    )
    if result.llm_error:
        print(f"LLM error: {result.llm_error}", file=sys.stderr)
    print()
    print("Answer:")
    print(result.answer)
    print()
    if result.sources:
        print("Sources:")
        for i, s in enumerate(result.sources, 1):
            score = s.rrf_score if s.rrf_score is not None else s.score
            url = s.metadata.get("url") or s.metadata.get("source", "")
            url_str = f"  ({url})" if url else ""
            print(f"  [{i}] score={score:.4f}{url_str}  {s.text[:100]}...")


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(textwrap.dedent("""\
            scrapedatshi CLI

            Commands:
              init [project-name]   Create a new scrapedatshi sandbox project
                                    (default name: scrapedatshi-project)

              query QUERY           Semantic search against your vector database
                                    --embedding-provider  openai|cohere|gemini|mistral|voyage
                                    --embedding-model     model name
                                    --vector-db           pinecone|qdrant|chroma|supabase|...
                                    --config              JSON config for vector DB
                                    --top-k               number of results (default: 5)
                                    --hybrid              enable hybrid search (BM25 + RRF)
                                    --rewrite-provider    LLM provider for query rewriting
                                    --rewrite-model       LLM model for query rewriting

              rag-chat QUERY        Retrieve chunks + generate a grounded LLM answer
                                    --embedding-provider  openai|cohere|gemini|mistral|voyage
                                    --embedding-model     model name
                                    --vector-db           pinecone|qdrant|chroma|supabase|...
                                    --config              JSON config for vector DB
                                    --llm-provider        openai|anthropic|gemini
                                    --llm-model           LLM model name
                                    --top-k               chunks to retrieve (default: 5)
                                    --hybrid              enable hybrid search (BM25 + RRF)
                                    --query-rewrite       rewrite query before embedding

            API keys are resolved from environment variables automatically:
              SCRAPEDATSHI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
              GEMINI_API_KEY, COHERE_API_KEY, MISTRAL_API_KEY, VOYAGE_API_KEY,
              PINECONE_API_KEY, PINECONE_INDEX_HOST, QDRANT_URL, etc.

            Examples:
              scrapedatshi init
              scrapedatshi init my-rag-project
              scrapedatshi query "how do I authenticate?" --vector-db pinecone --hybrid
              scrapedatshi rag-chat "how do I authenticate?" --vector-db pinecone --llm-provider openai --llm-model gpt-4o-mini
        """))
        return

    command = argv[0]
    rest = argv[1:]

    if command == "init":
        cmd_init(rest)
    elif command == "query":
        cmd_query(rest)
    elif command == "rag-chat":
        cmd_rag_chat(rest)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Run `scrapedatshi --help` for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
