# Phase 33 — ordinary-background replacement beta

This checkpoint makes the existing local person-segmentation experiment usable from the private studio without misrepresenting it as a production effect.

## User flow

1. On **Create**, choose **Replace background · Beta** for a presenter filmed against a white wall, timber wall or ordinary room.
2. Assign one presenter video and a different image or video background. The editor reserves the background as a layer and plans speech only from the presenter.
3. The ordinary preview is rendered with the original background.
4. On **Review**, explicitly create a two-second local comparison. It shows the source, the presenter over the chosen background and the raw person mask.
5. Inspect hair, hands, held objects, background holes and temporal flicker. Mark the sample usable or retain the original.

## Safety and product boundary

The comparison is CPU-only, single-threaded, bounded to 24 sampled frames and a 20-second process budget. The private API image and worker image package the same pinned Apache-2.0 PPHumanSeg model at build time; runtime requests never download weights. The API starts a killable isolated comparison child, while the existing media-volume lock permits only one comparison at a time. The cache binds the exact source sample and chosen background. It makes no hosted model call, changes no original, creates no edit version and creates no final export.

PPHumanSeg is a person mask, not a production hair matte or general foreground-object model. It can remove held products, fingers and fine hair. Therefore this checkpoint deliberately does **not** apply the result to the timeline or final export. Shipping full-reel replacement still requires representative real-footage acceptance, stable full-frame masks, held-object preservation, measured render cost and a persisted human approval/fallback contract.

Prepared green/blue-screen footage remains a separate advanced **Chroma key** path and continues to render through the existing deterministic FFmpeg keyer.
