# Social Emoji And Reaction Design

## Goal

Add Discord-style emoji shortcodes to social comments and replies, and expand the existing anchored reaction system so readers can use a broader emoji set from the reader UI.

This design replaces the earlier GIF direction for the MVP because Tenor is no longer accepting new API clients, and the user chose to prioritize an emoji-first social experience instead.

## Scope

This work includes two related features:

1. Comment and reply rendering for `:shortcode:` emoji tokens such as `:skull:` and `:nerd:`.
2. A richer anchored reaction picker backed by the existing reaction API and WebSocket flow.

This work does not include:

- GIF provider integration.
- Custom hosted emoji images in the MVP.
- Rich-text comment storage.
- Multi-level replies beyond the current one-level thread model.

## Recommended Approach

### Approach A: Frontend shortcode rendering with expanded reaction types

Keep comment content stored as plain text. Parse supported `:shortcode:` tokens at render time in the Readest UI. Expand the backend reaction type allowlist and the frontend reaction picker so the anchored reaction feature supports a broader emoji set.

Pros:

- Smallest change to the current architecture.
- No comment schema migration.
- Existing comments remain valid.
- Easy to extend with more shortcodes later.

Cons:

- Rendering logic lives in the client.
- Unknown shortcodes are only handled visually, not validated at write time.

### Approach B: Normalize shortcodes on write

Convert `:shortcode:` tokens to Unicode before storing comment content.

Pros:

- Simpler rendering path.
- No runtime parsing needed when displaying comments.

Cons:

- Original shortcode text is lost.
- Editing becomes less Discord-like.
- Makes later custom emoji support harder.

### Approach C: Structured comment content

Store comments as structured segments with text and emoji tokens.

Pros:

- Best long-term path for custom emoji and richer formatting.
- Clear semantics for future rendering upgrades.

Cons:

- Too large a redesign for the current comment system.
- Requires backend, storage, type, and rendering changes across both repos.

### Decision

Use Approach A.

It delivers the requested Discord-style feel with the smallest correct change, preserves the existing comment data model, and builds directly on the anchored reaction system that already exists.

## Current System Context

The current social system already provides:

- Plain-text comments and one-level replies stored in `social.db`.
- A fixed-set anchored reaction system with backend validation.
- Real-time updates over WebSocket.
- Readest UI components for comment composition, thread rendering, reaction badges, and inline reaction actions.

Comments currently render `comment.content` as plain text. Reactions already have their own data model and API, so the emoji work should preserve the split between comment content and anchor-level reactions.

## Architecture

The feature stays split into two independent but coordinated units:

1. Comment shortcode rendering.
2. Expanded anchored reactions.

Comment content remains a plain string in storage and over the API. The frontend introduces an emoji registry and a small parser that transforms supported `:shortcode:` tokens into renderable pieces.

Anchored reactions keep their current backend-first shape:

`Annotator` or social UI -> `useSocial` -> FastAPI social routes -> SQLite `reactions` table -> WebSocket broadcast -> Zustand store -> rendered badges and thread UI.

Only the allowed reaction set and picker behavior change.

## Comment Shortcodes

### User experience

Users can type normal comment text with inline emoji shortcodes:

- `That ending was cursed :skull:`
- `bro is literally me :nerd:`
- `this chapter cooked :fire:`

Display behavior:

1. Supported shortcodes render as Unicode emoji.
2. Unsupported shortcodes remain plain text.
3. Text outside shortcodes renders unchanged.
4. Adjacent or repeated shortcodes render in order.
5. Replies use the same parsing and rendering behavior as top-level comments.

Edit behavior:

1. The edit textarea shows the original raw text with shortcodes.
2. Saving the edit stores the raw shortcode text again.
3. Rendering after save re-applies parsing.

This preserves the Discord-like mental model where users type `:name:` and see emoji in the rendered message without losing the typed representation during edits.

### Emoji registry

The frontend should define a shared emoji registry keyed by shortcode name. Initial entries should be explicit and curated rather than exhaustive.

Example MVP registry:

- `skull` -> `💀`
- `nerd` -> `🤓`
- `fire` -> `🔥`
- `sob` -> `😭`
- `clap` -> `👏`
- `heart` -> `❤️`
- `angry` -> `😡`
- `wow` -> `😮`
- `think` -> `🤔`

The registry should be structured so a later phase can add metadata for custom emoji images without changing the parser contract.

Recommended shape:

```ts
type EmojiDefinition = {
  shortcode: string;
  unicode: string;
  aliases?: string[];
};
```

### Parsing rules

The parser should be intentionally simple for MVP.

Rules:

1. Match tokens in the form `:name:` where `name` is made of lowercase letters, numbers, `_`, `-`, or `+` if desired by the implementation.
2. Replace only known registry entries.
3. Leave unknown tokens untouched.
4. Do not support nested or escaped shortcode syntax in MVP.
5. Do not interpret markdown, links, or other formatting syntax.

