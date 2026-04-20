# Social Emoji And Reaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Discord-style `:shortcode:` emoji rendering for comments and replies, and expand the anchored reaction system with a richer emoji set in both backend validation and the Readest UI.

**Architecture:** Keep comments stored as plain text and render emoji shortcodes only in the frontend display layer. Preserve the current reaction API and database schema, but expand the allowed reaction type set and drive the frontend reaction picker and badge display from one shared emoji registry so the UI stays consistent.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, React, TypeScript, Zustand, Vitest, Testing Library

---

## File Map

### Backend repo: `/home/tung/Data/dev/backup/Valvrareteam.net-crawler`

- Modify: `vvr_scraper/social/models.py`
  - Expand `ReactionType` literal with the new emoji-backed reaction names.
- Modify: `vvr_scraper/social/db.py`
  - Expand `REACTION_TYPES` validation set.
- Modify: `tests/test_social_db.py`
  - Add DB-level tests for accepted and rejected reaction types.
- Modify: `tests/test_social_api.py`
  - Add API tests for new reaction types.
- Modify: `tests/test_social_websocket.py`
  - Add WebSocket broadcast coverage for a newly added reaction type.

### Frontend repo: `/home/tung/Data/dev/backup/readest`

- Create: `apps/readest-app/src/components/social/emoji.ts`
  - Shared emoji registry and helper lookups for shortcodes and reactions.
- Create: `apps/readest-app/src/components/social/renderCommentContent.tsx`
  - Tokenize plain text comment content and render supported `:shortcode:` entries as React nodes.
- Modify: `apps/readest-app/src/types/social.ts`
  - Expand `SocialReactionType` union to match backend.
- Modify: `apps/readest-app/src/components/social/ReactionBar.tsx`
  - Replace duplicated hard-coded options with shared registry-driven reaction picker data.
- Modify: `apps/readest-app/src/components/social/ReactionBadges.tsx`
  - Replace duplicated emoji map with registry lookup.
- Modify: `apps/readest-app/src/components/social/CommentThread.tsx`
  - Use the new comment renderer in display mode while preserving raw shortcode text in edit mode.
- Create: `apps/readest-app/src/__tests__/components/social/render-comment-content.test.tsx`
  - Parser and rendering behavior tests.
- Create: `apps/readest-app/src/__tests__/components/social/reaction-ui.test.tsx`
  - Reaction bar and badge rendering tests for the expanded emoji set.
- Modify: `apps/readest-app/src/__tests__/hooks/use-social.test.tsx`
  - Add hook coverage for the new reaction type names.

## Task 1: Expand backend reaction validation

**Files:**
- Modify: `vvr_scraper/social/models.py`
- Modify: `vvr_scraper/social/db.py`
- Test: `tests/test_social_db.py`

- [ ] **Step 1: Write the failing DB tests for the new reaction types**

Add these tests to `tests/test_social_db.py`:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("reaction_type", ["nerd", "laugh", "eyes", "pray", "sparkles"])
async def test_create_reaction_accepts_new_emoji_types(tmp_path, reaction_type):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    reaction_id = await db.create_reaction(user_id, "book-1", "chapter-1", "anchor", reaction_type)

    reaction = await db.get_reaction(reaction_id)
    assert reaction is not None
    assert reaction["reaction_type"] == reaction_type


@pytest.mark.asyncio
async def test_create_reaction_still_rejects_unknown_emoji_type(tmp_path):
    db = SocialDatabaseManager(db_path=str(tmp_path / "social.db"))
    await db.init_db()
    user_id = await db.create_user_for_test("alice")

    with pytest.raises(ValueError, match="invalid reaction type"):
        await db.create_reaction(user_id, "book-1", "chapter-1", "anchor", "tableflip")
