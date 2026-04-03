"""
OITC Access Control System: Logging service - Elasticsearch/OpenSearch functions
Author: Michael Oberdorf <info@oberdorf-itc.de>
Date:  2026-04-03
Copyright (c) 2026, Michael Oberdorf IT-Consulting. All rights reserved.
This software may be modified and distributed under the terms of the Apache 2.0 license. See the LICENSE file for details.
"""

import datetime
import json
import logging
import os

from elasticsearch import Elasticsearch
from opensearchpy import OpenSearch

__author__ = "Michael Oberdorf <info@oberdorf-itc.de>"
__status__ = "production"
__date__ = "2026-04-03"
__version_info__ = ("1", "0", "0")
__version__ = ".".join(__version_info__)

__all__ = ["initialize_db_connection", "insert_data"]

log = logging.getLogger(__name__)


def initialize_db_connection(db_password: str = None, api_key: str = None) -> Elasticsearch | OpenSearch:
    """
    Initialize the database connection to Elasticsearch or OpenSearch based on the configuration.

    :param db_password: The password for database authentication (optional, can also be set via environment variable DB_PASSWORD)
    :type db_password: str, optional
    :param api_key: The API key for database authentication (optional, can also be set via environment variable DB_API_KEY)
    :type api_key: str, optional
    :return The initialized database connection object.
    :rtype Elasticsearch or OpenSearch
    :raise ValueError: If the database configuration is not valid.
    :raise Exception: If the database connection cannot be initialized.
    """
    if os.environ.get("DB_TYPE", "opensearch").lower() == "elasticsearch":
        log.debug("Configure Elasticsearch connection")

        hosts = list()
        proto = "http"
        if os.environ.get("DB_USE_SSL", "false").lower() == "true":
            log.debug("Configure Elasticsearch connection to use TLS encryption.")
            proto = "https"
        for host in os.environ.get("DB_CLUSTER_NODES", "localhost:9200").split(","):
            hosts.append(f"{proto}://{host}")
        verify_certs = True
        ssl_assert_hostname = True
        if os.environ.get("DB_TLS_INSECURE", "false").lower() == "true":
            verify_certs = False
            ssl_assert_hostname = False
            log.debug("Configure OpenSearch connection to use TLS with insecure mode.")

        es = Elasticsearch(
            hosts=os.environ.get("DB_CLUSTER_NODES", "localhost:9200").split(","),
            api_key=api_key,
            http_compress=True,  # enables gzip compression for request bodies
            verify_certs=verify_certs,
            ssl_assert_hostname=ssl_assert_hostname,
            ssl_show_warn=False,
            ca_certs=os.environ.get("DB_CACERT_FILE", "/etc/ssl/certs/ca-certificates.crt"),
        )
        if es.exists():
            log.debug("Successfully connected to Elasticsearch cluster.")
        else:
            raise ConnectionError("Failed to connect to Elasticsearch cluster.")
        return es
    elif os.environ.get("DB_TYPE", "opensearch").lower() == "opensearch":
        log.debug("Configure OpenSearch connection")

        auth = None
        if os.environ.get("DB_USERNAME", None) and db_password:
            auth = (os.environ.get("DB_USERNAME"), db_password)
        hosts = list()

        for host in os.environ.get("DB_CLUSTER_NODES", "localhost:9200").split(","):
            server = host.split(":")[0]
            port = int(host.split(":")[1]) if len(host.split(":")) > 1 else 9200
            hosts.append({"host": server, "port": port})

        tls = False
        if os.environ.get("DB_USE_SSL", "false").lower() == "true":
            tls = True
            log.debug("Configure OpenSearch connection to use TLS encryption.")
        verify_certs = True
        ssl_assert_hostname = True
        if os.environ.get("DB_TLS_INSECURE", "false").lower() == "true":
            verify_certs = False
            ssl_assert_hostname = False
            log.debug("Configure OpenSearch connection to use TLS with insecure mode.")

        es = OpenSearch(
            hosts=hosts,
            http_compress=True,  # enables gzip compression for request bodies
            http_auth=auth,
            use_ssl=tls,
            verify_certs=verify_certs,
            ssl_assert_hostname=ssl_assert_hostname,
            ssl_show_warn=False,
            ca_certs=os.environ.get("DB_CACERT_FILE", "/etc/ssl/certs/ca-certificates.crt"),
        )

        if es.exists():
            log.debug("Successfully connected to OpenSearch cluster.")
        else:
            raise ConnectionError("Failed to connect to OpenSearch cluster.")
        return es
    else:
        raise ValueError("No valid database configuration found. Please check your environment variables.")


