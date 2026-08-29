# Changelog

## Agent V6.0.0 — LangGraph dual runtime and visual console

- Added a LangGraph `StateGraph` runtime with planner, tool-executor and
  output-verifier nodes while retaining the V5 custom Harness;
- added LangChain `StructuredTool` adapters and the official `ChatDeepSeek`
  integration;
- added LangGraph SQLite checkpointing, graph introspection and architecture API;
- added a reproducible V5/V6 comparison on the same 12-case fixture set;
- rebuilt Streamlit as a visual portfolio console with runtime switching,
  execution graph, evidence metrics and event timelines;
- added GitHub-rendered architecture artwork and resume-ready comparison notes;
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

## Agent V4.1.0 — portfolio release

- Added committed routing regression cases and a reproducible evaluator;
- added GitHub Actions offline regression gate;
- added architecture, learning notes, limitations and resume-ready project report;
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
