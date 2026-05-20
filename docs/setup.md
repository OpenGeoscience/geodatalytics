# Setup Guide
This guide walks you through setting up GeoDatalytics for local development using Dev Containers.

## Setup
1. Install [VS Code with dev container support](https://code.visualstudio.com/docs/devcontainers/containers#_installation).
1. Open the project in VS Code, then run `Dev Containers: Reopen in Container`
   from the Command Palette (`Ctrl+Shift+P`).
1. Once the container is ready, open a terminal and run:
   ```sh
   ./manage.py migrate
   ./manage.py createsuperuser
   ```

### Load Sample Data (Optional)
The ingest command loads datasets, charts, and project configuration from an ingestion file:

```sh
./manage.py ingest {JSON_FILE}
```

Available ingest options (paths relative to `sample_data/`):

- `boston_floods/data.json`
- `multiframe_test.json`
- `la_wildfires.json`
- `new_york_energy/data.json`

## Run
Open the **Run and Debug** panel (`Ctrl+Shift+D`) and select a launch configuration:

* **Django: Server** - Starts the development server at <http://localhost:8000/>
* **Django: Server (eager Celery)** - Same, but Celery tasks run synchronously
  in the web process (useful for debugging task code without a worker)
* **Celery: Worker** - Starts only the Celery worker
* **Vite: Dev Server** - Starts the frontend development server at <http://localhost:8080/>
* **Django: Management Command** - Pick and run any management command
* **Django + Celery + Vite** - Starts the server, a Celery worker, and the frontend

## Test
Run the full test suite from a terminal: `tox`

Auto-format code: `tox -e format`

Run and debug individual tests from the **Testing** panel (`Ctrl+Shift+;`).

## Rebuild
After changes to the Dockerfile, Docker Compose files, or `devcontainer.json`,
run `Dev Containers: Rebuild Container` from the Command Palette (`Ctrl+Shift+P`).

For dependency changes in `pyproject.toml`, just run `uv sync --all-extras --all-groups`.









---

## Running the Application

### Start the Services

**Default (CPU-only):**

```bash
docker compose up
```

**With GPU acceleration (NVIDIA systems only):**

```bash
docker compose --profile gpu up --scale celery=0
```

> **Note:** GPU mode requires NVIDIA drivers and [nvidia-docker](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) runtime.

### Access Points

| Service           | URL                                     |
| ----------------- | --------------------------------------- |
| User Interface    | http://localhost:8080/                  |
| Admin Panel       | http://localhost:8000/admin/            |
| API Documentation | http://localhost:8000/api/docs/swagger/ |

Log in using the credentials you created with `createsuperuser`.

### Stop the Services

Press `Ctrl+C` in the terminal running `docker compose up`, or run:

```bash
docker compose stop
```

## Troubleshooting

### Port Conflicts

If ports 8000, 8080, 5432, or 9000 are in use, modify the port mappings in `docker-compose.override.yml`.

### GPU Not Available

If you see an error like:

```
Error response from daemon: could not select device driver "nvidia" with capabilities: [[gpu]]
```

This means GPU mode was requested but NVIDIA drivers aren't available. Use the default CPU mode instead:

```bash
docker compose up
```

GPU acceleration is optional and only needed for accelerated inferencing.
