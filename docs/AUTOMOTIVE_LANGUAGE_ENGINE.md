# Automotive Language Engine — v1.1 (demo 2.3.9 / API 2.1.4)

This module provides deterministic RU/UK/EN automotive terminology matching for the AI Manager demo.

## Responsibilities
- Recognize common customer wording, workshop slang and technical names for common parts.
- Map aliases to stable terminology IDs.
- Expand a catalog search phrase with multilingual aliases while preserving the customer's original wording.
- Keep VINs, OE/OEM references and part codes as identifiers; never translate or rewrite them.

## Important boundary
This is a terminology normalizer, not a general-purpose neural translator. It does not translate arbitrary sentences or catalog descriptions. A production translation/reply layer must run server-side and use the following contract.

## Required server-side language pipeline
1. Detect language per customer message (RU, UK, EN); browser locale is only a fallback.
2. Preserve original customer text and language.
3. Normalize automotive terms to terminology IDs and attach relevant aliases to catalog search.
4. Query catalog providers using normalized search terms; never use translated text as the source of truth for fitment.
5. Translate free-form assistant replies and catalog descriptions into the customer's detected language.
6. Preserve VIN, OE/OEM numbers, manufacturer part numbers, engine codes, gearbox codes, measurements and diagram position numbers exactly.
7. If a term is ambiguous (e.g. colloquial “граната”), ask a clarifying question rather than choosing a side or assembly.
8. Return detected_language, reply_language, original_text, normalized_terms, and reply_text for auditability.

## Example
Customer: “Нужна наружная граната слева”.
- Recognized concept: cv_joint_outer
- Catalog synonyms: наружный ШРУС / зовнішній шрус / outer CV joint
- Side: left (only if the wording explicitly says left)
- The system must still verify vehicle fitment and exact side/variant in the OE catalog.

## Current demo integration
The browser module is automotive-language.js. It is loaded by index.html and expands recognized catalog query terms in RU/UK/EN. The API now accepts `en`, `uk`, `az`, and `ru` and forwards the detected language to the connected catalog provider. Fixed interface messages and vehicle-field labels are localized in the browser. Catalog text is localized only to the extent that the provider honors its `lang` argument; no general-purpose translation service is configured in this demo. Browser Web Speech recognition still requires one recognition locale at session start. The demo starts with the browser locale; recognized text then updates the language used for API requests and subsequent dictation sessions. This is not equivalent to true multilingual audio-language detection. Reliable detection of arbitrary spoken languages requires a server-side multilingual speech-to-text service.

## Extension
Add entries to rows in automotive-language.js. Every entry must have a stable id and aliases for all supported languages where known. Keep OE/OEM codes out of alias rewriting.