```

- [ ] **Step 2: Run the DB tests to verify they fail**

Run:

```bash
pytest tests/test_social_db.py::test_create_reaction_accepts_new_emoji_types -v
```

Expected: FAIL because `db.py` still rejects the new reaction types.

- [ ] **Step 3: Expand the backend reaction type definitions**

Update `vvr_scraper/social/models.py`:

```python
ReactionType = Literal[
    "heart",
    "cry",
    "wow",
    "angry",
    "fire",
    "skull",
    "think",
    "clap",
    "nerd",
    "laugh",
    "eyes",
    "pray",
    "sparkles",
]
```

Update `vvr_scraper/social/db.py`:

```python
REACTION_TYPES = {
    "heart",
    "cry",
    "wow",
    "angry",
    "fire",
    "skull",
    "think",
    "clap",
    "nerd",
    "laugh",
    "eyes",
    "pray",
    "sparkles",
}
```

- [ ] **Step 4: Run the DB tests to verify they pass**

Run:

```bash
pytest tests/test_social_db.py::test_create_reaction_accepts_new_emoji_types tests/test_social_db.py::test_create_reaction_still_rejects_unknown_emoji_type -v
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit the backend validation change**

```bash
git add tests/test_social_db.py vvr_scraper/social/models.py vvr_scraper/social/db.py
git commit -m "feat: expand social reaction emoji set"
```

## Task 2: Cover new reaction types through API and WebSocket

**Files:**
- Modify: `tests/test_social_api.py`
- Modify: `tests/test_social_websocket.py`

- [ ] **Step 1: Write the failing API and WebSocket tests**

Add this test to `tests/test_social_api.py` inside `TestSocialRoutes` or the equivalent reaction test section:

```python
def test_create_reaction_accepts_new_emoji_type(client, member_token):
    RATE_BUCKETS.clear()
    resp = client.post(
        "/api/social/books/book-1/chapters/ch-1/reactions",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"anchor": "epubcfi(/6/8)", "reaction_type": "nerd"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["reaction_type"] == "nerd"
```

Add this test to `tests/test_social_websocket.py`:

```python
def test_new_reaction_type_broadcasts_over_websocket(client, member_token):
    with client.websocket_connect("/ws/social/book-1/ch-1") as ws:
        response = client.post(
            "/api/social/books/book-1/chapters/ch-1/reactions",
            headers={"Authorization": f"Bearer {member_token}"},
            json={"anchor": "epubcfi(/6/2)", "reaction_type": "sparkles"},
        )

        assert response.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "reaction"
        assert msg["data"]["reaction_type"] == "sparkles"
```

- [ ] **Step 2: Run the API and WebSocket tests**

Run:

```bash
pytest tests/test_social_api.py::test_create_reaction_accepts_new_emoji_type tests/test_social_websocket.py::test_new_reaction_type_broadcasts_over_websocket -v
```

Expected: PASS if Task 1 is complete. If either test fails, fix that failure before moving on.

- [ ] **Step 3: Commit the new backend coverage**

```bash
git add tests/test_social_api.py tests/test_social_websocket.py
git commit -m "test: cover expanded social reactions"
```

## Task 3: Add a shared frontend emoji registry

**Files:**
- Create: `apps/readest-app/src/components/social/emoji.ts`
- Modify: `apps/readest-app/src/types/social.ts`
- Test: `apps/readest-app/src/__tests__/components/social/reaction-ui.test.tsx`

- [ ] **Step 1: Write the failing frontend test for new reaction options**

Create `apps/readest-app/src/__tests__/components/social/reaction-ui.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import ReactionBar from '@/components/social/ReactionBar';
import ReactionBadges from '@/components/social/ReactionBadges';

describe('social reaction UI', () => {
  test('renders expanded reaction picker options', () => {
    render(<ReactionBar onReact={vi.fn()} />);

    expect(screen.getByTitle('Nerd')).toBeInTheDocument();
    expect(screen.getByTitle('Sparkles')).toBeInTheDocument();
  });

  test('renders badges with expanded emoji set', () => {
    render(
      <ReactionBadges
        reactions={[
          {
            id: 'r1',
            anchor: 'a1',
            createdAt: '2026-04-19T00:00:00Z',
            reactionType: 'nerd',
            user: { id: 'u1', username: 'alice', displayName: 'Alice', role: 'member' },
          },
          {
            id: 'r2',
            anchor: 'a1',
            createdAt: '2026-04-19T00:00:00Z',
            reactionType: 'nerd',
            user: { id: 'u2', username: 'bob', displayName: 'Bob', role: 'member' },
          },
        ]}
      />,
    );

    expect(screen.getByText(/🤓 2/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the frontend reaction UI test to verify it fails**

Run from `/home/tung/Data/dev/backup/readest`:

```bash
pnpm --filter @readest/readest-app test -- --run src/__tests__/components/social/reaction-ui.test.tsx
```

Expected: FAIL because `SocialReactionType`, `ReactionBar`, and `ReactionBadges` do not yet support `nerd` or `sparkles`.

- [ ] **Step 3: Add the shared emoji registry and expand reaction types**

Create `apps/readest-app/src/components/social/emoji.ts`:

```ts
import type { SocialReactionType } from '@/types/social';

