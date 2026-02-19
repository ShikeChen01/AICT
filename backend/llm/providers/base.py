from __future__ import annotations

from abc import ABC, abstractmethod

from backend.llm.contracts import LLMRequest, LLMResponse


class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

