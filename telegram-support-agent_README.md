# AI Support Agent with Knowledge Base

Telegram-based AI support agent that answers customer questions using a controlled knowledge base and creates tickets when it cannot answer safely.

## What problem it solves

Businesses often receive repetitive support questions about delivery, returns, payments, warranty, refunds, and order issues.  
This agent answers only from a knowledge base and escalates unknown or sensitive questions to a human support agent.

## Main features

- Answers questions using `knowledge_base.md`
- Does not invent unsupported answers
- Creates support tickets when the knowledge base is insufficient
- Classifies questions by category:
  - delivery
  - returns
  - refund
  - warranty
  - payment
  - tracking
  - complaint
  - pricing
  - technical
  - other
- Assigns confidence level
- Assigns ticket priority
- Generates draft replies for tickets
- Shows ticket list and ticket details
- Updates ticket statuses
- Conversation history
- Support reports
- CSV export
- PostgreSQL database
- Optional private access with `ALLOWED_CHAT_IDS`

## Example use case

User asks:

```text
How long does delivery in Poland take?
```

The agent searches the knowledge base and answers:

```text
Delivery in Poland usually takes 1–3 business days.
```

If the user asks something not covered by the knowledge base:

```text
Can I get a 40% personal discount?
```

The agent does not guess and creates a ticket for a human.

## Commands

```text
/start — start the bot
/ask question — ask support question
/tickets — show tickets
/ticket ID — show ticket details
/status ID status — update ticket status
/draft ID — generate draft reply
/history — show message history
/report — show support statistics
/export — export tickets to CSV
/clear — clear all data
/knowledge — show knowledge base info
/myid — show Telegram chat ID
```

## Ticket statuses

```text
open
in_progress
resolved
closed
```

## Knowledge base

The knowledge base is stored in:

```text
knowledge_base.md
```

To change the agent's answers, edit this file and redeploy.

Example sections:

```markdown
## Delivery
Delivery in Poland costs 15 PLN and takes 1–3 business days.

## Returns
Customers can return products within 14 days.
```

## Tech stack

- Python
- python-telegram-bot
- Groq API
- PostgreSQL
- Markdown knowledge base
- Railway-compatible deployment

## Environment variables

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_postgres_database_url
ALLOWED_CHAT_IDS=
```

## How to run locally

```bash
pip install -r requirements.txt
python main.py
```

## How to deploy

The project includes a `Procfile`:

```text
worker: python main.py
```

It can be deployed to Railway or any service that supports Python workers.

## Portfolio value

This project demonstrates:

- knowledge-base support automation
- safe AI answer generation
- ticket escalation workflow
- support classification
- PostgreSQL persistence
- CSV reporting
- Telegram support interface
- foundation for future RAG or web chat widget
