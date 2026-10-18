---
name: Проверка кассовых операций
description: A contact sheet of the recording, with every flagged moment circled in china marker.
colors:
  film-base: "#161616"
  strip-black: "#0c0c0c"
  raised-base: "#222221"
  frame-grey: "#2e2e2c"
  hairline: "#333331"
  hairline-strong: "#4a4a47"
  paper: "#f3f3f0"
  paper-dim: "#c9c9c3"
  ink-2: "#a8a8a2"
  ink-3: "#8c8c86"
  china-marker: "#ffd23f"
  marker-ink: "#1a1505"
  marker-wash: "rgb(255 210 63 / 12%)"
  safelight: "#ff6a55"
  safelight-wash: "rgb(255 106 85 / 10%)"
typography:
  display:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 1.2rem + 1.4vw, 2.25rem)"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.5
  caption:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  timecode:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  none: "0"
  stage: "50%"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "48px"
  gutter: "clamp(16px, 2.8vw, 40px)"
components:
  button-primary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.film-base}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "#ffffff"
    textColor: "{colors.film-base}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 16px"
    height: "40px"
  button-quiet-hover:
    backgroundColor: "{colors.raised-base}"
    textColor: "{colors.paper}"
  button-quiet-disabled:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
  event-id:
    backgroundColor: "transparent"
    textColor: "{colors.china-marker}"
    rounded: "{rounded.none}"
    padding: "0 12px 0 8px"
    height: "40px"
  event-id-hover:
    backgroundColor: "{colors.china-marker}"
    textColor: "{colors.marker-ink}"
  event-tab:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "8px 12px"
    width: "240px"
  event-tab-selected:
    backgroundColor: "{colors.marker-wash}"
    textColor: "{colors.paper}"
  panel-switch-pressed:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.film-base}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    height: "36px"
  mode-badge:
    backgroundColor: "transparent"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "3px 12px"
  alert:
    backgroundColor: "{colors.safelight-wash}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  stage-number:
    textColor: "{colors.ink-3}"
    rounded: "{rounded.stage}"
    size: "28px"
---

# Design System: Проверка кассовых операций

## Overview

**Creative North Star: "The Contact Sheet"**

The interface is a photographer's contact sheet laid on a darkroom bench. The whole recording becomes one strip of stills on black film base, every flagged moment is circled by hand in yellow china marker, and the selected moment's frames are pulled up enlarged beside the rule it may break. The reviewer reads the sheet the way an editor reads proofs: scan the strip, go to the circles, check the evidence, move on.

The world is dark because film base is dark, not for drama. Neutrals are warm-grey film tones, words are printed in paper ink, and there is exactly one hand in the room: the marker. Everything machined (frames, tabs, buttons, panels) is square, hairline-ruled and flat. The only organic shapes are the marker's loops and the numbers scrawled beside them. Density is working density: the result screen fits verdict, full strip, evidence and detail into a single 1440×900 viewport.

Motion is the marker drawing. Loops draw themselves on when the result lands and redraw on selection. Everything else answers within 140ms and goes still. Under reduced motion, the loops arrive already drawn.

**Key Characteristics:**
- Film-base dark ground, paper ink, and one yellow china-marker accent with a narrow job.
- Square corners everywhere; 1px hairline rules instead of cards and shadows.
- Sprocket-holed film strips as the recurring container for sequences of stills.
- A two-pass, hand-drawn SVG marker loop as the signature mark.
- Onest for every word; JetBrains Mono only for timecodes.

## Colors

Warm film-base neutrals carry the whole interface. Two wax-and-darkroom accents each do one job.

### Primary
- **China Marker Yellow** (china-marker): flags, selection, event identity and keyboard focus only. It circles flagged strip cells, numbers events, outlines the key evidence frame and fills its timecode tag, marks the selected event tab, colours the flag count in the verdict line, and draws every `:focus-visible` ring (2px, 3px offset). Text set on it uses **Marker Ink** (marker-ink). Its translucent **Marker Wash** (marker-wash) backs a selected tab and an active drop target.

### Secondary
- **Safelight Red** (safelight): failures only. It borders error alerts over **Safelight Wash** (safelight-wash). It never marks a flagged event; a possible violation is a marker circle, not an error.

