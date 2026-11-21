---
name: Mageseeker
description: Frame-accurate video known-item search console for a timed competition.
colors:
  canvas: "#f7f7f5"
  surface: "#ffffff"
  ink: "#0f172a"
  ink-soft: "#475569"
  ink-muted: "#64748b"
  hairline: "#e2e8f0"
  action: "#2563eb"
  action-deep: "#1d4ed8"
  commit: "#047857"
  commit-deep: "#065f46"
  warning: "#b45309"
  warning-wash: "#fef3c7"
  danger: "#b91c1c"
  danger-wash: "#fef2f2"
  media: "#020617"
typography:
  body:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.35
  label:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
  data:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  xxl: "24px"
components:
  button-action:
    backgroundColor: "{colors.action}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "40px"
  button-commit:
    backgroundColor: "{colors.commit}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "36px"
  input-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "40px"
  result-tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "0"
  submit-bar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    padding: "8px 20px"
    height: "60px"
  keyframe-strip-tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    width: "80px"
    height: "45px"
---

# Design System: Mageseeker

## Overview

**Creative North Star: "The Calm Cutting Bench"**

The operator is working against a clock, so the interface behaves like a clean cutting bench: the frame is the object, the chrome is thin and quiet, and the next action is always one key away. The screen is near-white and charcoal, with exactly two accents doing real jobs: blue for action and selection, green for commit and correct. Everything else is a hairline.

This is deliberately the standard search console, chosen by the operator over a distinctive visual world. Its character comes from precision, scale, and restraint rather than ornament. The keyframe is always unobstructed; no hover preview, gradient scrim, or overlay chip covers the image. Metadata sits above or below it.

**Key Characteristics:**
- Near-white canvas, charcoal ink, 1px hairlines, 12px media corners.
- One large stage and a 2-up keyframe wall; the images are the only saturated color.
- Keyboard spine: `/`, Enter, arrows, Space, `[` `]`, `S`, `C`, `R`, `T`, `F`, `?`.
- A pinned submit bar with an inline video ID and timestamp, plus video-ID lookup.
- Flat surfaces; only popovers and dialogs lift.

## Colors

A restrained neutral field with two functional accents.

