---
name: Steward
colors:
  surface: '#fff8f4'
  surface-dim: '#e2d8d1'
  surface-bright: '#fff8f4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#fcf2ea'
  surface-container: '#f6ece5'
  surface-container-high: '#f1e6df'
  surface-container-highest: '#ebe1da'
  on-surface: '#1f1b17'
  on-surface-variant: '#54433e'
  inverse-surface: '#352f2b'
  inverse-on-surface: '#f9efe8'
  outline: '#87736d'
  outline-variant: '#d9c1ba'
  surface-tint: '#914b33'
  primary: '#8e4831'
  on-primary: '#ffffff'
  primary-container: '#ac6046'
  on-primary-container: '#fffbff'
  inverse-primary: '#ffb59d'
  secondary: '#54634a'
  on-secondary: '#ffffff'
  secondary-container: '#d7e8c8'
  on-secondary-container: '#5a6950'
  tertiary: '#645b4b'
  on-tertiary: '#ffffff'
  tertiary-container: '#7e7362'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbd0'
  primary-fixed-dim: '#ffb59d'
  on-primary-fixed: '#390b00'
  on-primary-fixed-variant: '#74341e'
  secondary-fixed: '#d7e8c8'
  secondary-fixed-dim: '#bbccad'
  on-secondary-fixed: '#121f0b'
  on-secondary-fixed-variant: '#3d4b34'
  tertiary-fixed: '#efe1cc'
  tertiary-fixed-dim: '#d2c5b1'
  on-tertiary-fixed: '#211b0e'
  on-tertiary-fixed-variant: '#4e4637'
  background: '#fff8f4'
  on-background: '#1f1b17'
  surface-variant: '#ebe1da'
typography:
  display-lg:
    fontFamily: Source Serif 4
    fontSize: 42px
    fontWeight: '600'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Source Serif 4
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Source Serif 4
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Source Serif 4
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  body-lg:
    fontFamily: Work Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Work Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Work Sans
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Work Sans
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.03em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 8px
  container-max: 1120px
  gutter: 24px
  margin-mobile: 20px
  section-gap: 64px
  element-gap: 16px
---

## Brand & Style

The design system is built upon the concept of "the steady hand." It facilitates difficult family transitions with a grounded, unhurried presence. The aesthetic rejects the frenetic energy of modern productivity tools in favor of a **warm, humanist minimalism** that feels more like a physical heirloom catalog than a digital database.

The visual direction avoids "gamification" entirely. There are no progress bars that demand completion or badges that reward speed. Instead, the UI uses generous whitespace and a tactile, paper-like quality to provide families with the emotional room to breathe and reflect. The style is "Plainspoken Luxury"—high-quality typography and subtle tonal shifts that communicate reliability and respect for the objects being managed.

## Colors

The palette is rooted in natural, earthy pigments. **Warm Clay** serves as the primary action color, providing a sense of hearth and home. **Soft Sage** acts as a secondary accent, used for balanced, secondary actions or supportive elements.

The background is a consistent **Warm Cream**, avoiding the clinical sterility of pure white. Status indicators are intentionally desaturated to lower the "alert level" of the interface:
- **Contested items** use a muted amber, signaling a need for conversation rather than an "error."
- **Resolved items** use a faded green that feels like a quiet sigh of relief.
- **Unclaimed items** sit in a soft gray, receding into the background until they are ready to be addressed.

## Typography

This design system utilizes a sophisticated pairing of **Source Serif 4** for headings and **Work Sans** for functional text. 

The Serif headings provide an authoritative yet warm voice, reminiscent of classic literature or personal correspondence. The Sans-Serif body text is chosen for its exceptional readability and "plainspoken" character; it is neutral and clear, ensuring that descriptions of family items remain the focus. 

Line heights are intentionally generous (1.5x - 1.6x) to prevent the text from feeling dense or overwhelming during emotionally heavy tasks.

## Layout & Spacing

The layout philosophy is based on a **Fixed, Centered Grid** for desktop to create a sense of focus and containment. Content should never feel like it is "escaping" to the edges of the screen.

- **Whitespace:** Use whitespace as a functional tool to separate different family branches or categories of items. Avoid packing information tightly.
- **Rhythm:** A strict 8px base unit governs all padding and margins. 
- **Adaptation:** On mobile, margins reduce to 20px, and the layout collapses into a single-column flow that emphasizes large touch targets and legible, centered typography.

## Elevation & Depth

To maintain the "kitchen table" feel, this design system avoids floating elements and harsh shadows. Depth is communicated through **Tonal Layering**:

1.  **Level 0 (Base):** The Warm Cream (#F2E9DC) background.
2.  **Level 1 (Cards/Containers):** Surfaces use a slightly lighter cream or a very subtle tint of Sage/Clay at 5% opacity. 
3.  **Outlines:** Instead of shadows, use "Ghost Borders"—thin (1px), low-contrast strokes that are only 10-15% darker than the surface color.

The only exception to the "no shadow" rule is a very soft, diffused ambient occlusion (blur 20px, 4% opacity) used for active modals to gently separate them from the background without creating a sense of "emergency."

## Shapes

The shape language is **Soft and Organic**. While not fully rounded or "bubbly," every corner is softened to remove any sense of sharpness or clinical precision.

- **Standard Radius:** 0.25rem (4px) for small inputs and buttons.
- **Large Radius:** 0.5rem (8px) for cards and main containers.
- **Image Treatment:** Photos of family belongings should feature the 8px corner radius to make them feel like physical photographs laid out on a table.

## Components

### Buttons
Primary buttons use the **Warm Clay** fill with white text. They are substantial in size but use the "Soft" corner radius. Secondary buttons use a simple Soft Sage outline. Hover states should be a subtle darkening of the color, never a flash or high-contrast change.

### Cards
Cards are the primary vehicle for item management. They should feature a "Soft" radius and a 1px border in a slightly darker cream. There should be no "lift" effect on hover; instead, use a subtle background color shift to Soft Sage at 5% opacity.

### Chips & Status Indicators
Status chips use the muted palette defined in the Colors section. They are rectangular with slightly rounded corners (Soft), never pill-shaped, to maintain a more "archival tag" aesthetic.

### Input Fields
Inputs are simple and unobtrusive. Use a Warm Cream fill that is slightly darker than the background, with a 1px border. Labels always sit above the field in **Work Sans Medium** to ensure clarity of intent.

### Lists
Lists of family members or item categories should have generous vertical padding (20px+) to ensure that each row feels distinct and respected.

### The "Heirloom" Component
A specific component for displaying individual belongings. It features a centered photo, a Source Serif 4 title, and a wide-margined description area below, mimicking the layout of a museum placard or a family album page.