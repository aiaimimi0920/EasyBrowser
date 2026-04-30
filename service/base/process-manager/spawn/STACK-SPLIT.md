# Process Stack Split

Current recommended split:

- parent orchestrator: Go
- Chrome child runtime: Node.js / TypeScript
- Camoufox child runtime: Python
- Browserbase child runtime: Node.js / TypeScript

The spawn layer should therefore be prepared to:

- assemble different command lines per provider
- pass provider-specific environment variables
- normalize child registration and readiness behavior
