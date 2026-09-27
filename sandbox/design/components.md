# Tallybird design system

Designs are body markup built from these classes. The page shell adds `tallybird.css` and puts the markup inside `<body class="tb-canvas">`. No inline styles, no `<style>` tags, no colors or fonts outside the tokens.

## Layout

| Class | Use |
|---|---|
| `tb-topbar`, `tb-logo` | The app header: `<header class="tb-topbar"><span class="tb-logo">Tallybird</span></header>` |
| `tb-page` | The centered content column. One per screen |
| `tb-stack`, `tb-row` | Vertical and horizontal groups with standard gaps |

## Surfaces and type

| Class | Use |
|---|---|
| `tb-card` | The main surface of a step or panel |
| `tb-divider` | An `<hr>` inside a card |
| `tb-eyebrow` | Small caps above a title, such as "Step 1 of 3" |
| `tb-title`, `tb-subtitle` | One title per screen; subtitles inside cards |
| `tb-body`, `tb-muted` | Body text and secondary text |
| `tb-code` | Inline code or a link to paste |

## Actions

| Class | Use |
|---|---|
| `tb-actions` | The row of buttons at the end of a card |
| `tb-btn tb-btn--primary` | The one main action. One per card |
| `tb-btn tb-btn--secondary` | An alternative the user may want |
| `tb-btn tb-btn--ghost` | A way out, such as "Skip for now" |
| `tb-link` | A text action inside a sentence |

Every button carries `data-action` naming what it does.

## Feedback

| Class | Use |
|---|---|
| `tb-banner` | Neutral information. Holds a `tb-subtitle` or bold line and a `tb-body` |
| `tb-banner tb-banner--warn` | Something blocks the user and needs a person to act, such as admin approval |
| `tb-badge`, `tb-badge--accent` | A short status label |

## Forms and progress

| Class | Use |
|---|---|
| `tb-field`, `tb-label`, `tb-input` | A labeled input |
| `tb-steps` with `tb-step`, `tb-step--done`, `tb-step--current` | The onboarding progress bar, as `<ol>` and `<li>` |
| `tb-list` | A bulleted or numbered list |
| `tb-hidden` | Hidden until an action shows it |

## Example: an onboarding step

```html
<header class="tb-topbar"><span class="tb-logo">Tallybird</span></header>
<main class="tb-page tb-stack">
  <ol class="tb-steps"><li class="tb-step tb-step--current"></li><li class="tb-step"></li><li class="tb-step"></li></ol>
  <section class="tb-card">
    <p class="tb-eyebrow">Step 1 of 3</p>
    <h1 class="tb-title">Connect your calendar</h1>
    <p class="tb-body">Tallybird joins the meetings on your calendar and writes the notes for you.</p>
    <div class="tb-actions">
      <button class="tb-btn tb-btn--primary" data-action="connect">Connect calendar</button>
    </div>
  </section>
</main>
```