### Neutral
- **Film Base** (film-base): page ground, lightbox ground, and the text colour on paper-filled controls.
- **Strip Black** (strip-black): film strips, the dropzone, empty player and frame wells, and the timecode tag backing (at 85%).
- **Raised Base** (raised-base): hover fill for quiet controls and tabs, empty placeholder cells, and progress-bar track.
- **Frame Grey** (frame-grey): strip cells before their thumbnail loads, and the brand mark's frames.
- **Hairline** (hairline): default 1px rules: topbar underline, event tab border, basis divider.
- **Hairline Strong** (hairline-strong): borders of quiet buttons, the panel switch and the dropzone, plus undecorated link underlines.
- **Paper** (paper): primary text, primary-button fill, pressed switch segment, playhead.
- **Paper Dim** (paper-dim): secondary body copy, test-mode badge border, completed stage fill.
- **Ink 2** (ink-2): metadata, labels, rule text.
- **Ink 3** (ink-3): pending stages, disabled controls, the standing review note.

### Named Rules
**The One Marker Rule.** China Marker Yellow means "look here, this is a flag, this is selected, this is focused". It never decorates, never fills a primary call to action, and never marks status chrome. The test-mode badge is paper ink for this reason.

**The Safelight Rule.** Safelight red appears only when something failed. A flagged event is never shown in red.

## Typography

**Body Font:** Onest (with system-ui, sans-serif), self-hosted at 400, 600 and 800, Cyrillic and Latin.
**Timecode Font:** JetBrains Mono (with ui-monospace, monospace), self-hosted at 500, Latin.

**Character:** Onest is a clear grotesque with Cyrillic built in. At 800 with tight tracking it gives headings the weight of a stamped print label, and at 400 it reads cleanly at length. JetBrains Mono is the edge-code on the film: fixed-width figures, so timecodes never jitter.

### Hierarchy
- **Display** (800, clamp 1.75rem to 2.25rem, line-height 1.08 to 1.1, -0.025em): one per screen: the verdict, the intake headline and the status headline. Balanced wrapping.
- **Headline** (800, 1.5rem, 1.2, -0.015em): the selected event's type and the dropzone title. The scrawled strip numbers also use this size and weight, in marker yellow and rotated -6°.
- **Body** (400, 1rem, 1.5): descriptions, capped at 65ch; intake copy capped at 46ch.
- **Label** (600, 0.875rem): buttons, switch segments, the "Основание" term and flag notes.
- **Caption** (400, 0.875rem): metadata, rule text, the review note.
- **Timecode** (JetBrains Mono 500; 0.75rem on frame tags, 11px on strip cells, 0.875rem in tabs, 1.25rem in the event chip): every timecode, and nothing else.

### Named Rules
**The Edge-Code Rule.** Mono is for timecodes only. Counts, durations in prose, stage numbers and event numbers outside the timecode chip stay in Onest, with tabular figures where they line up.

**The Three Weights Rule.** Onest ships at 400, 600 and 800. Do not introduce 500 or 700.

## Layout

Full-bleed within a fluid gutter (clamp 16px to 40px). There is no centred max-width column on the result screen; the strip spans the whole width because it is the whole recording. Rhythm follows a 4px-based scale (4, 8, 12, 16, 24, 32, 48). Groups inside a component use 8–12px. Regions on a screen use 24–32px. A screen's bottom margin is 48px.

- **Topbar:** at least 56px tall with a single hairline underline, and it persists across upload, status and result. Actions that apply only to a finished result live in the verdict row, not here.
- **Result:** verdict row (headline and meta on the left, actions on the right and bottom-aligned), then the full-width contact strip, then two columns at 7fr / 5fr (evidence on the left, event detail on the right), then the event tab row and the review note.
- **Upload:** two columns at 5fr / 7fr (copy on the left, dropzone on the right), vertically centred in the viewport.
- **Status:** a single column capped at 760px.
- **Breakpoints:** below 960px the review columns stack. Below 720px the intake stacks, the film strips halve their cell count, strip-cell timecodes hide, and the verdict actions go full width.
- **Evidence frames** take the video's own aspect ratio (`--frame-ar`, falling back to 16 / 9), so stills are never cropped to a house ratio. Strip cells are a fixed 16 / 10 and are cropped to cover.

## Elevation & Depth

The system is flat. Depth comes from tonal layering of the film-base neutrals (strip black under film base under raised base) and from 1px hairlines, not from shadows. Two exceptions earn a shadow. The lightbox floats over an 82% black backdrop because it is a true overlay. Small text laid over unknown footage (strip timecodes and the scrawled event numbers) carries a tight dark text-shadow for legibility.

### Shadow Vocabulary
- **Lift** (`box-shadow: 0 2px 4px rgb(0 0 0 / 30%), 0 18px 40px -16px rgb(0 0 0 / 70%)`): the lightbox dialog only.
- **Legibility halo** (`text-shadow: 0 1px 2px rgb(0 0 0 / 90%)`; `0 1px 3px rgb(0 0 0 / 80%)` on marker numerals): text printed over thumbnails.

### Named Rules
**The Flat Bench Rule.** Nothing on the page floats except a modal. Panels, tabs and buttons sit flush, separated by hairlines and tone.

