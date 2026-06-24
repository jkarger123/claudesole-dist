# Stripe -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm the exact MCP endpoint/command at https://docs.stripe.com/mcp.

## What it does
Query Stripe for customers, payments, subscriptions, and invoices, and search Stripe docs.

## Why use it
Revenue and billing are core signal for a product control center -- 'how much did we make this week', 'is this customer past due'.

## How it works
Stripe's official MCP server. Remote at https://mcp.stripe.com (OAuth); local toolkit uses a Restricted API Key. The install wired the remote form into `.mcp.json`. Data flow: agent -> MCP tool -> Stripe API -> back.

## Prerequisites
- A Stripe account. Strongly prefer a Restricted API Key (rk_*) with read-only scopes to start; or OAuth.

## Setup steps
1. Create a Restricted API Key with READ-ONLY permissions (or use remote OAuth).
2. For local: store `STRIPE_API_KEY=rk_...` in the gitignored env. Never use the live secret key; never commit it.
3. The install wired `stripe` into `.mcp.json`; restart sessions.

## Verify
Ask for the customer count or recent charges. Real numbers = connected.

## Usage
- "How much revenue this week?"
- "Is customer <email> past due?"
- "List failed payments today."

## Best practices / Safety
- Use a RESTRICTED, read-only key -- never the live secret key. Refund/charge-create only with explicit, logged approval (money = high blast radius). Never echo keys.
