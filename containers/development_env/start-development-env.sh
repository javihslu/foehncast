#!/bin/sh

# Register the project kernel, then keep the container running for local
# development.

set -eu

kernel_name="foehncast-development-env"
kernel_display_name="FoehnCast (development_env)"

kernel_python="${UV_PROJECT_ENVIRONMENT:-/home/appuser/.venv}/bin/python"
"$kernel_python" -m ipykernel install --user --name "$kernel_name" --display-name "$kernel_display_name"
"$kernel_python" -c 'from pathlib import Path; import json; kernel_path = Path.home() / ".local/share/jupyter/kernels/foehncast-development-env/kernel.json"; kernel_spec = json.loads(kernel_path.read_text()); kernel_spec["env"] = {**kernel_spec.get("env", {}), "PYTHONPATH": "/workspace/src"}; kernel_path.write_text(json.dumps(kernel_spec, indent=1) + "\n")'
printf 'Registered Jupyter kernel "%s"\n' "$kernel_display_name"

exec tail -f /dev/null
