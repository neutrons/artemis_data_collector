import argparse
import logging
import sys
import time
from importlib.resources import files

import psycopg
import requests

logger = logging.getLogger("AtremisDataCollector")


def initialize_database_tables(db_hostname, db_port, db_user, db_password, db_name):
    """Initializes the tables in the database from sql files. This will fail if the tables already exist.

    WebMon should have already created the tables so this is mostly for testing."""
    logger.info("Initializing tables")
    with psycopg.connect(dbname=db_name, host=db_hostname, port=db_port, user=db_user, password=db_password) as conn:
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
        self._session = self._session = requests.Session()
        self._session.auth = (self.config.artemis_user, self.config.artemis_password)
        self._session.headers.update({"Origin": "localhost"})

        self.base_url = f"{self.config.artemis_url}/console/jolokia/read/org.apache.activemq.artemis:broker=%22{self.config.broker_name}%22"  # noqa: E501

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

        logger.info(f"Monitoring queues: {" ".join(self.monitored_queue.keys())}")

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
        """Make a request to ActiveMQ Artemis Jolokia API"""
        try:
            response = self.session.get(self.base_url + query)
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error: {e}")
            return None

        if response.status_code != 200:
            logger.error(f"Error: {response.text}")
            return None

        try:
            if response.json()["status"] != 200:
                logger.error(f"Error: {response.json()}")
                return None
        except requests.exceptions.JSONDecodeError:
            logger.error(f"JSON decode Error: {response.text}")
            return None

        return response.json()["value"]

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


def main():
    parser = argparse.ArgumentParser(description="Collect data from Artemis")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    parser.add_argument(
        "--initialize_db",
        action="store_true",
        help="Initialize the database table and exit. Will fail if tables already exist",
    )
    parser.add_argument("--artemis_url", default="http://localhost:8161", help="URL of the Artemis instance")
    parser.add_argument("--artemis_user", default="artemis", help="User of the Artemis instance")
    parser.add_argument("--artemis_password", default="artemis", help="Password of the Artemis instance")
    parser.add_argument("--broker_name", default="0.0.0.0", help="Name of the Artemis broker")
    parser.add_argument("--database_hostname", default="localhost", help="Hostname of the database")
    parser.add_argument("--database_port", type=int, default=5432, help="Port of the database")
    parser.add_argument("--database_user", default="workflow", help="User of the database")
    parser.add_argument("--database_password", default="workflow", help="Password of the database")
    parser.add_argument("--database_name", default="workflow", help="Name of the database")
    parser.add_argument(
        "--queue_list", nargs="*", help="List of queues to monitor. If not specified, monitor all queues from database"
    )
    parser.add_argument("--interval", type=int, default=600, help="Interval to collect data (seconds)")
    parser.add_argument("--log_level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--log_file", help="Log file. If not specified, log to stdout")
    config = parser.parse_args()

    # setup logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=config.log_level, filename=config.log_file
    )

    try:
        if config.initialize_db:
            initialize_database_tables(
                config.database_hostname,
                config.database_port,
                config.database_user,
                config.database_password,
                config.database_name,
            )
            return 0

        adc = ArtemisDataCollector(config)
        adc.run()
    except KeyboardInterrupt:
        logger.info("Exiting")
        return 0
    except Exception as e:
        # catch any unhandled exception and log it before exiting
        logger.exception(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
