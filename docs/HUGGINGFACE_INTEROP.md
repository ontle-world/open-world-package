# External Model Hub Interoperability

OWP does not replace model artifact hubs. It complements them.

A World Model package may reference a checkpoint stored on Hugging Face or another artifact store while keeping World-specific semantics in OWP.

```yaml
spec:
  assets:
    - kind: ModelArtifact
      ref:
        provider: huggingface
        uri: hf://organization/model-name
        revision: <commit hash>      # pins the reference (spec section 5.1)
```

OWP adds the information that a generic model artifact repository normally cannot infer safely:

- which World representation the model is grounded in,
- which task/View contracts it supports,
- observation and action semantics,
- representation adapters,
- scale/resolution/temporal validity,
- datasets/evaluations/attestations connected to that World contract.

Weights remain in the system best suited to storing and distributing weights.
