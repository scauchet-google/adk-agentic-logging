# 🤖 adk-agentic-logging

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**adk-agentic-logging** transforms the observability of AI agents from a fragmented stream of text into a structured, queryable dataset.

Its core philosophy is the **"Wide Event"** model: capturing the entire lifecycle of an agentic interaction—including HTTP context, OpenTelemetry trace headers, and deep ADK internal state—into a single, high-cardinality JSON artifact per request.

By seamlessly bridging web frameworks with Google Cloud’s ecosystem, it enforces a "zero-config" standard that eliminates scattered debug prints, turning complex AI behavior into transparent insights from day one.

---

## ✨ Features

- **� One Request = One Log Line**: Aggregates all context into a single JSON object emitted at the end of the request.
- **🧠 Deep ADK Observability**: Automatically captures token usage, tool calls, and session metadata.
- **☁️ Zero-Config GCP**: Automatic detection of project ID and environment metadata.
- **🔍 Trace-Aware**: Injects OpenTelemetry `trace_id` and `span_id` for seamless Cloud Trace linking.
- **�🔌 Framework Agnostic**: First-class support for **FastAPI**, **Flask**, and **Django**.
- **🧹 Vertex AI Trace Sanitization**: Surgically removes large JSON payloads (prompts, tool definitions) from Cloud Trace spans to reduce noise and cost.
- **⚡ Supercharged Tracing**: One-line enablement of full Google Cloud Trace with automatic correlation to internal ADK spans.

---

## 📦 Installation

```bash
# Core library
uv pip install adk-agentic-logging

# With Google Cloud Tracing capabilities
uv pip install "adk-agentic-logging[google-adk]"
```

---

## ⚡ Supercharged Tracing (Unified Observability)

The `configure_logging` function is your unified entry point for observability. It activates full Google Cloud Tracing or Console Tracing with a single line of code, handling OTel configuration and GCP project detection automatically.

**Crucially, `adk-agentic-logging` is lazy.** It will not touch OpenTelemetry or initialize any SDK providers until you explicitly call `configure_logging()`.

### Usage Examples

#### 1. Local Development (Console Only)
By default, console tracing is enabled with beautiful [Rich](https://github.com/Textualize/rich) formatting.
```python
from adk_agentic_logging import configure_logging

# Console tracing is ON by default
configure_logging()
```

#### 2. Production (Google Cloud Trace)
Enable GCP export for production. If `project_id` is omitted, it is auto-detected from the environment.
```python
configure_logging(enable_google_tracing=True)
```

#### 3. Mixed Mode / Advanced
You can toggle exporters independently and specify an explicit project ID.
```python
configure_logging(
    enable_google_tracing=True,
    enable_console_tracing=False, # Silence console logs in production
    project_id="my-custom-gcp-project"
)
```

### Configuration Parameters

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `enable_google_tracing` | `False` | Enables export to Google Cloud Trace. Requires `[google-adk]` extra. |
| `enable_console_tracing` | `True` | Enables local console output via `RichConsoleSpanExporter`. |
| `project_id` | `None` | Explicit GCP Project ID. If `None`, auto-detects from metadata or env. |

> [!TIP]
> This unified configuration automatically manages `BatchSpanProcessor` settings, environment variables for log correlation, and instruments the Google Generative AI SDK if installed.

---


## 🚀 Quick Start

### 1. Integrate with your Web Framework

#### FastAPI
```python
from fastapi import FastAPI
from adk_agentic_logging.integrations.fastapi import AgenticLoggingMiddleware

app = FastAPI()
app.add_middleware(AgenticLoggingMiddleware)
```

#### Flask
```python
from flask import Flask
from adk_agentic_logging.integrations.flask import AgenticLogging

app = Flask(__name__)
agentic_logging = AgenticLogging(app)
```

#### Django
Add to your `MIDDLEWARE` in `settings.py`:
```python
MIDDLEWARE = [
    ...,
    "adk_agentic_logging.integrations.django.AgenticLoggingMiddleware",
    ...,
]
```

### 2. Instrument your ADK Agent

Use `@instrument_runner` to automatically capture internal state from your ADK runners.

```python
from adk_agentic_logging.adk.instrumentation import instrument_runner

class MyAgentRunner:
    @instrument_runner
    def run(self, runner_input, **kwargs):
        # Your ADK agent logic
        return result
```

### 3. Enrich with Agent Context

You can explicitly enrich the wide event with any context, such as the user's question and the agent's response, using `log_ctx`.

```python
from adk_agentic_logging import log_ctx

# In your agent logic or route handler
log_ctx.enrich(
    question="What is the weather in Paris?",
    response="The weather in Paris is sunny with 22°C."
)
```

Adding these fields makes your logs easily queryable for specific interactions.

### Cost Optimization & Sanitization

Traces can become expensive if they capture massive LLM prompts and responses. `adk-agentic-logging` includes a **Vertex AI Sanitizer** that automatically strips these large payloads from your traces (Waterfall UI) while keeping them safely in your structured logs.

This gives you the best of both worlds: lightweight, low-cost Waterfall traces and full-fidelity logs for debugging.

The sanitizer is **enabled by default** when you use `configure_logging()`.

```python
# Everything is handled: OTel, Exporters, and Sanitization
configure_logging(enable_google_tracing=True)
```

---

## 🛠️ How It Works

1.  **Context Initialization**: When a request starts, the middleware initializes a thread-local log context and resolves GCP/OTel metadata.
2.  **Execution**: As your code runs, arbitrary metadata is attached or captured automatically via ADK instrumentation.
3.  **Aggregation**: Content is held in a "bucket" bound to the current request.
4.  **Emission**: On request completion, a single structured JSON blob (HTTP info, performance metrics, ADK stats, errors) is emitted to stdout.

---

## 📄 License

This project is licensed under the terms of the MIT license.
