"""Wrapper delgado sobre la API de Anthropic (Claude) para llamadas que
esperan una respuesta JSON estructurada.

Toda la app pasa por aquí para hablar con el modelo, de modo que hay un solo
lugar que sabe cómo:
  - autenticarse (ANTHROPIC_API_KEY / CLAUDE_MODEL desde variables de entorno)
  - pedir salida JSON y parsearla de forma tolerante (el modelo a veces
    envuelve el JSON en ```json ... ``` pese a que se le pida no hacerlo)
  - fallar de forma clara si falta la API key, en vez de fallar a medias
    más adelante en el pipeline.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")


class ClaudeClientError(RuntimeError):
    """Error de configuración o comunicación con la API de Claude."""


class ClaudeJSONError(RuntimeError):
    """El modelo respondió, pero la respuesta no se pudo parsear como JSON."""

    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


@dataclass
class ClaudeClient:
    model: str = DEFAULT_MODEL
    max_tokens: int = 4096
    api_key: str | None = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ClaudeClientError(
                    "Falta ANTHROPIC_API_KEY. Define la variable de entorno "
                    "(o crea un archivo .env a partir de .env.example) antes "
                    "de usar cualquier función que llame a la API de Claude."
                )
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise ClaudeClientError(
                    "El paquete 'anthropic' no está instalado. Corre "
                    "'pip install -r requirements.txt'."
                ) from exc
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def call_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> Any:
        """Llama al modelo y devuelve el JSON parseado de su respuesta.

        Lanza ClaudeJSONError si la respuesta no contiene JSON válido, para
        que el llamador decida cómo manejarlo (nunca se debe asumir
        silenciosamente una estructura vacía).
        """
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return self._parse_json(raw_text)

    @staticmethod
    def _parse_json(raw_text: str) -> Any:
        text = raw_text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            try:
                return json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ClaudeJSONError(
            "La respuesta del modelo no contiene JSON válido.", raw_text=raw_text
        )
