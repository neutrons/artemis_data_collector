import unittest
from collections import namedtuple
from os import environ

import psycopg
import pytest
import stomp

from artemis_data_collector.artemis_data_collector import ArtemisDataCollector, initialize_database_tables, parse_args

Config = namedtuple(
    "Config",
    [
        "artemis_user",
        "artemis_password",
        "artemis_url",
        "artemis_failover_url",
        "artemis_broker_name",
        "queue_list",
        "database_hostname",
        "database_port",
        "database_user",
        "database_password",
        "database_name",
        "http_timeout",
    ],
)

config = Config(
    "artemis",
    "artemis",
    "http://localhost:8161",
    "http://invalidurl",
    "0.0.0.0",
    ["TEST_QUEUE", "TEST_QUEUE2", "DLD", "DOES_NOT_EXIST"],
    "localhost",
    5432,
    "workflow",
    "workflow",
    "workflow",
    10.0,  # http_timeout
)


class TestArtemisDataCollector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # initialize database tables
        try:
            initialize_database_tables(config)
        except psycopg.errors.DuplicateTable:
            pass

        # Add test queue to the database
        with psycopg.connect(
            dbname=config.database_name,
            host=config.database_hostname,
            port=config.database_port,
            user=config.database_user,
            password=config.database_password,
        ) as conn:
            with conn.cursor() as cur:
                # create test queue if it does not exist
                cur.execute("SELECT id FROM report_statusqueue WHERE name = 'TEST_QUEUE'")
                queue_id = cur.fetchone()
                if queue_id is None:
                    cur.execute("INSERT INTO report_statusqueue (name, is_workflow_input) VALUES ('TEST_QUEUE', true)")
                    cur.execute("SELECT id FROM report_statusqueue WHERE name = 'TEST_QUEUE'")
                    queue_id = cur.fetchone()
                cls.queue_id = queue_id[0]

                # create another test queue, one that doesn't exist in the Artemis broker
                cur.execute("SELECT id FROM report_statusqueue WHERE name = 'TEST_QUEUE2'")
                if cur.fetchone() is None:
                    cur.execute("INSERT INTO report_statusqueue (name, is_workflow_input) VALUES ('TEST_QUEUE2', true)")

        # create activeMQ Artemis test queue by sending a message with stomp
        conn = stomp.Connection(host_and_ports=[("localhost", 61613)])
        conn.connect("artemis", "artemis", wait=True)
        conn.send("/queue/TEST_QUEUE", "test")
        conn.disconnect()

    def test_get_database_statusqueues(self):
        adc = ArtemisDataCollector(config)
        queues = adc.get_database_statusqueues()
        assert isinstance(queues, dict)
        assert "TEST_QUEUE" in queues
        assert queues["TEST_QUEUE"] == self.queue_id

    def test_get_activemq_queues(self):
        adc = ArtemisDataCollector(config)
        queues = adc.get_activemq_queues()
        assert isinstance(queues, list)
        assert "TEST_QUEUE" in queues

    def test_collect_data(self):
        adc = ArtemisDataCollector(config)
        data = adc.collect_data()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0][0] == self.queue_id
        assert data[0][1] > 0

    def get_latest_queue_message_count(self):
        with psycopg.connect(
            dbname=config.database_name,
            host=config.database_hostname,
            port=config.database_port,
            user=config.database_user,
            password=config.database_password,
        ) as conn:
            with conn.cursor() as cur:
                # get newest record
                cur.execute(
                    "SELECT (id, queue_id, message_count) FROM report_statusqueuemessagecount ORDER BY id DESC LIMIT 1"
                )
                result = cur.fetchone()

        return [int(x) for x in result[0]]

    def test_add_to_database(self):
        adc = ArtemisDataCollector(config)
        adc.add_to_database([(self.queue_id, 0)])

        result = self.get_latest_queue_message_count()
        current_id = result[0]
        assert result[1] == self.queue_id
        assert result[2] == 0

        adc = ArtemisDataCollector(config)
        adc.add_to_database([(self.queue_id, 42)])

        result = self.get_latest_queue_message_count()
        assert result[0] == current_id + 1
        assert result[1] == self.queue_id
        assert result[2] == 42

    def test_no_valid_queues(self):
        config_no_valid_queues = Config(
            "artemis",
            "artemis",
            "http://localhost:8161",
            "invalidurl",
            "0.0.0.0",
            ["AAA", "BBB"],
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        with pytest.raises(ValueError) as e:
            ArtemisDataCollector(config_no_valid_queues)

        assert "No queues to monitor" in str(e)

    def test_default_queue_list(self):
        config_default_queues = Config(
            "artemis",
            "artemis",
            "http://localhost:8161",
            "invalidurl",
            "0.0.0.0",
            None,
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        adc = ArtemisDataCollector(config_default_queues)
        assert len(adc.monitored_queue) == 1
        assert "TEST_QUEUE" in adc.monitored_queue

    def test_invalid_artemis_url(self):
        config_invalid_url = Config(
            "artemis",
            "artemis",
            "http://localhost:12345",
            "invalidurl",
            "0.0.0.0",
            ["TEST_QUEUE"],
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        with pytest.raises(ValueError) as e:
            ArtemisDataCollector(config_invalid_url)

        assert "Failed to get queues from ActiveMQ Artemis" in str(e)

    def test_wrong_artemis_password(self):
        config_wrong_password = Config(
            "artemis",
            "AAA",
            "http://localhost:8161",
            "invalidurl",
            "0.0.0.0",
            ["TEST_QUEUE"],
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        with pytest.raises(ValueError) as e:
            ArtemisDataCollector(config_wrong_password)

        assert "Failed to get queues from ActiveMQ Artemis" in str(e)

    def test_wrong_broker_name(self):
        config_wrong_broker_name = Config(
            "artemis",
            "artemis",
            "http://localhost:8161",
            "invalidurl",
            "AAA",
            ["TEST_QUEUE"],
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        with pytest.raises(ValueError) as e:
            ArtemisDataCollector(config_wrong_broker_name)

        assert "Failed to get queues from ActiveMQ Artemis" in str(e)

    def test_failover_url(self):
        config_failover_url = Config(
            "artemis",
            "artemis",
            "invalidurl",  # main broker invalid
            "http://localhost:8161",  # use main broker as failover
            "0.0.0.0",
            ["TEST_QUEUE"],
            "localhost",
            5432,
            "workflow",
            "workflow",
            "workflow",
            10.0,  # http_timeout
        )

        adc = ArtemisDataCollector(config_failover_url)

        with self.assertLogs() as cm:
            queues = adc.get_activemq_queues()

        assert isinstance(queues, list)
        assert "TEST_QUEUE" in queues
        assert "Primary broker connection error" in cm.output[0]


def test_parse_args():
    # test some default values
    args = parse_args([])
    assert args.initialize_db is False
    assert args.artemis_user == "artemis"
    assert args.database_name == "workflow"
    assert args.queue_list is None
    assert args.interval == 600

    # test setting queue list
    args = parse_args(["--queue_list", "TEST_QUEUE", "TEST_QUEUE2", "TEST_QUEUE3"])
    assert args.queue_list == ["TEST_QUEUE", "TEST_QUEUE2", "TEST_QUEUE3"]

    # test getting queue from environment variable
    environ["QUEUE_LIST"] = '["TEST_QUEUE10", "TEST_QUEUE11", "TEST_QUEUE12"]'
    args = parse_args([])
    del environ["QUEUE_LIST"]
    assert args.queue_list == ["TEST_QUEUE10", "TEST_QUEUE11", "TEST_QUEUE12"]
