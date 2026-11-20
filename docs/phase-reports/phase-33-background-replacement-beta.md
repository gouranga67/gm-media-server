# Phase 33 — ordinary-background replacement beta

This checkpoint makes the existing local person-segmentation experiment usable from the private studio without misrepresenting it as an automatic production effect. It now supports an explicitly accepted full-reel beta while retaining the original edit version.

## User flow

1. On **Create**, choose **Replace background · Beta** for a presenter filmed against a white wall, timber wall or ordinary room.
2. Assign one presenter video and a different image or video background. The editor reserves the background as a layer and plans speech only from the presenter.
3. The ordinary preview is rendered with the original background.
4. On **Review**, explicitly create a two-second local comparison. It shows the source, the presenter over the chosen background and the raw person mask.
5. Inspect hair, hands, held objects, background holes and temporal flicker. Mark the sample usable or retain the original.
6. After accepting the sample, choose **Apply background to full reel**. The server queues a new zero-token edit version and processes every assembled frame locally.
7. Review the entire replacement preview. Captions, B-roll, picture layers and effects are composed after the matte. If a longer movement fails, choose **Restore original background** to queue another safe preview. Earlier versions remain available throughout.

## Safety and product boundary

The comparison is CPU-only, single-threaded, bounded to 24 sampled frames and a 20-second process budget. The private API image and worker image package the same pinned Apache-2.0 PPHumanSeg model at build time; runtime requests never download weights. The API starts a killable isolated comparison child, while the existing media-volume lock permits only one comparison at a time. The cache binds the exact source sample, edit-plan hash and chosen background. It makes no hosted model call and changes no original.

Full-reel application is accepted only when that bound comparison still matches the latest ready edit and background. It creates a new version that reuses the saved edit plan, renders a frame-aligned lossless grayscale matte, and composites before upper visual layers. The original preview is not overwritten. Final export uses the same explicit composition state and regenerates a delivery-resolution matte. The manifest records local model, dimensions, frame count, runtime and model hash. Application and fallback are both explicit user actions; the editor agent cannot silently enable the effect.

PPHumanSeg is a person mask, not a production hair matte or general foreground-object model. It can remove held products, fingers and fine hair. A successful two-second sample does not prove every frame. The feature therefore remains labelled **Beta**, stays off by default, requires a human sample decision and whole-reel review, and preserves a one-action fallback. Wider production approval still requires representative footage with fast hair, hands, product holding and partial occlusion plus measured appliance render cost.

Prepared green/blue-screen footage remains a separate advanced **Chroma key** path and continues to render through the existing deterministic FFmpeg keyer.
