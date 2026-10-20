# Investment recommendation interactions

## Independent OpenAI recommendation sequence

```mermaid
sequenceDiagram
    actor User
    participant UI as Closing simulator browser
    participant Server as investment server / close_recommendations.py
    participant Local as Basis, premiums, FX model and quotes
    participant AI as OpenAI Responses API
    participant DB as SQLite recommendation_runs
    User->>UI: Choose goal; click Generate
    UI->>Server: POST scenario prices, fees and conversion treatment
    Server->>Local: Read confirmed records and fitted parameters
    Local-->>Server: Source inputs
    Server->>Server: Validate and recalculate cash flows
    Server->>AI: Snapshot + instructions; server-only key; store=false
    AI-->>Server: Fresh assessment + usage + response ID
    Server->>DB: Save successful assessment and immutable snapshot
    Server-->>UI: Assessment, source inputs and calculated results
    UI-->>User: Show result and process
    User->>UI: View saved run
    UI->>Server: GET history
    Server->>DB: Read prior runs
    DB-->>UI: Saved text and original snapshots via server
```

Quote refresh is a separate explicit operation. An assessment uses the selected
scenario, with saved quote context. It has no chat history or research tools.
The application computes financial numbers; OpenAI explains conditional trade-offs.