### Primary
- **Action Blue** (#2563eb): the search button, selected result border/ring/chips, focused inputs, and text links. This is the only action color.

### Secondary
- **Commit Emerald** (#047857): the submit button and a correct verdict. It never decorates anything else.

### Neutral
- **Canvas** (#f7f7f5): the working field.
- **Surface** (#ffffff): the command bar, submit bar, popovers, and result tiles.
- **Ink** (#0f172a): primary text and active values.
- **Ink Soft** (#475569): secondary labels and explained values.
- **Ink Muted** (#64748b): tertiary labels, counts, and placeholders; never lower than this on the light field.
- **Hairline** (#e2e8f0): separators and control borders.
- **Media Black** (#020617): the stage background and the letterbox around a capped frame.
- **Warning Amber** (#b45309 on #fef3c7) and **Danger Red** (#b91c1c on #fef2f2) carry degraded and error states only.

### Named Rules

**The Two Accents Rule.** Blue means action or selection; green means commit or correct. Neither is decorative, and green never becomes a status dot.

**The Frame Carries Color Rule.** Keyframe images are the only saturated field on a working screen. Chrome stays neutral so the frame wins.

**The Unobstructed Frame Rule.** No hover preview, gradient scrim, or overlay chip covers a frame. Metadata belongs in the toolbar or below the media.

## Typography

**Body Font:** system UI stack (system-ui, Segoe UI, Roboto, Arial)
**Label Font:** system UI stack
**Data Font:** ui-monospace stack

**Character:** Fast, familiar, and quiet. System UI carries the operator's language; monospace carries only data — video IDs, timestamps, scores, and key hints. There is no display face.

### Hierarchy
- **Title** (600, 14px, 1.35): the selected video ID and panel headings.
- **Body** (400, 14px, 1.5): search, labels, and explanatory copy.
- **Label** (500, 11–12px, 1.4): counts, state hints, and control labels.
- **Data** (500, 11px, 1.4, tabular): timestamps, scores, IDs, and shortcut keys.

### Named Rules

**The Data Is Monospaced Rule.** IDs, timestamps, scores, and keycaps use the mono stack with tabular numerals; prose never does.

**The No Display Voice Rule.** Hierarchy comes from weight, scale, and spacing, not a display face.

## Layout

A 56px command bar holds the product mark, one search field, index status, the filter button, and shortcut help. Below it, at laptop widths (≥1100px), the workspace is a two-pane split: the stage takes about two-thirds and the result rail about one-third with a 420px minimum. Below 1100px the panes stack.

The stage contains, in order: the selected video ID, active timestamp, offset, shot and object tags; the 16:9 media (height-capped at `calc(100dvh - 26rem)` so the strips stay visible on short laptops); a slim scrubber; the follow-frame filmstrip; and the full-video keyframe strip. The result rail is a 2-up wall at laptop widths and 3-up only in the stacked 768–1099px range. The pinned submit bar is 60px tall with a 20px reserve above it. A 1280–1920px laptop range is the verified target; 1366×768 keeps the stage and both strips on screen without scrolling.

Spacing follows a 4/6/8/12/16/24 rhythm. Tight groups sit inside generous separations; every major region is divided by a 1px hairline rather than a card shadow.

## Elevation & Depth

The system is flat by default. Regions are separated by hairlines, not shadows. Floating surfaces — the filter popover, the object drawer, and the shortcuts dialog — are the only elements that lift, using a wide, soft, offset shadow. The media is inset with a 1px border and no shadow.

### Shadow Vocabulary
- **Popover** (`0 16px 40px -16px rgba(15,23,42,0.35)`): the filter panel.
- **Dialog** (`0 24px 64px -24px rgba(15,23,42,0.5)`): the shortcuts dialog and object drawer.

### Named Rules

**The Flat Until It Floats Rule.** Cards and regions are flat at rest; only popovers and dialogs carry a shadow.

## Shapes

Controls and inputs use gently curved 8px corners; media, result tiles, and the stage use 12px; status chips and tags are fully rounded. The selected result is a 2px blue border with a 2px page-colored offset and a 2px blue ring, so the selection reads at a glance without becoming a pill. There are no decorative corner treatments, no offset block shadows, and no geometric masks.

## Components

### Command Bar
A 56px white bar with the four-square mark, the Mageseeker wordmark, one search field, index status, the filter button with a count badge, and a shortcut-help button. The search field is the only primary blue action on the bar.

### Stage
The selected frame is the largest object on the screen. The toolbar carries the video ID, active timestamp, offset, shot, and up to three object tags; the score is deliberately absent because the tiles already carry it. Play/pause, similar, timeline, and expand are icon buttons. The media is a 16:9 black stage; when the height cap engages, the frame is letterboxed rather than cropped. The stage shows the keyframe image by default; the video stream is requested only when the operator presses play/Space, so browsing results does not pay for video. The scrubber appears once the video is armed. The follow filmstrip sits beneath the media; the full-video keyframe strip sits beneath that.

### Result Tile
A pure image tile with a 2px neutral border. The bottom-left chip carries the video ID and timestamp; the top-right chip carries the retrieval score (hidden in video lookup). The selected state is unmistakable: a 2px blue border, a 2px page-colored offset plus a 2px blue ring, blue ID/time and score chips, a translucent blue wash over the image, and a blue check badge. There is no hover zoom.

### Full-Video Keyframe Strip
Every keyframe of the selected video, ordered by shot and time, in an 80×45 horizontal strip with a timecode overlay. The active tile uses the same strong blue selection as the grid. ←/→ steps the selection and keeps the target centered; the mouse wheel scrolls the strip horizontally without moving the page until the strip reaches an end.

### Submit Bar
A pinned 60px surface with a green commit. The video ID and timestamp are inline, editable, and monospaced; these edit the answer, not the lookup. A copy button, an advanced menu (submission kind, payload), an evaluation selector when needed, and the green submit button complete the bar.

### Video Lookup Row
A compact one-line row at the top of the results rail: video icon, **Mã video** label, a monospaced input accepting `12 016` or `L12_V016`, a live `→ L12_V016` resolution hint, and a small blue **Tìm** button. Enter or the button loads every keyframe of that video into the rail and stage. The description search stays in the command bar, separate from this lookup.

### Query Dock
A compact trigger in the submit bar: document icon, **Query đề thi**, the evaluation/task/time summary, and **Mở**. Clicking opens a centered modal with the full DRES task hint text, **Dùng query** (fills the description field and runs the search), **Copy**, and a close button. The dock refreshes every 15 seconds and immediately when the evaluation changes; the modal shows the full text without clipping.

### Filters and Dialogs
One popover holds the model, result count, object tags, intro/logo toggle, and near-duplicate toggle. Object tags open a full-height drawer; shortcuts open a small centered dialog; the frame expands into a lightbox. All use standard web controls.

## Do's and Don'ts

### Do:
- **Do** keep the frame unobstructed; put metadata in the toolbar or below the media.
- **Do** use blue for action/selection and green only for commit/correct.
- **Do** make the selected tile unmistakable with a border, ring, blue chips, and a check.
- **Do** keep the keyboard spine and the video-ID Enter lookup.
- **Do** keep the full-video strip below the follow frames, with arrow stepping and wheel scrolling.
- **Do** use mono and tabular numerals for IDs, timestamps, scores, and keys.

### Don't:
- **Don't** add hover-to-zoom or floating previews over images.
- **Don't** overlay gradient scrims or chips on frames.
- **Don't** reintroduce a filter sidebar or a visual-world costume.
- **Don't** show retrieval scores in video-lookup mode.
- **Don't** use green or blue decoratively.
- **Don't** signal selection with a 1px border alone.