The output should be renderable as a sequence of text spans and emoji spans, not raw HTML.

## Anchored Reactions

### User experience

The existing anchored reaction feature becomes more expressive by adding more emoji options and making the picker feel closer to Discord.

Behavior:

1. Users select text or interact with an anchor area.
2. The reaction UI opens a compact picker.
3. Users choose one emoji reaction.
4. The existing uniqueness rule remains: one reaction per user per anchor per reaction type.
5. Reaction badges update in real time through the existing REST plus WebSocket flow.

### Reaction source of truth

The backend remains the source of truth for which reaction types are valid. The frontend picker should be driven from the same conceptual registry so comment shortcodes and reactions share a consistent emoji vocabulary where practical.

The current reaction set is:

- `heart`
- `cry`
- `wow`
- `angry`
- `fire`
- `skull`
- `think`
- `clap`

The implementation should expand this set in a deliberate MVP list. A reasonable starting set is:

- existing set above
- `nerd`
- `laugh`
- `eyes`
- `pray`
- `sparkles`

The final list should stay small enough that the picker remains fast and visually readable.

### API behavior

The reaction endpoints do not need shape changes. They only need expanded validation for additional reaction names.

Existing flow remains valid:

- `GET /api/social/books/{slug}/chapters/{cid}/reactions`
- `POST /api/social/books/{slug}/chapters/{cid}/reactions`
- `DELETE /api/social/reactions/{id}`
- WebSocket `reaction` and `reaction_deleted` events

No schema change is required if the reaction type continues to be stored as text.

## Component Design

### Readest frontend

Expected frontend additions or changes:

1. Add a shared emoji registry utility for shortcodes and reaction metadata.
2. Add a small comment content renderer that tokenizes and renders shortcode-aware output.
3. Update `CommentThread.tsx` to use the new renderer for display mode.
4. Keep `CommentInput.tsx` as plain text input for MVP.
5. Expand the reaction picker UI used from the annotator/social panel.
6. Update reaction badge rendering to display the expanded emoji set cleanly.

This keeps emoji parsing out of the input component and contained in display logic plus shared metadata.

### Backend

Expected backend changes are limited:

1. Expand the allowed reaction type set in `vvr_scraper/social/db.py` and related typing if present.
2. Update request typing in `vvr_scraper/social/models.py` if reaction literals are modeled there.
3. Ensure API responses continue returning reaction types unchanged.
4. Keep comments stored as raw text with no shortcode transformation.

## Data Model

### Comments

No storage changes.

`comments.content` remains plain text, including any literal `:shortcode:` tokens.

This preserves backward compatibility and avoids a migration.

### Reactions

No table shape changes.

`reaction_type` remains text, but the valid value set expands.

## Error Handling

Comment parsing errors should fail soft in the UI:

1. If parsing fails for any reason, render the raw text.
2. Unknown shortcodes are not errors.
3. Empty comments are still rejected by the existing validation rules.

Reaction handling should stay strict at the API boundary:

1. Unsupported reaction types are rejected by the backend.
2. The frontend should avoid surfacing unsupported options in the picker.
3. If frontend and backend drift, the UI should show a normal mutation failure instead of corrupting state.

## Testing Strategy

### Frontend

Add focused tests for:

1. Rendering plain comments with no shortcodes.
2. Rendering known shortcodes as emoji.
3. Leaving unknown shortcodes unchanged.
4. Rendering mixed text and multiple emoji tokens in order.
5. Editing comments without losing raw shortcode text.
6. Displaying the expanded reaction picker and badges.

### Backend

Add or update tests for:

1. Expanded reaction type acceptance.
2. Rejection of unsupported reaction types.
3. Existing reaction uniqueness behavior still holding.
4. WebSocket reaction broadcasts for new reaction types.

### End-to-end verification

Manual verification should cover:

1. Posting text-only comments.
2. Posting comments with known shortcodes.
3. Posting replies with shortcodes.
4. Editing comments that contain shortcodes.
5. Creating and removing new reaction types.
6. Seeing reaction and comment updates in another open client through WebSocket.

## Rollout Notes

The feature is additive and low risk because:

- Existing comment records remain valid.
- Existing reaction records remain valid.
- No migration is needed.
- The parser is isolated to display logic.

The main regression risk is frontend inconsistency between the emoji registry, rendered shortcodes, and picker options. That risk should be controlled by keeping one shared registry for emoji metadata.

## Future Extensions

This design intentionally keeps a clean path for later improvements:

1. Shortcode autocomplete while typing comments.
2. Emoji category grouping in the reaction picker.
3. Custom emoji image support with hosted assets.
4. Shared emoji metadata coming from the backend instead of being frontend-defined.
5. Converting the comment renderer into a richer structured formatting pipeline if the social feature expands further.
