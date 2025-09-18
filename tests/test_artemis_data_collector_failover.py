#!/usr/bin/env python3
"""
Unit tests for Artemis Data Collector failover functionality.

These tests verify that the failover mechanism works correctly when the primary
broker fails and a failover broker is configured.
"""

import unittest
from unittest.mock import Mock, patch

import requests

from artemis_data_collector.artemis_data_collector import ArtemisDataCollector, parse_args


class TestArtemisDataCollectorFailover(unittest.TestCase):
    def setUp(self):
        """Set up test configuration with failover URL"""
        self.config = Mock()
        self.config.artemis_url = "http://primary:8161"
        self.config.artemis_failover_url = "http://failover:8161"
        self.config.artemis_user = "admin"
        self.config.artemis_password = "admin"
        self.config.artemis_broker_name = "0.0.0.0"
        self.config.database_hostname = "localhost"
        self.config.database_port = 5432
        self.config.database_user = "workflow"
        self.config.database_password = "workflow"
        self.config.database_name = "workflow"
        self.config.queue_list = ["TEST_QUEUE"]
        self.config.interval = 600
        self.config.log_level = "INFO"

    def _create_mock_cursor_context(self, mock_cursor):
        """Helper method to create a mock cursor context manager"""
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_cursor)
        mock_context.__exit__ = Mock(return_value=None)
        return mock_context

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_parse_args_with_failover(self, mock_session_class, mock_connect):
        """Test that parse_args correctly handles failover URL"""
        args = [
            "--artemis_url", "http://primary:8161",
            "--artemis_failover_url", "http://failover:8161",
            "--database_hostname", "localhost",
            "--queue_list", "TEST_QUEUE"
        ]
        
        config = parse_args(args)
        
        self.assertEqual(config.artemis_url, "http://primary:8161")
        self.assertEqual(config.artemis_failover_url, "http://failover:8161")

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_parse_args_without_failover(self, mock_session_class, mock_connect):
        """Test that parse_args works without failover URL"""
        args = [
            "--artemis_url", "http://primary:8161",
            "--database_hostname", "localhost",
            "--queue_list", "TEST_QUEUE"
        ]
        
        config = parse_args(args)
        
        self.assertEqual(config.artemis_url, "http://primary:8161")
        self.assertIsNone(config.artemis_failover_url)

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_request_activemq_primary_success(self, mock_session_class, mock_connect):
        """Test successful primary broker request"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("1", "TEST_QUEUE")]
        mock_conn.cursor.return_value = self._create_mock_cursor_context(mock_cursor)
        mock_connect.return_value = mock_conn

        # Mock session
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock successful responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": 200, "value": ["TEST_QUEUE"]}
        mock_session.get.return_value = mock_response

        adc = ArtemisDataCollector(self.config)
        result = adc.request_activemq("/QueueNames")

        # Should return primary response without trying failover
        self.assertEqual(result, ["TEST_QUEUE"])
        self.assertEqual(mock_session.get.call_count, 2)  # Init + request

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_request_activemq_failover_success(self, mock_session_class, mock_connect):
        """Test failover to secondary broker when primary fails"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("1", "TEST_QUEUE")]
        mock_conn.cursor.return_value = self._create_mock_cursor_context(mock_cursor)
        mock_connect.return_value = mock_conn

        # Mock session
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock init success, primary failure, failover success
        mock_response_init = Mock()
        mock_response_init.status_code = 200
        mock_response_init.json.return_value = {"status": 200, "value": ["TEST_QUEUE"]}

        mock_response_primary = Mock()
        mock_response_primary.status_code = 500

        mock_response_failover = Mock()
        mock_response_failover.status_code = 200
        mock_response_failover.json.return_value = {"status": 200, "value": {"TEST_QUEUE": "data"}}

        mock_session.get.side_effect = [mock_response_init, mock_response_primary, mock_response_failover]

        adc = ArtemisDataCollector(self.config)
        result = adc.request_activemq("/QueueNames")

        # Should return failover response
        self.assertEqual(result, {"TEST_QUEUE": "data"})
        self.assertEqual(mock_session.get.call_count, 3)  # Init + primary + failover

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_request_activemq_primary_exception_failover_success(self, mock_session_class, mock_connect):
        """Test failover when primary throws exception"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("1", "TEST_QUEUE")]
        mock_conn.cursor.return_value = self._create_mock_cursor_context(mock_cursor)
        mock_connect.return_value = mock_conn

        # Mock session
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # First, mock the get_activemq_queues call (which should succeed for initialization)
        mock_response_init = Mock()
        mock_response_init.status_code = 200
        mock_response_init.json.return_value = {"status": 200, "value": ["TEST_QUEUE"]}

        mock_response_failover = Mock()
        mock_response_failover.status_code = 200
        mock_response_failover.json.return_value = {"status": 200, "value": {"TEST_QUEUE": "data"}}

        # Set up the call sequence: init call succeeds, then primary throws exception, then failover succeeds
        mock_session.get.side_effect = [
            mock_response_init,  # get_activemq_queues
            requests.exceptions.ConnectionError("Connection failed"),  # primary fails with exception
            mock_response_failover,  # failover succeeds
        ]

        adc = ArtemisDataCollector(self.config)
        result = adc.request_activemq("/QueueNames")

        # Should return failover response
        self.assertEqual(result, {"TEST_QUEUE": "data"})
        self.assertEqual(mock_session.get.call_count, 3)  # Init + primary exception + failover

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_request_activemq_no_failover_configured(self, mock_session_class, mock_connect):
        """Test behavior when no failover is configured and primary fails"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("1", "TEST_QUEUE")]
        mock_conn.cursor.return_value = self._create_mock_cursor_context(mock_cursor)
        mock_connect.return_value = mock_conn

        # Create config without failover
        config_no_failover = Mock()
        config_no_failover.artemis_url = "http://primary:8161"
        config_no_failover.artemis_failover_url = None
        config_no_failover.artemis_user = "admin"
        config_no_failover.artemis_password = "admin"
        config_no_failover.artemis_broker_name = "0.0.0.0"
        config_no_failover.database_hostname = "localhost"
        config_no_failover.database_port = 5432
        config_no_failover.database_user = "workflow"
        config_no_failover.database_password = "workflow"
        config_no_failover.database_name = "workflow"
        config_no_failover.queue_list = ["TEST_QUEUE"]
        config_no_failover.interval = 600
        config_no_failover.log_level = "INFO"

        # Mock session
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock init success, then primary failure
        mock_response_init = Mock()
        mock_response_init.status_code = 200
        mock_response_init.json.return_value = {"status": 200, "value": ["TEST_QUEUE"]}

        mock_response_primary = Mock()
        mock_response_primary.status_code = 500

        mock_session.get.side_effect = [mock_response_init, mock_response_primary]

        adc = ArtemisDataCollector(config_no_failover)
        result = adc.request_activemq("/QueueNames")

        # Should return None when primary fails and no failover
        self.assertIsNone(result)
        self.assertEqual(mock_session.get.call_count, 2)  # Init + primary only

    @patch("artemis_data_collector.artemis_data_collector.psycopg.connect")
    @patch("artemis_data_collector.artemis_data_collector.requests.Session")
    def test_request_activemq_both_fail(self, mock_session_class, mock_connect):
        """Test behavior when both primary and failover fail"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [("1", "TEST_QUEUE")]
        mock_conn.cursor.return_value = self._create_mock_cursor_context(mock_cursor)
        mock_connect.return_value = mock_conn

        # Mock session
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock successful init, then both primary and failover fail
        mock_response_init = Mock()
        mock_response_init.status_code = 200
        mock_response_init.json.return_value = {"status": 200, "value": ["TEST_QUEUE"]}

        mock_response_primary = Mock()
        mock_response_primary.status_code = 500

        mock_response_failover = Mock()
        mock_response_failover.status_code = 500

        mock_session.get.side_effect = [mock_response_init, mock_response_primary, mock_response_failover]

        adc = ArtemisDataCollector(self.config)
        result = adc.request_activemq("/QueueNames")

        # Should return None when both fail
        self.assertIsNone(result)
        self.assertEqual(mock_session.get.call_count, 3)  # Init + primary + failover


if __name__ == "__main__":
    unittest.main()
