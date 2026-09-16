# Site Builder

> **Outcome:** export and locally verify a responsive page against a written
> client/business acceptance checklist.

![Site Builder workspace](../img/agent-webdesign.png)

## Prerequisites

- One page goal, audience, CTA, required content, brand constraints, and output
  boundary.
- Authoritative copy/data and rights for media/fonts.
- A plan for hosting, forms, analytics, privacy, and security outside generation.

## Control atlas

| Control/tab | Meaning |
|---|---|
| Brief/provider/model | Generates a proposed implementation; recommendations optimise the task route |
| HTML / CSS / JS | Separate editable outputs that must work together |
| Copy All | Copies the current complete proposal for review/use |
| Save .html | Writes a local deliverable; verify embedded/linked CSS and JS behavior |
| Clear | Clears visible output after saving; not undo |
| Stop | Requests local streaming cancellation |

## Worked run

1. Write a bounded brief: one audience, one page, content hierarchy, responsive
   breakpoints, CTA, accessibility criteria, allowed libraries, and prohibited
   claims/tracking.
2. Generate once. Inspect HTML semantics first, then CSS responsiveness, then JS
   behavior and failure states.
3. Save the page. Open it locally and test narrow/mobile, desktop, keyboard,
   visible focus, zoom, form validation, empty/error/loading states, and links.
4. Remove invented testimonials, customers, awards, analytics, privacy language,
   prices, or guarantees.
5. Run appropriate security/accessibility/performance checks before hosting.

## How to read the output

Valid-looking code is a draft. A local page does not prove deployment,
analytics, form delivery, consent compliance, search indexing, security, or
conversion. Generated explanations are not test results.

## Acceptance checklist

- [ ] Content hierarchy and CTA match the brief.
- [ ] Keyboard, focus, labels, contrast, alt text, and zoom are usable.
- [ ] No overflow at target widths; touch targets and reduced motion are handled.
- [ ] Links/forms have real destinations and safe validation/error behavior.
- [ ] No secrets, fabricated proof, or unapproved tracking is embedded.
- [ ] The saved file works independently from the Imprint editor.

## Cost, cancellation, and gates

Text generation is only part of fulfilment cost; include design/review, assets,
hosting, testing, fixes, client revisions, and support. Humans approve claims,
data collection, credentials, deployment, domain changes, and client delivery.

## Verification

Open the saved file in a real browser and complete the acceptance checklist at
mobile and desktop widths using mouse, keyboard, and zoom.

## Common failures

**Page looks good but actions fail:** test integrated files, forms, and network
failure states.  
**Mobile clips:** add explicit responsive constraints and test the saved file.  
**The model invented content:** replace it with authoritative copy/data before
delivery.

## Done when

The saved page passes the written checklist in a real browser and the remaining
deployment/instrumentation work is explicit.

## Next action

For a client offer, continue to [Client Gigs](27-client-gigs.md); for demand
testing, define the funnel in [Design a fair experiment](32-experiment.md).
