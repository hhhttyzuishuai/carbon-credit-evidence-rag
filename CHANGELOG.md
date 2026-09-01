# Changelog

## Agent V6.1.1 — Streamlit request lifecycle fix

- Fixed Streamlit request rotation by updating widget state through a callback;
- cleared stale response and event panels when starting a new request;
- expanded the offline suite to 43 tests with a request-state regression case.

## Agent V6.1.0 — Python 3.10 and open-source readiness

- Restored and verified the Windows Python 3.10 development path;
- load `.env` consistently for CLI, API, and Streamlit runtimes;
- switched both DeepSeek planners to the current `deepseek-v4-flash` default;
- rewrote public documentation for installation, operation, data preparation,
  evaluation, security boundaries, and contribution;
- added the MIT License and contribution guide;
- replaced private career notes with a technical runtime comparison.

## Agent V6.0.0 — LangGraph dual runtime and visual console

- Added a LangGraph `StateGraph` runtime with planner, tool-executor and
  output-verifier nodes while retaining the V5 custom Harness;
- added LangChain `StructuredTool` adapters and the official `ChatDeepSeek`
  integration;
- added LangGraph SQLite checkpointing, graph introspection and architecture API;
- added a reproducible V5/V6 comparison on the same 12-case fixture set;
- rebuilt Streamlit as a visual control console with runtime switching,
  execution graph, evidence metrics and event timelines;
- added GitHub-rendered architecture artwork and runtime comparison notes;
- expanded the offline suite to 42 tests and added V6 CI evaluation.

## Agent V5.0.0 — resumable agent harness

- Replaced the default deterministic router with a bounded model-driven
  observe/act loop while retaining the V1–V4 implementations and tags;
- added typed tool schemas, validation, retry policies and explicit approval;
- added request idempotency, SQLite checkpoints, event replay and crash recovery;
- added context compaction and content-addressed externalization for large tool
  observations;
- exposed read-only knowledge and registry tools through an MCP stdio server;
- unified CLI, FastAPI and Streamlit on the same runtime;
- added citation enforcement, 34 offline tests and a 12-case V5 harness regression.

## Agent V4.1.0 — documented release

- Added committed routing regression cases and a reproducible evaluator;
- added GitHub Actions offline regression gate;
- added architecture, design notes, limitations and project report;
- retained V1–V4 release notes and tags as independent milestones.

## Agent V4.0.0 — multi-agent business tools

- Added router, conversation, knowledge, registry, risk-review and verifier agents;
- added business-tool approval gate, trace metadata, redacted audit logs and FastAPI;
- added failure isolation and offline integration tests.

## Agent V3.0.0 — knowledge base

- Connected the existing Hybrid + Cross-Encoder RAG pipeline through an adapter;
- added evidence formatting, citation auditing and insufficient-evidence behavior.

## Agent V2.0.0 — conversation memory

- Added SQLite sessions, atomic turn persistence and bounded history windows.

## Agent V1.0.0 — simple Q&A

- Added vendor-independent LLM gateway, stateless Q&A agent, CLI and fake model tests.
