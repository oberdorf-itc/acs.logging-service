import datetime
import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import the functions to test with aliases to avoid name mangling
from app.service import __initialize_logger as init_logger
from app.service import __initialize_mqtt_client as init_mqtt_client
from app.service import __initialize_prometheus_exporter as init_prometheus
from app.service import __validate_configuration as validate_config
from app.service import (
    on_connect,
    on_message,
    on_subscribe,
)


class TestService(unittest.TestCase):

    def setUp(self):
        # Clear relevant environment variables before each test
        env_vars = [
            "MQTT_SERVER",
            "MQTT_TOPIC_DOOR_ACCESS",
            "MQTT_TOPIC_ACS_STATUS",
            "DB_PASSWORD_FILE",
            "DB_PASSWORD",
            "DB_API_KEY_FILE",
            "DB_API_KEY",
            "MAPPING_FILE",
            "TZ",
            "PROMETHEUS_LISTENER_ADDR",
            "PROMETHEUS_LISTENER_PORT",
            "MQTT_CLIENT_ID",
            "MQTT_PROTOCOL_VERSION",
            "MQTT_TLS",
            "REQUESTS_CA_BUNDLE",
            "MQTT_CACERT_FILE",
            "MQTT_TLS_INSECURE",
            "MQTT_PASSWORD",
            "MQTT_PASSWORD_FILE",
            "MQTT_USERNAME",
            "DEBUG",
        ]
        for var in env_vars:
            os.environ.pop(var, None)

        # Set mock globals for testing
        import app.service as service

        service.log = MagicMock()
        service.metrics = MagicMock()
        service.es = MagicMock()
        service.topic2index = {"topic": {"elasticIndex": "index", "elasticBody": {}}}

    @patch("app.service.logging.getLogger")
    @patch("app.service.logging.StreamHandler")
    def test_initialize_logger_valid_severity(self, mock_stream_handler, mock_get_logger):
        mock_logger = MagicMock()
        mock_handler = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_stream_handler.return_value = mock_handler

        result = init_logger(logging.INFO)

        mock_get_logger.assert_called_once()
        mock_logger.setLevel.assert_called_with(logging.INFO)
        mock_handler.setLevel.assert_called_with(logging.INFO)
        self.assertEqual(result, mock_logger)

    def test_initialize_logger_invalid_severity(self):
        with self.assertRaises(ValueError):
            init_logger(999)

    @patch("app.service.os.path.isfile")
    @patch("app.service.open", new_callable=mock_open, read_data='{"test": "data"}')
    @patch.dict(os.environ, {"MAPPING_FILE": "/app/etc/mappings.json"})
    @patch("app.service.log")
    def test_validate_configuration_success_env_vars(self, mock_log, mock_file, mock_isfile):
        mock_isfile.return_value = True
        os.environ["MQTT_SERVER"] = "localhost"
        os.environ["MQTT_TOPIC_DOOR_ACCESS"] = "topic1"
        os.environ["MQTT_TOPIC_ACS_STATUS"] = "topic2"
        os.environ["DB_PASSWORD"] = "password"
        os.environ["DB_API_KEY"] = "apikey"

        result = validate_config()

        self.assertEqual(result, ("password", "apikey"))

    def test_validate_configuration_missing_mqtt_server(self):
        with self.assertRaises(ValueError):
            validate_config()

    @patch("app.service.prom.start_http_server")
    @patch("app.service.prom.Info")
    @patch("app.service.prom.Counter")
    @patch("app.service.log")
    def test_initialize_prometheus_exporter(self, mock_log, mock_counter, mock_info, mock_start):
        mock_start.return_value = (True, True)
        mock_info.return_value = MagicMock()
        mock_counter.return_value = MagicMock()

        result = init_prometheus()

        self.assertIn("service_info", result)
        self.assertIn("mqtt_connects", result)
        mock_start.assert_called_once()

    @patch("app.service.mqtt.Client")
    @patch.dict(os.environ, {"MQTT_CLIENT_ID": "test_client"})
    @patch("app.service.log")
    def test_initialize_mqtt_client_v311(self, mock_log, mock_client):
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        result = init_mqtt_client()

        mock_client.assert_called_once()
        self.assertEqual(result, mock_client_instance)

    @patch("app.service.log")
    @patch("app.service.metrics")
    @patch("app.service.topic2index")
    def test_on_connect_success(self, mock_topic2index, mock_metrics, mock_log):
        mock_topic2index.keys.return_value = ["topic1"]
        client = MagicMock()
        flags = {}
        rc = 0
        properties = MagicMock()

        on_connect(client, None, flags, rc, properties)

        mock_metrics.__getitem__.return_value.inc.assert_called_once()
        client.subscribe.assert_called_with("topic1")

    @patch("app.service.log")
    def test_on_subscribe_success(self, mock_log):
        client = MagicMock()
        userdata = {}
        mid = 1
        reason_code_list = [MagicMock(is_failure=False, value=0)]
        properties = MagicMock()

        on_subscribe(client, userdata, mid, reason_code_list, properties)

        # Should not raise error

    @patch("app.service.log")
    @patch("app.service.metrics")
    @patch("app.service.insert_data")
    @patch("app.service.es")
    @patch("app.service.topic2index")
    @patch("app.service.datetime")
    @patch("app.service.mqtt.topic_matches_sub")
    def test_on_message_valid(
        self, mock_topic_matches, mock_datetime, mock_topic2index, mock_es, mock_insert_data, mock_metrics, mock_log
    ):
        mock_topic_matches.return_value = True
        mock_topic2index.keys.return_value = ["topic"]
        mock_topic2index.__getitem__.return_value = {"elasticIndex": "index", "elasticBody": {}}
        msg = MagicMock()
        msg.topic = "topic"
        msg.payload = b'{"timestamp": "2023-01-01T00:00:00Z"}'
        msg.qos = 0
        msg.retain = False

        current_time = datetime.datetime.now()
        mock_datetime.datetime.now.return_value = current_time
        mock_datetime.datetime.fromisoformat.return_value = current_time - datetime.timedelta(seconds=5)

        on_message(None, None, msg)

        mock_insert_data.assert_called_once()
        mock_metrics.__getitem__.return_value.labels.return_value.inc.assert_called_once()

    @patch("app.service.log")
    @patch("app.service.metrics")
    def test_on_message_old_timestamp(self, mock_metrics, mock_log):
        msg = MagicMock()
        msg.payload = b'{"timestamp": "2023-01-01T00:00:00Z"}'

        with patch("app.service.datetime") as mock_datetime:
            current_time = datetime.datetime.now()
            mock_datetime.datetime.now.return_value = current_time
            mock_datetime.datetime.fromisoformat.return_value = current_time - datetime.timedelta(seconds=15)

            on_message(None, None, msg)

            mock_metrics.__getitem__.return_value.inc.assert_called()  # mqtt_messages_refused
