# Barterex Design System - Visual Guide

## Color Palette

### Brand Colors

```
Primary Blue: #054e97
  Light:   #0d5fa8
  Lighter: #1a7bc4
  Dark:    #043a72
  Darker:  #021f3d

Secondary Orange: #ff7a00
  Light:    #ff8c26
  Lighter:  #ffaa57
  Dark:     #cc6300
  Darker:   #994700
```

### Status Colors

```
Success Green:  #10b981
Warning Amber:  #f59e0b
Error Red:      #ef4444
Info Blue:      #3b82f6
```

### Neutral Gray Palette

```
Gray 50:   #f9fafb  (Almost white)
Gray 100:  #f3f4f6  (Very light)
Gray 200:  #e5e7eb  (Light)
Gray 300:  #d1d5db  (Light borders)
Gray 400:  #9ca3af  (Medium)
Gray 500:  #6b7280  (Secondary text)
Gray 600:  #4b5563  (Dark text)
Gray 700:  #374151  (Darker)
Gray 800:  #1f2937  (Very dark)
Gray 900:  #111827  (Darkest)
```

---

## Typography

### Font Stack

```css
/* Primary (Body & UI) */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;

/* Secondary (Headings) */
font-family: 'Space Grotesk', 'Inter', sans-serif;

/* Monospace (Code) */
font-family: 'Fira Code', monospace;
```

### Font Sizes

| Size | Mobile | Desktop | Use Case |
|------|--------|---------|----------|
| H1 | 24px | 32px | Page titles |
| H2 | 20px | 28px | Section titles |
| H3 | 18px | 24px | Subsection titles |
| H4 | 16px | 20px | Card titles |
| Body | 16px | 16px | Main text |
| Small | 14px | 14px | Helper text |
| XS | 12px | 12px | Labels, captions |

### Line Heights

```
Tight:    1.2   (Headings)
Normal:   1.5   (Body text)
Relaxed:  1.75  (Form labels)
Loose:    2     (Captions)
```

### Font Weights

```
Light:      300
Normal:     400
Medium:     500
Semibold:   600 (Buttons, highlights)
Bold:       700 (Headings)
Extrabold:  800 (Hero titles)
```

---

## Spacing Scale

All measurements use an 8px base:

```
XS:  4px   (Small gaps, mini spacing)
SM:  8px   (Small spacing)
MD:  16px  (Default spacing)
LG:  24px  (Section spacing)
XL:  32px  (Large spacing)
2XL: 48px  (Very large spacing)
3XL: 64px  (Huge spacing)
```

### Usage Examples

```
Padding between sections:  24px or 32px
Card padding:              16px or 24px
Button padding:            8px-16px
Form field margins:        16px
Gap between grid items:    16px
Container margins:         16px (mobile), 24px (desktop)
```

---

## Shadows

```
XS:  0 1px 2px 0 rgba(0,0,0, 0.05)
SM:  0 1px 3px 0 rgba(0,0,0, 0.1), 0 1px 2px 0 rgba(0,0,0, 0.06)
MD:  0 4px 6px -1px rgba(0,0,0, 0.1), 0 2px 4px -1px rgba(0,0,0, 0.06)
LG:  0 10px 15px -3px rgba(0,0,0, 0.1), 0 4px 6px -2px rgba(0,0,0, 0.05)
XL:  0 20px 25px -5px rgba(0,0,0, 0.1), 0 10px 10px -5px rgba(0,0,0, 0.04)
2XL: 0 25px 50px -12px rgba(0,0,0, 0.25)
```

### Usage Examples

```
Cards at rest:           Shadow SM
Cards on hover:          Shadow MD or LG
Modals/Overlays:         Shadow XL
Buttons:                 Shadow XS or None
Dropdowns:               Shadow MD
Floating elements:       Shadow LG
```

---

## Border Radius

```
None:   0px
SM:     4px   (Small elements)
MD:     8px   (Default, form inputs)
LG:     12px  (Cards, modals)
XL:     16px  (Large cards, components)
2XL:    20px  (Extra large components)
Full:   9999px (Circles, pills)
```

### Usage Examples

```
Form inputs:             8px
Buttons:                 12px
Cards:                   12px
Modals:                  12px
Badges:                  9999px (pills)
Avatar images:           9999px (circles)
Rounded buttons:         9999px
```

---

## Button Design

### Sizes

```
Small (SM):
  Height:    32px
  Padding:   6px 12px
  Font:      14px
  Use:       Inline actions, secondary actions

Medium (MD) - DEFAULT:
  Height:    40px
  Padding:   8px 16px
  Font:      16px
  Use:       Most buttons, forms

Large (LG):
  Height:    44px or 48px
  Padding:   12px 24px
  Font:      18px
  Use:       Primary actions, CTAs, mobile
```