export type EmojiDefinition = {
  shortcode: string;
  unicode: string;
  label: string;
  aliases?: string[];
  reactionType?: SocialReactionType;
};

export const EMOJI_REGISTRY: Record<string, EmojiDefinition> = {
  heart: { shortcode: 'heart', unicode: '❤️', label: 'Heart', reactionType: 'heart' },
  cry: { shortcode: 'cry', unicode: '😢', label: 'Cry', reactionType: 'cry' },
  wow: { shortcode: 'wow', unicode: '😮', label: 'Wow', reactionType: 'wow' },
  angry: { shortcode: 'angry', unicode: '😠', label: 'Angry', reactionType: 'angry' },
  fire: { shortcode: 'fire', unicode: '🔥', label: 'Fire', reactionType: 'fire' },
  skull: { shortcode: 'skull', unicode: '💀', label: 'Skull', reactionType: 'skull' },
  think: { shortcode: 'think', unicode: '🤔', label: 'Think', reactionType: 'think' },
  clap: { shortcode: 'clap', unicode: '👏', label: 'Clap', reactionType: 'clap' },
  nerd: { shortcode: 'nerd', unicode: '🤓', label: 'Nerd', reactionType: 'nerd' },
  laugh: { shortcode: 'laugh', unicode: '😂', label: 'Laugh', reactionType: 'laugh' },
  eyes: { shortcode: 'eyes', unicode: '👀', label: 'Eyes', reactionType: 'eyes' },
  pray: { shortcode: 'pray', unicode: '🙏', label: 'Pray', reactionType: 'pray' },
  sparkles: { shortcode: 'sparkles', unicode: '✨', label: 'Sparkles', reactionType: 'sparkles' },
  sob: { shortcode: 'sob', unicode: '😭', label: 'Sob' },
};

export const REACTION_EMOJI_OPTIONS = Object.values(EMOJI_REGISTRY).filter(
  (emoji): emoji is EmojiDefinition & { reactionType: SocialReactionType } => Boolean(emoji.reactionType),
);

export function getEmojiByShortcode(shortcode: string) {
  return EMOJI_REGISTRY[shortcode] ?? null;
}

export function getReactionEmoji(reactionType: string) {
  return EMOJI_REGISTRY[reactionType]?.unicode ?? reactionType;
}

export function getReactionLabel(reactionType: string) {
  return EMOJI_REGISTRY[reactionType]?.label ?? reactionType;
}
```

Update `apps/readest-app/src/types/social.ts`:

```ts
export type SocialReactionType =
  | 'heart'
  | 'cry'
  | 'wow'
  | 'angry'
  | 'fire'
  | 'skull'
  | 'think'
  | 'clap'
  | 'nerd'
  | 'laugh'
  | 'eyes'
  | 'pray'
  | 'sparkles';
```

- [ ] **Step 4: Update the reaction UI components to use the shared registry**

Update `apps/readest-app/src/components/social/ReactionBar.tsx`:

```tsx
import React from 'react';
import type { SocialReactionType } from '@/types/social';
import { REACTION_EMOJI_OPTIONS } from './emoji';

const ReactionBar = ({ onReact }: { onReact: (reactionType: SocialReactionType) => void }) => (
  <div className='flex flex-wrap gap-2 p-2'>
    {REACTION_EMOJI_OPTIONS.map((reaction) => (
      <button
        key={reaction.reactionType}
        type='button'
        className='btn btn-ghost btn-sm'
        onClick={() => onReact(reaction.reactionType)}
        title={reaction.label}
      >
        <span aria-hidden='true'>{reaction.unicode}</span>
      </button>
    ))}
  </div>
);

export default ReactionBar;
```

Update `apps/readest-app/src/components/social/ReactionBadges.tsx`:

```tsx
import React from 'react';
import type { SocialReaction } from '@/types/social';
import { getReactionEmoji } from './emoji';

