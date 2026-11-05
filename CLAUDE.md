# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A single-page web app ("Bake My Fic!") that lets users paste an AO3 fanfic URL, optionally upload a cover image, and download the fic as an EPUB for Kindle. The UI is fully functional visually; the actual AO3 fetch and EPUB generation are currently simulated with `setTimeout`.

## How to run

Open `home.html` directly in a browser (no build step needed). The file loads `support.js` from the same directory, which pulls React 18 from unpkg at runtime.

## Architecture

The project uses the **dc-runtime** — a thin React wrapper whose compiled output lives in `support.js`. You should never edit `support.js` by hand; it is generated from `dc-runtime/src/*.ts` with:

```
cd dc-runtime && bun run build
```

### `.dc.html` file structure

Every Design Component is a single `.dc.html` file with two parts:

1. **`<x-dc>` block** — the HTML template, using:
   - `{{ expr }}` — interpolation (value or dotted path)
   - `<sc-if value="{{ expr }}">` — conditional render
   - `<sc-for list="{{ expr }}" as="item">` — list render; `$index` is also in scope
   - `<dc-import name="ComponentName" />` — embed a sibling `.dc.html` component
   - `<x-import from="url" component="ExportName" />` — load external JS/JSX at runtime
   - `<helmet>` — injects `<script>`, `<link>`, `<style>`, `<title>`, etc. into `<head>`
   - `style-hover="…"`, `style-focus="…"`, etc. — inline pseudo-class CSS (generates scoped rules)

2. **`<script type="text/x-dc" data-dc-script>`** — the component logic class:

```js
class Component extends DCLogic {
  state = { /* initial state */ };

  // lifecycle (mirrors React class component)
  componentDidMount() {}
  componentDidUpdate(prevProps) {}
  componentWillUnmount() {}

  // returns the flat object the template renders against (merged over props)
  renderVals() { return { ...this.state, someHandler: () => this.setState({…}) }; }
}
```

`this.setState(patch)` works like React's class `setState`. `this.props` holds props passed in from a parent DC. `renderVals()` is called on every render; its return value is what `{{ … }}` expressions resolve against.

### Current app state machine

Screen states: `link → loading → (error | details) → cover → generating → done`

`stepMap` maps each screen to one of 4 wizard steps. The EPUB generation and AO3 fetch are mocked; real implementation would replace the `setTimeout` calls in `start()` and `generate()`.

### CSS / theming

All colours are CSS custom properties on `:root` (light) and `[data-theme="dark"]`. The theme is toggled by `toggleTheme`, persisted to `localStorage` under the key `cookie-theme`, and applied to `document.documentElement.dataset.theme`.
