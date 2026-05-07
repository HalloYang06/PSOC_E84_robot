# AI Collaboration Platform Design System

## 1. Visual Theme & Atmosphere

This product is a human-led operations workspace for AI collaboration in embedded and robotics projects. It should feel calm, precise, and engineered rather than flashy, game-like, or marketing-heavy. The interface is dark-mode-native and should borrow the ordering discipline of Linear while keeping a slight terminal-native edge for agent operations.

The first screen must read as a working surface, not a landing page. Users should immediately understand status, action, and risk. Strong hierarchy matters more than visual effects.

### Core mood
- Near-black canvas
- Thin luminous borders
- Sparse accent color
- Dense but readable information
- Minimal chrome
- Calm control room, not dashboard-card mosaic

## 2. Color Palette & Roles

### Surfaces
- Background: `#08090a`
- Panel: `rgba(255,255,255,0.02)`
- Elevated panel: `rgba(255,255,255,0.04)`
- Hover/elevated state: `rgba(255,255,255,0.06)`

### Text
- Primary: `#f7f8f8`
- Secondary: `#d0d6e0`
- Muted: `#8a8f98`

### Accent
- Primary accent: `#5e6ad2`
- Accent hover: `#7170ff`

### Status
- Info: `#58a6ff`
- Warn: `#d29922`
- Danger: `#f85149`
- Success: `#27a644`

### Borders
- Standard border: `rgba(255,255,255,0.08)`
- Subtle border: `rgba(255,255,255,0.05)`

## 3. Typography Rules

### Fonts
- Primary: `Inter Variable`, `Segoe UI`, `system-ui`, sans-serif
- Monospace: `ui-monospace`, `SFMono-Regular`, `Consolas`, monospace

### Hierarchy
- Page title: 32px, weight 590, letter-spacing `-0.7px`
- Section title: 18px, weight 590
- Large numeric stat: 28px, weight 590
- Body: 14px to 15px, weight 400 to 510
- Labels / overlines: 11px to 12px, uppercase, muted

### Rules
- Do not use oversized poster headlines on working pages
- Keep page titles concise
- Use one strong title, then utility copy
- Prefer readable density over dramatic scale

## 4. Component Stylings

### Panels
- Background: `rgba(255,255,255,0.02)`
- Border: `1px solid rgba(255,255,255,0.08)`
- Radius: `8px`
- Padding: `16px` to `24px`

### Buttons
- Primary button uses accent background
- Secondary button uses translucent surface and border
- No pill soup
- No heavy shadows

### Status pills
- Small, quiet, and compact
- Use only for real state, not decoration

## 5. Layout Principles

- The first screen is an operations surface
- Start with header, live status, summary, and active dispatch
- Use 2-column or 4-column grids with consistent spacing
- Avoid mixing hero marketing composition with admin workspace structure
- Let whitespace come from restraint, not giant empty dramatic areas

## 6. Do

- Keep the page calm
- Let sections have one job each
- Use accent color sparingly
- Keep cards only where there is direct action or scanning value
- Make the most important workflow visible in the first viewport

## 7. Don't

- Do not build a generic dashboard card mosaic
- Do not use giant promo copy on operational pages
- Do not mix multiple visual metaphors on one screen
- Do not overload the first viewport with every zone at once
- Do not use decorative gradients, floating blobs, or fake game HUD clutter

## 8. Page Intent For `/base`

`/base` is the command surface of the platform.

The first viewport should contain:
- product name and branch
- top status counters
- a concise summary of current mission
- the live dispatch list

Below the first viewport:
- facility zones
- AI workstation cards
- later: task stream and incident stream

## 9. Product Translation

This project can still be described as a "research base" or "AI operations base", but the UI should express that through naming and structure, not by turning the page into a game screen full of decorative effects.
