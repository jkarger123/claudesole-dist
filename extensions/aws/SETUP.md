# AWS -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm exact endpoint/command at https://awslabs.github.io/mcp/.

## What it does
Inspect AWS resources and search AWS documentation via the official awslabs MCP servers.

## Why use it
For AWS-hosted projects, gives agents grounded infra visibility (resources, config, docs).

## How it works
The awslabs MCP server suite (run via uvx). The install wired the API server into `.mcp.json` using an `${AWS_PROFILE}` (least-privilege). Data flow: agent -> awslabs MCP -> AWS APIs (your profile's permissions).

## Prerequisites
- An AWS account + credentials. STRONGLY prefer a read-only IAM role / least-privilege profile.

## Setup steps
1. Configure a least-privilege (read-only) AWS profile.
2. Set `AWS_PROFILE=...` + `AWS_REGION=...` in the gitignored deployment env. Never wire admin creds; never echo credentials.
3. The install wired `aws-api` into `.mcp.json`; restart sessions. (uvx required.)

## Verify
Make one read-only call (e.g. list a region's resources / fetch a doc).

## Usage
- "List our running EC2 instances in us-east-1."
- "Search AWS docs for <topic>."

## Best practices / Safety
- READ-ONLY IAM role first; never wire admin credentials; scope to needed services; require approval for any mutating call. High blast radius -- treat with care.
