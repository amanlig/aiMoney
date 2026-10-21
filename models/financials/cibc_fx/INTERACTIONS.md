# Model interactions

The implementation uses Python modules, functions and dictionaries rather than
classes. These UML participants represent the actual components and data objects.

```mermaid
sequenceDiagram
    actor User
    participant Train as train.py
    participant DB as SQLite samples
    participant Model as model.py
    participant Files as Local JSON artifacts
    participant Predict as predict.py
    User->>Train: Run training
    Train->>DB: Read reviewed samples (read-only)
    DB-->>Train: Transaction rows
    Train->>Train: Validate and split by settlement date
    Train->>Model: fit(earlier rows)
    Model-->>Train: Evaluation model dictionary
    Train->>Model: metrics(evaluation model, later rows)
    Model->>Model: predict() for each holdout row
    Model-->>Train: Errors by direction and size
    Train->>Files: Save evaluation/holdout.json
    Train->>Model: fit(all eligible rows)
    Model-->>Train: Final model dictionary
    Train->>Files: Save artifacts/model.json
    User->>Predict: Supply direction, USD amount, reference rate
    Predict->>Files: Read artifacts/model.json
    Files-->>Predict: Final model dictionary
    Predict->>Model: predict(model, direction, reference, USD)
    Model-->>Predict: Estimated rate, CAD total, range warning
    Predict-->>User: JSON estimate
```

The **evaluation model** only sees earlier transactions. Its errors are measured
on later transactions. The **final model** is then refitted on all eligible data
and used by the prediction command. Keeping these separate prevents test results
from being calculated with a model that already saw the test transactions.

`plot.py` reads the same database, final model and evaluation report to produce
`evaluation/data-plots.html`. It uses the saved evaluation parameters for holdout
predictions and the final model parameters for the adjustment lines in chart 2.
No component writes model predictions back into the transaction database.

