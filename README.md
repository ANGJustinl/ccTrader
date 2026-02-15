# Trader - AI-Powered Perpetual Futures Trading Agent System

An intelligent trading system using Domain-Driven Design (DDD) architecture for perpetual futures trading.

## Project Structure

```
src/trader/
├── domain/          # Domain layer - Business entities, value objects, and domain logic
├── infrastructure/  # Infrastructure layer - External services, databases, and implementations
├── application/     # Application layer - Use cases and application services
├── ai/             # AI integration layer - AI models and integration logic
└── utils/          # Utility layer - Helper functions and common utilities
tests/              # Test directory
data/               # Data directory
```

## Features

- AI-powered trading decisions
- Support for multiple exchanges via CCXT
- Technical analysis indicators
- DDD architecture for maintainability
- Comprehensive test coverage

## Requirements

- Python >= 3.10
- uv (Python package manager)

## Installation

```bash
uv sync
uv pip install -e .
```

## Running Tests

```bash
uv run pytest
```

## License

MIT License
