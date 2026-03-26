# KVizzing Visualizer — Product Requirements Document

## Overview

A web app for browsing, filtering, and exploring the KVizzing question archive. The primary audience is the KVizzing WhatsApp group members — people who asked or answered these questions and want to relive, search, and discover them.

---

## Goals

1. Make the question archive **browsable and searchable** without needing to scroll WhatsApp
2. Surface **stats and patterns** — who asks the most, what topics come up, which questions were hardest
3. Provide a **per-question view** that replays the discussion thread
4. Celebrate **highlights** — funniest questions, crowd favourites, fastest solves

---

## Data Source

All data comes from `KVizzingQuestion` JSON objects conforming to `v2/schema/schema.json`. The visualizer is read-only — it consumes pre-extracted data, it does not write back.

Primary input: `data/questions.json` — array of all questions sorted by `question.timestamp`.

---

## Pages & Views

### 1. Question Feed (Home)

The default landing page. A paginated/infinite-scroll list of question cards.

**Each card shows:**
- Question text (truncated if long)
- Asker name + date
- Topic badge (colour-coded by category)
- Difficulty badge (`easy` / `medium` / `hard`)
- Answer (collapsed by default, expandable)
- Key stats: wrong attempts, time to answer, participant count
- Reaction summary (e.g. `😂 ×3  ❤️ ×2`) if available
- Highlight badges if present (e.g. `crowd_favourite`, `funny`)

**Filter bar (persistent):**
- Topic (multi-select from `TopicCategory` enum)
- Difficulty
- Question type (`factual`, `connect`, `identify`, `fill_in_blank`, `multi_part`)
- Has media (toggle)
- Date range picker
- Asker (dropdown of all askers)
- Session (dropdown of all sessions)
- Extraction confidence (default: hide `low`)

**Sort options:** Newest, Oldest, Most reactions, Hardest, Fastest solve

---

### 2. Question Detail

Full view of a single question, opened from a card or direct URL.

**Sections:**
- Full question text (+ media placeholder if `has_media: true`)
- Answer block — text, solver, confirmation message, collaborative flag, parts breakdown for multi-part questions
- Discussion thread — chronological replay of all `discussion[]` entries, each styled by role:
  - `attempt` — speech bubble (green if `is_correct`, grey otherwise)
  - `hint` — italicised nudge
  - `confirmation` — highlighted confirm message
  - `answer_reveal` — asker reveal (no solver)
  - `chat` — muted banter
- Stats panel — wrong attempts, hints given, time to answer, unique participants
- Reactions panel — per-emoji counts + category labels (if available)
- Session context — if part of a session, show session name, quizmaster, question number, theme

**URL format:** `/question/2025-09-23-003`

---

### 3. Stats & Leaderboards

Aggregate views derived from the question archive.

**Leaderboard tabs:**

| Tab | Metric |
|---|---|
| Top Solvers | Most correct answers |
| Top Askers | Most questions posed |
| Fastest | Lowest average `time_to_answer_seconds` (min 5 questions) |
| Most Engaged | Highest total `unique_participants` across questions |

**Topic breakdown:**
- Bar/donut chart of question count by `TopicCategory`
- Average difficulty per topic

**Difficulty over time:**
- Line chart of rolling average `wrong_attempts` by month

**Question type distribution:**
- Donut chart of `QuestionType` breakdown

---

### 4. Sessions

Lists all structured quiz sessions (questions where `session != null`).

**Session card shows:**
- Session ID, quizmaster, date, theme
- Number of questions
- Average time to answer

**Session detail page:**
- All questions in the session in order (`question_number`)
- Session-level stats: total participants, average difficulty, fastest/slowest question

**URL format:** `/session/2026-03-16-pratik`

---

### 5. Highlights Reel

A curated feed of questions that have `highlights` populated, sorted by `total_reactions` descending.

**Category filter:** `funny`, `crowd_favourite`, `spicy`, `surprising`, `confirmed_correct` (driven by whatever categories exist in the data — not hardcoded)

---

## Non-Functional Requirements

| Requirement | Detail |
|---|---|
| **Static / no backend** | All data loaded from pre-built JSON files. No server required. Deployable to GitHub Pages or Netlify. |
| **Fast initial load** | Paginate or lazy-load `questions.json`. Per-day JSON files (`data/questions_by_date/`) available for date-range queries without loading the full archive. |
| **Mobile-first** | Members primarily use phones. Cards and thread views must be readable on small screens. |
| **Private by default** | No public indexing (add `<meta name="robots" content="noindex">`). The group is private; the site should be shared only with members. |
| **No login required** | Access by URL only. Keep it frictionless for group members. |

---

## Out of Scope (v1)

- Editing or correcting extracted questions
- Adding new questions manually
- User accounts or personalisation
- Real-time updates from WhatsApp
- Comments or reactions within the visualizer

---

## Open Questions

1. **Media**: `has_media: true` questions reference images/videos from WhatsApp. These are not extractable from a `.txt` export. Show a placeholder, or skip media questions from the feed by default?
2. **Low-confidence questions**: Show or hide `extraction_confidence: "low"` entries? Probably hidden by default with an opt-in toggle.
3. **Hosting**: GitHub Pages (free, simple) vs Netlify vs self-hosted?
4. **Framework**: Static site with vanilla JS + JSON, or a lightweight framework (e.g. SvelteKit, Next.js static export)?
