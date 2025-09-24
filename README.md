# Artemis Data Collector

This program is responsible for collecting information about the workflow queue lengths periodically from a ActiveMQ Artemis server and storing them in a PostgreSQL database of the WebMon application found at [neutrons/data_workflow](https://github.com/neutrons/data_workflow/). This will be deployed using the docker image built as part of this repo GitHub actions and can be found [here](https://github.com/orgs/neutrons/packages/container/package/artemis_data_collector/artemis_data_collector).

The queue information is collected from ActiveMQ Artemis broker using [Jolokia REST API](https://activemq.apache.org/components/artemis/documentation/latest/management.html#exposing-jmx-using-jolokia). For this to work the ActiveMQ Artemis management console must be accessible from this application.

## Setup for local development and testing

Create and activate the pixi environment

```
pixi install
pixi shell
```

Then you can run the application by

```
artemis_data_collector
```

The testing requires both ActiveMQ Artemis and PostgreSQL applications running. This can be easily done with the provided docker compose file.

```
docker compose up -d
```

after which you can run the unittests with ``pytest``

```
python -m pytest --cov=src
```

## Configuration

The configuration options can be set either by command line parameters or environment variables.

The command line option can be found by running

```
artemis_data_collector -h
```

The environment variables are the following

| Variable | Description |
| -------- | ----------- |
| ``ARTEMIS_URL`` | Base URL of the primary Artemis instance. Default ``http://localhost:8161``|
| ``ARTEMIS_FAILOVER_URL`` | Base URL of the failover Artemis instance (optional). No default |
| ``ARTEMIS_USER`` | Admin user that has read permission of the API. Default ``artemis`` |
| ``ARTEMIS_PASSWORD`` | Admin password for artemis user. Default ``artemis`` |
| ``ARTEMIS_BROKER_NAME`` | The name of the artemis broker. This must match the one set in the ``broker.xml``. Default ``0.0.0.0`` |
| ``DATABASE_HOST`` | Hostname of the database. Default ``workflow`` |
| ``DATABASE_PORT`` | Port of the database. Default ``5432`` |
| ``DATABASE_USER`` | Database user to use. Default ``workflow`` |
| ``DATABASE_PASS`` | Password for user. Default ``workflow`` |
| ``DATABASE_NAME`` | Name of database to use. Default ``workflow`` |
| ``QUEUE_LIST`` | List of queue to monitor. If not specified, monitor all queues from database. _e.g._ ``["QUEUE1", "QUEUE2"]`` |
| ``INTERVAL`` | Interval to collect data (seconds), Default ``600`` |
| ``HTTP_TIMEOUT`` | HTTP timeout in seconds for broker requests. Default ``10`` |
| ``LOG_LEVEL`` | Log level (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``). Default ``INFO`` |
| ``LOG_FILE`` | Fike where to save log. If not specified, log to stdout. |

## Building docker image

To build the docker image you first need a packaged version of this application to install.

```
rm -r dist  # remove previous builds
python -m build
```

After which you can build the docker container

```
docker build -t artemis_data_collector .
```

You can configure the running options of the container by the environment variables.

[![codecov](https://codecov.io/gh/neutrons/artemis_data_collector/graph/badge.svg?token=PAP1KRTOR0)](https://codecov.io/gh/neutrons/artemis_data_collector)