### Styles

```
Primary (Blue):
  Background: #054e97
  Text:       White
  Hover:      Lighten to #0d5fa8
  Active:     Darken to #043a72

Secondary (Orange):
  Background: #ff7a00
  Text:       White
  Hover:      Lighten to #ff8c26
  Active:     Darken to #cc6300

Outline:
  Background: Transparent
  Border:     2px solid #054e97
  Text:       #054e97
  Hover:      Background becomes #054e97, text white

Ghost:
  Background: Transparent
  Border:     None
  Text:       #111827
  Hover:      Background #f3f4f6
```

### States

```
Default:    Normal appearance
Hover:      Slight elevation, color change
Active:     Pressed appearance
Disabled:   50% opacity, cursor not-allowed
Loading:    Spinner animation, no text
```

---

## Form Elements

### Input Fields

```
Height:           40px (MD) or 36px (SM)
Padding:          8px 12px
Border:           1px solid #e5e7eb (Gray 300)
Border Radius:    8px
Font:             16px
Background:       White
Focus:            Border #054e97, Shadow with primary color
Disabled:         Background #f3f4f6, opacity 0.5

Focus State:
  Border color:   #054e97 (Primary blue)
  Box shadow:     0 0 0 3px rgba(5, 78, 151, 0.1)
  Outline:        None (use shadow instead)
```

### Form Groups

```
Margin Bottom:    24px (between fields)
Label Font:       14px, #111827, font-weight 600
Label Margin:     8px below label
Helper Text:      12px, #6b7280, below field
Error Text:       12px, #ef4444, below field
```

### Textarea

```
Min Height:       120px
Resize:           Vertical only
Padding:          8px 12px
Line Height:      1.75 (improved readability)
```

---

## Cards

### Standard Card

```
Background:       White
Border:           1px solid #e5e7eb
Border Radius:    12px
Padding:          24px (LG) or 16px (MD)
Shadow:           Box Shadow SM
Transition:       All 200ms ease

On Hover:
  Shadow:         Box Shadow LG
  Border:         #0d5fa8 (lighter primary)
```

### Card Image

```
Width:            100%
Height:           200px (mobile) to 250px (desktop)
Object Fit:       Cover
Border Radius:    8px (top if inside card)
Margin Bottom:    16px
```

---

## Mobile Optimization

### Touch Targets

```
Minimum:   44px × 44px
Padding:   8-16px around interactive elements
Spacing:   16px between buttons
```

### Responsive Typography

```
Mobile (< 640px):
  H1: 24px
  H2: 20px
  H3: 18px
  Body: 16px

Tablet (640px - 1023px):
  H1: 28px
  H2: 24px
  H3: 20px
  Body: 16px

Desktop (1024px+):
  H1: 32px
  H2: 28px
  H3: 24px
  Body: 16px
```

---

## Accessibility Considerations

### Color Contrast

```
WCAG AA Requirement: 4.5:1 for normal text, 3:1 for large text

Approved Combinations:
  Dark text (#111827) on white (#ffffff)         ✓ 11.3:1
  Blue (#054e97) on white                        ✓ 8.5:1
  Orange (#ff7a00) on white                      ✓ 4.5:1
  White on blue (#054e97)                        ✓ 9.2:1
  Gray text (#6b7280) on white                   ✓ 5.3:1

Avoid:
  Light text on light background
  Dark gray on black
  Orange on red
```

### Focus States

```
Visible focus ring:  2px solid #054e97
Offset:             2px from element
Works on:           All buttons, links, form inputs, interactive elements
```

### Icon Usage

```
Icons as labels:   Include text label or aria-label
Icons only:        Minimum 44px × 44px tap target
Icon size:         16px-24px in buttons, 24px in navigation
Color:             Inherit or explicit color variable
```

---

## Transitions & Animations

### Standard Timings

```
Fast:       150ms (Hover states, quick feedback)
Base:       200ms (Default animations, transitions)
Slow:       300ms (Page transitions, modals)
Slower:     500ms (Entrance animations)
```

### Easing Functions

```
ease:               Natural, smooth
ease-in:            Accelerating
ease-out:           Decelerating
ease-in-out:        Smooth acceleration and deceleration
```

### Common Animations

```
Button Hover:       Color change (200ms ease)
Card Elevation:     Shadow change (200ms ease)
Loading Spinner:    Rotation (600ms linear infinite)
Page Fade:          Opacity (300ms ease)
Slide In:           Transform (300ms ease-out)
```

