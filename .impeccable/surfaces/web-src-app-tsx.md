---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

# Surface: Mageseeker operator console

## Scope

`web/src/App.tsx` and `web/src/components/*` — the single operator console for text KIS search, frame verification, and DRES submission.

## Visitor mode

Operate

## Audience and job

One operator on a laptop in a timed round. They type a Vietnamese event description, recognize the best keyframe, verify the exact moment in the source video, choose the best follow frame, and submit the video ID plus timestamp to DRES.

## Action

- Type a query and press Enter.
- Type a video ID or shorthand in the results rail's **Mã video** field and press Enter to load every keyframe of that video.
- Arrow keys move through the result tiles; the stage updates instantly.
- Space toggles the video at the active frame.
- `[` / `]` step the filmstrip; `S` submits; `C` copies the payload.
- The full-video keyframe strip below the follow frames supports ←/→ stepping and mouse-wheel horizontal scrolling.
- The bottom **Query đề thi** dock shows the live DRES task hint; click it for the full popup, **Dùng query** to fill and run the search, **Copy** for the clipboard. It follows the selected evaluation/task.
- Filters and advanced DRES kinds recede behind one button.

## Proof and content

Real keyframes, follow frames, and video streams from the local API. Real DRES status and evaluation. No invented claims.

## Constraints

- Vite + React 19 + TypeScript + Tailwind CSS 4.
- Vietnamese UI copy.
- 30–60 seconds per query.
- Video streams load only on first play; keyframe and follow-frame browsing stay light on a weak network.
- Keyboard-first; every primary action reachable without a mouse.
- Images large and clear; no gradient scrim over the frame.
- All existing capabilities reachable: DRES submit, video playback, follow-frame picking, similar/timeline, object filters, model switching.

## Chosen direction

Standard search console (standing exit, chosen by the operator). Google Photos' large visual grid combined with Linear's keyboard speed. White/charcoal shell, one blue action, green submit, hairline separators, images carry the color. No world costume, no ornamental chrome, no novel controls.

## Memorable moment

The selected keyframe fills the stage; arrow keys travel the result tile grid and the stage follows instantly; Space flips to the video at the same timestamp; S submits without leaving the screen.

## Unresolved

- Raw JSON submission may stay in the advanced panel or be removed from the primary UI.
- Final example queries for the empty state.

## Direction contract

THESIS: A standard, fast search console where the query, the chosen keyframe, and the submit action share one screen; refuses the filter-heavy three-column dashboard and every decorative world costume.

OWN-WORLD: White and near-white surfaces over a charcoal ink, one blue action, one green commit, hairline separators, 12px media radii, tabular numerals, system UI type; the keyframes carry all the color.

STORY: Type a description, press Enter, see the top keyframe at stage scale, travel the result tiles with arrows, verify the moment with Space, step follow frames, and press S to submit; a video ID typed into the results rail's Mã video field loads that video's full keyframe timeline; the verdict returns in place.

FIRST VIEWPORT: A 56px command bar with the product mark, one search field, index status, filter button, and shortcut help; below, a large stage (about two-thirds width) with the selected frame, its toolbar, a follow-frame filmstrip, and the full-video keyframe strip; a right rail whose first row is a compact Mã video lookup, followed by large keyframe tiles; a pinned bottom submit bar showing the exact video ID and timestamp with one green submit button.

FORM: Standard search console (standing exit, chosen by the operator); seed: 48dcc4bc822d66a3.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
