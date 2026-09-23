"""Compaction that keeps the model server's prefix cache: until the history passes `limit_tokens` it only grows at its
end, then one compaction brings it down to `target_tokens`. TieredCompaction alone compacts whenever it is over target."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import ModelRequestContext, RunContext
from pydantic_ai_harness import TieredCompaction
from pydantic_ai_harness.compaction import estimate_context_tokens

from ..deps import Deps


@dataclass
class CompactAtLimit(TieredCompaction[Deps]):
    limit_tokens: int = field(default=200_000, kw_only=True)

    async def before_model_request(self, ctx: RunContext[Deps], request_context: ModelRequestContext) -> ModelRequestContext:
        tokens = estimate_context_tokens(request_context.messages, self.tokenizer, model_request_parameters=request_context.model_request_parameters)
        if tokens <= self.limit_tokens:
            return request_context
        return await super().before_model_request(ctx, request_context)