const ReactionBadges = ({ reactions }: { reactions: SocialReaction[] }) => {
  const grouped = reactions.reduce<Record<string, number>>((acc, reaction) => {
    acc[reaction.reactionType] = (acc[reaction.reactionType] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className='flex flex-wrap gap-1'>
      {Object.entries(grouped).map(([reactionType, count]) => (
        <span key={reactionType} className='badge badge-outline text-xs'>
          {getReactionEmoji(reactionType)} {count}
        </span>
      ))}
    </div>
  );
};

export default ReactionBadges;
```

- [ ] **Step 5: Run the reaction UI test to verify it passes**

Run:

```bash
pnpm --filter @readest/readest-app test -- --run src/__tests__/components/social/reaction-ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit the shared emoji registry work**

```bash
git -C /home/tung/Data/dev/backup/readest add \
  apps/readest-app/src/components/social/emoji.ts \
  apps/readest-app/src/components/social/ReactionBar.tsx \
  apps/readest-app/src/components/social/ReactionBadges.tsx \
  apps/readest-app/src/types/social.ts \
  apps/readest-app/src/__tests__/components/social/reaction-ui.test.tsx
git -C /home/tung/Data/dev/backup/readest commit -m "feat: centralize social emoji metadata"
```

## Task 4: Add comment shortcode parsing and rendering

**Files:**
- Create: `apps/readest-app/src/components/social/renderCommentContent.tsx`
- Modify: `apps/readest-app/src/components/social/CommentThread.tsx`
- Test: `apps/readest-app/src/__tests__/components/social/render-comment-content.test.tsx`

- [ ] **Step 1: Write the failing render tests**

Create `apps/readest-app/src/__tests__/components/social/render-comment-content.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { renderCommentContent } from '@/components/social/renderCommentContent';

describe('renderCommentContent', () => {
  test('renders plain text without modification', () => {
    render(<div>{renderCommentContent('plain text only')}</div>);
    expect(screen.getByText('plain text only')).toBeInTheDocument();
  });

  test('renders known shortcodes as emoji', () => {
    render(<div>{renderCommentContent('that was cursed :skull:')}</div>);
    expect(screen.getByText('that was cursed ')).toBeInTheDocument();
    expect(screen.getByText('💀')).toBeInTheDocument();
  });

  test('leaves unknown shortcodes untouched', () => {
    render(<div>{renderCommentContent('hello :tableflip:')}</div>);
    expect(screen.getByText('hello :tableflip:')).toBeInTheDocument();
  });

  test('renders multiple shortcodes in order', () => {
    render(<div>{renderCommentContent(':fire: wow :nerd:')}</div>);
    expect(screen.getByText('🔥')).toBeInTheDocument();
    expect(screen.getByText('🤓')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the render tests to verify they fail**

Run:

```bash
pnpm --filter @readest/readest-app test -- --run src/__tests__/components/social/render-comment-content.test.tsx
```

Expected: FAIL because `renderCommentContent` does not exist yet.

- [ ] **Step 3: Implement the comment renderer**

Create `apps/readest-app/src/components/social/renderCommentContent.tsx`:

```tsx
import React from 'react';
import { getEmojiByShortcode } from './emoji';

const SHORTCODE_RE = /:([a-z0-9_+-]+):/g;

export function renderCommentContent(content: string) {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(SHORTCODE_RE)) {
    const fullMatch = match[0];
    const shortcode = match[1];
    const start = match.index ?? 0;
    const emoji = getEmojiByShortcode(shortcode);

    if (!emoji) {
      continue;
    }

    if (start > lastIndex) {
      nodes.push(content.slice(lastIndex, start));
    }

    nodes.push(
      <span key={`${shortcode}-${start}`} aria-label={emoji.label} role='img'>
        {emoji.unicode}
      </span>,
    );
    lastIndex = start + fullMatch.length;
  }

  if (lastIndex === 0) {
    return content;
  }

  if (lastIndex < content.length) {
    nodes.push(content.slice(lastIndex));
  }

  return nodes;
}
```

- [ ] **Step 4: Use the renderer in comment display mode only**

Update the non-editing branch in `apps/readest-app/src/components/social/CommentThread.tsx`:

```tsx
import { renderCommentContent } from './renderCommentContent';

// ...inside CommentItem
      ) : (
        <p className='text-sm whitespace-pre-wrap mb-1'>{renderCommentContent(comment.content)}</p>
      )}
