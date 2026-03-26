# KVizzing Question Schema

## Design Decisions

- **`id`**: `YYYY-MM-DD-NNN` format (human-readable, chronologically sortable)
- **`answer.parts`**: Handles multi-part questions (e.g. "Id X, Y, Z") where different people may solve each part
- **`answer.is_collaborative`**: True when multiple people contribute to the full answer
- **`session`**: Null for ad-hoc questions; populated when a quizmaster runs a structured quiz (detected by "###Quiz Start", score tracking, etc.)
- **`extraction_confidence`**: `high` = asker explicitly confirmed; `medium` = inferred from context; `low` = no confirmation found
- **`topic`** and **`difficulty`**: Optional fields, best assigned by LLM post-processing. Difficulty can be derived from `stats.wrong_attempts` heuristically.
- **`discussion`**: Full ordered message thread for website replay and context display

---

## JSON Schema

> **Auto-generated** — do not edit by hand. Run `python3 schema.py` to regenerate `schema.json` from the Pydantic models in `schema.py`, which is the single source of truth.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "KVizzing Question",
  "type": "object",
  "required": ["id", "date", "question", "answer", "discussion", "stats", "extraction_confidence", "source"],
  "properties": {

    "id": {
      "type": "string",
      "description": "Unique identifier. Format: YYYY-MM-DD-NNN (e.g. 2025-09-23-001)",
      "examples": ["2025-09-23-001"]
    },

    "date": {
      "type": "string",
      "format": "date",
      "description": "Date the question was posted (YYYY-MM-DD)"
    },

    "question": {
      "type": "object",
      "required": ["timestamp", "text", "asker", "type", "has_media"],
      "properties": {
        "timestamp": {
          "type": "string",
          "format": "date-time",
          "description": "ISO 8601 timestamp of the question message"
        },
        "text": {
          "type": "string",
          "description": "Full question text, cleaned of WhatsApp artifacts"
        },
        "asker": {
          "type": "string",
          "description": "Username of the question poser (normalised, without leading ~)"
        },
        "type": {
          "type": "string",
          "enum": ["factual", "connect", "identify", "fill_in_blank", "multi_part", "unknown"],
          "description": "Question format type — describes the thinking required, independent of medium. 'factual' = recall a fact; 'connect' = find common link between a list; 'identify' = name the person/thing/place; 'fill_in_blank' = FITB style; 'multi_part' = multiple sub-answers (X/Y/Z style). Use has_media:true for image/video questions — they can be any of these types."
        },
        "has_media": {
          "type": "boolean",
          "description": "True if the question message included an image/video (detected via 'image omitted' / 'video omitted')"
        },
        "topic": {
          "type": ["string", "null"],
          "enum": ["history", "science", "literature", "technology", "sports", "geography", "entertainment", "food_drink", "art_culture", "business", "general", null],
          "description": "Topic category. Null if not yet classified. Best assigned via LLM."
        },
        "tags": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Free-form tags for fine-grained categorisation (e.g. ['India', 'architecture', 'colonial'])"
        }
      }
    },

    "answer": {
      "type": "object",
      "required": ["confirmed", "is_collaborative"],
      "properties": {
        "text": {
          "type": ["string", "null"],
          "description": "The correct answer text. Null if answer was never confirmed or revealed."
        },
        "solver": {
          "type": ["string", "null"],
          "description": "Username of the first person to give the correct answer. Null if asker revealed without anyone getting it."
        },
        "timestamp": {
          "type": ["string", "null"],
          "format": "date-time",
          "description": "Timestamp of the winning answer message. For collaborative/answer_reveal cases where no single message is the answer, this is the confirmation message timestamp. Null if unanswered."
        },
        "confirmed": {
          "type": "boolean",
          "description": "Whether the asker explicitly confirmed the answer"
        },
        "confirmation_text": {
          "type": ["string", "null"],
          "description": "The exact message the asker used to confirm (e.g. 'correct', 'Bingo', 'Yes!')"
        },
        "is_collaborative": {
          "type": "boolean",
          "description": "True when multiple participants together produced the full answer"
        },
        "parts": {
          "type": ["array", "null"],
          "description": "For multi-part questions (X/Y/Z style). Null for single-answer questions.",
          "items": {
            "type": "object",
            "required": ["label", "text"],
            "properties": {
              "label": {
                "type": "string",
                "description": "Part identifier (e.g. 'X', 'Y', 'Z', or '1', '2', '3')"
              },
              "text": {
                "type": "string",
                "description": "The answer for this part"
              },
              "solver": {
                "type": ["string", "null"],
                "description": "Who solved this specific part"
              }
            }
          }
        }
      }
    },

    "discussion": {
      "type": "array",
      "description": "Ordered list of all relevant messages in the Q&A thread",
      "items": {
        "type": "object",
        "required": ["timestamp", "username", "text", "role"],
        "properties": {
          "timestamp": {
            "type": "string",
            "format": "date-time"
          },
          "username": {
            "type": "string"
          },
          "text": {
            "type": "string"
          },
          "role": {
            "type": "string",
            "enum": ["attempt", "hint", "confirmation", "chat", "answer_reveal"],
            "description": "'attempt' = participant answer try; 'hint' = asker nudge; 'confirmation' = asker confirms correct answer; 'chat' = non-answer banter/reaction message in thread; 'answer_reveal' = asker reveals answer without anyone getting it"
          },
          "is_correct": {
            "type": ["boolean", "null"],
            "description": "True if this attempt was the winning answer. Null for non-attempt roles."
          }
        }
      }
    },

    "stats": {
      "type": "object",
      "required": ["wrong_attempts", "hints_given"],
      "properties": {
        "wrong_attempts": {
          "type": "integer",
          "minimum": 0,
          "description": "Number of incorrect attempts before the correct answer"
        },
        "hints_given": {
          "type": "integer",
          "minimum": 0,
          "description": "Number of hints/nudges the asker gave"
        },
        "time_to_answer_seconds": {
          "type": ["integer", "null"],
          "minimum": 0,
          "description": "Seconds from question timestamp to first correct answer. Null if unanswered."
        },
        "unique_participants": {
          "type": "integer",
          "minimum": 1,
          "description": "Number of distinct users who attempted an answer"
        },
        "difficulty": {
          "type": ["string", "null"],
          "enum": ["easy", "medium", "hard", null],
          "description": "Heuristic: easy = 0 wrong attempts; medium = 1-3; hard = 4+. Or LLM-assigned."
        }
      }
    },

    "session": {
      "type": ["object", "null"],
      "description": "Populated when question is part of a structured quiz session (QM-hosted). Null for ad-hoc questions.",
      "required": ["id", "quizmaster", "question_number"],
      "properties": {
        "id": {
          "type": "string",
          "description": "Session identifier (e.g. date + quizmaster slug: '2026-03-16-pratik')"
        },
        "quizmaster": {
          "type": "string",
          "description": "Username of the session host"
        },
        "question_number": {
          "type": "integer",
          "minimum": 1,
          "description": "Position of this question within the session (1-based)"
        },
        "theme": {
          "type": ["string", "null"],
          "description": "Session theme if announced (e.g. 'Hollywood Movies', 'Bollywood')"
        }
      }
    },

    "extraction_confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"],
      "description": "high = asker gave explicit confirmation; medium = strong contextual signal; low = no confirmation found, question validity uncertain"
    },

    "reactions": {
      "type": ["array", "null"],
      "description": "Optional enrichment field. Populated from WhatsApp's local SQLite DB (iOS: ChatStorage.sqlite via unencrypted Finder backup → ZWAMESSAGEREACTION table; Android: msgstore.db → message_reactions table). Null when DB data is unavailable. Raw granular data — one entry per (message, user, emoji) tuple.",
      "items": {
        "type": "object",
        "required": ["message_timestamp", "username", "emoji", "reaction_timestamp"],
        "properties": {
          "message_timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp of the message that was reacted to. FK into question.timestamp (if reacted to the question itself) or discussion[].timestamp (if reacted to any thread message)."
          },
          "username": {
            "type": "string",
            "description": "Who reacted"
          },
          "emoji": {
            "type": "string",
            "description": "The reaction emoji (e.g. '✅', '👍', '❤️', '😂')"
          },
          "reaction_timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "When the reaction was placed"
          }
        }
      }
    },

    "highlights": {
      "type": ["object", "null"],
      "description": "Optional enrichment field. Derived from reactions[]. Null when reactions are unavailable. Computed by the pipeline using a configurable emoji→category mapping (not hardcoded in schema) so new categories can be added without schema changes.",
      "required": ["reaction_counts", "total_reactions", "categories"],
      "properties": {
        "reaction_counts": {
          "type": "object",
          "description": "Total count per emoji across all messages in the thread (question + all discussion entries). Keys are emoji characters, values are integer counts. Open-ended — any emoji that appears becomes a key.",
          "additionalProperties": { "type": "integer", "minimum": 1 },
          "examples": [{ "😂": 5, "❤️": 3, "✅": 8, "👍": 2, "🔥": 1 }]
        },
        "total_reactions": {
          "type": "integer",
          "minimum": 0,
          "description": "Sum of all reaction_counts values. Useful for sorting by engagement."
        },
        "categories": {
          "type": "array",
          "description": "Derived category labels computed by mapping emoji → category via a pipeline config file (e.g. { '😂': 'funny', '😄': 'funny', '❤️': 'crowd_favourite', '✅': 'confirmed_correct', '👍': 'confirmed_correct', '🔥': 'spicy', '😮': 'surprising' }). A category is included if its total emoji count meets a configurable threshold. Open-ended — new categories are added by updating the config, not the schema.",
          "items": { "type": "string" },
          "examples": [["funny", "crowd_favourite"]]
        }
      }
    },

    "source": {
      "type": "object",
      "description": "Provenance — which file and pair index this came from",
      "required": ["file", "pair_index"],
      "properties": {
        "file": {
          "type": "string",
          "description": "Source daily chat file (e.g. 'chat_2025-09-23.txt')"
        },
        "pair_index": {
          "type": "integer",
          "minimum": 1,
          "description": "Pair number within the source file (1-based)"
        }
      }
    }
  }
}
```

---

## Sample Instances

### 1. Factual question (single solver, confirmed)

```json
{
  "id": "2025-09-23-003",
  "date": "2025-09-23",
  "question": {
    "timestamp": "2025-09-23T14:49:49",
    "text": "Although there is a patent issued in 1938 to John Jordent for an improved version of this invention, no one knows who the very first inventor is, since the original patent was lost in a fire in the US Patent Office in 1936. We will never know the inventor of which life saving invention?",
    "asker": "Aditi Bapat",
    "type": "factual",
    "has_media": false,
    "topic": "history",
    "tags": ["patents", "USA", "inventions"]
  },
  "answer": {
    "text": "Fire Hydrant",
    "solver": "Lzafeer Ahmad B F",
    "timestamp": "2025-09-23T14:51:49",
    "confirmed": true,
    "confirmation_text": "Bingo",
    "is_collaborative": false,
    "parts": null
  },
  "discussion": [
    { "timestamp": "2025-09-23T14:50:20", "username": "Shubham", "text": "CPR?", "role": "attempt", "is_correct": false },
    { "timestamp": "2025-09-23T14:50:43", "username": "Aditi Bapat", "text": "Not quite. Some hints in the question. 🙊", "role": "hint", "is_correct": null },
    { "timestamp": "2025-09-23T14:51:03", "username": "Akshay", "text": "Extinguisher 🧯", "role": "attempt", "is_correct": false },
    { "timestamp": "2025-09-23T14:51:13", "username": "Aditi Bapat", "text": "Very close", "role": "hint", "is_correct": null },
    { "timestamp": "2025-09-23T14:51:49", "username": "Lzafeer Ahmad B F", "text": "Fire Hydrant", "role": "attempt", "is_correct": true },
    { "timestamp": "2025-09-23T14:52:01", "username": "Aditi Bapat", "text": "Bingo", "role": "confirmation", "is_correct": null }
  ],
  "stats": {
    "wrong_attempts": 2,
    "hints_given": 2,
    "time_to_answer_seconds": 120,
    "unique_participants": 3,
    "difficulty": "medium"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": [
    { "message_timestamp": "2025-09-23T14:49:49", "username": "Akshay", "emoji": "❤️", "reaction_timestamp": "2025-09-23T14:52:10" },
    { "message_timestamp": "2025-09-23T14:49:49", "username": "Pavan Pamidimarri", "emoji": "😂", "reaction_timestamp": "2025-09-23T14:52:30" },
    { "message_timestamp": "2025-09-23T14:49:49", "username": "Khandoba", "emoji": "😂", "reaction_timestamp": "2025-09-23T14:52:45" },
    { "message_timestamp": "2025-09-23T14:51:49", "username": "Aditi Bapat", "emoji": "✅", "reaction_timestamp": "2025-09-23T14:52:05" }
  ],
  "highlights": {
    "reaction_counts": { "❤️": 1, "😂": 2, "✅": 1 },
    "total_reactions": 4,
    "categories": ["funny", "crowd_favourite"]
  },
  "source": { "file": "chat_2025-09-23.txt", "pair_index": 3 }
}
```

### 2. Multi-part identify question (collaborative)

```json
{
  "id": "2026-03-16-001",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T03:49:23",
    "text": "Q. X was born in Taiwan and immigrated to the United States... Id X, company Y, and Z.",
    "asker": "Kartikey Pradhan",
    "type": "multi_part",
    "has_media": false,
    "topic": "technology",
    "tags": ["CEO", "semiconductors", "AI", "AMD", "Nvidia"]
  },
  "answer": {
    "text": "X = Lisa Su, Y = AMD, Z = Jensen Huang",
    "solver": "Saumay",
    "timestamp": "2026-03-16T03:55:33",
    "confirmed": true,
    "confirmation_text": "Lisa Su is X, AMD is Y, and Jensen Huang, her mamaji, is Z",
    "is_collaborative": false,
    "parts": [
      { "label": "X", "text": "Lisa Su", "solver": "Saumay" },
      { "label": "Y", "text": "AMD", "solver": "Saumay" },
      { "label": "Z", "text": "Jensen Huang", "solver": "Saumay" }
    ]
  },
  "discussion": [
    { "timestamp": "2026-03-16T03:54:04", "username": "Saumay", "text": "Jensen..", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T03:54:06", "username": "Saumay", "text": "Nvidia", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T03:54:22", "username": "Saumay", "text": "AMD?", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T03:54:42", "username": "Kartikey Pradhan", "text": "which letter?", "role": "hint", "is_correct": null },
    { "timestamp": "2026-03-16T03:55:03", "username": "Saumay", "text": "Z", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T03:55:19", "username": "Kartikey Pradhan", "text": "good, that's what I wanted 😀", "role": "hint", "is_correct": null },
    { "timestamp": "2026-03-16T03:55:33", "username": "Saumay", "text": "Lisa is X", "role": "attempt", "is_correct": true },
    { "timestamp": "2026-03-16T03:56:02", "username": "Kartikey Pradhan", "text": "Lisa Su is X, AMD is Y, and Jensen Huang, her mamaji, is Z", "role": "confirmation", "is_correct": null }
  ],
  "stats": {
    "wrong_attempts": 4,
    "hints_given": 2,
    "time_to_answer_seconds": 370,
    "unique_participants": 1,
    "difficulty": "hard"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": null,
  "highlights": null,
  "source": { "file": "chat_2026-03-16.txt", "pair_index": 1 }
}
```

### 3. Visual question (structured quiz session)

```json
{
  "id": "2026-03-16-007",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T07:18:47",
    "text": "[image: movie poster visual quiz]",
    "asker": "pratik.s.chandarana",
    "type": "factual",
    "has_media": true,
    "topic": "entertainment",
    "tags": ["movies", "Hollywood", "poster quiz"]
  },
  "answer": {
    "text": "Rush Hour 2",
    "solver": "Chinmay Mehta",
    "timestamp": "2026-03-16T07:19:07",
    "confirmed": true,
    "confirmation_text": "Rush Hour 2 is correct; Chinmay with the correct answer",
    "is_collaborative": false,
    "parts": null
  },
  "discussion": [
    { "timestamp": "2026-03-16T07:18:57", "username": "Lzafeer Ahmad B F", "text": "Oceans 11", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T07:18:57", "username": "Radhika", "text": "Hangover?", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T07:18:58", "username": "Gautam Aswani", "text": "21", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T07:19:07", "username": "Chinmay Mehta", "text": "Rush hour?", "role": "attempt", "is_correct": true },
    { "timestamp": "2026-03-16T07:19:35", "username": "Nikunj", "text": "Rounders?", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T07:19:59", "username": "pratik.s.chandarana", "text": "Rush Hour 2 is correct; Chinmay with the correct answer", "role": "confirmation", "is_correct": null }
  ],
  "stats": {
    "wrong_attempts": 3,
    "hints_given": 0,
    "time_to_answer_seconds": 20,
    "unique_participants": 5,
    "difficulty": "medium"
  },
  "session": {
    "id": "2026-03-16-pratik",
    "quizmaster": "pratik.s.chandarana",
    "question_number": 7,
    "theme": "Hollywood Movies"
  },
  "extraction_confidence": "high",
  "reactions": [
    { "message_timestamp": "2026-03-16T07:19:07", "username": "Nikunj", "emoji": "✅", "reaction_timestamp": "2026-03-16T07:20:05" },
    { "message_timestamp": "2026-03-16T07:19:07", "username": "Radhika", "emoji": "✅", "reaction_timestamp": "2026-03-16T07:20:08" },
    { "message_timestamp": "2026-03-16T07:19:35", "username": "Nikunj", "emoji": "😂", "reaction_timestamp": "2026-03-16T07:20:10" }
  ],
  "highlights": {
    "reaction_counts": { "✅": 2, "😂": 1 },
    "total_reactions": 3,
    "categories": ["confirmed_correct", "funny"]
  },
  "source": { "file": "chat_2026-03-16.txt", "pair_index": 7 }
}
```

### 4. Connect question (collaborative solve)

```json
{
  "id": "2026-03-16-003",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T06:14:40",
    "text": "Flash Q.\nConnect:\nCarolyn Keene\nFranklin Dixon\nRoy Rockwood\nVictor Appleton\nMargaret Penrose",
    "asker": "Sidhesh K K",
    "type": "connect",
    "has_media": false,
    "topic": "literature",
    "tags": ["pseudonyms", "publishing", "Hardy Boys", "Nancy Drew"]
  },
  "answer": {
    "text": "Pseudonyms / house names owned by the Stratemeyer Syndicate — multiple ghostwriters published under each name",
    "solver": null,
    "timestamp": "2026-03-16T06:18:00",
    "confirmed": true,
    "confirmation_text": "Together you folks have cracked the funda... these are pennames of authors given by the same syndicate",
    "is_collaborative": true,
    "parts": null
  },
  "discussion": [
    { "timestamp": "2026-03-16T06:15:46", "username": "Chaitanya Malhotra", "text": "Pseudonym authors?", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T06:15:47", "username": "Nikunj", "text": "Franklin Dixon is Hardy boys right?", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T06:16:15", "username": "Sidhesh K K", "text": "Yes... but there's a deeper funda for these names", "role": "hint", "is_correct": null },
    { "timestamp": "2026-03-16T06:16:42", "username": "Lzafeer Ahmad B F", "text": "Wasn't pen name picked by publisher so that whoever wrote was published under that author name", "role": "attempt", "is_correct": false },
    { "timestamp": "2026-03-16T06:16:55", "username": "Sidhesh K K", "text": "Correct", "role": "hint", "is_correct": null },
    { "timestamp": "2026-03-16T06:18:00", "username": "Sidhesh K K", "text": "Together you folks have cracked the funda... these are pennames of authors given by the same syndicate", "role": "confirmation", "is_correct": null }
  ],
  "stats": {
    "wrong_attempts": 3,
    "hints_given": 2,
    "time_to_answer_seconds": 200,
    "unique_participants": 3,
    "difficulty": "medium"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": [
    { "message_timestamp": "2026-03-16T06:14:40", "username": "Chaitanya Malhotra", "emoji": "❤️", "reaction_timestamp": "2026-03-16T06:18:20" },
    { "message_timestamp": "2026-03-16T06:14:40", "username": "Nikunj", "emoji": "❤️", "reaction_timestamp": "2026-03-16T06:18:25" },
    { "message_timestamp": "2026-03-16T06:14:40", "username": "Lzafeer Ahmad B F", "emoji": "🔥", "reaction_timestamp": "2026-03-16T06:18:30" },
    { "message_timestamp": "2026-03-16T06:18:00", "username": "Chaitanya Malhotra", "emoji": "😂", "reaction_timestamp": "2026-03-16T06:18:40" }
  ],
  "highlights": {
    "reaction_counts": { "❤️": 2, "🔥": 1, "😂": 1 },
    "total_reactions": 4,
    "categories": ["crowd_favourite", "spicy", "funny"]
  },
  "source": { "file": "chat_2026-03-16.txt", "pair_index": 3 }
}
```

---

## Output File Format

Questions should be stored as:
- **`data/questions.json`** — array of all question objects (primary source of truth)
- **`data/questions_by_date/YYYY-MM-DD.json`** — per-day arrays (for efficient date-range queries)

The `questions.json` array is sorted by `question.timestamp` ascending.
