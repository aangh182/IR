# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One operator, working alone on a laptop during a timed AIC2024 final round. They read a Vietnamese event description, search a corpus of broadcast video, visually confirm the right keyframe, and submit a video ID plus exact timestamp to DRES before the clock runs out. Practice sessions use the same flow without time pressure.

## Product Purpose

Turn a described event into a submitted, frame-accurate answer in 30–60 seconds. The corpus is indexed by keyframes; search returns candidate keyframes ranked by semantic similarity, and the operator's job is recognition, verification, and submission. Success means a correct submission with the fewest possible interactions and no uncertainty about which frame is being submitted.

## Positioning

The interface treats the retrieved frame as the primary object, not the result metadata. Search, verification, timestamp selection, and DRES submission share one continuous surface, so the operator never translates between a result grid, a player, and a submission form.

## Operating Context

- Live competition round with one operator and one laptop screen.
- Queries are typed in Vietnamese or English; the backend translates before CLIP encoding.
- Candidate keyframes come from a large broadcast corpus with follow frames around each keyframe.
- Video playback is available for verifying the exact moment; follow frames provide sub-keyframe precision.
- DRES submission is the finish line: video ID, timestamp, and the correct active evaluation.
- Advanced controls (embedding model, object filters, boilerplate, dedup) are used selectively and must not slow the default path.

## Capabilities and Constraints

- Existing API: `POST /api/search`, `/api/similar`, `/api/timeline`, `GET /api/videos/{video_id}/keyframes`, `GET /api/dres/status`, `POST /api/dres/submit`, keyframe/follow-frame/video-stream endpoints.
- Video lookup lives in the results rail's **Mã video** field, not the description search: a full ID or a two-part shorthand (`12 016` → `L12_V016`) followed by Enter loads every keyframe of that video.
- The full-video keyframe strip below the follow-frame strip supports ←/→ stepping and mouse-wheel horizontal scrolling.
- Video streams are requested only when the operator presses play; keyframe and follow-frame images are the default browsing surface.
- API startup warm-loads every available embedding profile (`embed.warmup_all`), so switching CLIP ↔ SigLIP2 does not pay a model-load cost.
- Supported submission kinds in the API: KIS, Q&A, TRAKE, raw JSON. The redesign's primary flow is text KIS; other kinds remain reachable but secondary.
- No VKIS image upload/drawing search endpoint exists.
- Stack is fixed: Vite + React 19 + TypeScript + Tailwind CSS 4 in `web/`.
- Keyboard-driven operation is required; all primary actions must work without a mouse.
- Images must render large and clear enough to recognize a described event at a glance.
- Vietnamese is the working language for UI copy; English technical terms stay where the competition uses them.

## Brand Commitments

No formal brand system exists. The AIC2024 competition context and the current Vietnamese terminology (KIS, DRES, keyframe, follow frame, boilerplate, dedup) are binding. Existing product functionality and URLs must be preserved.

The operator explicitly chose the standard search console over a distinctive visual world: reliability and speed over novelty. Do not reintroduce world costumes, ornamental chrome, or novel controls. The craft bar is Google Photos' large visual grid combined with Linear's keyboard-first speed; arrow keys navigate frames, Space previews the video, and the primary path stays one screen.

## Evidence on Hand

- Real keyframes, follow frames, and video streams served by the local API.
- Real DRES status and submission endpoints.
- Object facets and model profiles from the live index.
- No testimonials, marketing claims, or external brand assets exist; none should be invented.

## Product Principles

1. Recognition over reading: the image carries the decision; metadata supports it quietly.
2. One continuous decision: search, verify, and submit without changing context.
3. The default path is the fastest path; advanced controls recede until invoked.
4. Every primary action is one gesture or one keystroke away.
5. The submitted frame is always unambiguous: the operator can see exactly what will be sent.
6. Standard patterns, executed precisely: familiar web controls, no invented interaction models.