def __prepare_index_name(index: str) -> str:
    """
    Prepare the index name by replacing placeholders with current date values.

    :param index: The index name with placeholders
    :type index: str
    :return: The resolved index name
    :rtype: str
    """

    elasticIndex = (
        index.replace("{Y}", datetime.datetime.today().strftime("%Y"))
        .replace("{m}", datetime.datetime.today().strftime("%m"))
        .replace("{d}", datetime.datetime.today().strftime("%d"))
    )

    if index != elasticIndex:
        log.debug("Replacing placeholders in index name:")
        log.debug(f"  OLD: {index}")
        log.debug(f"  NEW: {elasticIndex}")
    else:
        log.debug(f"No placeholders found in index name: {index}")

    return elasticIndex


def __create_index(con: Elasticsearch | OpenSearch, index: str, body: dict) -> None:
    """
    Create a new index in the database if it does not exist.

    :param con: The database connection object
    :type con: Elasticsearch or OpenSearch
    :param index: The name of the index to create
    :type index: str
    :param body: The settings and mappings for the index
    :type body: dict
    :return: None
    :rtype: None
    """
    index = __prepare_index_name(index)

    if not con.indices.exists(index=index):
        host_port = os.environ.get("DB_CLUSTER_NODES", "localhost:9200").split(",")[0]
        log.debug(f"Creating index: {host_port}{index}")
        log.debug(f"  {body}")
        con.indices.create(index=index, body=body)
    else:
        log.debug("Skip creation of index, because it already exists.")

    return None


# def __removeIndex(con: Elasticsearch | OpenSearch, index: str, exitAfterRemoval: bool = True) -> None:
#    """
#    Removing an index in the database if it exists.
#
#    :param con: The database connection object
#    :type con: Elasticsearch or OpenSearch
#    :param index: The name of the index to remove
#    :type index: str
#    :param exitAfterRemoval: Whether to exit the program after removing the index (default: True)
#    :type exitAfterRemoval: bool
#    :return: None
#    :rtype: None
#    """
#    index = __prepare_index_name(index)
#
#    if con.indices.exists(index=index):
#        log.debug("Removing index: {}".format(index))
#        con.indices.delete(index=index)
#    else:
#        log.debug("Skip to removing index, because it is not existing.")
#
#    if exitAfterRemoval:
#        log.debug("End program after removing index.")
#        sys.exit()
#    else:
#        return None


def insert_data(con: Elasticsearch | OpenSearch, index: str, body: dict, data: dict) -> None:
    """
    Insert data into the specified index in the database.

    :param con: The database connection object
    :type con: Elasticsearch or OpenSearch
    :param index: The name of the index to insert data into
    :type index: str
    :param body: The settings and mappings for the index (used for index creation if index does not exist)
    :type body: dict
    :param data: The data to insert into the index
    :type data: dict
    :return: None
    :rtype: None
    """

    index = __prepare_index_name(index)

    # check if index exist, if not trigger creation
    if not con.indices.exists(index=index):
        __create_index(con=con, index=index, body=body)

    log.info(f"Add data to index: {index}")
    res = con.index(index=index, body=json.dumps(data))

    log.debug(f"Result: {res['result']}")

    return None
