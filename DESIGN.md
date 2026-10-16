---
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
name: BidWeave
description: Revision-aware procurement work, with an editorial public landing and a restrained operational workspace.
colors:
  landing-ink: "#142434"
  landing-navy: "#0d2638"
  landing-paper: "#fbfaf6"
  landing-sand: "#e8e2d7"
  landing-line: "#d7d1c7"
  landing-rust: "#bb4d2e"
  workspace-background: "#ffffff"
  workspace-surface: "#f8fafc"
  workspace-muted-surface: "#f1f5f9"
  workspace-border: "#cbd5e1"
  workspace-foreground: "#0f172a"
  workspace-muted: "#475569"
  workspace-focus: "#3b82f6"
  workspace-success: "#15803d"
  workspace-warning: "#b45309"
  workspace-danger: "#b91c1c"
  dark-background: "#020617"
  dark-surface: "#0f172a"
  dark-muted-surface: "#1e293b"
  dark-border: "#334155"
  dark-foreground: "#f8fafc"
  dark-muted: "#cbd5e1"
  dark-focus: "#60a5fa"
  dark-success: "#4ade80"
  dark-warning: "#fbbf24"
  dark-danger: "#f87171"
typography:
  landing-display:
    fontFamily: '"Newsreader Variable", Georgia, serif'
    fontSize: "clamp(3.3rem, 6vw, 6rem)"
    fontWeight: 550
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  workspace-title:
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1.3rem"
    fontWeight: 700
    letterSpacing: "-0.025em"
  workspace-body:
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "0.875rem"
    lineHeight: 1.45
  workspace-label:
    fontSize: "0.72rem"
    fontWeight: 600
rounded:
  control: "6px"
  panel: "8px"
  notice: "7px"
spacing:
  compact: "8px"
  control-inline: "12px"
  section: "20px"
components:
  workspace-primary:
    backgroundColor: "{colors.workspace-foreground}"
    textColor: "{colors.workspace-background}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  workspace-primary-dark:
    backgroundColor: "{colors.dark-foreground}"
    textColor: "{colors.dark-surface}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  workspace-secondary:
    backgroundColor: "{colors.workspace-background}"
    textColor: "{colors.workspace-foreground}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
---

# Design System: BidWeave

## Overview

**Creative North Star: "A clear operational dossier."**

The public landing retains its editorial identity: warm paper, navy ink, Newsreader headings and a rust change marker. The user-approved 1.1 redesign applies only to the authenticated workspace, its pre-authentication states and Keycloak login. These surfaces use the restrained, compact administrative language of the selected Shadcn Admin reference. The implementation is original React/CSS, not a copied component library or replacement authentication service.

**Key Characteristics:**
- Separate public explanation from day-to-day task execution.
- Keep case, revision, evidence and approval context visible.
- Use neutral surfaces and semantic status text, with light/dark/system preferences.
- Let real API state determine content and available actions.

## Colors

The frontmatter records the reusable landing palette and workspace light/dark roles. Primary workspace actions invert foreground and background; status colors never replace labels. Workspace tokens are scoped to the application shell, including centered loading and authentication-error states, rather than applied to the public landing.

Keycloak uses the same neutral palette and focus colors. Its inherited form alerts have their own error-surface tokens in `infra/keycloak/themes/bidweave/login/resources/css/bidweave.css`; do not flatten them into a color-only indication.

**The Surface Boundary Rule.** Workspace theme changes must not recolor the landing page.

## Typography

Newsreader is self-hosted under SIL OFL-1.1 for landing display text. Workspace uses the system-sans stack recorded above; Inter is used only when available, not fetched from a remote font service. Keycloak uses a system-sans stack directly. Stable requirement keys, hashes and code values may use monospace; ordinary instructions and status labels do not.

Workspace title, body and label roles prioritize Vietnamese reading and compact data density. The landing headline reduces to 3.2rem at the narrow breakpoint. Preserve full field labels and accessible names even when the visible case title is truncated.

## Layout

Desktop workspace uses a 224px sidebar and a flexible content column. The content wrapper is capped at 1500px, with horizontal padding that scales from 18px to 48px. The H/P/D/I views share a case selector, theme selector and action area; their operational panels align at the top rather than stretching to equal heights.

At 900px and below, the sidebar becomes a top navigation region with four H/P/D/I controls, and multi-column work areas stack. At 620px, forms and dense rows adapt further. Centered pre-authentication states use a single column at every width. Dialogs keep focus and scrolling within the editing task; validation errors stay inside that dialog.

The unchanged landing has a 1240px content frame and an editorial split hero. Its composition and type scale are not a template for workspace screens.

## Elevation & Depth

Operational panels rely primarily on borders and tonal surfaces. Toasts use the existing soft elevation; dialogs use a dimmed backdrop and a bordered surface. Login has a distinct centered form surface and its own soft shadow; it inherits Keycloak form semantics rather than reimplementing them. Avoid introducing decorative shadows or hover movement into dense task controls.

## Shapes

Workspace controls, panels and notices use their recorded radius roles. Status indicators are compact, text-labeled pills. The application mark is a simple authored vector; it is not an illustration or a substitute for product evidence.

## Components

- **Navigation:** H/P/D/I has a visible selected state and `aria-current`; the same destinations remain available on mobile.
- **Buttons:** standard workspace actions have a 36px minimum height, compact padding and a visible focus outline. Secondary/ghost actions remain visually subordinate. Disabled presentation does not replace backend authorization.
- **Fields:** visible labels, themed native inputs/selects, and a distinct focus indicator. Keep native file/date controls and explicit server validation.
- **Requirement matrix:** stable key, type/threshold, owner, source and status. Do not hide change context merely to make rows shorter.
- **Evidence and review:** show filename, hash prefix, uploader and verification state; preserve independent review and exact-revision approval semantics.
- **Notices:** error text, semantic color and a bordered surface. A dialog error receives focus so it is not hidden below the mobile viewport.
- **Agent:** display actual model output, source IDs and limitations. Empty, unavailable and needs-review states must remain truthful.
- **Login:** inherit Keycloak templates, CSRF handling, required actions and password visibility. New realms default to Vietnamese; existing realm language settings are preserved.

**The State Is Evidence Rule.** An unavailable provider, stale revision or rejected operation must never be presented as successful completion.

## Do's and Don'ts

### Do:
- **Do** preserve the landing/workspace visual boundary.
- **Do** apply the resolved theme to loading, signed-out and authentication-error states as well as authenticated content.
- **Do** use real API data and label synthetic demonstration content.
- **Do** preserve labels, keyboard focus, reduced-motion behavior and narrow-screen access to every action.
- **Do** keep source and license attribution for integrated products separate from original UI code.

### Don't:
- **Don't** replace Keycloak with a decorative login form or store bearer tokens in localStorage.
- **Don't** infer authorization, independent verification or approval from visual status alone.
- **Don't** silently overwrite an existing realm's users, clients, passwords or locale to apply a theme.
- **Don't** add external font/image dependencies, invented metrics or fabricated Agent success.
