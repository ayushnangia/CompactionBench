"""LongLLMLingua wrapper for CompactionBench compression comparison."""

from __future__ import annotations

from dataclasses import dataclass

from .chunking import estimate_tokens


@dataclass(frozen=True)
class LLMLinguaResult:
    compressed_text: str
    original_tokens: int
    compressed_tokens: int

    @property
    def ratio(self) -> float:
        return self.compressed_tokens / max(self.original_tokens, 1)


def compress_with_longllmlingua(
    context: str,
    *,
    question: str | None = None,
    target_tokens: int = 200,
) -> LLMLinguaResult:
    """Compress context using LongLLMLingua.

    If question is provided, uses question-aware compression.
    Otherwise falls back to general prompt compression.
    """
    try:
        from llmlingua import PromptCompressor
    except ImportError:
        raise ImportError(
            "llmlingua is required. Install with: uv add llmlingua"
        )

    original_tokens = estimate_tokens(context)
    compressor = PromptCompressor(
        model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        use_llmlingua2=True,
        device_map="cpu",
    )

    if question and question.strip():
        compressed = compressor.compress_prompt(
            context=[context],
            question=question,
            target_token=target_tokens,
        )
    else:
        compressed = compressor.compress_prompt(
            context=[context],
            target_token=target_tokens,
        )

    result_text = compressed.get("compressed_prompt", context) if isinstance(compressed, dict) else str(compressed)
    compressed_tokens = estimate_tokens(str(result_text))

    return LLMLinguaResult(
        compressed_text=str(result_text),
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
    )
