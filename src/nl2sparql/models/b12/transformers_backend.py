"""Lazy Transformers/BitsAndBytes adapter for real Kaggle inference."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

from nl2sparql.models.b12.contracts import (
    ChatMessage,
    Completion,
    GenerationConfig,
    SmallLLMError,
    _attest_completion,
)


class TransformersBackend:
    """Batch-one greedy generation adapter without import-time ML side effects."""

    def __init__(
        self,
        model: object,
        tokenizer: object,
        *,
        model_id: str,
        model_revision: str,
        trusted: bool = False,
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._model_id = model_id
        self._model_revision = model_revision
        self._trusted = trusted

    @classmethod
    def from_loaded(
        cls,
        model: object,
        tokenizer: object,
        *,
        model_id: str,
        model_revision: str,
    ) -> TransformersBackend:
        """Wrap already loaded objects for adapter-contract verification."""
        if not isinstance(model_id, str) or not model_id:
            raise SmallLLMError("loaded model ID must not be empty")
        GenerationConfig(model_revision=model_revision, model_id=model_id)
        return cls(
            model,
            tokenizer,
            model_id=model_id,
            model_revision=model_revision,
        )

    @classmethod
    def load(
        cls,
        config: GenerationConfig,
        *,
        local_files_only: bool = True,
    ) -> TransformersBackend:
        """Load the pinned quantized model only after workflow preflight."""
        if not isinstance(config, GenerationConfig):
            raise SmallLLMError("config must be a GenerationConfig")
        if not isinstance(local_files_only, bool):
            raise SmallLLMError("local_files_only must be boolean")
        if not local_files_only:
            raise SmallLLMError(
                "local_files_only must remain true; network downloads are forbidden"
            )
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
            quantization = transformers.BitsAndBytesConfig(
                load_in_4bit=config.load_in_4bit,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                config.model_id,
                revision=config.model_revision,
                local_files_only=local_files_only,
                trust_remote_code=False,
            )
            model = transformers.AutoModelForCausalLM.from_pretrained(
                config.model_id,
                revision=config.model_revision,
                local_files_only=local_files_only,
                trust_remote_code=False,
                device_map="auto",
                torch_dtype=torch.bfloat16,
                quantization_config=quantization,
            )
        except Exception as exc:
            raise SmallLLMError(f"unable to load pinned Transformers model: {exc}") from exc
        return cls(
            model,
            tokenizer,
            model_id=config.model_id,
            model_revision=config.model_revision,
            trusted=True,
        )

    def generate(
        self,
        messages: tuple[ChatMessage, ...],
        config: GenerationConfig,
    ) -> Completion:
        """Render chat, generate greedily, and decode only completion tokens."""
        if not isinstance(config, GenerationConfig):
            raise SmallLLMError("config must be a GenerationConfig")
        if config.model_id != self._model_id or config.model_revision != self._model_revision:
            raise SmallLLMError("generation config identity does not match loaded model identity")
        if (
            not isinstance(messages, tuple)
            or not messages
            or any(not isinstance(message, ChatMessage) for message in messages)
        ):
            raise SmallLLMError("messages must be a non-empty immutable ChatMessage tuple")
        try:
            torch = importlib.import_module("torch")
            torch.manual_seed(config.seed)
            rendered = self._tokenizer.apply_chat_template(
                [{"role": message.role, "content": message.content} for message in messages],
                tokenize=False,
                add_generation_prompt=True,
            )
            encoded = self._tokenizer(rendered, return_tensors="pt")
            if not isinstance(encoded, Mapping) or "input_ids" not in encoded:
                raise SmallLLMError("tokenizer must return input_ids")
            device = self._model.device
            model_inputs: dict[str, Any] = {
                key: value.to(device) if callable(getattr(value, "to", None)) else value
                for key, value in encoded.items()
            }
            input_tokens = int(model_inputs["input_ids"].shape[-1])
            pad_token_id = self._tokenizer.pad_token_id
            if pad_token_id is None:
                pad_token_id = self._tokenizer.eos_token_id
            with torch.inference_mode():
                output = self._model.generate(
                    **model_inputs,
                    max_new_tokens=config.max_new_tokens,
                    do_sample=config.do_sample,
                    pad_token_id=pad_token_id,
                )
            new_tokens = output[0][input_tokens:]
            raw_text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
            output_tokens = int(new_tokens.shape[-1])
        except SmallLLMError:
            raise
        except Exception as exc:
            raise SmallLLMError(f"Transformers generation failed: {exc}") from exc
        if not isinstance(raw_text, str):
            raise SmallLLMError("tokenizer decode must return text")
        completion = Completion(
            raw_text=raw_text,
            model_id=self._model_id,
            model_revision=self._model_revision,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return _attest_completion(completion) if self._trusted else completion
