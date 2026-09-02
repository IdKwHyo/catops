# CatalogOps contribution direction

CatalogOps is an auditable ML operations product, not a generic chatbot or dashboard template.

- Treat the public demo as a cinematic, editorial product surface: strong hierarchy, intentional pacing, and a clear narrative from incoming listing to evidence, decision, review, and rollback.
- Keep the working operations console fast and restrained. Prefer information density, meaningful status, and progressive disclosure over decorative panels.
- Avoid default SaaS card grids, heavy borders, gratuitous gradients, and motion that delays comprehension.
- Make important transitions legible, but keep animation subtle and optional. Honor `prefers-reduced-motion` and never make motion necessary to operate the product.
- Build with progressive enhancement. Core matching, review, approval, and audit flows must remain usable without animation and on constrained devices.
- Reuse the existing stack and platform primitives before introducing a large dependency. Any new dependency needs a concrete accessibility, reliability, or maintenance benefit.
- Preserve the evidence chain: model output, confidence, rationale, human action, and immutable audit event should stay traceable across every interface.
