# MS3 Presentation

<span class="fc-pill fc-pill--progress">Presentation scope</span>

MS3 is the presentation checkpoint. Its job is not to introduce a new system. Its job is to explain the working local system clearly and show why the architecture is credible beyond the demo.

## Presentation Arc

<div class="mermaid">
flowchart LR
  A[Working local stack] --> B[Ranked spot outcome]
  B --> C[Feature and training DAGs]
  C --> D[Stable FTI architecture]
  D --> E[Cloud direction]
</div>

## What The Presentation Covers

<div class="grid cards" markdown>

- **One real system**

  The presentation starts from the validated local stack, not from a hypothetical future deployment.

- **Pipeline split**

  The explanation ties the feature, training, and inference modules back to the same FTI structure used throughout the repository.

- **User-facing outcome**

  Ranked spots and API responses keep the checkpoint grounded in the rider-facing result.

- **Cloud direction**

  The close-out shows that the cloud plan keeps the same boundaries and changes the infrastructure around them.

</div>

## Suggested Demo Sequence

1. Start from the rider question and the configured spots.
2. Show the local stack responding through `/health`, `/predict`, or `/rank`.
3. Connect that output back to the feature and training DAGs.
4. Use the architecture diagram to explain why the backend is structured as feature, training, and inference instead of one monolith.
5. Finish by showing that the hosted path extends the validated backend instead of replacing it.

## What A Reviewer Should Take Away

- The pipelines already run end to end locally with real data.
- Airflow already executes the feature and training jobs in that local stack.
- The app already serves predictions and ranking from the same model pipeline used in training.
- The cloud roadmap extends the validated backend instead of replacing it with a second architecture.

See [MS2 Backend](ms2.md) for the validated local baseline and [Architecture](../system/architecture.md) for the system view that supports the presentation.
