# Part 01. Interface And Interaction Unification

> This is a normative component of the [Part 00 documentation authority](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md).

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are
normative. Numeric defaults may change only after workload measurement, while
the safety property behind every limit MUST be preserved.

## Central Authority And Material Divergence

This Part takes precedence over conflicting project-local documentation.
Project documents MUST adapt these rules to current project-specific values
without weakening them. A material implementation difference follows the
reporting and decision protocol in [Part 00](./PART_00_SYSTEM_UNIFICATION_SPECIFICATION.md#1-mandatory-material-divergence-protocol); stale local documentation is corrected and is not an alternative authority.

---
## 1. Product Character

An operational interface is a tool, not a marketing page. It should be quiet,
technical, dense and optimized for repeated work. Content appears immediately;
decorative hero sections, floating cards, gradients, glass effects, textures
and ornamental shapes are outside this visual language.

The unified style is based on:

- a true black working surface;
- white information and structural lines with one nested-opacity level;
- one configurable accent, with blue `#00A8FF` as the baseline;
- Space Grotesk for service and page display names and Consolas for every other
  interface role;
- rectangular geometry;
- hierarchy expressed through line opacity, spacing and position rather than
  shadows or nested decorative containers.

### 1.1 Reference Templates And Precedence

The PNG files in [`./src`](./src/) are normative visual references where this
part links them. They define composition, palette, hierarchy, relative scale,
control anatomy and interaction-state appearance. The reference canvas is
approximately `1919x1030`; the full-page PNG exports are `1919x1034`. These
pixel dimensions describe the supplied reference view, not a fixed CSS canvas.

The exact measurement audit of the linked PNG templates is incorporated into
the coordinate, component and template ledgers below. This Part is the
implementation source of truth; developers do not need to reconcile two files
at runtime or copy product-specific labels from the measurement audit.

The written token, behavior, accessibility and responsive rules in this part
take precedence over incidental anti-aliasing colors, export cropping and
one-pixel rounding in a PNG. When a measured template dimension is marked
`approximately`, preserve the relationship and layout token rather than
forcing an absolute coordinate at every viewport.

Template content is interpreted as follows:

- `example` is a placeholder for the actual service name;
- the blue doughnut is a placeholder for the actual service icon and MUST NOT
  ship unless it is the real product asset;
- example metrics, labels, menu commands, versions, hosts and values illustrate
  information hierarchy and are not product data requirements;
- visual order is normative only where a section explicitly defines it;
- a service-specific departure from a linked template is a material UI/UX
  difference and follows the Mandatory Material-Divergence Protocol.

## 2. Theme, Typography And Geometry

### 2.1 Theme Inputs

The interface uses exactly five base hues: black, white, the configured accent,
success green and danger red. `#111111`, 80%-white and the fixed `#D9D9D9`
decorative-dot shade are approved variants of black and white, not additional
theme inputs.

| Token | Baseline | Configurable | Purpose |
| --- | --- | --- | --- |
| `--black` | `#000000` | No | Page, sidebar, card, control and dialog background |
| `--surface-hover` | `#111111` | No | Hover, focus and raised interactive surface |
| `--white` | `#FFFFFF` | No | Primary text and level-one outlines |
| `--white-80` | `rgb(255 255 255 / 80%)` | No | Secondary text and every nested outline; renders as `#CCCCCC` on black |
| `--decorative-dot` | `#D9D9D9` | No | Rest-state four-dot drag marks only |
| `--accent` | `#00A8FF` | Yes | Active state, display titles, focus, selection and live emphasis |
| `--success` | `#62FF8C` | No | Healthy, successful or explicitly good state |
| `--danger` | `#F83D3D` | No | Failed, unavailable, destructive or explicitly bad state |

Only `--accent` is editable under Appearance. Editing previews the accent
immediately across the login and authenticated shell, but the new value becomes
authoritative only after `Apply color`. `Reset color` restores `#00A8FF` and is
subject to the same explicit apply step. Cancel or navigation before apply
restores the last persisted accent.

The canonical tokens are:

```css
:root {
  --black: #000000;
  --surface-hover: #111111;
  --white: #ffffff;
  --white-80: rgb(255 255 255 / 80%);
  --decorative-dot: #d9d9d9;
  --accent: #00a8ff;
  --success: #62ff8c;
  --danger: #f83d3d;
  --line-outer: var(--white);
  --line-inner: var(--white-80);
  --text-primary: var(--white);
  --text-secondary: var(--white-80);
}
```

All structural borders are normally `1px`. The outline hierarchy has exactly
two levels:

1. A top-level bordered element that is not inside another bordered element
   uses `--line-outer` at 100% white.
2. Every bordered element inside a bordered element uses `--line-inner` at 80%
   white. Deeper descendants remain at 80%; a third visual level MUST NOT be
   introduced by reducing opacity again.

Accent, success and danger may replace a structural outline only when they
communicate an interactive or semantic state. Color never replaces text,
position, iconography or an accessible state name. Arbitrary per-feature colors
MUST NOT be introduced. Explicit opacity remains permitted for non-outline
effects already defined by this guide, including disabled state, drag source,
overlay backdrop and visualization de-emphasis; it does not create another
outline-hierarchy level.

### 2.2 Typography

Only Regular and Bold weights are used. Do not request or synthesize medium,
semibold, extrabold or black weights.

```css
.service-wordmark,
.page-title {
  font-family: "Space Grotesk", "Segoe UI", sans-serif;
  font-weight: 700;
  letter-spacing: 0;
}

body,
button,
input,
select,
textarea,
code {
  font-family: Consolas, "Cascadia Mono", "Segoe UI Mono", monospace;
  font-weight: 400;
  letter-spacing: 0;
}

strong,
b,
.metric-value,
.section-title {
  font-weight: 700;
}
```

- Desktop page titles are left-aligned, accent-colored Space Grotesk Bold,
  exactly `80px` at the reference width, with a responsive
  `clamp(48px, 4.2vw, 80px)` and line height from `0.95` to `1.05`.
- The login service wordmark is approximately `72px`; the sidebar service name
  is exactly `42px` at the reference canvas. Long real names shrink within
  explicit bounds and never clip, wrap one glyph per line or overlap the
  service icon.
- Titled-card and metric headings are `24px` Consolas Bold and use the accent.
  Settings group headings are `20px` Consolas Bold. A measured `28px` label in
  a design annotation is annotation text, not a runtime UI type token.
- Navigation, controls, descriptions, log cells, ordinals and ordinary body
  text are `14px` at the reference canvas.
- Muted explanatory text uses `--text-secondary` and a line height between
  `1.5` and `1.7`.
- Button labels begin with a capital letter.
- Preserve the product's actual title casing. Do not force large service or
  page names to uppercase.
- Ordinary content MUST NOT use negative letter spacing or unbounded
  viewport-width font scaling.

Description text may step down at explicit character thresholds. Its vertical
origin remains fixed, so editing never moves the first line.

### 2.3 Geometry And Spacing

- All stated component widths and heights use `box-sizing: border-box` unless a
  source measurement explicitly describes an outer export rather than a box.
- Corners are square by default. Radius is `0` and MUST NOT exceed `8px` when a
  platform convention requires rounding.
- Borders and dividers are `1px` unless an explicit focus outline is defined.
- Base control height is `40px`; compact controls MAY be `36px` but never below
  the accessible target required by the target platform.
- The spacing scale is `4px`, `8px`, `10px`, `20px`, `30px` and `40px`.
  Components SHOULD compose these tokens instead of introducing arbitrary
  nearby values.
- The fixed desktop sidebar is `250px` wide. The main page header is
  exactly `123px` high at the reference canvas, and main content uses a `30px`
  outer inset.
- Full-width section bodies use approximately `40px` inner padding. Compact
  controls and navigation rows use `10-12px` internal padding where `20px`
  would make the interface unnecessarily sparse.
- The standard vertical gap between dashboard rows and between primary grid
  groups is `30px`. Two `1x` cards inside a `2x` group use a `40px` gap.
- Stable controls and status changes MUST NOT reflow neighboring content.
- A bordered workspace may contain structured sections, but decorative cards
  MUST NOT be nested recursively.

At the reference desktop content width, universal card widths are derived as a
hierarchy:

```text
4x = 1610px
2x = (4x - 30px primary gap) / 2 = 790px
1x = (2x - 40px nested gap) / 2 = 375px
```

These are reference results, not rigid minimums. Below the reference width,
tracks use `minmax(0, 1fr)`, card contents reflow, and the layout collapses by
logical group while preserving DOM, keyboard and reading order.

### 2.4 Reference Coordinate Model

Exact pixel coordinates in this document use the top-left of the supplied
desktop export as `(0, 0)`. The measured PNG is `1919x1034px`, while the design
layout targets a `1920px`-wide browser canvas; the export may omit the final
rightmost raster column. This does not change the following reference tracks:

| Region | Reference geometry |
| --- | --- |
| Viewport/export | `1919x1034px` capture of the `1920px` design canvas |
| Expanded sidebar | `left: 0; top: 0; width: 250px; height: 1033px` |
| Main layout track | `left: 250px; width: 1670px` on the design canvas |
| Main header divider | horizontal line at `top: 123px` |
| Main content inset | `left: 280px`, or `30px` after the sidebar |
| Full content/card width | `1610px`, ending at design coordinate `1890px` |

The canonical implementation is `width: 250px; border-right: 1px solid
var(--white); box-sizing: border-box`. The main region therefore begins at
`left: 250px`. A legacy source layer represented the same separator as a rotated
line near `x=251`; that construction is not normative. Visual output must be one
continuous device-pixel line with no second seam.

The canonical reference-spacing ledger is:

| Relationship | Exact value |
| --- | --- |
| Navigation label origin | `31px` from the sidebar's left edge |
| Navigation ordinal origin | `left: 209px`, or `41px` before the sidebar's right edge |
| Active-row frame inset | `18px` from the sidebar's left edge |
| Nominal navigation text-row step | `45px` |
| Main content origin | `280px`, equal to `250px + 30px` |
| Metric-card content origin | `37px` from the card's left edge |
| `2x` dashboard column-origin step | `820px`, equal to `790px + 30px` |
| Dashboard row-origin step | `196px`, equal to `166px + 30px` |
| `1x` nested-card origin step | `415px`, equal to `375px + 40px` |
| Card ordinal inset | `10px` from the left and top |

Global coordinates are verification targets only for the reference viewport
with the sidebar fixed open. Production layout MUST derive them from sidebar,
header, inset and grid tokens rather than absolutely positioning the entire
application. When the viewport or sidebar mode changes, responsive rules in
section 9 take precedence; component-local dimensions and internal insets stay
exact wherever space permits.

A one-device-pixel difference caused by screenshot cropping, CSS border
rasterization or fractional scaling is acceptable for isolated divider
coordinates. It does not permit cumulative drift, different component sizes or
changing a documented gap token.

## 3. Shared Interaction Contract

### 3.1 Hover, Focus, Pressed And Disabled States

Buttons, clickable rows, inputs, selects and interactive work items share one
state language. The visual references are [example - hover - no hover](<./src/example - hover - no hover.png>),
[example - hover - hover 1](<./src/example - hover - hover 1.png>) and
[example - hover - hover 2](<./src/example - hover - hover 2.png>).

The states are:

| State | Fill | Element border | Text | Extra outline | Geometry |
| --- | --- | --- | --- | --- | --- |
| Rest | `--black` | Structural 100% or nested 80% white | Existing primary/secondary roles | None | Base size |
| Hover 1 | `--surface-hover` | Accent | Existing content colors | None | Proportional growth |
| Hover 2 / keyboard focus | `--surface-hover` | Accent | Interactive label or ordinal becomes accent | `1px` accent with approximately `3px` visual separation | Same grown element size as Hover 1 |
| Pressed | Hover fill | Accent | Active state color | Focus outline remains for keyboard activation | Uniform `scale(.985)` |
| Disabled/pending | Existing fill | Existing border | Existing color at `0.45` opacity | None | Base size; no growth |

Hover 1 is the normal pointer treatment for a bordered card or neutral control.
Hover 2 is the emphasized treatment and the minimum keyboard-focus treatment.
The outer outline in Hover 2 does not participate in layout sizing, so both
hover templates have the same control-box size even though the second PNG has
additional pixels around it.

The three source PNG dimensions record the supplied historical exports:

| State export | Outer export | Interactive card box | Offset inside export |
| --- | --- | --- | --- |
| Rest | `375x166px` | `375x166px` | `0, 0` |
| Hover 1 | `380x169px` | `380x169px` | `0, 0` |
| Hover 2 / focus | `388x177px` | `380x169px` | `4px, 4px` |

They demonstrate state anatomy, not the normative scaling result. The formula
below takes precedence over the old `380x169px` raster. For a `375x166px` base,
it produces `growth = 8.3px` and a target control box of approximately
`383.3x174.3px`. Hover 2 adds the non-layout focus outline and its separation
around that same computed box. Its ordinal becomes accent while four-dot marks
become `#FFFFFF`.

Hover and focus transitions last about `160ms` with an ease curve. The element
grows through `transform`, never through layout dimensions. Its background is
the exact `#111111` token; do not substitute a runtime 10%-white color mix that
produces a different hex value.

Growth adds the same absolute number of pixels to both dimensions:

```js
const growth = Math.min(width, height) * 0.05;
const scaleX = (width + growth) / width;
const scaleY = (height + growth) / height;
```

Items touching a grid edge set `transform-origin` to that edge so growth moves
inward. Other elements use a centered origin. Growth MUST NOT overlap unrelated
controls, trigger scrollbars, change track calculation or move adjacent items.

The canonical pressed effect is `transform: scale(.985)` with a transition
duration of about `60ms`; release returns through
the ordinary `160ms` transition. This short uniform scale is an intentional
press-feedback exception to proportional hover growth.

Disabled or pending controls preserve their dimensions, use `0.45` opacity and
do not scale. A long-running command replaces its verb with a progressive label
such as `Saving...` or `Checking...`. `prefers-reduced-motion: reduce` removes
transform and non-essential animation while retaining border, fill, text and
focus distinctions.

### 3.2 Drag And Drop

Use direct manipulation only where order has semantic or personal meaning.

There are two reorder presentations:

- a one-dimensional navigation or list reorder uses an accent insertion line at
  the exact before/after position;
- a two-dimensional card reorder uses a live placeholder with the dragged
  card's span and reflows every affected card into its prospective position.

During either drag:

1. Source opacity becomes approximately `45%`.
2. The pointer is compared continuously with the target midpoint.
3. A `1px` accent insertion line or full-size grid placeholder shows the exact
   destination; changing pointer position updates the preview before drop.
4. Drop updates the order immediately and adaptive two-digit ordinals are
   recomputed from the new visible order.
5. Authenticated layout order is persisted as operator presentation state so it
   survives reload and a new login. Browser-only persistence is acceptable only
   for an explicitly local unauthenticated surface.
6. Failed persistence restores the last confirmed order and shows an error.

Universal cards start pointer dragging from the four-dot handle at the upper
right. Navigation rows may use the row as the drag target. Dragging MUST
suppress the item's ordinary open, navigation or command action. A keyboard
reorder command MUST expose the same destinations and announce the resulting
position.

### 3.3 Overlays

Focused forms, destructive confirmation, Access Key changes, control-plane token
rotation, imports, restore actions and update discovery use a custom overlay:

- a fixed full-viewport backdrop;
- `rgba(0,0,0,.35)` plus about `9px` backdrop blur;
- a dialog centered on every open;
- maximum dimensions constrained to the viewport with internal scrolling;
- header dragging clamped to an `8px` viewport inset;
- an explicit close control and Escape handling;
- no accidental close from a click inside the dialog.

The dialog outer border is level-one white; controls nested inside it use the
level-two 80%-white outline. Opening moves focus to the heading or first field,
Tab is trapped inside, and closing restores focus to the invoking control.
Backdrop click may close a read-only or untouched dialog. It MUST NOT silently
discard entered credentials, a selected restore archive or an accepted
destructive step.

A restore overlay controls file-selection state, archive metadata,
confirmation, progress and outcome. The operating-system file picker launched
from it remains native; a web application MUST NOT imitate or replace that
trusted picker.

Notifications render above overlays; overlays render above workspaces and
context menus that belong to the underlying page.

### 3.4 Clipboard Copy And Constrained Webviews

Writing generated text, links or commands to the system clipboard is a
progressive enhancement. Automatic copying MUST NOT be the only way to obtain
a value or a prerequisite for completing a workflow.

A clipboard write SHOULD use `navigator.clipboard.writeText()` and MUST be
attempted only from a secure context, while the document is active and focused,
and directly in response to a trusted pointer or keyboard action. If the value
must first be generated or fetched asynchronously, the operation MUST finish
before the user is offered a `Copy` or `Copy and continue` action. Page load,
timer, redirect completion and background-event handlers MUST NOT be relied on
for clipboard writes because user activation may be absent or may have expired.

The interface MUST:

1. feature-detect clipboard support instead of inferring it from the user agent;
2. handle rejected clipboard promises as an expected capability outcome;
3. show `Copied` only after the write promise resolves;
4. keep the complete value visible and selectable when copying fails;
5. provide an explicit retry control and concise manual-copy guidance;
6. preserve the user's progress when copying is unavailable.

A deprecated `document.execCommand("copy")` fallback MAY be attempted for legacy
webviews, but only during the same user action and never as the sole fallback.
`Open in browser` or `Share` MAY be offered as secondary actions on constrained
mobile clients. A native clipboard bridge MAY be used only in an application-
owned webview and MUST preserve the same explicit action and success feedback.

Embedded browsers, including the browser opened from Telegram, MUST be treated
as capability-variable environments. Their web engine, application version,
permission handling or embedding policy may prevent a clipboard write even
when it works in a standalone browser. Telegram Mini Apps provide a native
clipboard-read operation but no documented clipboard-write operation, so the
web fallback remains mandatory.

Sensitive values such as credentials, recovery codes and access tokens MUST
NOT be copied silently. Copying them requires an explicit action and a visible
description of what will replace the current clipboard contents.

### 3.5 Context Menus

The visual reference is [example context menu](<./src/example context menu.png>).
A context menu MAY invert the ordinary palette for maximum contrast: white
background, black text and accent text for the hovered, focused or selected
command. This is an approved component-specific inversion, not a second theme.

Context menus:

- use rectangular geometry, no decorative shadow and compact Consolas text;
- size to their longest localized command within a viewport maximum;
- open next to the invocation point, then flip or clamp to remain fully inside
  an `8px` viewport inset;
- keep command order and separators stable while open;
- move focus with Arrow Up/Down, activate with Enter or Space, close with Escape
  or an outside pointer press and restore focus to the invoker;
- expose disabled state without removing the command from its expected place;
- never use hover color as the only indication of keyboard focus.

The Russian commands and numbering in the PNG are illustrative. Product
commands, localization and authorization determine the actual menu content.

The reference export uses `width: 155px; height: 197px; overflow: hidden`. Its
inner white panel uses `width: 156px; height: 197px; left: -1px`, with a `1px`
white border. The
ordered-list origin is `left: 16px; top: 9px`; list content uses `14px` Consolas
Bold, black text, `21px` list-item left indentation and `22px` line height. The
highlighted fourth example command is accent. Production commands may differ,
but row height, text origin and menu geometry remain the component baseline;
hover or focus MUST NOT resize the `155x197px` outer box.

## 4. Authentication And Primary Navigation

### 4.1 Login View

The visual reference is [example Log in page](<./src/example Log in page.png>).
The service is single-operator: authentication uses one Access Key field and
MUST NOT ask for a login name, username, email or separate password.

The login view uses the `public authenticated` exposure profile. It MUST be
reachable through the canonical HTTPS origin from every client IP; neither the
application nor the server Nginx may require `OPERATOR_CIDR`, a source-IP
allow-list or a VPN merely to render the login and submit an Access Key. Before
successful authentication, the response exposes no operator data. Protected
pages and APIs require a valid Access Key-derived server session, enforce
authorization on every request and never treat network location as proof of
identity. IP address remains usable for rate limiting and abuse telemetry, not
as the operator authentication boundary.

At the reference desktop viewport:

- the complete login composition is horizontally centered and visually centered
  around the viewport midpoint with at least `24px` viewport padding;
- the bordered authentication panel is exactly `560x268px` and becomes
  `min(560px, calc(100vw - 48px))` on smaller screens;
- the accent service name and actual service icon sit immediately above the
  panel as one brand group; the name is `72px` Space Grotesk Bold and the icon
  fits a `100x100px` visual box without distortion;
- the panel has one level-one white border, black fill, no radius and no shadow;
- reachability, the Access Key field and the submit button share the same left
  origin; the field and button share the full inner content width;
- nested fields and buttons use the 80%-white outline until hover, focus or a
  semantic state replaces it.

The exact `1919x1034px` reference ledger is:

| Login element | Global geometry or painted bounds |
| --- | --- |
| Example service wordmark | painted bounds `left: 677px; top: 350px; width: 317px; height: 72px`; width changes with the real name |
| Example service-icon artwork | painted bounds `left: 1139px; top: 345px; width: 87px; height: 72px` inside the `100x100px` icon box |
| Authentication panel | `left: 680px; top: 444px; width: 560px; height: 268px` |
| Reachability box | `left: 705px; top: 466px; width: 255px; height: 50px` |
| Reachability label paint | `left: 717px; top: 486px; width: 154px; height: 13px` for the example label |
| Reachability square | `left: 926px; top: 482px; width: 18px; height: 18px` |
| Access Key field | `left: 705px; top: 578px; width: 511px; height: 31px` |
| Access Key placeholder paint | `left: 717px; top: 588px; width: 98px; height: 12px` for `Access Key...` |
| Submit button | `left: 705px; top: 635px; width: 511px; height: 50px` |
| Submit-label paint | `left: 910px; top: 655px; width: 99px; height: 11px` for `Enter service` |

Painted bounds document this exact example raster and are not fixed boxes for a
different service name, localization or font rasterizer. The `31px` visible
Access Key field is a Login-specific visual exception to the `40px` base-control
height; its wrapper/hit target MUST still meet the platform minimum without
changing the visible reference border.

Reachability is independent of authentication:

| State | Text and square | Motion |
| --- | --- | --- |
| Checking | Explicit neutral text using white/80%-white | None required |
| Reachable | `#62FF8C` text and solid square; nested border is the 80% semantic color `#4ECC70` | One smooth opacity fade cycle every `2s` |
| Unreachable | `#F83D3D` text and solid square; nested border uses 80% danger | None |

The green square never disappears completely during its fade. Reduced-motion
mode makes it static. Availability is checked immediately and periodically; an
invalid Access Key does not change a reachable service to unavailable.

The Access Key control:

- is empty on every fresh render and reset;
- uses a masked secret input with an accessible `Access Key` label even if the
  compact visual presentation uses a placeholder;
- accepts the explicitly supplied value as opaque exact text: there is no
  minimum or maximum length, strength/entropy score, required or forbidden
  character class, URL-safe/ASCII-only restriction or denylist;
- has no password-strength meter and shows no composition hint such as a
  character count or a requirement for letters, digits or symbols;
- never trims, normalizes, changes case, truncates or otherwise rewrites the
  submitted value; an absent value is an unconfigured/empty field, not a weak
  value;
- uses `autocomplete="current-password"` so standards-based password managers
  can offer the saved Access Key without requiring a fabricated username field;
- is never initialized from markup, server-rendered state, query parameters,
  local storage or a previously submitted value;
- submits through the same pending-safe action from Enter and the full-width
  `Enter service` button;
- stays visible after rejection and receives focus with a concise error that
  does not disclose which part of the credential was wrong.

Authentication, recovery, provisioning and settings forms MUST render every
Access Key, password, PIN, recovery-code and access-token input empty on first
open. Reopening or resetting such a form MUST clear those values again. A
placeholder is descriptive UI text, not a value, and MUST NOT contain a real
credential. Application code must not simulate credential-manager behavior
with defaults.

### 4.2 Sidebar

The visual references are [example Left Menu](<./src/example Left Menu.png>) and
[Example of left menu and main page side by side, base layer of main page, name of main page](<./src/Example of left menu and main page side by side, base layer of main page, name of main page.png>).

The expanded desktop sidebar is fixed to the left edge, occupies the full
viewport height and is `250px` wide including its `1px` level-one right border.
Its canonical box is:

```css
.sidebar {
  box-sizing: border-box;
  width: 250px;
  border-right: 1px solid var(--white);
}
```

Its final background is opaque `#000000`. The source composition places an
optional full-size `object-fit: cover` image below that fully opaque black
layer; an implementation SHOULD omit the hidden image request when no visible
state reveals it. The reference composition uses:

- an actual service icon in a `192x192px` box at `left: 31px; top: 6px`, using
  `object-fit: cover` only when cropping is approved for the real asset;
- the accent service name in `42px` Space Grotesk Bold, centered in a
  `170x76px` text box whose horizontal center is `x=125px` and whose top is
  `175px`;
- primary navigation beginning with a `221x42px` active-row box at
  `left: 18px; top: 285px`;
- label text at `left: 31px` and adaptive ordinals at `left: 209px`, both
  `14px` Consolas Bold;
- Documentation and Logout as an unnumbered group with text tops at `943px`
  and `988px` respectively in the `1033px` reference sidebar.

The reference text-top ledger is:

| Visible position | Label | Text top | Ordinal | Ordinal top |
| --- | --- | --- | --- | --- |
| 1 | Active primary destination | `299px` | `01` | `299px` |
| 2 | Primary destination | `346px` | `02` | `346px` |
| 3 | Primary destination | `391px` | `03` | `391px` |
| 4 | Primary destination | `436px` | `04` | `436px` |
| 5 | Primary destination | `481px` | `05` | `481px` |
| 6 | Settings in the supplied reference | `526px` | `06` | `526px` |

The nominal text-top step after the second entry is `45px`; the first measured
step is `47px`. Implement the list as a `42px` row plus a `3px` row gap and use
the active row's own content alignment to reproduce the reference without
hard-coded per-route coordinates. The supplied destination names are examples;
actual primary destinations occupy the same ordered slots.

Every primary destination row contains its label at left and an adaptive
two-digit ordinal at right. Ordinals represent current visible position: after
a reorder they are recomputed sequentially as `01`, `02`, `03` and so on. They
are not persistent IDs.

The legacy sidebar PNGs contain the sequence `01`, `02`, `04`, `05`, `06`,
`07`. The missing `03` is a template defect and MUST NOT be reproduced.

The active primary destination uses accent label text, a rectangular `1px`
accent border and an external accent arrow on the left. The arrow has a short
rectangular base and points toward the active row. It occupies reserved or
overflow-visible marker space and MUST NOT change row width or move its label.
At the first reference row, the rectangular base is `4x22px` at
`left: -2px; top: 295px`; the right-pointing SVG triangle is `12x5.77px` at
`left: 0` and is vertically centered around `top: 306px`.

Inactive primary rows have a transparent border reservation. On hover they use
the shared proportional growth, `#111111` fill, accent border and accent label.
The ordinal remains legible and may also become accent in the emphasized
variant. The row touching the sidebar edge grows inward.

Documentation and Logout are explicit exceptions: they are never bordered,
never numbered, never scaled and never draggable. Hover, focus and the active
Documentation state change their text to accent while retaining a separate
keyboard-visible focus indication that does not resemble the primary-row box.

Primary destinations may be reordered through pointer or keyboard interaction.
The new order and recomputed ordinals persist after reload and a new login.
Documentation and Logout remain outside that order. Navigation changes views
without a full page reload, and the active destination name appears exactly
once in the main page header.

The reference desktop state keeps the sidebar open. The operator may choose a
persisted fixed or auto-hide mode under Appearance:

- fixed mode reserves exactly `250px`; the main region uses the remaining width
  and its own `30px` content inset;
- auto-hide mode translates the sidebar fully left while an `18px` activation
  strip remains; reveal and hide take about `180ms`;
- when the sidebar closes, the main region expands through grid/flex track
  calculation, and cards reflow in their existing logical order without
  absolute-position jumps, overlap or horizontal scrolling;
- at `720px` and below, an explicit menu button opens the sidebar as an overlay
  instead of reserving permanent width.

## 5. Workspaces, Feedback And Documentation

### 5.1 Main Page Shell And Workspaces

The base-shell reference is
[Example of left menu and main page side by side, base layer of main page, name of main page](<./src/Example of left menu and main page side by side, base layer of main page, name of main page.png>).
It demonstrates page construction rather than dashboard content.

With the sidebar fixed open at the reference width:

- the sidebar occupies `250px` and the main page begins immediately after its
  right border;
- the header spans the remaining `1670px` and is exactly `123px` high in the
  source coordinate model;
- the page title begins at `left: 280px; top: 15px`, occupies a measured
  `783x76px` reference box, uses `80px` Space Grotesk Bold and the accent, and
  is vertically centered without touching the divider;
- a level-one white horizontal divider terminates the header;
- the reference content-zone frame begins at `left: 250px; top: 123px`, has
  design dimensions `1670x978px` and is viewport-clipped when its measured
  height extends below the export; page content itself begins at `left: 280px`
  and normally `28-30px` below the divider;
- empty working space remains true black and is not filled with decorative
  containers.

A detail view uses one fullscreen work surface with its page title at the upper
left, an optional close control at the upper right, description and structured
fields first, and related collections below when required. Close returns
exactly one navigation level. Shared field definitions are references: editing
one updates every placement, while placement order can remain local to each
collection.

Graph workspaces use all available space; presentation controls start
collapsed. Domain entities and field metadata need visibly distinct styling
without adding arbitrary theme colors.

### 5.2 Universal Cards

The universal-card references are:

- [universal card - 1x](<./src/universal card - 1x.png>);
- [universal card - 1x - title](<./src/universal card - 1x - title.png>);
- [Universal card - 2x](<./src/Universal card - 2x.png>);
- [Universal card - 2x - title](<./src/Universal card - 2x - title.png>);
- [universal card - 4x](<./src/universal card - 4x.png>);
- [universal card - 4x - title](<./src/universal card - 4x - title.png>).

A universal card is a rectangular, reusable content region with black fill and
a `1px` outline. It has these invariant parts:

1. An adaptive two-digit ordinal at the upper left, inset exactly `10px`
   horizontally and `10px` vertically in the untitled metric reference.
2. A four-dot drag handle at the upper right. Each visible dot is a `4x4px`
   circle (`r=2px`) using `--decorative-dot` at rest. Dot centers form an `8px`
   by `8px` grid. As a deliberate midpoint between the source-layer offsets and
   raster bounds, position the right-column dot boxes at `right: 8px` and the
   left-column boxes at `right: 16px`; the upper row uses `top: 6px` and the
   lower row `top: 14px`. The four marks share a larger accessible hit area.
3. An optional title on the same header line, placed after the ordinal, using
   accent-colored Consolas Bold at approximately `20-24px`.
4. When a title exists, a horizontal 80%-white divider below a header about
   `54px` high. Untitled cards do not reserve an empty title header.
5. A content body that uses approximately `30-40px` horizontal padding when it
   contains normal settings or metrics. Deliberately edge-aligned graphs may
   use a narrower documented inset.

At the reference content width, `1x`, `2x` and `4x` cards are approximately
`375px`, `790px` and `1610px` wide and `166px` high for the base single-row
variant. Height is a content-driven minimum, not a maximum. A card MUST grow or
scroll internally according to its content contract; it must not clip controls
to preserve the reference height.

For the `790x166px` untitled metric-card reference, the exact component-local
ledger is:

| Element | Reference measurement |
| --- | --- |
| Card | `width: 790px; height: 166px; background: #000000; border: 1px solid #FFFFFF` |
| Ordinal | `left: 10px; top: 10px; 14px Consolas Bold; rgba(255,255,255,.80)` |
| Metric title | `left: 37px; top: 36px; 24px Consolas Bold; color: --accent` |
| Metric value | same `left: 37px`; `top: 89px`; `24px Consolas Bold; color: #FFFFFF` |
| Progress track | full card width; border-box `height: 9px`; attached to `bottom: 0`; `1px #FFFFFF` outline |
| Progress fill | `height: 9px`; accent width proportional to the clamped percentage |

At `50%`, the reference fill is approximately `392px` inside the `790px`
bordered track. The `37px` text inset, `10px` ordinal inset, dot grid and `9px`
progress height remain component-local when a card moves or the main layout
reflows.

Cards placed directly on the page use a 100%-white outline. Cards placed inside
another bordered section use an 80%-white outline, and all further nested card
outlines remain at 80%. A title divider is always inside the card and therefore
uses `--line-inner` at 80%-white. A top-level titled card consequently has a
100%-white outer border and an 80%-white divider; when the card itself is
nested, both its outer border and its divider remain at 80%.

The simple drag-mark variant uses four filled `#D9D9D9` circles. The outlined
variant used by nested Settings cards preserves the same `4px` mark footprint
but renders the source's inner circle at `r=1.5px`, `fill: #D9D9D9`, with an
80%-white stroke. Hover changes either variant's visible dots to `#FFFFFF`.

The drag handle means the card is reorderable. During dragging, a placeholder
with the same `1x`, `2x` or `4x` span shows the exact future geometry and the
rest of the grid reflows live. Drop persists order, recomputes ordinals and
preserves the result across reload and login. If a card is not reorderable, the
four-dot handle MUST be omitted rather than shown disabled without explanation.

### 5.3 Dashboard

The visual reference is [example dashboard](<./src/example dashboard.png>).
Every service dashboard MUST begin with these four operator-health cards:

| Card | Required information | Preferred visualization |
| --- | --- | --- |
| CPU Usage | Current percentage and logical core count | Accent progress line when percentage is known |
| RAM Usage | Current percentage and used/total capacity with unit | Accent progress line |
| Disk Usage | Current percentage and service-usable occupied/total capacity for the relevant service volume, calculated from `bavail` | Accent progress line |
| Uptime | Explicit active duration of the current service instance, never host uptime | Text; no meaningless progress line |

Disk telemetry MUST query the filesystem that contains the service's
authoritative persistent data, not an unrelated container overlay or host root
filesystem. For a POSIX `statvfs` result, calculate the displayed values from
blocks available to the unprivileged service identity:

```text
total_bytes = f_blocks * f_frsize
available_bytes = f_bavail * f_frsize
used_bytes = total_bytes - available_bytes
usage_percent = used_bytes / total_bytes * 100
```

`f_bfree` MUST NOT replace `f_bavail`: blocks reserved for a privileged user are
not writable by the service and therefore count as unavailable in its
Dashboard. Guard a zero or invalid `f_blocks`, clamp only the rendered
percentage to `0-100%`, preserve the raw diagnostic internally and render an
explicit unavailable/stale state instead of a fabricated value.

Uptime is measured with a monotonic clock from the start of the currently
running application/service process. It resets when that service process,
container or deployed instance restarts, even if the host did not reboot. Host
boot age, `/proc/uptime`, reverse-proxy uptime, database uptime and Updater
uptime MUST NOT be substituted. In a multi-process service, the Dashboard uses
the uptime reported by the active operator-facing service/API instance and
labels any separately shown worker uptime explicitly.

At the reference desktop width, CPU and RAM form the first two `2x` cards; Disk
and Uptime form the next two `2x` cards. Additional service-specific cards may
use `4x`, `2x` or `1x` spans below them. This row arrangement may collapse on a
narrow container but the logical order remains CPU, RAM, Disk, Uptime, then
service-specific information.

With the sidebar fixed open on the `1919x1034px` export, exact global card
coordinates are:

| Reference item | Left | Top | Width | Height |
| --- | ---: | ---: | ---: | ---: |
| CPU Usage (`01`) | `280px` | `151px` | `790px` | `166px` |
| RAM Usage (`02`) | `1100px` | `151px` | `790px` | `166px` |
| Disk Usage (`03`) | `280px` | `347px` | `790px` | `166px` |
| Uptime (`04`) | `1100px` | `347px` | `790px` | `166px` |
| Optional full-width card (`05`) | `280px` | `543px` | `1610px` | `166px` |
| Optional `1x` card (`06`) | `280px` | `739px` | `375px` | `166px` |
| Optional `1x` card (`07`) | `695px` | `739px` | `375px` | `166px` |

The `2x` column origins differ by `820px`: `790px` width plus a `30px` gap.
Successive dashboard row origins differ by `196px`: `166px` height plus a
`30px` gap. The two shown `1x` origins differ by `415px`: `375px` width plus a
`40px` nested gap. CPU/RAM/Disk/Uptime are semantic examples attached to the
required operator-health cards; the coordinate system is not a route-specific
absolute-position implementation.

A dashboard contains information that is important immediately on entry,
requires continuous observation or supports a frequent operator decision. It
MUST NOT become a catalogue of values available elsewhere. Titles use accent,
metric values use Consolas Bold and units remain visible. Unknown, stale and
unavailable data use explicit text and MUST NOT be rendered as `0`.

All dashboard cards are reorderable unless a documented safety reason fixes a
card. Order persists across reload and login, and ordinals always reflect the
current order. The rule in section 6.1 that combines collection-bar metrics
does not apply to dashboard cards.

### 5.4 Confirmation And Notices

Deletion, revocation, deny-listing and restore operations require a custom
confirmation that states:

- which resource is affected;
- whether the effect is local or global;
- what remains installed or stored elsewhere;
- whether identity data is revoked or denied;
- whether and how the operation can be reversed.

Native browser `confirm()` and `alert()` are not acceptable finished UI.

The notice stack is fixed `18px` from the top and right, with width
`min(410px, calc(100vw - 36px))`. Show at most five notices. Success,
information and error use their semantic borders and explicit text. Success and
information may dismiss after `4.5s`; errors remain about `8s`. Every accepted
mutation shows pending feedback and a final outcome.

### 5.5 Settings Information Architecture

The references are [example settings main](<./src/example settings main.png>),
[example settings backup](<./src/example settings backup.png>),
[example settings updates](<./src/example settings updates.png>) and
[example settings logs](<./src/example settings logs.png>).

When a service integrates shared backup or messaging agents, the specialized references are
[Backup](<./src/backup.png>), [Bot connection](<./src/bot connection.png>) and
[Updates](<./src/updates.png>). Their concrete states, controls and ownership
boundaries are defined in
[Service Agents: UI And Operator Workflows](./PART_10_SERVICE_AGENTS_UI_AND_OPERATOR_WORKFLOWS.md).

Settings is a primary destination and every service provides these full-width
`4x` sections:

1. Appearance.
2. Security.
3. Backup.
4. Updates.
5. Logs.

Additional sections follow according to service responsibilities. Sections use
the universal titled-card anatomy, may be reordered by their four-dot handle,
persist order and recompute their two-digit ordinals. Each section contains
small named groups. Security, persistence and external behavior controls
include a concise consequence or recovery hint.

The supplied Settings main template has these exact global measurements at the
reference viewport:

| Element | Reference geometry or text origin |
| --- | --- |
| Page title | `left: 280px; top: 15px; font-size: 80px` |
| Appearance section | `left: 280px; top: 153px; width: 1610px; height: 401px` |
| Appearance header divider | horizontal `1px` 80%-white line at `top: 208px` |
| Appearance ordinal `01` | `left: 294px; top: 175px; font-size: 14px` |
| Appearance title | `left: 319px; top: 168px; font-size: 24px` |
| Color correction heading | `left: 319px; top: 236px; font-size: 20px` |
| Color correction description | `left: 319px; top: 269px; font-size: 14px` |
| Security section | `left: 280px; top: 581px; width: 1610px; height: 418px` |
| Security header divider | horizontal `1px` 80%-white line at `top: 636px` |
| Security ordinal `02` | `left: 294px; top: 603px; font-size: 14px` |
| Security title | `left: 319px; top: 596px; font-size: 24px` |
| Changing Access Key heading | `left: 319px; top: 664px; font-size: 20px` |
| Changing Access Key description | `left: 319px; top: 697px; font-size: 14px` |
| Access Key overlay invoker | `left: 319px; top: 735px; width: 326px; height: 40px` |
| Access Key invoker label | measured at `left: 392px; top: 748px; font-size: 14px` |
| Control-plane connection heading | `left: 319px; top: 823px; font-size: 20px` |
| Control-plane URL control | `left: 317px; top: 858px; width: 326px; height: 40px` |
| Control-plane URL value | `left: 332px; top: 871px; font-size: 14px` |
| Control-plane reachability row | `left: 665px; top: 858px; width: 1185px; height: 39px` |
| Control-plane reachability label | `left: 682px; top: 871px; font-size: 14px` |
| Reachability status text | right-side text origin measured at `left: 1644px; top: 871px` |
| Reachability square | `left: 1812px; top: 868px; width: 18px; height: 18px` |
| Control-plane-token rotation invoker | `left: 317px; top: 915px; width: 1532px; height: 40px` |
| Control-plane-token action label | measured at `left: 903px; top: 927px; font-size: 14px` |

The Access Key and control-plane-token rectangles are command/invoker controls in the
current security contract, even if an early source layer named them inputs.
They open the empty, focus-trapped overlays defined below and MUST NOT expose a
persisted secret inline. Positions are derived from section-local offsets in
production so reordered Settings sections retain the same internal geometry.

Ordinary settings apply immediately after the operator commits a control: a
toggle's change, a select's change or a validated text field's blur/Enter. This
does not mean sending every incomplete keystroke. There is no page-level Save
button. A pending state appears without moving the control; success becomes the
new confirmed value; failure restores the prior confirmed value and exposes a
recovery action.

Accent color is the sole exception. It previews immediately but persists only
after `Apply color`, as defined in section 2.1.

#### Appearance

Appearance contains:

- a color swatch linked to a text field containing a normalized six-digit hex
  value;
- `Reset color` and `Apply color` controls;
- the persisted sidebar mode: fixed open or auto-hide/reveal from the left
  activation edge.

In the reference Appearance section, the color row uses:

| Element | Exact global geometry |
| --- | --- |
| Swatch frame | `left: 322px; top: 307px; width: 40px; height: 40px` |
| Color swatch | `left: 330px; top: 315px; width: 24px; height: 24px` |
| Hex field | `left: 382px; top: 307px; width: 326px; height: 40px` |
| Hex text | `left: 401px; top: 320px; font-size: 14px` |
| Reset color | `left: 728px; top: 307px; width: 123px; height: 40px` |
| Reset label | `left: 747px; top: 320px; font-size: 14px` |
| Apply color | `left: 871px; top: 307px; width: 123px; height: 40px` |
| Apply label | `left: 890px; top: 320px; font-size: 14px` |
| Sidebar-mode heading | `left: 319px; top: 411px; font-size: 20px` |
| Sidebar-mode description | `left: 319px; top: 444px; font-size: 14px` |
| Checkbox frame | `left: 322px; top: 482px; width: 20px; height: 20px` |
| Checkbox selected mark | `left: 327px; top: 487px; width: 10px; height: 10px` |
| Checkbox label | `left: 354px; top: 486px; font-size: 14px` |

The color field accepts exactly `#RRGGBB`, normalizes case for display, rejects
invalid or incomplete input without changing the persisted token and previews
only a valid value. Black, white, hover, success and danger are not editable.

#### Security And Control-Plane Connection

The Access Key is changed only in a custom overlay containing the current key,
the new key and confirmation of the new key. All fields begin empty. The action
checks the current key, requires two exactly matching explicitly supplied new
entries, rotates the server-side verifier atomically and revokes every other
active browser session. It performs no length, composition, character-set,
strength, entropy, breached-password, example-value or placeholder-value check
and does not trim or normalize either entry.
The current field uses `autocomplete="current-password"`; both new-key fields
use `autocomplete="new-password"`. The UI never reveals either stored verifier
or current key.

The control-plane connection group contains:

- an editable control-plane base URL or authority URL;
- the resolved public control-plane identity or role when available;
- explicit reachability using the shared semantic status pattern;
- a full-width action to rotate the secure control-plane access token.

The control-plane URL is non-secret. The `.env` value is an initial first-start seed;
after initialization, the authenticated server-side setting is authoritative.
A committed URL is normalized and validated before atomic activation. If the
new control plane cannot be validated, the previous confirmed endpoint remains active
and the failure is shown.

The control-plane token is a write-only secret. Its overlay accepts a replacement but
never preloads, echoes or returns the current token. The server stores it in the
approved secret boundary, validates it against the selected control plane, activates
it atomically only after success, audits the rotation without the value and
keeps or restores the previous credential when validation fails.

#### Backup

`Create and download snapshot` starts one pending-safe operation that creates a
fresh logical ZIP archive and begins its same-origin download as soon as the
archive is ready. It does not create an invisible server backup and require a
second unrelated download action. The final notice reports filename, creation
time and failure recovery without exposing archive contents.

`Restore snapshot` opens the custom restore overlay. A button inside invokes
the native local file picker. After selection, the overlay shows sanitized
filename, declared format/version and bounded size, then requires the restore
confirmation defined in section 5.4. Validation, progress, success and rollback
failure stay in that overlay. Detailed archive and transaction requirements are
defined in [Part 03](./PART_03_BACKUP_AND_RECOVERY.md).

Backup-agent-aware services append the local agent status and contextual
initialization/repair action defined by the service-agent UI guide. Automatic
schedules and explicit remote runs remain in the central synchronization workspace; a module
Backup card MUST NOT expose a second schedule authority.

#### Updates

The Updates section shows the installed version plus reachability of the local
updater and approved release registry. `Check for updates` opens a custom
overlay and starts verified discovery. The overlay distinguishes checking,
up-to-date, confirmed update available, offline/last-known-good and verification
failure.

If a platform is updated only by an external package manager or administrator,
the Updates section still exists and names that authoritative mechanism,
installed version and last verification time. It omits or disables local Apply
with an explicit explanation; it MUST NOT simulate a local updater.

When a newer confirmed version exists, the same overlay shows its version,
publication information, release notes, compatibility and backup readiness,
then exposes the explicit update-initiation button. Merely discovering a
release never starts installation. Detailed trust, rollback and machine-state
requirements are defined in [Part 05](./PART_05_CI_RELEASES_AND_LOCAL_UPDATES.md).
The main-module update, local update-helper self-update and shared-agent component update
paths are labeled separately and never share an ambiguous Apply action.

#### Logs

The Logs section is a bounded real-time stream with columns for type, body and
local time. Information/success labels use `#62FF8C`; error/denied labels use
`#F83D3D`; every outcome is also written as text. New rows append without
changing column geometry, unbounded client history is never accumulated and
the view pauses or resynchronizes safely when hidden or disconnected.

`Download archived logs` creates and downloads a timestamped ZIP while keeping
Settings open. Detailed retention, redaction, pagination and archive rules are
defined in [Part 02](./PART_02_OBSERVABILITY_AUDIT_AND_LOG_EXPORT.md).

Within the `1610x399px` cropped Logs reference, exact measured coordinates are:

| Log element | Template-local measurement |
| --- | --- |
| Header text (`TYPE BODY ... TIME`) | `left: 55.69px; top: 149px; 14px Consolas Bold` |
| Type tag | `left: 55.69px`; success/info green or error red |
| Body cell | `left: 123.41px; width: 1304.44px`; 80%-white |
| Time cell | anchor `left: 1567.22px; width: 564.37px; transform: translateX(-100%)`; right aligned |
| Consecutive row origins | `25px` step, demonstrated by `top: 198px` then `223px` |
| Table outline and header divider | `left: 39px; width: 1540px`; `1px` 80%-white lines |

Fractional coordinates are accepted output from the source layout. CSS may
retain them or obtain equivalent device-pixel rasterization through flexible
track calculation; it MUST NOT accumulate a visible drift across rows.
Data rows do not have horizontal row dividers; rhythm is provided by the `25px`
row-origin step.

### 5.6 Search

Search is a rectangular toolbar unit, not a floating rounded box. Filtering is
immediate, case-insensitive and client-side when the complete bounded dataset
is already loaded. It matches the visible label plus stable identifiers and
descriptive metadata appropriate to that view. Search does not create audit
events or success notices.

An empty query restores the current list. No-match state remains muted and
does not hide the create action.

Every editable search field MUST contain a dedicated clear-query control at
its inline end, inside the field border. The control is shown only while the
query is non-empty; the empty state removes it from the tab order. Use the
shared close/cross icon rather than a text letter, center the visible glyph in
a platform-minimum hit target and keep the same interior end inset as the
field's other horizontal padding. The input permanently reserves enough
inline-end padding for that hit target, so text, selection and the clear
control never overlap and the field does not reflow when the control appears.
Use logical inline positioning so right-to-left layouts place it correctly.

Pointer or keyboard activation clears the complete query, emits the same
filter update as ordinary input, restores the unfiltered current scope and
keeps focus in the search field. `Escape` MAY perform the same clear action
when the query is non-empty. The control has a localized accessible name such
as `Clear search`, exposes disabled/read-only state correctly and receives the
normal accent hover/focus treatment without resizing the field. Normalize or
hide a browser's native search-cancel decoration when it would duplicate the
application control.

The search field belongs to the collection command bar defined in section 6.
It MUST NOT scroll away while the collection below it continues scrolling.

### 5.7 Documentation View

Documentation is a normal application view, not a modal. On desktop it uses a
left navigation column of about `220px` and a flexible article column. The
navigation is sticky and begins with immediate search over headings and body
text.

The canonical desktop composition is shown in
[documentation_example](./src/documentation_example.png) and specified in
section 10.7. Product identity, article copy and the raster's missing accent
states are placeholders; the shared shell, palette and interaction rules in
this document still apply.

The article column uses `24px 32px 64px` padding, restrained heading sizes,
bordered code blocks, collapsed-border tables and accent-left notes. At about
`1000px`, documentation navigation stacks above content and article padding
reduces to `20px`.

Services may change article content and domain examples, but not the shared
layout, search behavior, typography hierarchy or responsive contract.

The Documentation view is a versioned operator surface, not a manually updated
afterthought. A change to an operator-visible workflow, navigation destination,
setting, action, permission, limit, status, error, backup/restore procedure or
update behavior MUST update the corresponding internal article in the same
outgoing revision. Renamed and removed behavior must update or remove stale
terms, anchors, screenshots and instructions.

Before every push, the Documentation impact check MUST finish as `PASS` or as a
reasoned `N/A` under the central pre-push gate. For an affected change, `PASS`
requires:

- article content that matches the outgoing implementation and names defaults,
  prerequisites, consequences, failure states and recovery where relevant;
- synchronized navigation order, article identifiers, heading/search index and
  cross-links;
- a successful documentation build/render and broken-link check;
- a search check proving that the changed topic is discoverable by its current
  UI label and important operator terminology;
- removal or explicit versioning of instructions that no longer apply.

Internal Documentation content and service technical documentation have
different audiences. Updating one does not satisfy the required review of the
other; [Part 06](./PART_06_UNIFIED_ACCEPTANCE_CHECKLIST.md#411-mandatory-pre-push-integrity-and-documentation-gate)
defines both pre-push checks.

## 6. Sticky Collection Command Bars

Any page or menu that filters, creates, summarizes or changes a collection has
one command bar immediately above that collection. Search MUST NOT be rendered
as a list item, placed below the first records or separated from related
commands by an unrelated panel.

### 6.1 Content And Order

When present, controls appear in this left-to-right order:

1. Search or filter input.
2. Collection information, such as item count, active revision, checksum,
   selection count or synchronization state.
3. Primary collection action, normally create or add.
4. Secondary collection actions, such as history, import, export or bulk edit.

Search, information and actions share one horizontal line and one visual
height. Do not put a create button at the bottom of a long list when it is a
page-level action. Row-specific actions remain inside their own rows.

If several metrics are required, combine them inside one information unit
rather than turning each number into a separate card. The most important
primary action stays visible without opening an overflow menu. This rule is
limited to a collection command bar; it does not combine the mandatory CPU,
RAM, Disk and Uptime dashboard cards defined in section 5.3.

### 6.2 Reference Geometry

The proven desktop geometry is:

```css
.collection-command-bar {
  display: grid;
  grid-template-columns:
    minmax(240px, 1fr)
    minmax(250px, auto)
    auto
    auto;
  align-items: stretch;
  gap: 12px;
}

.collection-search,
.collection-information {
  min-width: 0;
  border: 1px solid var(--line-inner);
  padding: 10px 12px;
}

.collection-list {
  margin-top: 14px;
}
```

The search unit is a two-column grid: a short uppercase or title-case prefix
and `minmax(0, 1fr)` input separated by `12px`. The inner input has no second
border; the toolbar unit provides the boundary. Base controls remain at least
`36px` high.

If the information unit has a primary value and subordinate digest or count,
use two columns with `4px 14px` gaps and let the subordinate line span both
columns. The primary value uses the accent color; labels and secondary values
are muted.

### 6.3 Sticky Behavior

The command bar is attached to the top of the list's scrolling context:

```css
.collection-command-bar {
  position: sticky;
  top: var(--collection-sticky-offset, 0px);
  z-index: 20;
  background: var(--black);
}
```

- The sticky offset equals the height of any persistent application header
  inside the same scrolling container. Do not guess a viewport offset when an
  ancestor is the actual scroll owner.
- The bar remains visible from the first row to the final row.
- Its opaque background prevents list text from showing through.
- Add bottom padding or the existing `14px` list gap so content never touches
  the bar while scrolling.
- Sticky behavior MUST be tested inside the real overflow ancestor. An
  ancestor with an accidental `overflow: hidden`, transform or insufficient
  height can silently break it.
- Focus, autocomplete and dropdown menus from the bar render above list rows
  but below global dialogs and notices.
- Filtering preserves scroll only when the current position remains valid;
  otherwise return the list to its first result.

On ordinary desktop and tablet widths the units stay on one line. At a width
where the four minimum columns cannot fit, a product may enter an explicit
mobile mode: hide non-essential secondary metadata, shorten secondary actions
to accessible icon buttons, or wrap the complete bar into two controlled rows.
The bar remains one sticky unit, search stays first and the primary action
never moves below the collection.

### 6.4 Behavioral Rules

- Filtering is immediate for a bounded local dataset; remote filtering is
  debounced, cancellable and announces loading and result count.
- The count describes the filtered set and, when useful, also the total, for
  example `18 of 240`.
- Clearing search restores the canonical order.
- Reordering is disabled while a filter changes the visible order unless the
  product defines an unambiguous filtered-reorder contract.
- Search input does not create audit events. Create, import, bulk edit and
  order persistence do.
- Empty and error states render below the command bar, so recovery controls
  remain available.
- The bar receives a semantic search landmark or toolbar label, and every
  control remains keyboard reachable.

## 7. Embedded Node-Canvas Editors

A node canvas is appropriate when spatial relationships, directional links,
ordered processing or containment communicate more than a table can. It is
not a replacement for an ordinary form, list or dependency report.

The reference architecture is a reusable node-editor framework embedded by a
host application in a restricted visual-only profile. The host owns identity,
authorization, persistence, revision history and notifications. The editor
owns world-coordinate interaction, graph editing and serialization.

### 7.1 Layered Architecture

Keep these boundaries separate:

| Layer | Responsibility |
| --- | --- |
| Project model | Versioned schema, stable IDs, geometry, membership, connections and annotations |
| Command/history layer | Atomic mutations, undo/redo, copy/paste, duplicate and delete |
| Type and node registry | Allowed node definitions, parameters, ports and compatibility |
| Canvas UI | Rendering, selection, pan/zoom, drag, resize, library, inspector and overlays |
| Embed adapter | Mount/destroy lifecycle, mode, theme tokens and host callbacks |
| Host application | Authentication, API loading/saving, checksums, revisions, restore and audit |
| Optional runtime | Scheduling, execution, assets, timeline and telemetry only when the product executes graphs |

The saved project remains data, never serialized DOM. At minimum it contains
format and schema versions, metadata, settings, viewport, background, nodes,
containers, groups, connections and annotations. Optional presets and assets
are included only when enabled. Every reference uses a stable ID rather than a
screen label or array index.

### 7.2 What To Keep And What To Remove

For a visual architecture or topology editor, retain:

- world-coordinate pan, cursor-anchored zoom, fit-all, fit-selection and return
  to origin;
- an optional hierarchical grid and snapping for nodes, containers and groups;
- selection, marquee selection, multi-element movement, resize and keyboard
  editing shortcuts;
- a library containing only allowed domain node types, empty containers and
  approved presets;
- typed or decorative connections, explicit routing and arrow direction when
  relationships need them;
- containers for visible ordered membership and groups for loose spatial
  organization;
- text and geometric annotations;
- inspector, context menu, minimap and visibility toggles when they support the
  actual use case;
- schema validation, unresolved-node handling, canonical serialization and
  viewport culling;
- host callbacks for save, project-change reason and lifecycle cleanup.

Remove or disable in a visual-only embedding:

- run, stop, queue, execution status and backend selection;
- scheduler, worker, GPU and host-execution adapters;
- timeline, frame controls and streaming/backpressure settings;
- resource telemetry and runtime dashboards;
- generic executable node packs that are outside the host domain;
- asset import and media preview when the map does not use media;
- standalone multi-project tabs, filesystem open/save and export UI when the
  host API owns one authoritative project;
- machine-control APIs, plugin installation and any path that executes dynamic
  code.

If the shared schema requires optional execution or timeline fields, keep
inert validated defaults in serialized data while removing their UI and runtime
side effects. Do not create a divergent private schema merely to hide controls.

### 7.3 Embedding Contract

The host initializes the editor only after loading and validating the project.
It supplies:

- `embedded-edit` or `embedded-readonly` mode;
- `visual-only` capability when execution is forbidden;
- an allow-list of domain node definitions;
- whether the framework's generic node library is registered;
- theme tokens compatible with the host shell;
- save and project-change callbacks.

The reference visual profile registers one descriptive text-node family,
disables the generic node pack and enables visual-only mode. A registry may
still require a no-op implementation for structural validation; the editor
MUST make it unreachable because UI hiding alone is not an authorization
boundary.

Mount and destroy are paired. Destroy cancels listeners, observers, telemetry,
animation and pending work. Recreating an editor without cleanup is a memory
and input-handler leak.

### 7.4 Canvas Navigation And Editing

- Wheel zoom is anchored under the pointer and clamped. The demonstrated
  editor uses a broad `0.05` to `8` range.
- Hold Space and drag, or use the middle button, to pan.
- Fit commands use all visible graph bounds plus approximately `96px` padding.
- Origin returns the viewport center to world origin without changing domain
  data.
- Double-clicking empty canvas may open the library at the pointer. A keyboard
  shortcut offers the same action.
- Marquee drag selects. Shift adds or removes items. Dragging any selected item
  moves the selection as one transaction.
- Copy, cut, paste, duplicate, delete, bypass and undo/redo operate through the
  command layer, so internal connections and history remain consistent.
- Interactive fields stop pointer propagation; editing text must not begin a
  node drag.
- Right-click opens an element or connection menu at the pointer. Menus are
  clamped to the viewport and close after a command.
- Off-screen top-level elements are culled with a roughly `300px` screen-space
  safety margin. Selected and actively dragged elements are never culled.

Viewport movement is presentation state but may still be persisted so the map
reopens where the operator left it. It should use a slower save debounce than
structural edits.

### 7.5 Nodes, Containers, Groups And Connections

A node contains stable type ID and version, position, size, label, parameters,
ports, visual state and optional parent IDs. Rendering resolves its definition
from the registry. Unknown definitions remain visible as unresolved nodes with
their raw state preserved; never discard data merely because a plugin is
temporarily absent.

A container owns an ordered list of node IDs and aggregate input/output ports.
An embedded Open Node host MUST make every supported node definition that it
exposes in its library movable into a Container and back to the top level.
Containment changes layout, ordering and boundary routing; it MUST NOT reduce
the node's represented information or functional capability. The contained
renderer MUST preserve:

- a recognizable version of the node's visual identity, hierarchy, color and
  state;
- the primary content, values, validation state and meaningful port context;
- every operator action and editable control available on the full node,
  including file Open, Download and Upload/Replace actions where applicable;
- attached assets and all serialized node state without conversion or loss.

A compact layout MAY reflow controls or expose them through an explicit
contained-node expansion affordance, but it MUST keep them reachable without
temporarily removing the node from the Container. Replacing the real contained
view with a generic parameter summary is not conformant when that hides visual
or functional behavior. Moving a node into a Container, saving, reloading and
moving it back out MUST be a lossless round trip. An unresolved third-party
definition may remain visibly unresolved and non-insertable, but it is not a
supported library node for purposes of this requirement.

Dropping a compatible top-level node into it:

1. verifies the node definition declares container compatibility;
2. calculates insertion position from the pointer and visible slot midpoint;
3. removes the node from a spatial group;
4. sets the parent-container reference and inserts the ID once;
5. removes computational connections that cannot remain valid through the
   container boundary while preserving decorative relationships;
6. records the operation as one undoable transaction.

Because removing connections can lose semantic information, a general-purpose
editor SHOULD preview or confirm that effect when more than trivial visual
links are attached.

Contained nodes are displayed in a fixed-height compact card and can be
reordered with a live insertion line. The container's port positions track the
first and last visible slots. Collapsing a container hides its list but retains
membership and order.

A group is spatial rather than sequential. Membership is recalculated from
complete containment; when groups overlap, the smallest containing group wins.
Contained nodes are excluded because their container is the top-level spatial
member. Moving a group moves its current members together.

Connections store endpoints by element and port ID. Decorative connections use
normalized anchors so resizing preserves attachment. Computational connections
validate direction, kind, multiplicity and type compatibility before commit.

### 7.6 Proportional Compact-Node Geometry

Changing a node from top-level rendering to a contained preview MUST preserve
the proportion devoted to its primary content. Do not blindly apply the normal
three-column `inputs / parameters / outputs` layout to a text-dominant node.

The demonstrated geometry is:

- top-level text node: `360px` outer width and `30px` horizontal body inset,
  leaving about 83% for text;
- default container: `280px` outer width with `9px` list padding;
- contained card: approximately `262px` outer width;
- compact text body: one flexible column with `22px` horizontal inset, again
  leaving about 83% for text.

The portable rule is:

```text
content_ratio = editable_content_width / node_card_width
abs(compact_ratio - full_ratio) <= allowed_tolerance
```

Use a tolerance no larger than `0.12` in a geometry test. The field must then
scale continuously when the container is resized.

```css
.compact-node.is-text .compact-node-body {
  grid-template-columns: minmax(0, 1fr);
  padding-inline: 22px;
}

.compact-node.is-text .port-summary {
  display: none;
}

.compact-node.is-text .primary-parameter {
  width: 100%;
}
```

Hiding repeated per-node port labels is appropriate when the container already
represents sequential input/output and the text field is the dominant content.
For a node whose ports carry essential meaning, place compact port indicators
as non-sizing overlays or reserve a proportional, bounded inset; never let two
fixed side columns consume most of a narrowing card.

### 7.7 Persistence, Revisions And Concurrency

The host loads one canonical project, displays revision and checksum metadata,
and listens for change reasons. Structural changes may save after roughly one
second of inactivity; viewport-only changes use a longer debounce.

Only one save runs at a time. If another change occurs during the request, set
a queued flag and serialize the newest complete project after the active save
finishes. This prevents an older response from overwriting a newer edit.

Each accepted save creates an immutable revision with actor, reason, timestamp
and content checksum. Restore creates a new revision from a selected source; it
does not move the active pointer backward or erase later history. The UI shows
`Modified`, `Saving`, `Saved` and `Save failed` explicitly.

For multiple simultaneous editors, add optimistic concurrency through a base
revision or ETag. A debounce queue alone prevents local overlap but not
last-writer-wins loss between browsers.

### 7.8 Canvas Verification

- [ ] Visual-only mode has no reachable execution path.
- [ ] Only allow-listed node definitions appear in the library.
- [ ] Invalid schema, duplicate IDs and dangling references are rejected.
- [ ] Cursor-anchored zoom preserves the world point under the pointer.
- [ ] Selection, copy/paste and undo preserve internal connections.
- [ ] Container insertion and reorder preserve unique membership.
- [ ] Every supported library node can move into and out of a Container, and a
      save/reload round trip preserves its visual identity, complete state,
      controls, actions and attached assets.
- [ ] A contained text field keeps the full-node width ratio within `0.12` and
      follows container resizing.
- [ ] Text editing never starts drag or canvas pan.
- [ ] Autosave serializes overlapping changes and reports failure.
- [ ] Revision restore produces a new checksummed revision.
- [ ] Off-screen culling does not remove selected or dragged items.
- [ ] Destroying and remounting does not duplicate listeners or observers.

### 7.9 Browser-Backed Document Nodes

A visual canvas may need a second, non-executable node family whose purpose is
to attach source material to the diagram. Keep this node distinct from the
descriptive text node: text parameters belong to the graph model, while a
document node owns an asset reference and explicit file actions.

The reference profile supports four document families:

| Family | Accepted representation | Open behavior |
| --- | --- | --- |
| PDF | A file with a PDF signature and `.pdf` name | Open a short-lived `blob:` URL with the fixed `application/pdf` MIME type |
| Markdown | Valid non-empty UTF-8 text without null bytes and a `.md` name | Open as `text/plain;charset=utf-8`; do not add an application-specific renderer |
| Word document | A valid OOXML ZIP package with `.docx`, `[Content_Types].xml` and `word/document.xml` | Hand the fixed DOCX MIME type to the browser; the browser may open, delegate or download according to installed capabilities |
| Native graph project | A UTF-8 JSON document using the supported graph format and schema version | Parse and validate it, then open it in a separate editor tab without replacing the authoritative host project |

Do not promise that every browser renders every office format inline. The
portable contract is that **Open** delegates to the browser or an existing
editor capability, while **Download** always produces the original bytes with
a safe filename. A separate PDF, Markdown or office reader is unnecessary.

#### Node Definition And Visual Contract

Use a declarative capability tag such as `browser-document` instead of
hard-coding a host-specific node type inside the shared renderer. A recommended
definition has:

- one optional generic input and output when visual relationships are useful;
- one `file` parameter that stores an asset ID, not a platform path;
- an `accept` allow-list for PDF, Markdown, DOCX and the configured native
  graph-project suffixes;
- preview-sized default geometry, because file identity and three actions need
  more vertical room than a scalar parameter;
- no side effects and no reachable execution behavior in a visual-only host;
- container compatibility enabled only when the compact contained-node renderer
  preserves the same attached-file identity, type and size presentation and
  exposes Open, Download and Upload/Replace without clipping or substituting a
  generic parameter summary.

The node body has two states:

```text
EMPTY                           ATTACHED
+--------------------------+    +--------------------------+
| +  Attach a document     |    | FILE  architecture.pdf  |
|    PDF · MD · DOCX · ... |    |       PDF · 820 KB       |
| [ Upload ]               |    | [Open][Download][Replace]|
+--------------------------+    +--------------------------+
```

The filename is the primary label and is ellipsized with its full value in a
tooltip. The second line shows normalized type and size. Actions wrap rather
than overflow at the minimum width. Drag-and-drop and the Upload button invoke
the same import transaction. Read-only mode keeps Open and Download available
but disables Upload and Replace.

#### Import And Persistence Transaction

Treat import as one atomic command:

1. Enforce the byte limit before reading the file.
2. Read the browser `File` once. Copy `name`, `type` and `size` explicitly;
   these properties may live on the prototype and disappear during object
   spread.
3. Detect and validate the real content independently of the browser-supplied
   MIME type.
4. Compute a cryptographic checksum over the original bytes.
5. Create an asset reference with stable ID, safe original name, normalized
   MIME type, byte size, checksum and storage mode.
6. Persist the bytes and reference before assigning the asset ID to the node.
7. Replace the node's previous asset reference in the same graph mutation.
8. Remove the previous asset only when no other node references it.
9. Trigger normal autosave and show a visible success or validation message.

An asset registry that returns bytes from `import()` but retains only the
reference is incomplete: reload will leave a convincing node with a missing
file. Test persistence across a real host save and browser reload.

For small, portable diagrams, bytes may be embedded as canonical base64 inside
the versioned project. The demonstrated bounded profile uses a `4 MiB` per-file
limit and an `8 MiB` serialized-project limit. Base64 adds roughly one third to
the byte count, so the project limit must include that expansion plus graph
metadata. For larger assets, use content-addressed host storage and keep only a
checksummed, authorization-scoped reference in the project. Never silently
fall back from durable storage to an in-memory object URL.

Embedded storage simplifies backup and revision restore but duplicates bytes
across immutable revisions. Content-addressed storage reduces that duplication
but requires reference counting, garbage collection, authorization and backup
coverage. Choose the mode deliberately and document its recovery behavior.

#### Browser Open And Download Lifecycle

For an embedded asset, decode only after the operator presses Open or Download.
Create a `Blob` with a MIME type selected from the validated format enum, never
from mutable project metadata. Opening uses a new browser tab with no opener
relationship. Download uses an anchor with the `download` attribute and a
filename stripped of path separators and control characters.

Object URLs are capabilities and consume browser memory. Do not create them
during node render or retain them in serialized metadata. Revoke a download URL
immediately after dispatch. Keep an Open URL only long enough for the new tab to
load, then revoke it; also revoke all outstanding URLs on editor destruction.

Native graph projects are different from documents: decode JSON, validate the
format and supported schema again, create a new editor tab, and only then load
the project. Never replace the current authoritative graph before validation,
and do not execute imported nodes merely because their definitions exist.

#### Security Validation

The UI `accept` attribute is a convenience, not a security boundary. Repeat
validation at the authoritative save or upload endpoint:

- allow-list storage modes and reject remote HTTP assets unless the product has
  a separately designed fetch policy;
- require canonical base64 when bytes are embedded;
- compare decoded length with declared size and enforce both file and whole-
  project limits;
- require and recompute SHA-256, then reject a missing or mismatched checksum;
- bind each format enum to one fixed MIME type and allowed filename suffix;
- check `%PDF-` for PDF;
- decode Markdown with fatal UTF-8 validation and reject null bytes;
- verify ZIP magic and required OOXML members for DOCX;
- parse graph JSON and require both supported format and schema versions;
- reject HTML, SVG, JavaScript and arbitrary `data:` or remote URLs in this
  node profile.

Fixed MIME mapping is essential. Opening attacker-controlled bytes as
`text/html` from a same-origin `blob:` URL can turn a document feature into a
script-execution path. Content Security Policy remains defense in depth, not a
substitute for file validation.

#### Document-Node Verification

- [ ] The library exposes descriptive and document node families separately.
- [ ] Upload button and file drop use one validation/import function.
- [ ] PDF, UTF-8 Markdown, real DOCX and supported graph JSON are accepted.
- [ ] Renamed arbitrary ZIP, HTML, malformed JSON and over-limit files are
      rejected with visible errors.
- [ ] The attached filename, type, size, Open, Download and Replace survive
      host save and full browser reload.
- [ ] Moving an attached document node into or out of a container preserves its
      visual identity, original bytes and every file action; the compact card
      remains usable at the minimum container width.
- [ ] Downloaded bytes and checksum equal the imported file.
- [ ] Graph Open creates a separate validated editor tab.
- [ ] Replace removes an unreferenced old asset but preserves shared assets.
- [ ] Read-only mode disables mutation and retains safe Open/Download.
- [ ] No object URL is serialized; every created URL is eventually revoked.
- [ ] Server validation rejects forged MIME, size, checksum and storage mode.

## 8. Dependency Correlation Graphs

A dependency correlation graph answers a different question from an editable
node canvas. The canvas is an authoring surface; the correlation graph is a
derived projection of authoritative records. Operators move nodes to inspect
the layout, but dragging does not rewrite the underlying relationships.

### 8.1 Bipartite Data Model

The implemented pattern is a bipartite graph:

- entity nodes represent domain records or fixed overview blocks;
- property nodes represent reusable attributes from a shared library;
- an undirected visual edge connects a property to every entity where that
  property is placed;
- entity-to-entity and property-to-property edges are not generated.

The derivation algorithm:

1. Build the valid entity set from fixed blocks and current domain records.
2. Build a property map from the shared library.
3. Add property records found in placements even if the library is temporarily
   incomplete, without replacing the canonical instance.
4. For each valid entity, de-duplicate its placed property IDs.
5. Emit one edge from the namespaced property node ID to that entity ID.
6. Keep library properties with degree zero so the graph can expose unused
   definitions.

IDs for different node families MUST be namespaced before entering one map.
Labels are presentation only and may repeat.

### 8.2 Correlation Score

The displayed percentage measures reuse of properties across entities, not
graph density in the general graph-theory sense.

For `P` property nodes, `E` entity nodes and `c(p)` distinct entities using
property `p`:

```text
score = 100 / P * sum(max(0, c(p) - 1) / (E - 1))
```

Return zero when there are no properties or fewer than two entities. A
property used by only one entity contributes zero. A property used by every
entity contributes one before the final percentage conversion. Round the
result to two decimals and compute it on the server from de-duplicated stable
IDs; the client calculation is only a display fallback.

### 8.3 Persisted Structure

The reusable state consists of:

| Structure | Meaning |
| --- | --- |
| Description map | Text keyed by entity/block ID |
| Placement map | Ordered property records keyed by entity/block ID |
| Property library | Canonical reusable property records |
| Graph settings | Presentation and force parameters |

The server creates defaults when no state exists and merges missing graph
settings on read and write. The reference boundary rejects more than 5,000
library records or more than 10,000 placement-map keys. Those storage limits do
not imply that a browser can animate that many nodes.

The browser caches the same state locally for immediate continuity and queues a
server update about `350ms` after changes. Server state wins when it contains
authoritative property data; a non-empty local state may seed an empty server.
For a multi-user system, replace this implicit merge with revisioned optimistic
concurrency and an explicit conflict path.

### 8.4 Visual Composition

- The graph fills a bordered work area with height
  `calc(100vh - 78px)` and minimum height `520px`.
- The Canvas 2D element fills the area, disables browser touch gestures and
  uses grab/grabbing cursors.
- The backing bitmap uses device pixel ratio capped at `2` to preserve clarity
  without unbounded GPU memory.
- Background is the configured dark surface.
- Links are straight, use a 50%-white visualization stroke and render at `0.72`
  global alpha.
- Entity circles use the accent color by default. Property circles use white.
  Empty color overrides mean “follow the current theme”.
- A node's radius is the configured base multiplied by connection growth:
  `1 + min(0.25, sqrt(degree) * 0.06)`. Highly connected nodes are therefore at
  most 25% larger.
- Labels use an `11px` monospace screen-space size and start just to the right
  of the circle. Label opacity is `1 - text_fade`.
- The graph score is fixed `14px` from the top and left, accent-colored,
  `18px`, bold and non-interactive.
- A two-item legend identifies the node families by text and color.

Labels currently have no collision avoidance, wrapping or truncation. A port
to dense production data SHOULD add hover detail, bounded labels and a
decluttering strategy rather than drawing thousands of overlapping strings.

### 8.5 Control Panel

The control panel is an overlay at `top: 12px; right: 12px`, width
`min(280px, calc(100% - 24px))` and maximum height
`calc(100% - 24px)`. It uses a middle border, `12px` padding and gap, 94%-dark
translucent fill, `8px` backdrop blur and internal scrolling with a hidden
visual scrollbar.

It starts collapsed. Only a full-width Expand/Collapse button remains visible;
display controls, force controls and legend are hidden. Expanded sections use
`10px` top padding, a structural divider and `8px` internal gaps. At narrow
widths the panel maximum width reduces to `260px`.

Every range control displays its current numeric output and updates the graph
immediately. Color controls include Reset, which clears the override and
returns to the live theme rather than copying today's theme hex value.

### 8.6 Settings And Defaults

| Setting | Default | UI range and step | Actual effect |
| --- | ---: | --- | --- |
| Property color | Theme white | Color plus reset | Fill of property nodes; empty value tracks theme |
| Entity color | Theme accent | Color plus reset | Fill of entity nodes; empty value tracks theme |
| Text fade | `0.15` | `0-1`, step `0.05` | Constant label opacity is `1 - value`; `1` hides labels |
| Node size | `6` | `2-18`, step `1` | Base world-space circle radius before degree growth |
| Link thickness | `1` | `0.5-6`, step `0.5` | Screen-space line width |
| Animate | enabled | Checkbox | Enables or pauses force integration |
| Center force | `0.006` | `0-0.05`, step `0.001` | Pull toward world origin on each step |
| Repel force | `1800` | `0-3000`, step `50` | Pairwise inverse-square repulsion |
| Link force | `0.025` | `0-0.15`, step `0.005` | Spring correction toward desired distance |
| Link distance | `150` | `30-300`, step `5` | Desired world-space edge length |

“Text fade” is not a zoom threshold in the reference algorithm; it is a direct
opacity control. Name it `Label opacity` or implement true zoom-dependent fade
in a new system so the label matches behavior.

UI range attributes are not server validation. Persisted settings MUST use a
typed schema that rejects non-finite numbers, clamps or rejects values outside
the documented ranges and ignores unknown fields deliberately.

### 8.7 Initial Layout And Force Simulation

Initial positions are deterministic from stable IDs. Two independent hashes
select polar angle and a radius beginning at `80` and growing with the square
root of node count, capped by a `360`-unit spread contribution. Rebuilding the
graph reuses current position and velocity for IDs already present, reducing
visual jumps.

Each animation step applies:

1. Pairwise inverse-square repulsion with a minimum squared distance of `64`.
2. A spring on every link proportional to
   `(current_distance - desired_distance) * link_force`.
3. Center force proportional to distance from origin.
4. Velocity damping by `0.82`.
5. Position integration for every node except the node currently dragged.

Dragging writes the pointer's world position directly and zeroes velocity.
After release, the node is not pinned; forces may move it again. If persistent
manual layout is required, add explicit pinned coordinates to the authoritative
presentation state rather than confusing temporary drag position with saved
domain relationships.

### 8.8 Navigation And Hit Testing

- Pointer down uses reverse paint order and selects a node within its visual
  radius or at least a `12px` screen-space hit radius.
- Dragging a hit node moves it. Dragging empty space pans by client-pixel delta.
- Wheel zoom is clamped from `0.25` to `4`.
- Double-click resets pan and zoom to `{x: 0, y: 0, scale: 1}`.
- ResizeObserver rebuilds the backing bitmap and redraws at the new size.

The reference correlation view zooms around the canvas center. A new
implementation SHOULD use cursor-anchored zoom for consistency with the
authoring canvas, unless centered zoom is an intentional product rule.

The derived graph currently has no keyboard node navigation, selection state,
tooltip or open-details action. If it becomes more than a passive visualization,
provide an accessible parallel table, keyboard traversal or a semantic list of
relationships. Canvas pixels alone do not form an accessibility tree.

### 8.9 Performance And Lifecycle

Pairwise repulsion is `O(N^2)` per animated frame. It is suitable only for a
bounded moderate graph. Storage limits in the thousands are far above a safe
interactive force-layout limit.

A scalable port MUST:

- define a separately measured render/animation node cap;
- move layout to a worker or use a Barnes-Hut/quadtree approximation above the
  small-graph threshold;
- stop requesting frames when the view is hidden;
- use invalidation-based drawing when animation is disabled;
- avoid rebuilding data for presentation-only changes;
- cap label work and consider level-of-detail rendering by zoom;
- cancel animation and ResizeObserver on teardown.

The reference loop skips physics while the view is inactive but continues
requesting and drawing frames. Treat that as an optimization gap, not a pattern
to reproduce.

### 8.10 Dependency Graph Verification

- [ ] Node families and IDs cannot collide.
- [ ] Duplicate placement does not create duplicate edges.
- [ ] Invalid or deleted entities do not leave dangling edges.
- [ ] Degree and the correlation score use unique entity/property pairs.
- [ ] Server and client score agree for empty, single-use, partially shared and
      fully shared fixtures.
- [ ] All settings load defaults, persist, reset to theme and validate ranges.
- [ ] Deterministic initial positions are stable across reloads.
- [ ] Pan, zoom, drag, reset and high-DPI resize behave correctly.
- [ ] Animation off produces no physics movement and no unnecessary redraw
      loop.
- [ ] The measured graph cap keeps frame time within the product budget.
- [ ] A non-canvas accessible relationship representation is available.

## 9. Responsive And Accessibility Rules

Responsive behavior is based on available component width, not a user-agent
string. The primary desktop acceptance views are approximately `1919x1030`
(the supplied exports are `1919x1034`) and `1920x1080`, each with the sidebar
fixed open and fully hidden. Both states MUST be free of overlap, clipped text,
unexpected horizontal scroll and reordered reading content.

- At full reference width with the `250px` sidebar open, the main content has
  exactly `1610px` between its `30px` horizontal insets and therefore
  produces the canonical `4x`, `2x` and `1x` card widths.
- Closing the sidebar gives the extra width to the main grid. Cards expand or
  reflow through normal layout; they do not retain stale absolute coordinates.
- Below the reference content width, card tracks are fluid. When a `2x` pair
  cannot preserve readable content, it becomes one column before controls or
  values collide. At approximately `1000px`, multi-column work areas normally
  become one column.
- At `720px` and below, the sidebar becomes an explicit overlay opened by a
  labeled menu control. Main content no longer reserves `250px`.
- Forms and dense list rows collapse before text overlaps. Action order remains
  primary then secondary, and a destructive action never moves into the place
  of a routine primary action without clear labeling.
- Grid and flex children that contain text use `min-width: 0`. Fixed-format
  controls use `minmax()`, `aspect-ratio`, explicit bounds and deliberate
  overflow handling.
- A page title may shrink within its documented clamp but never overlaps the
  sidebar, divider, close action or first content row.
- Hover growth and focus outlines are included in overflow tests at every grid
  edge. Transform origins direct growth inward.
- Hide a visual scrollbar only when wheel, touch and keyboard scrolling remain
  available and the scroll position is not essential information.
- Every icon-only command, including the four-dot drag handle, has an accessible
  name and at least the platform's minimum hit target.
- Native interactive elements remain keyboard reachable. Reorderable rows and
  cards have a keyboard alternative that announces position changes.
- Status is expressed through text as well as color or animation. Green/red
  reachability, progress lines and blinking indicators are never the sole
  source of meaning.
- Reduced-motion mode disables non-essential scale, fade, sidebar movement and
  physics movement while preserving immediate state changes and focus.
- Contrast is rechecked after every valid accent preview and before persistence;
  an unusable accent is rejected with an explanation rather than saved.

Visual regression coverage MUST include the linked reference templates,
open/hidden sidebar transitions, all universal-card spans, both hover variants,
keyboard focus, context-menu edge clamping, overlay focus/viewport behavior and
Settings pending/error states.

## 10. Reference Template Catalogue

This catalogue makes every supplied image independently actionable. Dimensions
below are source-PNG dimensions. Shared tokens and behavior from sections 1-9
remain normative even when they are not repeated in every entry.

### 10.1 Shell, Navigation And Authentication Templates

#### [Example of left menu and main page side by side, base layer of main page, name of main page](<./src/Example of left menu and main page side by side, base layer of main page, name of main page.png>)

- Source canvas: `1919x1034px`.
- Purpose: canonical desktop shell with fixed-open sidebar and otherwise empty
  main workspace. It is a page-construction template, not a dashboard mockup.
- Sidebar: `250px` including its right `1px` white border. Main content begins at
  `x=250`.
- Main header: exactly `123px` high at the reference canvas with a level-one
  white bottom divider. The title starts at `left: 280px; top: 15px`, giving a
  `30px` main inset.
- Title: actual page name, accent `#00A8FF` by default, Space Grotesk Bold,
  `80px` in a measured `783x76px` reference box, one line where possible.
- Main body: black with no decorative frame. First content starts at the same
  `30px` horizontal inset and approximately `30px` below the header divider.
- Behavior: fixed-open, auto-hide and mobile-overlay sidebar modes use the same
  DOM/navigation order. When the sidebar hides, the main header divider and
  body expand to the left; the title and content recalculate from the new main
  region rather than retaining `x=280` as a fixed screen coordinate.
- Verification: compare open and hidden states at `1919x1034` and `1920x1080`;
  no seam, double border, stale blank column or horizontal scrollbar is allowed.

#### [example Left Menu](<./src/example Left Menu.png>)

- Source canvas: `250x1033px`; it represents the complete expanded sidebar.
- Background: `#000000`. The standalone crop omits the right boundary, while
  the combined page exports render it at `x=250`; production always uses the
  canonical `width: 250px; border-right: 1px` border-box contract.
- Brand zone: actual service icon in a `192x192px` box at `left: 31px; top: 6px`.
  The service name uses `42px` accent Space Grotesk Bold in a `170x76px` box
  centered on `x=125px` with `top: 175px`.
- Primary navigation begins with the active `221x42px` row at
  `left: 18px; top: 285px`. Labels start at `left: 31px`; adaptive ordinals at
  `left: 209px`; both use `14px` Consolas Bold. Exact row text origins are in
  section 4.2.
- Active row: `1px` accent rectangle, accent label and an external left arrow
  with rectangular base. The arrow points at the row center and must not change
  the row's measured width. The base is `4x22px` at `left: -2px; top: 295px`;
  the triangle is `12x5.77px` at `left: 0`, centered around `top: 306px`.
- Inactive row: transparent reserved border, white/80%-white text, black fill.
  Pointer hover applies the shared Hover 1/2 contract without moving adjacent
  rows.
- Reorder: all primary rows, including Settings, may move; drop preview is an
  accent before/after line. Ordinals recompute sequentially and order persists.
  The legacy `01, 02, 04, 05, 06, 07` values visible in the PNG are not valid
  production numbering.
- Bottom group: Documentation and Logout are left aligned, unnumbered, unboxed,
  unscaled and non-draggable. Their only pointer-hover color change is accent.
- Overflow: if translated off-screen in auto-hide mode, no focusable hidden
  navigation remains accidentally reachable; revealing it restores normal
  keyboard order.

#### [example Log in page](<./src/example Log in page.png>)

- Source canvas: `1919x1034px`; background is uninterrupted `#000000`.
- The combined brand and authentication panel is centered. The bordered panel
  is exactly `560x268px` at `left: 680px; top: 444px`, matching
  `min(560px, calc(100vw - 48px))` on narrow screens.
- Brand: actual service name in accent `72px` Space Grotesk Bold; actual service
  icon to its right in a `100x100px` box. Exact painted example bounds are in
  section 4.1.
  Both form one accessible brand heading/group despite separate visual items.
- Panel: level-one `1px` white outline, square corners, black fill, no shadow.
  Inner horizontal inset is approximately `24px`.
- Reachability block: compact bordered status at the top-left of the panel.
  It is `255x50px` at `left: 705px; top: 466px`. Reachable uses `#62FF8C`
  text/square and an 80%-semantic `#4ECC70` nested border with one smooth
  two-second fade cycle. Unreachable uses danger red and a static square.
- Form: exactly one empty masked Access Key control followed by one full-width
  `Enter service` button. The field is `511x31px` at `left: 705px; top: 578px`;
  the button is `511x50px` at `left: 705px; top: 635px`. Both use nested
  80%-white borders at rest.
- Interaction: Enter and button submit the same operation; pending disables
  duplicate submission without size change; rejection preserves the panel and
  never changes reachability state.
- Responsive: below `608px`, panel and brand fit within `24px` viewport insets;
  icon may reduce, but the Access Key control and button remain full width.

### 10.2 Hover-State Templates

#### [example - hover - no hover](<./src/example - hover - no hover.png>)

- Source canvas and base control box: `375x166px`, corresponding to a reference
  `1x` untitled universal card.
- Fill: `#000000`; outer border: `1px` structural white at the appropriate
  hierarchy level.
- Ordinal: two digits at `left: 10px; top: 10px`, `14px` Consolas Bold and
  80%-white.
- Drag handle: four `4x4px` `#D9D9D9` dots in the exact two-by-two geometry from
  section 5.2. The visible mark does not reduce the card's content width;
  content padding reserves its hit target.
- This rest state contains no accent merely because the card is reorderable.

#### [example - hover - hover 1](<./src/example - hover - hover 1.png>)

- Source canvas: `380x169px`. It shows the normal pointer-hover control box
  used by the historical mockup. Its dimensions are not the normative output of
  the current proportional-growth formula.
- Fill changes exactly to `#111111`; the element border becomes `#00A8FF` or
  the configured accent.
- Existing non-interactive content color is preserved; the four-dot handle
  remains white. Accent is carried primarily by fill/border in this variant.
- Production growth uses the short-side formula in section 3.1 and a `160ms`
  eased transform. For a `375x166px` card the computed box is approximately
  `383.3x174.3px`; it is composited and never updates grid width or height.
- At a grid boundary, transform origin turns inward so the accent border and
  content remain visible.

#### [example - hover - hover 2](<./src/example - hover - hover 2.png>)

- Source canvas: `388x177px`. In this historical mockup the inner card is
  `380x169px` at `left: 4px; top: 4px`; production keeps this visual anatomy but
  applies it around the formula-derived Hover 1 box.
- Fill is `#111111`; the element border and outer `1px` outline are accent,
  separated visually by approximately `3px` of black.
- The interactive label or ordinal becomes accent; the drag dots remain white.
- Use this as the keyboard-focus minimum and for an intentionally emphasized
  hover target. The outline is an overlay and MUST NOT enlarge layout bounds.
- Pressing either hover variant uses the canonical `scale(.985)`/`60ms` feedback;
  reduced-motion retains the color and outline changes without scaling.

### 10.3 Universal Card Templates

#### [universal card - 1x](<./src/universal card - 1x.png>)

- Source size: `375x166px`.
- Untitled `1x` anatomy: ordinal upper left, four-dot handle upper right, no
  header divider and one uninterrupted body.
- Use for a compact metric, status, action group or short summary that remains
  understandable at the narrowest desktop card width.
- Content must wrap or simplify before it overlaps the ordinal/handle reserve.

#### [universal card - 1x - title](<./src/universal card - 1x - title.png>)

- Source size: `375x166px`.
- The horizontal divider occupies source row `y=54px`. Ordinal appears first,
  accent title follows on the same baseline, and the handle remains at the
  upper right.
- A `1px` divider spans the full inner width below the header and uses the
  inner `--line-inner` token at 80%-white. The outer card border is independently
  100% white at top level or 80% when the entire card is nested.
- Title truncation is a last resort: prefer a shorter product label, then a
  bounded two-line header that increases card height consistently.

#### [Universal card - 2x](<./src/Universal card - 2x.png>)

- Source size: `790x166px`, derived from two `1x` tracks plus a `40px` nested
  gap in the reference hierarchy.
- Untitled anatomy and interactions are identical to `1x`; additional width
  is for richer values, small charts, paired controls or longer status text.
- Do not center a narrow `1x` composition inside it. Its content grid should
  deliberately use or bound the available width.

#### [Universal card - 2x - title](<./src/Universal card - 2x - title.png>)

- Source size: `790x166px`.
- Uses the same exact source divider at `y=54px`, full-width divider,
  ordinal/title baseline and top-right handle as the titled `1x` card.
- Header actions, when needed, appear before the drag handle and do not replace
  it. Focus and hover targets remain visually distinct.

#### [universal card - 4x](<./src/universal card - 4x.png>)

- Source size: `1610x166px`, the full reference main-content width.
- Untitled full-width region for timelines, tables, graphs or composite status
  whose structure supplies its own internal heading.
- It spans both primary `2x` groups and therefore participates as one reorder
  item. Its placeholder must also span the complete grid width.
- Wide content still needs a maximum readable line length or internal columns;
  width is not permission to create a single unbounded text line.

#### [universal card - 4x - title](<./src/universal card - 4x - title.png>)

- Source size: `1610x166px`.
- Canonical full-width settings/collection section: adaptive ordinal, accent
  title, top-right handle and full-width divider at source `y=54px`.
- In the supplied top-level `4x` titled template the outer border is
  `#FFFFFF` and the inner divider is `#CCCCCC`, directly demonstrating the
  two-level hierarchy.
- Body height expands for content. A `166px` source file illustrates the minimum
  anatomy, not a maximum settings-section height.
- When this card is nested inside another bordered workspace, its border and
  divider both use 80%-white; descendants do not introduce a third opacity.

### 10.4 Dashboard Template

#### [example dashboard](<./src/example dashboard.png>)

- Source canvas: `1919x1034px`; sidebar and page header follow section 10.1.
- Main card region begins at `left: 280px; top: 151px` and has an exact
  `1610px` `4x` width.
- Row 1: CPU Usage and RAM Usage, each `790x166px`, with a
  `30px` primary gap.
- Row 2: Disk Usage and Uptime in the same geometry, separated from row 1 by
  `30px`.
- Row 3: one optional `4x` card, separated by `30px`.
- Row 4: example optional `1x` cards demonstrating narrow spans and a `40px`
  nested gap. Empty example cards mean available extension positions, not
  required blank UI.
- Exact global coordinates for every shown card are defined in section 5.3 and
  are normative visual-regression fixtures for this viewport.
- Every card shows an adaptive ordinal and four-dot handle. Metric titles use
  accent Consolas Bold; values use white Consolas Bold; labels and units remain
  textual.
- CPU, RAM and Disk use a bottom progress line with accent completed portion and
  structural remaining portion. Clamp display to `0-100%` while preserving an
  explicit over-limit diagnostic if the source can exceed its contract.
- Disk percentage and used capacity use `f_bavail` for the relevant service
  data filesystem exactly as specified in section 5.3; they do not use
  `f_bfree` or an unrelated container/host filesystem.
- Uptime has no progress line because it has no meaningful fixed maximum. It is
  the current service-instance uptime and resets on a service/container restart;
  it is never the host's boot uptime.
- Refreshes update text and progress without resizing cards. Stale or failed
  telemetry is named and timestamped; it is not displayed as a healthy zero.

### 10.5 Settings Templates

The isolated Backup, Updates and Logs exports all show ordinal `02`. Those
values demonstrate ordinal styling only; actual ordinals are recomputed from
the persisted Settings-section order.

The three service-agent exports are registered composition references:

- [Backup](<./src/backup.png>) defines the backup-agent status-group rhythm, but its
  local schedule editor is superseded by the central synchronization workspace;
- [Bot connection](<./src/bot connection.png>) defines messaging-gateway card geometry,
  while service-function and Telegram-user binding remain separate controls;
- [Updates](<./src/updates.png>) defines the main release-status rows and action
  alignment; component-specific versions stay in their own groups.

The written service-agent UI guide takes precedence over obsolete example
labels or controls in these raster exports.

#### [example settings main](<./src/example settings main.png>)

- Source canvas: `1919x1034px`; fixed-open sidebar, `settings` page title and
  `123px` page header follow the shell template.
- Full-width sections begin at `x=280`, end at design coordinate `x=1890` and
  use the exact `1610px` reference width. Appearance is
  `left: 280px; top: 153px; width: 1610px; height: 401px`; Security is
  `left: 280px; top: 581px; width: 1610px; height: 418px`.
- Section header specifies an 80%-white divider at local `y=55px`; the raster
  appears at `y=54px`, which is the accepted one-pixel border tolerance. The
  adaptive ordinal starts at `left: 14px` relative to the card and the accent
  title at `left: 39px`. The complete global ledger is in section 5.5.
- Appearance body uses the exact control coordinates in section 5.5. Color
  correction places a swatch, hex field, Reset and Apply actions on one
  controlled row at desktop width; they wrap in that order before collision.
- Accent changes preview immediately. Only Apply persists. Sidebar-mode toggle
  persists immediately and updates the shell after the setting succeeds.
- Security body separates Access Key rotation from control-plane connection with clear
  headings and consequence text. Buttons open overlays; they do not expose
  secret inputs inline in the permanent page.
- The sentence `Changing the operator password...` in the legacy PNG means
  changing the Access Key. A separate operator password does not exist and the
  legacy term MUST NOT ship.
- Control-plane connection shows URL, public identity/status and reachability without
  exposing the token. Token rotation uses one full-width action.
- Settings sections carrying a four-dot handle are reorderable and persist their
  new order; ordinals recompute after drop.

#### [example settings backup](<./src/example settings backup.png>)

- Source size: `1610x400px`; canonical full-width titled settings card.
- Header is approximately `55px`; body begins with approximately `39-40px`
  horizontal and `30px` vertical padding.
- First group describes logical snapshot contents and exclusions, then presents
  an approximately `326x40px` `Create and download snapshot` action.
- Second group is Restore snapshot, despite the duplicated `System snapshot`
  wording visible in the draft PNG. Its action opens the restore overlay and
  native picker; it does not accept drag/drop outside the documented import
  target.
- Groups use heading, explanation and action order with enough vertical spacing
  to avoid interpreting the second button as part of the first description.
- Pending archive creation and restore validation preserve button geometry and
  expose final success/error notices.

#### [example settings updates](<./src/example settings updates.png>)

- Source size: `1610x396px`; full-width titled section with black fill and the
  correct current nesting outline.
- Body uses approximately `39-40px` horizontal padding. `Update pipeline` and
  its description appear first, followed by installed version with the version
  value in accent.
- Two full-width approximately `40px` status rows show the local update helper and
  approved release registry independently. Each places the component
  label at left and textual reachability plus square at right.
- Healthy status is `#62FF8C`; failed status is `#F83D3D`; a mixed state remains
  mixed rather than collapsing into one generic indicator.
- `Check for updates` is an approximately `326x40px` action below the statuses.
  It opens the discovery overlay. Apply appears only inside that overlay after
  a newer release passes provenance and compatibility checks.

#### [example settings logs](<./src/example settings logs.png>)

- Source size: `1610x399px`; full-width titled Logs section.
- The short description aligns left below the header. `Download archived logs`
  aligns right on the same command band where width permits and wraps below the
  description before overlap.
- The stream table uses a `1px` 80%-white outline and header divider. Desktop
  columns are TYPE, BODY and TIME; BODY receives all flexible width.
- Data rows have no horizontal dividers; their exact vertical rhythm is a
  `25px` row-origin step.
- Information/success type text is `#62FF8C`; error/denied type text is
  `#F83D3D`. The body remains primary/secondary white, and local timestamp is
  right aligned without forcing BODY under it.
- The viewport is bounded, normally no more than `460px` high. New records
  append in order; retention and pagination prevent DOM growth from mirroring
  the entire server history.
- On narrow width, TIME then other secondary metadata move below BODY with
  labels. TYPE and the human-readable outcome remain visible.
- Download creates a timestamped ZIP, keeps Settings open and reports pending,
  completion or failure without interrupting the live stream.

### 10.6 Context Menu Template

#### [example context menu](<./src/example context menu.png>)

- Source size: `155x197px`; it illustrates a compact eight-command menu.
- Background is `#FFFFFF`; text is `#000000`; the highlighted command uses the
  configured accent. Anti-aliased grays in the PNG are rendering artifacts, not
  additional palette tokens.
- Text uses compact Consolas Regular/Bold as required by command emphasis.
  Numbers and labels align consistently; localized production menus need not
  display numeric prefixes unless numbers are meaningful shortcuts.
- Rows use `22px` line height with list origin `left: 16px; top: 9px` and
  `21px` list-item indentation. Hover does not resize rows or the menu.
- The example command list is non-normative. Authorization determines whether
  download, delete, rename, share or other actions are present and enabled.
- Pointer hover, keyboard focus and current selection use accent without
  changing the inverted white surface. Destructive meaning must still be named;
  accent hover does not convert a destructive command into a safe action.

### 10.7 Documentation View Template

#### [documentation_example](./src/documentation_example.png)

- Source canvas: `1919x1033px`. The approximately `8px` dark-gray outer matte,
  rounded crop and shadow belong to the screenshot presentation, not the
  application. Production renders the shared shell directly against its real
  viewport and does not add a rounded desktop frame.
- Geometry is measured from the inner application's top-left corner at source
  coordinate `8,8`. In that coordinate system the sidebar is the canonical
  `250px` border-box, its `1px` right border appears at source `x=257`, and the
  `123px` page-header divider appears at source `y=130`. This image therefore
  does not amend the shell dimensions in sections 2 and 4.
- Identity is illustrative: the atom icon, `KERNEL` label, article names,
  breadcrumb and article copy MUST be replaced with the actual service icon,
  name and versioned internal documentation. They do not create reusable
  product names or content requirements.
- Page title: `Documentation`, Space Grotesk Bold at the standard `80px` desktop
  size and the shared page-title position. Production uses the configured
  accent for the title. The white title in this raster is a non-normative source
  state, not a new palette exception.
- Current sidebar destination: Documentation remains in the unnumbered bottom
  group. It uses accent text to communicate the current page, without a frame,
  arrow, scale effect or drag behavior. The white current label in the raster
  is likewise non-normative. Logout remains white until its own hover/focus
  state.
- Desktop content begins at application-local `left: 280px; top: 151px`, or
  source `left: 288px; top: 159px`. It forms a two-column grid: a `220px`
  documentation navigation column, a `30px` gap and an article surface with a
  `1120px` maximum width. Extra viewport width stays after the article instead
  of stretching prose into an unreadable line length.
- Search is `220x40px` in the reference, with black fill, a `1px` nested
  `#CCCCCC` outline and `12px` horizontal inset. Its Consolas label is a prompt,
  not a substitute for an accessible name. Input, clear and no-result states
  preserve the same box dimensions. Because the illustrated query is empty,
  its clear control is correctly absent; a non-empty query shows the mandatory
  cross at the field's right/inline end with the reserved inset from section
  5.6.
- Documentation navigation has no additional outer card. Group headings use
  muted/80%-white Consolas Bold; article labels use Consolas Regular. Article
  rows are approximately `36px` high and use `1px #CCCCCC` separators across
  the `220px` column. These are navigation separators, not prohibited data-table
  row dividers. Active, hover and keyboard-focus states use the configured
  accent without changing row height or column width.
- Navigation order follows the document information architecture, not the
  primary sidebar's numeric ordering. Groups such as getting started,
  operation and maintenance are examples; each service supplies only groups
  with real, searchable articles. Empty groups are omitted.
- The article surface begins at source `left: 538px; top: 159px`, has a
  `1120px` reference width, black fill and a `1px` top-level white outline. Its
  content inset is `32px` horizontally, `24px` at the top and at least `64px` at
  the bottom. The article grows vertically with content; clipping at the bottom
  of the PNG is a viewport crop, not a fixed article height.
- Article typography uses Consolas: breadcrumb and body `14px/22px`, article
  title Bold `36px/44px`, and level-two headings Bold `24px/30px`. Long prose
  wraps within the article column. Heading hierarchy remains semantic and must
  not be simulated only with font size.
- The breadcrumb identifies the service/document set and current article. It is
  keyboard navigable where an ancestor is actionable, uses text separators
  rather than decorative images and never exposes filesystem paths or private
  repository coordinates.
- Article section dividers use the nested `#CCCCCC` line. The reference note is
  a rectangular `#111111` surface with a `2px` white left rule and approximately
  `16px` padding; semantic success, warning or failure notes additionally use
  the prescribed green, accent or red meaning in text/icon treatment and never
  rely on color alone.
- Code blocks, tables, lists and links follow section 5.7. Copy actions provide
  explicit success/failure feedback and retain a manual-selection fallback for
  embedded browsers where programmatic clipboard access is unavailable.
- At widths near `1000px` the documentation navigation stacks before the
  article and both use the available main width. At `720px` and below the global
  sidebar becomes its standard modal overlay; documentation navigation remains
  in normal document order, search stays reachable and no horizontal page
  scrolling is introduced.
- When the global sidebar is hidden at desktop width, the whole documentation
  grid moves left and may use the released width, while the `220px` navigation,
  `30px` inter-column gap and `1120px` readable article maximum remain stable.
  Verify open and hidden states at `1919x1034` and `1920x1080` as required by
  section 9.