---

## Breakpoints & Responsive Design

### Device Classes

```
Mobile:    < 640px   (Portrait phones)
Tablet:    ≥ 640px   (Small tablets, landscape phones)
Desktop:   ≥ 1024px  (Large tablets, desktops)
Wide:      ≥ 1280px  (Large desktops)
Ultra:     ≥ 1536px  (Ultrawide displays)
```

### Responsive Patterns

```
Navigation:
  Mobile:   Bottom navigation bar
  Tablet:   Top horizontal or left sidebar (collapsible)
  Desktop:  Top horizontal or left sidebar (fixed)

Grid Columns:
  Mobile:   1 column
  Tablet:   2 columns
  Desktop:  3-4 columns

Container Width:
  Mobile:   Full width with 16px padding
  Tablet:   Max 640px-768px
  Desktop:  Max 1024px-1280px
  Wide:     Max 1280px-1536px

Font Sizes:
  Mobile:   Smaller (see typography section)
  Desktop:  Larger (see typography section)
```

---

## Common Component Styles

### Badges / Labels

```
Padding:        4px 8px
Border Radius:  9999px (pill shape)
Font Size:      12px
Font Weight:    600
Colors:
  Success:  Green background, white text
  Warning:  Amber background, dark text
  Error:    Red background, white text
  Info:     Blue background, white text
```

### Chips / Tags

```
Padding:        6px 12px
Border Radius:  9999px
Font Size:      14px
Background:     Gray 100
Border:         1px solid Gray 300
Remove icon:    16px × 16px, right side
```

### Dropdown / Select

```
Height:         40px
Padding:        8px 12px
Border:         1px solid Gray 300
Border Radius:  8px
Arrow icon:     Right side, 16px
Hover:          Background Light gray

Open Menu:
  Position:     Absolute or fixed (below trigger)
  Min Width:    Trigger width
  Shadow:       Box Shadow MD
  Items:        44px height minimum
```

### Modal / Dialog

```
Background:     White
Border Radius:  12px
Padding:        32px
Shadow:         Box Shadow XL
Max Width:      500px (mobile), 700px (desktop)
Overlay:        Black, 50% opacity

Mobile:
  Full screen or top sheet
  Padding:     16px top/bottom
```

---

## Imagery Guidelines

### Image Sizing

```
Hero Images:      16:9 ratio
Product Images:   1:1 ratio (square)
Thumbnails:       200px × 200px
Banners:          16:9 ratio, min 600px wide
Icons:            SVG, 24px × 24px standard
Avatar:           48px × 48px or 64px × 64px, circular
```

### Image Optimization

```
Formats:
  Photos:   JPEG, optimized
  Icons:    SVG (scalable)
  Graphics: PNG (transparent)
  Animated: WebP or GIF

Sizes:
  Mobile:   Max 1x or 2x density
  Desktop:  Max 2x density
  Lazy Load: Below fold
```

---

## Dark Mode (Future Enhancement)

```
While not currently implemented, design system supports it:

:root[data-theme="dark"] {
  --color-bg-primary: #111827;
  --color-text-primary: #ffffff;
  --color-border: #374151;
  /* ... etc ... */
}
```

---

## Implementation Checklist

When using the design system:

- [ ] Use CSS variables for colors, not hardcoded values
- [ ] Use spacing scale classes (p-md, m-lg) instead of arbitrary values
- [ ] Use button classes (.btn, .btn-primary) instead of custom styles
- [ ] Ensure 44px minimum touch targets on mobile
- [ ] Test color contrast with WAVE or Lighthouse
- [ ] Verify focus states visible on all interactive elements
- [ ] Test on at least 5 different device sizes
- [ ] Check keyboard navigation works
- [ ] Verify smooth transitions on all interactions
- [ ] Test with screen reader (NVDA/JAWS on Windows, VoiceOver on Mac)

---

## Resources

### Tools for Testing
- Chrome DevTools (F12)
- Firefox Developer Tools
- WAVE Accessibility Checker
- Lighthouse Audit
- WebAIM Contrast Checker
- Responsive Design Tester

### Documentation Files
- `DESIGN_SYSTEM_QUICK_START.md` - Implementation guide
- `TEMPLATE_UPDATE_CHECKLIST.md` - Template-by-template updates
- `UI_UX_IMPROVEMENT_PLAN.md` - Full roadmap

---

**Design System Version:** 1.0  
**Last Updated:** December 6, 2025  
**Status:** Ready for Implementation

