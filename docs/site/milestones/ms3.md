# MS3 Presentation

<span class="fc-pill fc-pill--progress">Presentation scope</span>

MS3 is the presentation checkpoint. Its job is to explain one working system clearly: a local stack that already runs the feature, training, and inference paths together with real forecast data.

## Presentation Arc

<div class="mermaid">
flowchart LR
  A[Working local stack] --> B[Health, predict, and rank endpoints]
  B --> C[Feature and training DAGs]
  C --> D[Optional online feature lookup]
  D --> E[Cloud mapping]
</div>

## What The Presentation Covers

<div class="grid cards" markdown>

- **Working local proof**

  The demo starts from a real local stack, not slides alone, so reviewers can see one path from forecast ingestion to ranking.

- **Pipeline split**

  The explanation ties the feature, training, and inference modules back to the FTI structure used throughout the repository.

- **User-facing result**

  The API responses and optional online-feature lookup keep the presentation grounded in the rider-facing outcome.

- **Cloud direction**

  The close-out shows that the cloud plan keeps the same boundaries and changes the infrastructure around them.

</div>

## What A Reviewer Should Take Away

- The pipelines already run end to end locally with real data.
- Airflow already executes the feature and training jobs in that local stack.
- The app already serves predictions, ranking, and optional online feature lookup.
- The cloud roadmap extends the validated backend instead of replacing it with a second architecture.
