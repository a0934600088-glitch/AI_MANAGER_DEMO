# AI Manager — Original Parts Diagram Selection

**Module ID:** `original_parts_diagram_selection`  
**Status:** Architecture requirement approved; an interactive synthetic front-end demo is implemented in AI_MANAGER_DEMO v1.9. Live OEM catalog integration remains unimplemented.

## Purpose

After the customer confirms the vehicle identified from the VIN, AI Manager must send the customer an original-catalog exploded diagram for the requested vehicle subsystem. The customer selects the required component by its numbered callout directly in the chat. The system resolves that callout to the catalog item and its OE/OEM part number, then continues with verified alternatives and an offer.

This module is a first-class domain capability, not an image attachment feature.

## Position in the modular architecture

The module belongs to the **Catalog & Fitment domain** and is orchestrated by the conversation/application layer.

- **Transport/API:** chat message, diagram delivery, selection event, and status updates.
- **Application use cases:** `RequestPartsDiagram`, `PublishPartsDiagram`, `SelectDiagramPosition`, `ResolveSelectedPart`.
- **Domain:** diagram, diagram revision, vehicle applicability, callout/position, catalog item, OE number, selection session.
- **Infrastructure:** OEM catalog adapters, diagram asset storage/CDN, image-coordinate or SVG hotspot metadata, cache, audit events, and provider rate limits.

It integrates with existing domain modules:
- Tenant / RBAC — tenant permissions and provider entitlements.
- Vehicle / VIN — confirmed vehicle identity and exact configuration.
- Catalog ingestion — OEM catalog data and diagram indexing.
- Fitment — applicability validation for the selected vehicle.
- Cross-reference — OE-to-aftermarket analog mapping.
- Inventory / pricing — availability and customer-specific price.
- Conversation / Operator Console — chat UX, handoff, and operator override.
- Audit — provenance for every resolved position and part number.

## Required workflow

1. **Gate on vehicle confirmation.** Do not request a parts diagram until the customer confirms the decoded vehicle configuration. A changed VIN or changed vehicle configuration invalidates the active diagram selection session.
2. **Understand the requested node.** Resolve the customer's request (for example, front suspension, control arm, brake assembly) to a catalog group. Ask a clarifying question if the node is ambiguous.
3. **Resolve the exact catalog context.** Query the OEM provider using the confirmed vehicle configuration, market, production date/range, engine, transmission, and any required PR/option codes.
4. **Retrieve the original diagram.** Load the diagram asset and its structured callout metadata from the OEM source/authorized data provider. Keep provider, catalog, revision, market, and vehicle applicability provenance.
5. **Deliver it in chat.** Render the diagram inline with tappable numbered callouts. On narrow screens, support zoom/pan and an accessible numbered-position list. A plain image without a machine-readable callout map is insufficient for reliable selection.
6. **Capture the customer's selection.** Store the diagram ID/revision, selection session ID, callout number, customer, tenant, and timestamp. Support selecting more than one position where appropriate.
7. **Resolve the selected position.** Map the callout number to the catalog item and OE/OEM number. Validate the result against the confirmed vehicle configuration and source revision.
8. **Show a verification result.** Return the position number, part name, OE number, and relevant notes. If the catalog has multiple variants or an incomplete mapping, ask for the missing PR code, dimensions, side/axle, or operator review.
9. **Continue selection.** Retrieve analogues through the cross-reference module, independently validate their fitment, then query tenant inventory/pricing and prepare the offer.

## Core domain entities

- `PartsDiagram`: provider, catalog/group identifiers, asset URI, revision, locale/market, vehicle applicability, source timestamp.
- `DiagramCallout`: diagram ID/revision, callout number, catalog item ID, hotspot geometry or SVG target, optional notes.
- `DiagramSelectionSession`: tenant, customer/conversation, confirmed vehicle snapshot, requested node, diagram revision, status, expiry.
- `DiagramPositionSelection`: session, callout number, selected catalog item, customer confirmation, audit metadata.
- `CatalogItemOE`: catalog item, OE/OEM number(s), validity interval, market/variant restrictions, source provenance.

## API / event contract (logical)

- `POST /conversations/{id}/parts-diagrams` — request a diagram for a confirmed vehicle and requested node.
- `GET /parts-diagram-sessions/{id}` — retrieve diagram metadata and available callouts.
- `POST /parts-diagram-sessions/{id}/selections` — submit one or more callout selections.
- `parts_diagram.requested`, `parts_diagram.published`, `parts_diagram.position_selected`, `parts_diagram.part_resolved`, `parts_diagram.resolution_failed` — domain events for async processing and audit.

These are logical contracts for architecture planning, not existing deployed endpoints.

## Reliability and safety rules

- Never infer an OE number from the visual appearance or from an LLM guess.
- The callout-to-catalog-item mapping must come from structured OEM catalog data for the exact diagram revision.
- Keep OE number, aftermarket cross-reference, fitment, stock, and price as separate verified facts with source and timestamp.
- Do not silently substitute diagrams across model years, markets, body styles, engine codes, or option/PR-code variants.
- If the diagram or mapping is missing, stale, ambiguous, or unauthorized, say so and escalate to an operator rather than inventing a result.
- Store source attribution and audit history for every customer selection.
- Respect OEM licensing, redistribution restrictions, tenant permissions, and regional data access rules.

## UI requirements

- Diagram displayed directly in the customer messenger.
- Numbered hotspots are clickable/tappable and have visible selected state.
- Customer can select multiple positions if the requested repair requires it.
- Selected position is echoed back in chat before OE resolution.
- Provide zoom/pan, mobile-friendly hit targets, and a text list fallback.
- Operator Console shows the same diagram, selected callout, resolved OE item, source, and uncertainty state.

## Acceptance criteria

1. No diagram is shown before vehicle confirmation.
2. Diagram is tied to the exact confirmed vehicle configuration and catalog revision.
3. Tapping callout N sends N as structured selection data, not as free text alone.
4. The selected callout resolves to the correct catalog item and OE number from provider data.
5. Unmapped or ambiguous callouts never produce guessed part numbers.
6. The result and provenance are visible to the operator and recorded in the audit trail.
7. The workflow supports mobile chat, multiple selections, retries, and operator escalation.

## Demo implementation status

`AI_MANAGER_DEMO` v1.9 implements a client-side test flow for front suspension/control arms and front brake assemblies. It parses supported part-list keywords after VIN confirmation, opens one or more hand-authored SVG test diagrams, supports multi-select numbered callouts, and resolves selections through local structured fixtures to synthetic catalog item IDs, test-only OE labels, and synthetic analogue IDs. Unsupported or ambiguous requests prompt for clarification rather than selecting an arbitrary diagram.

These SVGs are explanatory test drawings, not original OEM diagrams. Their callout-to-part mappings are invented fixtures and do not establish real Volkswagen applicability or real OE numbers. The feature has no backend session persistence, live catalog access, or real OEM provider adapter.

## Demo boundary

`AI_MANAGER_DEMO` illustrates the sequence with synthetic diagrams and fixture data. A demo click or successful simulated mapping is not proof of real OEM catalog access, OE correctness, or vehicle fitment. Production requires authorized OEM catalog providers/adapters, structured callout mappings, and backend validation.
