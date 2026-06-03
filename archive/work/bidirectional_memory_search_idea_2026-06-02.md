# Bidirectional memory search idea

Follow-up direction after the hierarchy runs.

The next interesting design is not just “agent searches context” or “context feeds agent.” It is a meet-in-the-middle protocol where the agent and memory system both expose structure.

## Core framing

The agent expands from the question toward a typed need. The memory system expands from stored context toward answer-bearing handles. They meet at a small proof packet.

Example:

```text
Question: Where was Fred before the cinema?

Agent-side query contract:
- answer_type: location
- entity: Fred
- relation: location_before
- constraint: before cinema
- needs: ordered movement history

Memory-side handles:
- current_state[person]
- movement_history[person]
- object_holder[obj]
- event_counters[type]
- stale/current fact chains
- raw archive spans

Meet point:
- Fred movement history: office -> cinema
- proof: office event immediately precedes cinema event
- answer: office
```

## Why this is better than retrieval-only

Flat retrieval returns snippets. Hierarchy returns state. Bidirectional search returns a proof path between the question contract and the memory handles.

This is especially useful for:

- BABILong state transitions
- OOLONG roll/spell counters
- stale/current preference chains
- aggregate memory questions
- contradiction checks

## Candidate mechanisms

### 1. Query contracts

The agent or a deterministic parser turns the question into a typed contract:

```json
{
  "answer_type": "count",
  "entity": "pasta",
  "relation": "dinner_count",
  "scope": "whole_memory_log",
  "needs": ["meal_event_counter"]
}
```

### 2. Memory handles

The memory system exposes available operators and state tables:

```text
available_handles:
- meal_counts[dinner]
- movement_history[person]
- current_location[person]
- object_holder[object]
- roll_counts[episode,type]
- latest_preference[key]
```

### 3. Proof-carrying packets

The memory packet should include:

- answer candidate
- proof path
- tier/operator used
- supporting events or state rows
- contradiction/staleness checks

### 4. Hypothesis / verification loop

The agent can propose candidate answers. The memory kernel tries to prove or disprove them:

```text
candidate: green tea
check: latest preference event? rejected newer suggestion? stale profile import?
result: green tea disproved; mint tea is latest confirmed preference
```

### 5. Context critic

Before final answer, context runs an anti-search:

- is there a newer update?
- is the cited fact stale?
- is there a rejected proposal?
- does raw archive contradict the state table?
- is provenance missing?

## Concrete next arm

Add a `bidirectional_memory_packet` arm:

1. parse question into query contract
2. list available memory handles from hierarchy
3. match contract to handles
4. execute deterministic handle/operator
5. return minimal proof packet
6. model answers from the proof packet

Important guardrail: keep the context side deterministic/logged. Otherwise this becomes a hidden second agent doing the benchmark.

## Best research claim

> Hierarchical memory should not just retrieve evidence; it should expose typed state handles. The agent and memory system can meet in the middle: the agent supplies a query contract, the context supplies proof-carrying state.
