# Factory of One

A PM with agents rarely fails by building too slowly. They fail by shipping 10 things and learning from none of them.

Status: in progress. The simulated company and scenario 1 run. The agents come next.

## Try the sandbox

```bash
python -m venv .venv
.venv/Scripts/pip install -e .[dev]   # macOS or Linux: .venv/bin/pip
python -m sandbox.generator --seed 1
python -m pytest
```

This builds 8 weeks of data for Tallybird, a fictional AI meeting notetaker, with one problem hidden inside. See [sandbox/SPEC.md](sandbox/SPEC.md).
