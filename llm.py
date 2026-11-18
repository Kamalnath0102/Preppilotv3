"""LLM wrapper. Provider-agnostic: Groq or any OpenAI-compatible API (free tiers), or Anthropic.
Provider is chosen from environment variables:
  GROQ_API_KEY       -> Groq (free, no card).         MODEL default: llama-3.3-70b-versatile
  LLM_API_KEY + LLM_BASE_URL -> any OpenAI-compatible provider (Gemini, OpenRouter, Cerebras...)
  ANTHROPIC_API_KEY  -> Anthropic.                      MODEL default: claude-sonnet-5-5
Calls are validated with Pydantic and self-repaired once on bad JSON."""
import json, os, re, time
from pydantic import ValidationError

if os.getenv("GROQ_API_KEY"):
    PROVIDER, BASE_URL, API_KEY = "openai", "https://api.groq.com/openai/v1", os.environ["GROQ_API_KEY"]
    MODEL = os.getenv("MODEL", "openai/gpt-oss-120b")
elif os.getenv("LLM_API_KEY"):
    PROVIDER, BASE_URL, API_KEY = "openai", os.getenv("LLM_BASE_URL", ""), os.environ["LLM_API_KEY"]
    MODEL = os.environ["MODEL"]  # required for generic providers
else:
    PROVIDER, BASE_URL, API_KEY = "anthropic", None, os.getenv("ANTHROPIC_API_KEY")
    MODEL = os.getenv("MODEL", "claude-sonnet-5-5")

_client = None


def _complete(system: str, messages: list[dict]):
    """Returns (text, input_tokens, output_tokens)."""
    global _client
    if PROVIDER == "openai":
        if _client is None:
            from openai import OpenAI
            _client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
        r = _client.chat.completions.create(
            model=MODEL, max_tokens=1500, temperature=0.3,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}] + messages)
        u = r.usage
        return r.choices[0].message.content or "", u.prompt_tokens, u.completion_tokens
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic(api_key=API_KEY)
    r = _client.messages.create(model=MODEL, max_tokens=1500, system=system, messages=messages)
    return r.content[0].text, r.usage.input_tokens, r.usage.output_tokens


def call_json(system: str, user: str, schema):
    messages = [{"role": "user", "content": user}]
    t0, tin, tout, err = time.time(), 0, 0, None
    for attempt in (1, 2):
        text, i, o = _complete(system, messages)
        tin, tout = tin + i, tout + o
        try:
            raw = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            obj = schema.model_validate(json.loads(raw))
            return obj, {"latency_s": round(time.time() - t0, 2), "tokens": tin + tout, "attempts": attempt, "model": MODEL}
        except (json.JSONDecodeError, ValidationError) as e:
            err = e
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"Invalid output: {str(e)[:400]}. Return corrected JSON only."}]
    raise ValueError(f"LLM output failed validation: {err}")