```

Do not change the edit textarea state. It must keep using raw `comment.content`.

- [ ] **Step 5: Run the renderer test and the existing social hook test**

Run:

```bash
pnpm --filter @readest/readest-app test -- --run \
  src/__tests__/components/social/render-comment-content.test.tsx \
  src/__tests__/hooks/use-social.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit the comment shortcode rendering change**

```bash
git -C /home/tung/Data/dev/backup/readest add \
  apps/readest-app/src/components/social/renderCommentContent.tsx \
  apps/readest-app/src/components/social/CommentThread.tsx \
  apps/readest-app/src/__tests__/components/social/render-comment-content.test.tsx
git -C /home/tung/Data/dev/backup/readest commit -m "feat: render emoji shortcodes in comments"
```

## Task 5: Update the social hook tests for the expanded reaction names

**Files:**
- Modify: `apps/readest-app/src/__tests__/hooks/use-social.test.tsx`

- [ ] **Step 1: Add a hook test that posts one of the new reaction types**

Add this test to `apps/readest-app/src/__tests__/hooks/use-social.test.tsx`:

```tsx
test('creates an expanded emoji reaction', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'r2', reactionType: 'sparkles' }), { status: 200 }),
    ),
  );

  const { result } = renderHook(() => useSocial());
  const res = await result.current.createReaction('book-1', 'ch-1', 'anchor-1', 'sparkles');

  expect(res.reactionType).toBe('sparkles');
});
```

- [ ] **Step 2: Run the hook test**

Run:

```bash
pnpm --filter @readest/readest-app test -- --run src/__tests__/hooks/use-social.test.tsx
```

Expected: PASS if `SocialReactionType` was expanded correctly in Task 3.

- [ ] **Step 3: Commit the hook test update**

```bash
git -C /home/tung/Data/dev/backup/readest add apps/readest-app/src/__tests__/hooks/use-social.test.tsx
git -C /home/tung/Data/dev/backup/readest commit -m "test: cover expanded social emoji reactions"
```

## Task 6: End-to-end verification and cleanup

**Files:**
- Modify only if verification finds a bug.

- [ ] **Step 1: Run the full targeted backend verification**

Run from `/home/tung/Data/dev/backup/Valvrareteam.net-crawler`:

```bash
pytest tests/test_social_db.py tests/test_social_api.py tests/test_social_websocket.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the full targeted frontend verification**

Run from `/home/tung/Data/dev/backup/readest`:

```bash
pnpm --filter @readest/readest-app test -- --run \
  src/__tests__/components/social/render-comment-content.test.tsx \
  src/__tests__/components/social/reaction-ui.test.tsx \
  src/__tests__/hooks/use-social.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Manually verify the web social flow**

Run the existing apps, then verify:

```bash
# backend repo
uv run python -m vvr_scraper.cli web

# readest repo
pnpm dev-web
```

Manual checks:

1. Log in from the Readest web UI.
2. Post a comment containing `:skull:` and confirm it renders as `💀` in the thread.
3. Post a comment containing `:tableflip:` and confirm it remains literal text.
4. Edit a comment containing `:nerd:` and confirm the textarea still shows `:nerd:`.
5. Open the anchored reaction picker and confirm `🤓` and `✨` are available.
6. Add one of the new reactions and confirm the badge count updates.
7. Open a second client and confirm comment and reaction updates arrive over WebSocket.

- [ ] **Step 4: Commit final fixes if verification uncovered anything**

If verification required code changes:

```bash
git add <verified-files>
git commit -m "fix: polish social emoji integration"
```

If verification found no further issues, skip this step.

## Self-Review

Spec coverage check:

- Comment shortcode rendering: covered by Tasks 3 and 4.
- Expanded anchored reaction set: covered by Tasks 1, 2, 3, and 5.
- Shared emoji metadata to avoid drift: covered by Task 3.
- Backward compatibility and no schema migration: preserved by Tasks 1 through 5.
- Error handling and verification: covered by Task 6.

Placeholder scan:

- No `TODO`, `TBD`, or deferred placeholders remain in the task steps.
- Each code-changing step includes concrete file paths and code snippets.
- Each verification step includes exact commands.

Type consistency check:

- Backend new reaction names are `nerd`, `laugh`, `eyes`, `pray`, `sparkles`.
- Frontend `SocialReactionType` uses the same names.
- Shared registry uses the same names for picker and badge rendering.
