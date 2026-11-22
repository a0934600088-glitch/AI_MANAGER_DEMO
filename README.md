# AI_MANAGER_DEMO v2.1.2

Live test release: FastAPI serves the messenger and exposes public catalog integrations.

## Live integrations
- SoloCatalog MCP at https://solocatalog.com/mcp — VIN decode, parts search, diagrams and diagram parts. Light daily use is documented as available without a key; limits may apply.
- NHTSA vPIC — public VIN decoder without a key. It is a VIN data source, not a parts catalog.
- Up to 10 provider slots are reserved in the architecture; only the two integrations above are currently enabled. RockAuto and Tradesoft are not represented as connected.

## Run and deploy
Docker builds from repository root and serves the UI at / plus API docs at /docs. No provider secrets are required for the two public integrations.