## Shapes

Corners are square system-wide (border-radius 0). The single exception is the status stage-number circle (28px, 50%), a numbered processing step rather than a container. Containers are hairline-bordered or tone-filled, never both heavy. Sequences of stills sit in **film strips**: a strip-black band with sprocket holes along the top and bottom edges, drawn as repeating linear gradients. The contact strip, the dropzone preview and the status exposure strip all use this form. The only free-form geometry is the marker loop and its numerals.

## Components

### Buttons
Printed and plain: square, 40px tall, label type.
- **Shape:** square corners (0), 1px border, 16px horizontal padding, icon gap 8px.
- **Primary:** a paper fill with film-base text. Hover lifts to pure white. Use one per region, for the forward action ("Проверить другое видео").
- **Quiet:** transparent, with a hairline-strong border and paper text. Hover brings the border to paper dim and a raised-base fill. Disabled drops to a hairline border and ink-3 text.
- **Active:** both nudge down 1px. Focus is the global 2px marker ring.

### Event Identity Chip
A marker-outlined chip in mono 1.25rem: play icon, event number and timecode. Hover floods it with marker yellow and marker-ink text. Clicking it plays the video from that moment.

### Event Tabs
Square, hairline-bordered tiles (180–240px wide, 8px 12px padding). The marker numeral is Onest 800, the timecode is mono, and the type below is clamped to two lines in paper dim. Hover gives a hairline-strong border and a raised fill. Selected gives a marker border over marker wash. They scroll horizontally when they overflow.

### Panel Switch
A segmented control: square segments joined by hairline-strong dividers inside one bordered frame, 36px tall. The pressed segment inverts to a paper fill with film-base text.

### Evidence Frames
Square wells in strip black at the video's own aspect ratio. A timecode tag sits flush at the bottom-left corner (85% strip black, mono 0.75rem). The key frame gets a 3px inset marker outline, and its tag inverts to marker yellow with marker-ink text. On keyboard focus the key frame's outline switches to paper so focus stays distinguishable. A zoom affordance fades in at the top-right corner on hover or focus.

### Alerts and Badges
- **Alert:** a 1px safelight border over safelight wash, paper text, capped at 72ch.
- **Test-mode badge:** a 1px paper-dim border, paper text, xs 600. Status chrome stays out of the marker's job.

### Status Stages
A numbered list. Pending steps are ink-3 with a hairline-strong circle. Done steps get a paper-dim filled circle. The current step has a 2px marker ring with a marker numeral and paper 600 text. Below the list, an exposure strip of 20 cells fills from raised base to paper dim as stages complete. These are real stages, not invented percentages.

### Marker Loop (signature)
An irregular, hand-drawn SVG loop around each flagged strip cell. Each loop is two passes: a heavy main stroke (3.4) that overshoots and crosses its own start, and a lighter echo stroke (1.3, 85% opacity) slightly off the first, the way wax skips and doubles on a print. Three variants rotate through flags, each with its own tilt (-4°, 3°, -2°). The loop draws itself on with `stroke-dashoffset` over 700ms. Loops stagger 160ms apart, and the echo trails its main stroke by 240ms. Selection thickens both passes (5.2 / 2.2) and redraws them. A numeral in Onest 800 marker yellow, rotated -6°, is scrawled above each loop. Under `prefers-reduced-motion` the loops render fully drawn, with no animation.

## Do's and Don'ts

### Do:
- **Do** keep corners square (0) on every container, control and frame. The 28px stage-number circle is the only round shape.
- **Do** reserve china-marker yellow for flags, selection, event identity and focus, and set text on it in marker ink.
- **Do** set every timecode in JetBrains Mono 500 and nothing else in mono.
- **Do** separate regions with 1px hairlines and tonal steps (strip black, film base, raised base) rather than shadows.
- **Do** show stills at the video's own aspect ratio (`--frame-ar`) in evidence views.
- **Do** put sequences of stills in a sprocket-holed film strip.
- **Do** let the marker loop draw itself on, and render it fully drawn under reduced motion.
- **Do** keep transitions at 140ms on `cubic-bezier(0.16, 1, 0.3, 1)`, limited to colour, opacity and small transforms.

### Don't:
- **Don't** round cards or stack rounded event cards beside a player.
- **Don't** use marker yellow for primary buttons, status badges, decoration or headings.
- **Don't** use safelight red for a flagged event. Red means a technical failure.
- **Don't** add drop shadows to panels, tabs or buttons. Only the lightbox lifts.
- **Don't** draw marker loops as perfect ellipses or uniform strokes. They are hand-drawn, two-pass and tilted.
- **Don't** add a fourth Onest weight or a second display family.
