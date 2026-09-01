from __future__ import annotations

import subprocess
import sys

import pytest

from nl2sparql.models.b12 import ChatMessage, GenerationConfig, SmallLLMError
from nl2sparql.models.b12.transformers_backend import TransformersBackend

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


def test_import_does_not_import_heavy_ml_modules() -> None:
    code = (
        "import sys; "
        "import nl2sparql.models.b12.transformers_backend; "
        "print(int('torch' in sys.modules), int('transformers' in sys.modules))"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )

    assert result.stdout.strip() == "0 0"


def test_adapter_uses_chat_template_and_decodes_only_new_tokens() -> None:
    import torch

    class FakeTokenizer:
        eos_token_id = 2
        pad_token_id = None

        def __init__(self) -> None:
            self.messages = None

        def apply_chat_template(self, messages, *, tokenize, add_generation_prompt) -> str:
            assert tokenize is False
            assert add_generation_prompt is True
            self.messages = messages
            return "rendered prompt"

        def __call__(self, prompt, *, return_tensors):
            assert prompt == "rendered prompt"
            assert return_tensors == "pt"
            return {
                "input_ids": torch.tensor([[1, 2, 3]]),
                "attention_mask": torch.tensor([[1, 1, 1]]),
            }

        def decode(self, tokens, *, skip_special_tokens):
            assert tokens.tolist() == [8, 9]
            assert skip_special_tokens is True
            return SAFE_SQL

    class FakeModel:
        device = torch.device("cpu")

        def __init__(self) -> None:
            self.kwargs = None

        def generate(self, **kwargs):
            self.kwargs = kwargs
            return torch.tensor([[1, 2, 3, 8, 9]])

    model = FakeModel()
    tokenizer = FakeTokenizer()
    adapter = TransformersBackend.from_loaded(
        model,
        tokenizer,
        model_id="meta-llama/Meta-Llama-3-8B-Instruct",
        model_revision="a" * 40,
    )
    messages = (
        ChatMessage(role="system", content="system"),
        ChatMessage(role="user", content="question"),
    )

    completion = adapter.generate(messages, GenerationConfig("a" * 40))

    assert completion.raw_text == SAFE_SQL
    assert completion.input_tokens == 3
    assert completion.output_tokens == 2
    assert completion.synthetic_backend is True
    assert tokenizer.messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "question"},
    ]
    assert model.kwargs["do_sample"] is False
    assert model.kwargs["max_new_tokens"] == 512
    assert model.kwargs["pad_token_id"] == 2
    assert "temperature" not in model.kwargs


def test_adapter_rejects_network_enabled_loading_before_import(monkeypatch) -> None:
    monkeypatch.setattr(
        "nl2sparql.models.b12.transformers_backend.importlib.import_module",
        lambda name: (_ for _ in ()).throw(AssertionError("must not import")),
    )

    with pytest.raises(SmallLLMError, match="local_files_only"):
        TransformersBackend.load(GenerationConfig("a" * 40), local_files_only=False)


def test_adapter_rejects_config_identity_mismatch() -> None:
    adapter = TransformersBackend.from_loaded(
        object(),
        object(),
        model_id="meta-llama/Meta-Llama-3-8B-Instruct",
        model_revision="a" * 40,
    )

    with pytest.raises(SmallLLMError, match="identity"):
        adapter.generate(
            (ChatMessage(role="user", content="question"),),
            GenerationConfig("b" * 40),
        )
