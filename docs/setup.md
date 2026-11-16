[TOC]

# Prerequisites

For local development, it is recommended that you run containerized services with [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers) or [Docker Compose](https://docs.docker.com/compose/).

## Dev Containers

1. Install [VS Code with dev container support](https://code.visualstudio.com/docs/devcontainers/containers#_installation).

2. Open the project in VS Code, then run `Dev Containers: Reopen in Container`
   from the Command Palette (`Ctrl+Shift+P`).

3. Run services with the `Django + Celery + Vite` Run Configuration in the VS Code `Run and Debug` panel.

4. Run tests either via command line with `tox` (see [Testing](#testing)) or in the VS Code `Testing` panel.

5. Rebuild after any changes to the Dockerfile, Docker Compose files, or `devcontainer.json`. Run `Dev Containers: Rebuild Container` from the Command Palette (`Ctrl+Shift+P`).

6. Manage dependencies with [`uv`](https://docs.astral.sh/uv/). Sync dependencies with `uv sync --all-extras --all-groups`.

## Docker Compose

Run services with `docker compose up`, using `Ctrl+C` to stop them gracefully. Or, to run them in the background, use `docker compose up -d` and `docker compose stop` to stop them gracefully.

To run celery worker with GPU access, use the `gpu` profile:

```
docker compose --profile gpu up --scale celery=0
```

!!! note
    GPU mode requires NVIDIA drivers and [nvidia-docker](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) runtime.

To run commands in a service container, use `docker compose run`:

```
docker compose run --rm django ./manage.py migrate
docker compose run --rm django uv run tox
```

# Initialization

Run the following commands in the Django context (VS Code terminal if using Dev Containers, Django container if using docker compose).

```
./manage.py migrate
./manage.py createsuperuser
```

# Access Points

Log in using the credentials you created with `createsuperuser`.

| Service           | URL                                     |
| ----------------- | --------------------------------------- |
| User Interface    | http://localhost:8080/                  |
| Admin Panel       | http://localhost:8000/admin/            |
| API Documentation | http://localhost:8000/api/docs/swagger/ |

# Load Sample Data (Optional)
The ingest command loads datasets, charts, and project configuration from an ingestion file:

```
./manage.py ingest {JSON_FILE}
```

Available ingest options (paths relative to `sample_data/`):

- `boston_floods/data.json`
- `multiframe_test.json`
- `la_wildfires.json`
- `new_york_energy/data.json`

# Testing

Run test suite with [`tox`](https://tox.wiki/en/4.67.13/). `tox` is installed automatically with the `dev` package extra. Pass an environment name to perform specific tests.

```
tox -e lint
tox -e format
tox -e test
tox -e type
tox -e check-migrations
```
