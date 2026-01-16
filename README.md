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

---

## 📦 Installation

```bash
uv pip install adk-agentic-logging
```

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

### 4. Vertex AI Trace Sanitizer (Recommended)

To reduce Cloud Trace costs and declutter the Waterfall UI, use the `configure_adk_telemetry` helper. This removes massive JSON payloads (prompts, history) from traces while preserving them in the structured logs.

```python
from adk_agentic_logging.otel.config import configure_adk_telemetry

# Initialize at app startup
configure_adk_telemetry(project_id="your-gcp-project-id")
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
