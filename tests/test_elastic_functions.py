import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import the functions to test
from app.lib.elastic_functions import initialize_db_connection, insert_data


class TestElasticFunctions(unittest.TestCase):

    def setUp(self):
        # Clear environment variables before each test
        env_vars = [
            "DB_TYPE",
            "DB_CLUSTER_NODES",
            "DB_TLS_INSECURE",
            "DB_CACERT_FILE",
            "DB_USERNAME",
            "DB_PASSWORD",
            "DB_API_KEY",
            "DB_TLS",
        ]
        for var in env_vars:
            os.environ.pop(var, None)

    @patch("app.lib.elastic_functions.Elasticsearch")
    def test_initialize_db_connection_elasticsearch_default(self, mock_es):
        # Test Elasticsearch connection with default settings
        os.environ["DB_TYPE"] = "elasticsearch"
        mock_instance = MagicMock()
        mock_instance.exists.return_value = True
        mock_es.return_value = mock_instance

        result = initialize_db_connection()

        mock_es.assert_called_once_with(
            hosts=["localhost:9200"],
            api_key=None,
            http_compress=True,
            verify_certs=True,
            ssl_assert_hostname=True,
            ssl_assert_fingerprint=True,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.Elasticsearch")
    def test_initialize_db_connection_elasticsearch_with_ssl(self, mock_es):
        # Test Elasticsearch with SSL
        os.environ["DB_TYPE"] = "elasticsearch"
        os.environ["DB_USE_SSL"] = "true"
        os.environ["DB_CLUSTER_NODES"] = "es.example.com:9200"
        mock_instance = MagicMock()
        mock_instance.exists.return_value = True
        mock_es.return_value = mock_instance

        result = initialize_db_connection(api_key="test_key")

        mock_es.assert_called_once_with(
            hosts=["es.example.com:9200"],
            api_key="test_key",
            http_compress=True,
            verify_certs=True,
            ssl_assert_hostname=True,
            ssl_assert_fingerprint=True,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.Elasticsearch")
    def test_initialize_db_connection_elasticsearch_insecure(self, mock_es):
        # Test Elasticsearch with insecure TLS
        os.environ["DB_TYPE"] = "elasticsearch"
        os.environ["DB_TLS_INSECURE"] = "true"
        mock_instance = MagicMock()
        mock_instance.exists.return_value = True
        mock_es.return_value = mock_instance

        result = initialize_db_connection()

        mock_es.assert_called_once_with(
            hosts=["localhost:9200"],
            api_key=None,
            http_compress=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_assert_fingerprint=False,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.Elasticsearch")
    def test_initialize_db_connection_elasticsearch_connection_failure(self, mock_es):
        # Test Elasticsearch connection failure
        os.environ["DB_TYPE"] = "elasticsearch"
        mock_instance = MagicMock()
        mock_instance.ping.return_value = False
        mock_es.return_value = mock_instance

        with self.assertRaises(ConnectionError):
            initialize_db_connection()

    @patch("app.lib.elastic_functions.OpenSearch")
    def test_initialize_db_connection_opensearch_default(self, mock_os):
        # Test OpenSearch connection with default settings
        os.environ["DB_TYPE"] = "opensearch"
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_os.return_value = mock_instance

        result = initialize_db_connection()

        mock_os.assert_called_once_with(
            hosts=[{"host": "localhost", "port": 9200}],
            http_compress=True,
            http_auth=None,
            use_ssl=False,
            verify_certs=True,
            ssl_assert_hostname=True,
            ssl_assert_fingerprint=True,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.OpenSearch")
    def test_initialize_db_connection_opensearch_with_auth(self, mock_os):
        # Test OpenSearch with authentication
        os.environ["DB_TYPE"] = "opensearch"
        os.environ["DB_USERNAME"] = "user"
        os.environ["DB_TLS"] = "true"
        os.environ["DB_CLUSTER_NODES"] = "os.example.com:9200"
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_os.return_value = mock_instance

        result = initialize_db_connection(db_password="pass")

        mock_os.assert_called_once_with(
            hosts=[{"host": "os.example.com", "port": 9200}],
            http_compress=True,
            http_auth=("user", "pass"),
            use_ssl=True,
            verify_certs=True,
            ssl_assert_hostname=True,
            ssl_assert_fingerprint=True,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.OpenSearch")
    def test_initialize_db_connection_opensearch_insecure(self, mock_os):
        # Test OpenSearch with insecure TLS
        os.environ["DB_TYPE"] = "opensearch"
        os.environ["DB_TLS_INSECURE"] = "true"
        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_os.return_value = mock_instance

        result = initialize_db_connection()

        mock_os.assert_called_once_with(
            hosts=[{"host": "localhost", "port": 9200}],
            http_compress=True,
            http_auth=None,
            use_ssl=False,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_assert_fingerprint=False,
            ssl_show_warn=False,
            ca_certs="/etc/ssl/certs/ca-certificates.crt",
        )
        self.assertEqual(result, mock_instance)

    @patch("app.lib.elastic_functions.OpenSearch")
    def test_initialize_db_connection_opensearch_connection_failure(self, mock_os):
        # Test OpenSearch connection failure
        os.environ["DB_TYPE"] = "opensearch"
        mock_instance = MagicMock()
        mock_instance.ping.return_value = False
        mock_os.return_value = mock_instance

        with self.assertRaises(ConnectionError):
            initialize_db_connection()

    def test_initialize_db_connection_invalid_db_type(self):
        # Test invalid DB_TYPE
        os.environ["DB_TYPE"] = "invalid"

        with self.assertRaises(ValueError):
            initialize_db_connection()

    @patch("app.lib.elastic_functions.__create_index")
    def test_insert_data_index_exists(self, mock_create_index):
        # Test insert_data when index exists
        mock_con = MagicMock()
        mock_con.indices.exists.return_value = True
        mock_con.index.return_value = {"result": "created"}

        insert_data(mock_con, "test_index", {}, {"key": "value"})

        mock_create_index.assert_not_called()
        mock_con.index.assert_called_once_with(index="test_index", body=json.dumps({"key": "value"}))

    @patch("app.lib.elastic_functions.__create_index")
    def test_insert_data_index_not_exists(self, mock_create_index):
        # Test insert_data when index does not exist
        mock_con = MagicMock()
        mock_con.indices.exists.return_value = False
        mock_con.index.return_value = {"result": "created"}
        body = {"mappings": {}}

        insert_data(mock_con, "test_index", body, {"key": "value"})

        mock_create_index.assert_called_once_with(con=mock_con, index="test_index", body=body)
        mock_con.index.assert_called_once_with(index="test_index", body=json.dumps({"key": "value"}))

    @patch("app.lib.elastic_functions.__prepare_index_name")
    def test_insert_data_prepare_index(self, mock_prepare):
        # Test that insert_data calls __prepare_index_name
        mock_prepare.return_value = "prepared_index"
        mock_con = MagicMock()
        mock_con.indices.exists.return_value = True
        mock_con.index.return_value = {"result": "created"}

        insert_data(mock_con, "test_index", {}, {"key": "value"})

        mock_prepare.assert_called_with("test_index")
