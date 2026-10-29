# GeoDatalytics

[![License][apache-license-image]][license-link]

<p float="left">
<img style="display: inline-block;" src="docs/kitware.svg" alt="Kitware Logo" width="125">
<img style="display: inline-block;" src="docs/sds_lab.png" alt="NEU SDS Lab Logo" width="100">
</p>

> Developed by [Kitware Inc.][kitware-link] in collaboration with the [Sustainability and Data Sciences Lab at Northeastern University][sds-lab-link]

![](docs/assets/readme_screenshot.png)

> Sample use case examines the effect of coastal flooding on the availability of the Boston Transit system (MBTA). Transit system data obtained from [MassMapper][mass-mapper-link], a public tool for open infrastructure data hosted by the state of Massachusetts. Flood data generated with this [flood simulation library][flood-sim-link] developed by NEU SDS Lab as part of this effort.

## Introduction

GeoDatalytics is a web-based platform designed to enable AI-driven analytics and simulation in urban environments. It empowers analysts, planners, and data scientists with the tools they need to ingest, explore, simulate, model, and visualize complex urban data, all in one integrated environment.

GeoDatalytics can support diverse use cases related to urban environments, enabling comprehensive data visualization and simulation capabilities that enhance the resilience of infrastructure and foster sustainable urban solutions.

GeoDatalytics is built with Kitware's [Resonant][resonant-cookiecutter-link] technology stack. This stack includes a Django Python server, PostgreSQL/PostGIS database, S3 object store, Vue web application, and Celery task service.

## Key Capabilities

- **Scenario-based analytics**: explore flood impact analysis, transportation disruption, infrastructure risk assessment, etc.

- **AI & simulation workflows**: run pretrained models on geospatial and network data to generate actionable insights

- **Interactive visualization**: explore multiscale results through interactive maps, custom layer styling, and side-by-side comparison

- **Multi-source data integration**: ingest vector, raster, and tabular data representing roads, utilities, floods, amenities, elevation, satellite imagery, sensor data, etc.

- **Collaborative project management**: configure your projects to include relevant datasets, set permissions for your collaborators, and save informative views for others to see your results


## Getting Started

To run GeoDatalytics locally with `docker-compose`, follow the instructions in the [Setup Guide](docs/setup.md).

[apache-license-image]: https://img.shields.io/badge/license-Apache%202-blue.svg
[license-link]: https://raw.githubusercontent.com/OpenGeoscience/geodatalytics/master/LICENSE
[kitware-link]: https://kitware.com
[sds-lab-link]: https://sdslab.io
[mass-mapper-link]: https://maps.massgis.digital.mass.gov/MassMapper/MassMapper.html
[flood-sim-link]: https://github.com/OpenGeoscience/uvdat-flood-sim
[resonant-cookiecutter-link]: https://github.com/kitware-resonant/cookiecutter-resonant
