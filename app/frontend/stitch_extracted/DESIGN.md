---
name: Sacred Scholarly
colors:
  surface: '#fbf9f5'
  surface-dim: '#dbdad6'
  surface-bright: '#fbf9f5'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3ef'
  surface-container: '#efeeea'
  surface-container-high: '#eae8e4'
  surface-container-highest: '#e4e2de'
  on-surface: '#1b1c1a'
  on-surface-variant: '#43474e'
  inverse-surface: '#30312e'
  inverse-on-surface: '#f2f0ed'
  outline: '#74777f'
  outline-variant: '#c4c6cf'
  surface-tint: '#455f88'
  primary: '#002045'
  on-primary: '#ffffff'
  primary-container: '#1a365d'
  on-primary-container: '#86a0cd'
  inverse-primary: '#adc7f7'
  secondary: '#7b5800'
  on-secondary: '#ffffff'
  secondary-container: '#fdc34d'
  on-secondary-container: '#715000'
  tertiary: '#29200c'
  on-tertiary: '#ffffff'
  tertiary-container: '#3f3520'
  on-tertiary-container: '#ac9d82'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d6e3ff'
  primary-fixed-dim: '#adc7f7'
  on-primary-fixed: '#001b3c'
  on-primary-fixed-variant: '#2d476f'
  secondary-fixed: '#ffdea6'
  secondary-fixed-dim: '#f7bd48'
  on-secondary-fixed: '#271900'
  on-secondary-fixed-variant: '#5d4200'
  tertiary-fixed: '#f2e0c2'
  tertiary-fixed-dim: '#d5c5a7'
  on-tertiary-fixed: '#231a08'
  on-tertiary-fixed-variant: '#51452f'
  background: '#fbf9f5'
  on-background: '#1b1c1a'
  surface-variant: '#e4e2de'
typography:
  display-lg:
    fontFamily: Source Serif 4
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Source Serif 4
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Source Serif 4
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Source Serif 4
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Libre Franklin
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 30px
  body-md:
    fontFamily: Libre Franklin
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  label-sm:
    fontFamily: Libre Franklin
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  sidebar_width: 280px
  sources_panel_width: 360px
  gutter: 24px
  margin_mobile: 16px
  margin_desktop: 40px
  stack_gap: 16px
---

## Brand & Style
The brand personality is that of a "Modern Sage"—authoritative yet accessible, bridging ancient wisdom with cutting-edge technology. The target audience includes scholars, students, and curious minds seeking a deep, focused connection with Jewish texts. The UI must evoke a sense of **intellectual clarity** and **spiritual reverence**.

The design style is a blend of **Minimalism** and **Modern Corporate**, utilizing heavy whitespace to simulate the margins of a traditional Talmud folio. The atmosphere is quiet and focused, prioritizing the "weight" of the text over ornamental flair. Every element is intentional, reflecting the meticulous nature of Torah study.

## Colors
The palette is anchored in tradition. The **Primary Deep Blue** (Tallit Blue) provides a sense of stability and depth. The **Secondary Gold/Copper** is used sparingly for accents, signifying the value and "light" of the insights. 

The background uses a **Cream/Light Paper** (`#FDFBF7`) rather than pure white to reduce eye strain during long study sessions and to evoke the tactile feel of parchment. Status colors (success, error, warning) should be muted to maintain the sophisticated, respectful tone of the interface.

## Typography
This design system uses a hybrid typographic approach. **Source Serif 4** provides a scholarly, authoritative feel for headlines and primary text sources, echoing the serif styles of traditional Hebrew printing. **Libre Franklin** is used for functional UI elements and body text to ensure modern legibility and a clean, systematic structure.

For Hebrew text support, ensure fallbacks prioritize high-quality serif faces (like Frank Ruhl Libre) to maintain the "Sacred Scholarly" aesthetic. Line heights are intentionally generous (1.6x+) to facilitate deep reading and cross-referencing between Hebrew and English.

## Layout & Spacing
The layout follows a **3-column fixed-fluid-fixed** model optimized for academic research. 
1. **Sidebar (Navigation):** Fixed width, collapsible, containing history and navigation.
2. **Main Chat (Canvas):** Fluid width, centered, with maximum readability constraints (max-width 800px).
3. **Sources Panel (Context):** Fixed width, containing reference cards and full-text excerpts.

The system must seamlessly support **RTL (Right-to-Left)** mirroring. In Hebrew mode, the Sidebar moves to the right, and the Sources Panel moves to the left. The spacing rhythm is based on a 4px/8px scale, using generous margins to signify the "breathing room" required for complex study.

## Elevation & Depth
Depth is conveyed through **Tonal Layers** and **Low-contrast Outlines** rather than heavy shadows. The primary canvas sits on the "Paper" background, while panels use a slightly darker or lighter tint to indicate hierarchy.

Shadows, when used (e.g., for active Modals), are "Ambient Shadows"—extremely soft, using the Primary Blue color at 5% opacity to create a subtle glow rather than a harsh drop-shadow. This maintains the clean, modern aesthetic while providing necessary depth cues for interactive layers.

## Shapes
The shape language is **Soft (0.25rem)**. While modern, it avoids the "bubbly" feel of consumer social apps. The subtle rounding provides a human touch while maintaining the structural integrity of a serious research tool. Buttons and input fields use this minimal radius to feel like precisely cut vellum or paper.

## Components
- **Chat Bubbles:** These should not look like traditional "SMS" bubbles. Instead, use a flat, card-like style with a subtle left/right border (Tallit-inspired) to indicate the speaker. No heavy rounding.
- **Source Cards:** Use the Copper accent for a top-border or icon to denote "Precious Knowledge." Include metadata labels in `label-sm` for source type (e.g., Gemara, Mishna, Rambam).
- **Buttons:** Primary buttons are Solid Tallit Blue with white text. Secondary buttons use an outline style with the Copper accent.
- **Collapsible Panels:** Use clean, 1px lines (`#E2D1B3`) to separate the sidebar and sources panel. The toggle should be an elegant, minimalist arrow.
- **Modals:** Used for "Full Text" viewing. The modal should fill 90% of the screen with a large vertical scroll area, using `Source Serif 4` for the primary text to simulate a book page.
- **Input Fields:** A simple underline or a very light 1px border. Focus states are indicated by the Gold accent.