import argparse
import ast
import logging
import sys
import time
from importlib.resources import files
from os import environ

import psycopg
import requests

logger = logging.getLogger("AtremisDataCollector")


def initialize_database_tables(config):
    """Initializes the tables in the database from sql files. This will fail if the tables already exist.

    WebMon should have already created the tables so this is mostly for testing."""
    logger.info("Initializing tables")
    with psycopg.connect(
        dbname=config.database_name,
        host=config.database_hostname,
        port=config.database_port,
        user=config.database_user,
        password=config.database_password,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(files("artemis_data_collector.sql").joinpath("report_statusqueue.sql").read_text())
            conn.commit()
            cur.execute(files("artemis_data_collector.sql").joinpath("report_statusqueuemessagecount.sql").read_text())
            conn.commit()


class ArtemisDataCollector:
    def __init__(self, config):
        logger.info("Initializing ArtemisDataCollector")
        self.config = config
        self._conn = None

        # common session for all requests
        self._session = requests.Session()
        self._session.auth = (self.config.artemis_user, self.config.artemis_password)
        self._session.headers.update({"Origin": "localhost"})

        # Build primary and failover base URLs
        self.base_url = f"{self.config.artemis_url}/console/jolokia/read/org.apache.activemq.artemis:broker=%22{self.config.artemis_broker_name}%22"  # noqa: E501
        self.base_failover_url = None
        if hasattr(self.config, "artemis_failover_url") and self.config.artemis_failover_url:
            self.base_failover_url = f"{self.config.artemis_failover_url}/console/jolokia/read/org.apache.activemq.artemis:broker=%22{self.config.artemis_broker_name}%22"  # noqa: E501

        database_statusqueues = self.get_database_statusqueues()
        amq_queues = self.get_activemq_queues()
        if amq_queues is None:
            raise ValueError("Failed to get queues from ActiveMQ Artemis")

        # validate requested queues exist in database and activemq.
        # If queue_list is not specified, monitor all queues from the database
        queue_list = self.config.queue_list if self.config.queue_list is not None else database_statusqueues.keys()

        self.monitored_queue = {}
        for queue in queue_list:
            if queue not in database_statusqueues:
                logger.error(f"Queue {queue} not found in database, skipping")
            elif queue not in amq_queues:
                logger.error(f"Queue {queue} not found in ActiveMQ Artemis, skipping")
            else:
                self.monitored_queue[queue] = database_statusqueues[queue]

        if not self.monitored_queue:
            raise ValueError("No queues to monitor")

        logger.info(f"Monitoring queues: {' '.join(self.monitored_queue.keys())}")

    @property
    def conn(self):
        """Connect to the database if not already connected"""
        logger.debug("Getting database connection")
        if self._conn is None or self._conn.closed:
            logger.debug("Connecting to database %s at %s", self.config.database_name, self.config.database_hostname)
            self._conn = psycopg.connect(
                dbname=self.config.database_name,
                host=self.config.database_hostname,
                port=self.config.database_port,
                user=self.config.database_user,
                password=self.config.database_password,
            )
        return self._conn

    @property
    def session(self):
        return self._session

    def run(self):
        """Main loop to collect data and add to database"""
        while True:
            data = self.collect_data()
            if data is not None:
                self.add_to_database(data)
            time.sleep(self.config.interval)

    def request_activemq(self, query):
        """Make a request to ActiveMQ Artemis Jolokia API with failover support"""
        # Try primary URL first
        try:
            response = self.session.get(self.base_url + query, timeout=self.config.http_timeout)
            if response.status_code == 200:
                try:
                    json_response = response.json()
                    if json_response["status"] == 200:
                        return json_response["value"]
                    else:
                        logger.error(f"Primary broker error: {json_response}")
                except (ValueError, requests.exceptions.JSONDecodeError):
                    logger.exception("Primary broker JSON decode error (truncated payload): %s", str(response.text)[:512])
            else:
                logger.error(f"Primary broker HTTP error {response.status_code}: {str(response.text)[:512]}")
        except requests.exceptions.RequestException:
            logger.exception("Primary broker connection error")

        # If primary fails and failover is configured, try failover URL
        if self.base_failover_url:
            logger.info("Primary broker failed, trying failover broker")
            try:
                response = self.session.get(self.base_failover_url + query, timeout=self.config.http_timeout)
                if response.status_code == 200:
                    try:
                        json_response = response.json()
                        if json_response["status"] == 200:
                            logger.info("Successfully connected to failover broker")
                            return json_response["value"]
                        else:
                            logger.error(f"Failover broker error: {json_response}")
                    except (ValueError, requests.exceptions.JSONDecodeError):
                        logger.exception("Failover broker JSON decode error (truncated payload): %s", str(response.text)[:512])
                else:
                    logger.error(f"Failover broker HTTP error {response.status_code}: {str(response.text)[:512]}")
            except requests.exceptions.RequestException:
                logger.exception("Failover broker connection error")
        else:
            logger.warning("No failover broker configured")

        return None

    def get_activemq_queues(self):
        """Returns a list of queues from the Artemis"""
        return self.request_activemq("/AddressNames")

    def collect_data(self):
        # get all queue lengths in one call
        values = self.request_activemq(",address=%22*%22,component=addresses/MessageCount,Address")
        if values is None:
            return None

        queue_message_counts = []

        for counts in values.values():
            if counts["Address"] in self.monitored_queue:
                queue_message_counts.append(
                    (
                        self.monitored_queue[counts["Address"]],
                        counts["MessageCount"],
                    )
                )

        if queue_message_counts:
            logger.info(f"Successfully collected data for {len(queue_message_counts)} queues")
        return queue_message_counts

    def add_to_database(self, data):
        try:
            with self.conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO report_statusqueuemessagecount (queue_id, message_count, created_on) VALUES(%s,%s, now())",  # noqa: E501
                    data,
                )
            self.conn.commit()
        except psycopg.errors.DatabaseError as e:
            # We want to catch any database errors and log them but continue running
            logger.error(e)
        else:
            logger.info("Successfully added records to the database")

    def get_database_statusqueues(self):
        """Returns maps of status queues to id from the database"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, name FROM report_statusqueue")
            queues = cur.fetchall()

        # make map from name to id
        queue_map = {}
        for queue in queues:
            queue_map[queue[1]] = queue[0]

        return queue_map


def parse_args(args):
    # parse command line arguments where values can alternavitly be set via environment variables
    parser = argparse.ArgumentParser(description="Collect data from Artemis with failover support")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    parser.add_argument(
        "--initialize_db",
        action="store_true",
        help="Initialize the database tables and exit. Will fail if tables already exist",
    )
    parser.add_argument(
        "--artemis_url", 
        default=environ.get("ARTEMIS_URL", "http://localhost:8161"), 
        help="URL of the primary Artemis instance"
    )
    parser.add_argument(
        "--artemis_failover_url",
        default=environ.get("ARTEMIS_FAILOVER_URL"),
        help="URL of the failover Artemis instance (optional)",
    )
    parser.add_argument(
        "--artemis_user", default=environ.get("ARTEMIS_USER", "artemis"), help="User of the Artemis instance"
    )
    parser.add_argument(
        "--artemis_password",
        default=environ.get("ARTEMIS_PASSWORD", "artemis"),
        help="Password of the Artemis instance",
    )
    parser.add_argument(
        "--artemis_broker_name",
        default=environ.get("ARTEMIS_BROKER_NAME", "0.0.0.0"),
        help="Name of the Artemis broker",
    )
    parser.add_argument(
        "--database_hostname", default=environ.get("DATABASE_HOST", "localhost"), help="Hostname of the database"
    )
    parser.add_argument(
        "--database_port", type=int, default=environ.get("DATABASE_PORT", 5432), help="Port of the database"
    )
    parser.add_argument(
        "--database_user", default=environ.get("DATABASE_USER", "workflow"), help="User of the database"
    )
    parser.add_argument(
        "--database_password", default=environ.get("DATABASE_PASS", "workflow"), help="Password of the database"
    )
    parser.add_argument(
        "--database_name", default=environ.get("DATABASE_NAME", "workflow"), help="Name of the database"
    )
    parser.add_argument(
        "--queue_list",
        nargs="*",
        default=ast.literal_eval(environ.get("QUEUE_LIST", "None")),
        help="List of queues to monitor. If not specified, monitor all queues from database",
    )
    parser.add_argument(
        "--interval", type=int, default=environ.get("INTERVAL", 600), help="Interval to collect data (seconds)"
    )
    parser.add_argument(
        "--log_level",
        default=environ.get("LOG_LEVEL", "INFO"),
        help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument("--log_file", default=environ.get("LOG_FILE"), help="Log file. If not specified, log to stdout")
    parser.add_argument(
        "--http_timeout",
        type=float,
        default=float(environ.get("HTTP_TIMEOUT", "10")),
        help="HTTP timeout in seconds for broker requests",
    )
    return parser.parse_args(args)


def main():
    config = parse_args(sys.argv[1:])

    # setup logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=config.log_level, filename=config.log_file
    )

    if config.initialize_db:
        initialize_database_tables(config)
        return 0

    try:
        adc = ArtemisDataCollector(config)
        adc.run()
    except KeyboardInterrupt:
        logger.info("Exiting")
        return 0
    except Exception as e:
        # catch any unhandled exception and log it before exiting
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
