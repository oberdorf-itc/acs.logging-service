"""
OITC Access Control System: Logging service
Author: Michael Oberdorf <info@oberdorf-itc.de>
Date:  2019-03-14
Copyright (c) 2019, Michael Oberdorf IT-Consulting. All rights reserved.
This software may be modified and distributed under the terms of the Apache 2.0 license. See the LICENSE file for details.
"""

import datetime
import json
import logging
import os
import ssl
import sys

import paho.mqtt.client as mqtt
import prometheus_client as prom
import pytz
from lib.elastic_functions import initialize_db_connection, insert_data

__author__ = "Michael Oberdorf <info@oberdorf-itc.de>"
__status__ = "production"
__date__ = "2026-04-05"
__version_info__ = ("1", "0", "0")
__version__ = ".".join(__version_info__)

__local_tz__ = pytz.timezone(os.environ.get("TZ", "UTC"))

if not os.path.isfile(os.environ.get("MAPPING_FILE", "/app/etc/mappings.json")):
    raise ValueError(f"MAPPING_FILE file {os.environ.get("MAPPING_FILE", "/app/etc/mappings.json")} not found.")
with open(os.environ.get("MAPPING_FILE", "/app/etc/mappings.json")) as f:
    topic2index = json.load(f)

"""
###############################################################################
# F U N C T I O N S
###############################################################################
"""


def __initialize_logger(severity: int = logging.INFO) -> logging.Logger:
    """
    Initialize the logger with the given severity level.

    :param severity int: The optional severity level for the logger. (default: 20 (INFO))
    :return logging.RootLogger: The initialized logger.
    :raise ValueError: If the severity level is not valid.
    :raise TypeError: If the severity level is not an integer.
    :raise Exception: If the logger cannot be initialized.
    """
    valid_severity = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
    if severity not in valid_severity:
        raise ValueError(f"Invalid severity level: {severity}. Must be one of {valid_severity}.")

    log = logging.getLogger()
    log_handler = logging.StreamHandler(sys.stdout)

    log.setLevel(severity)
    log_handler.setLevel(severity)
    log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_handler.setFormatter(log_formatter)
    log.addHandler(log_handler)

    return log


def __validate_configuration() -> tuple[str, str]:
    """
    Validate the configuration from environment variables.

    :return tuple[str, str]: The validated db password and api_key.
    :raise ValueError: If the configuration is not valid.
    :raise Exception: If the configuration cannot be validated.
    """
    if os.environ.get("MQTT_SERVER", None) is None:
        raise ValueError("MQTT_SERVER environment variable is not set.")

    # validate and read db user password from environment variables or files
    __db_password__ = None
    if os.environ.get("DB_PASSWORD_FILE", None) is not None:
        if not os.path.isfile(os.environ.get("DB_PASSWORD_FILE", None)):
            raise ValueError(f"DB_PASSWORD_FILE file {os.environ.get("DB_PASSWORD_FILE")} not found.")
        with open(os.environ["DB_PASSWORD_FILE"]) as file:
            __db_password__ = file.read().strip().replace("\n", "")
            if __db_password__ == "":
                raise ValueError(f"DB_PASSWORD_FILE file {os.environ.get("DB_PASSWORD_FILE")} is empty.")
    else:
        if os.environ.get("DB_PASSWORD", None) is not None:
            log.debug("Use db password from environment variable.")
            __db_password__ = os.environ.get("DB_PASSWORD")

    # validate and read api_key from environment variables or files
    __api_key__ = None
    if os.environ.get("DB_API_KEY_FILE", None) is not None:
        if not os.path.isfile(os.environ.get("DB_API_KEY_FILE", None)):
            raise ValueError(f"DB_API_KEY_FILE file {os.environ.get("DB_API_KEY_FILE")} not found.")
        with open(os.environ["DB_API_KEY_FILE"]) as file:
            __api_key__ = file.read().strip().replace("\n", "")
            if __api_key__ == "":
                raise ValueError(f"DB_API_KEY_FILE file {os.environ.get("DB_API_KEY_FILE")} is empty.")
    else:
        if os.environ.get("DB_API_KEY", None) is not None:
            log.debug("Use db api key from environment variable.")
            __api_key__ = os.environ.get("DB_API_KEY")

    return __db_password__, __api_key__


def __initialize_prometheus_exporter() -> dict:
    """
    Intialize and start the prometheus exporter endpoint

    :return The different initialized prometheus metrics as a dict of objects
    :rtype dict
    :raise Exception: If the prometheus exporter cannot be initialized or started.
    """
    log.debug("def initialize_prometheus_exporter() -> dict:")

    m = {
        "service_info": prom.Info("service_info", "Information about the service"),
        "mqtt_connects": prom.Counter("mqtt_connects", "Count all MQTT connection events"),
        "mqtt_messages": prom.Counter("mqtt_messages", "Count all received MQTT messages"),
        "mqtt_messages_refused": prom.Counter(
            "mqtt_messages_refused", "Count all refused MQTT messages due to timestamp drift."
        ),
        "acs_access_granted": prom.Counter(
            "acs_access_granted",
            "Count all access granted events received by transponders",
            labelnames=["entrypoint_ip"],
        ),
        "acs_access_denied": prom.Counter(
            "acs_access_denied", "Count all access denied events received by transponders", labelnames=["entrypoint_ip"]
        ),
        "acs_status_messages": prom.Counter(
            "acs_status_messages",
            "Count all status messages received by the access control system",
            labelnames=["severity"],
        ),
        "objects_written_to_db": prom.Counter(
            "objects_written_to_db", "Count all objects written to the database", labelnames=["object_type"]
        ),
    }

    prometheus_listener_addr = os.environ.get("PROMETHEUS_LISTENER_ADDR", "0.0.0.0")
    prometheus_listener_port = int(os.environ.get("PROMETHEUS_LISTENER_PORT", "8080"))
    log.info("Starting prometheus exporter listener: %s:%s", prometheus_listener_addr, prometheus_listener_port)
    s, t = prom.start_http_server(port=prometheus_listener_port, addr=prometheus_listener_addr)
    if not s or not t:
        raise RuntimeError("The Prometheus exporter http endpoint failed to start.")

    return m


def __initialize_mqtt_client() -> mqtt.Client:
    """
    Initialize the MQTT client with the given configuration from environment.

    :return mqtt.Client: The initialized MQTT client.
    :raise ValueError: If the MQTT client configuration is not valid.
    :raise Exception: If the MQTT client cannot be initialized.
    """
    if os.environ.get("MQTT_CLIENT_ID", None) is not None:
        log.debug("Use MQTT client ID: {}".format(os.environ.get("MQTT_CLIENT_ID", None)))

    if os.environ.get("MQTT_PROTOCOL_VERSION") == "5":
        log.debug("MQTT protocol version 5")
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=os.environ.get("MQTT_CLIENT_ID", None),
            userdata=None,
            transport="tcp",
            protocol=mqtt.MQTTv5,
        )
    else:
        log.debug("MQTT protocol version 3.1.1")
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=os.environ.get("MQTT_CLIENT_ID", None),
            clean_session=True,
            userdata=None,
            transport="tcp",
            protocol=mqtt.MQTTv311,
        )

    # configure TLS
    if os.environ.get("MQTT_TLS", "false").lower() == "true":
        log.debug("Configure MQTT connection to use TLS encryption.")

        __ca_cert_file__ = "/etc/ssl/certs/ca-certificates.crt"
        if os.environ.get("REQUESTS_CA_BUNDLE", None) is not None:
            __ca_cert_file__ = os.environ.get("REQUESTS_CA_BUNDLE")
        if os.environ.get("MQTT_CACERT_FILE", None) is not None:
            __ca_cert_file__ = os.environ.get("MQTT_CACERT_FILE")

        if os.environ.get("MQTT_TLS_INSECURE", "false").lower() == "true":
            log.debug("Configure MQTT connection to use TLS with insecure mode.")
            client.tls_set(
                ca_certs=__ca_cert_file__,
                cert_reqs=ssl.CERT_NONE,
                tls_version=ssl.PROTOCOL_TLSv1_2,
                ciphers=None,
            )
            client.tls_insecure_set(True)
        else:
            log.debug("Configure MQTT connection to use TLS with secure mode.")
            client.tls_set(
                ca_certs=__ca_cert_file__,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
                ciphers=None,
            )
            client.tls_insecure_set(False)

    # configure authentication
    mqtt_pass = None
    if os.environ.get("MQTT_PASSWORD", None) is not None:
        mqtt_pass = os.environ.get("MQTT_PASSWORD")
    if os.environ.get("MQTT_PASSWORD_FILE", None) is not None:
        if not os.path.isfile(os.environ.get("MQTT_PASSWORD_FILE", None)):
            raise ValueError("MQTT password file {} not found.".format(os.environ.get("MQTT_PASSWORD_FILE", None)))
        with open(os.environ.get("MQTT_PASSWORD_FILE", None)) as f:
            mqtt_pass = f.read().strip().replace("\n", "")
    if os.environ.get("MQTT_USERNAME", None) is not None and mqtt_pass is not None:
        log.debug("Set username ({}) and password for MQTT connection".format(os.environ.get("MQTT_USERNAME", None)))
        client.username_pw_set(os.environ.get("MQTT_USERNAME", None), mqtt_pass)

    # register callback functions
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe

    return client


def on_connect(client: mqtt.Client, userdata: dict, flags: dict, rc: int, properties: mqtt.Properties) -> None:
    """
    on_connect - The MQTT callback for when the client receives a CONNACK response from the server.

    :param client: The object of the MQTT connection
    :type client: paho.mqtt.client.Client
    :param userdata: the user data of the MQTT connection
    :type userdata: dict
    :param flags: connection parameters
    :type flags: dict
    :param rc: the return code
    :type rc: int
    :return None
    """
    log.debug(f"MQTT client connected with result code {rc}")
    log.debug(f"MQTT connection flags: {flags}")
    log.debug(f"MQTT connection userdata: {userdata}")
    log.debug(f"MQTT connection properties: {properties}")

    metrics["mqtt_connects"].inc()

    # check for return code
    if rc != 0:
        log.error(f"Error in connecting to MQTT Server, RC={rc}")
        sys.exit(1)

    # Subscribing in on_connect() means that if we lose the connection and reconnect then subscriptions will be renewed.
    for topic in topic2index.keys():
        log.debug(f"MQTT client subscribing to topic: {topic}")
        client.subscribe(topic)


def on_subscribe(
    client: mqtt.Client, userdata: dict, mid: int, reason_code_list: list, properties: mqtt.Properties
) -> None:
    """
    on_subscribe - The MQTT callback for when the client receives a SUBACK response from the server.

    :param client: The object of the MQTT connection
    :type client: paho.mqtt.client.Client
    :param userdata: the user data of the MQTT connection
    :type userdata: dict
    :param mid: the message ID of the subscribe request
    :type mid: int
    :param reason_code_list: the list of reason codes for the subscribe request
    :type reason_code_list: list
    :param properties: the MQTT properties of the subscribe response
    :type properties: paho.mqtt.client.MQTTProperties
    :return None
    """
    log.debug(
        f"MQTT client received SUBACK for message ID {mid} with reason codes {reason_code_list} and properties {properties}"
    )
    log.debug(f"MQTT client userdata: {userdata}")
    if reason_code_list[0].is_failure:
        log.error(f"Broker rejected you subscription: {reason_code_list[0]}")
    else:
        log.debug(f"Broker granted the following QoS: {reason_code_list[0].value}")


def on_message(client: mqtt.Client, userdata: dict, msg: mqtt.MQTTMessage) -> None:
    """
    on_message - The MQTT callback for when a PUBLISH message is received from the server.

    :param client: the object of the MQTT connection
    :type client: paho.mqtt.client.Client
    :param userdata: the user data of the MQTT connection
    :type userdata: dict
    :param msg: the object of the MQTT message received
    :type msg: paho.mqtt.client.MQTTMessage
    :return None
    """
    log.debug(f"MQTT message received on topic {msg.topic} with QoS {msg.qos} and retain flag {msg.retain}")
    metrics["mqtt_messages"].inc()

    # parse message payload as JSON object
    PAYLOAD = json.loads(str(msg.payload.decode("utf-8")))
    log.debug(f"MQTT message payload: {PAYLOAD}")

    # parse timestamp from payload and compare with current time to check if message is not too old (older than 10 seconds)
    timestamp = PAYLOAD.get("timestamp", None)
    if timestamp:
        # Convert timestamp to datetime object
        msg_timestamp = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        # Get current time
        current_time = datetime.datetime.now(__local_tz__)
        # Check if message is older than 10 seconds
        if (current_time - msg_timestamp).total_seconds() > 10:
            log.warning(f"MQTT message is too old: {timestamp}")
            metrics["mqtt_messages_refused"].inc()
            return

    # check if topic of message matches any of the configured topics, if not skip message
    for topic in topic2index.keys():
        if mqtt.topic_matches_sub(topic, msg.topic):
            log.debug(f"MQTT message topic {msg.topic} matches configured topic {topic}")

            insert_data(
                con=es,
                index=topic2index[topic]["elasticIndex"],
                body=topic2index[topic]["elasticBody"],
                data=PAYLOAD,
            )
            metrics["objects_written_to_db"].labels(object_type=topic).inc()
            return
    else:
        log.warning(f"No mapping found for topic: {msg.topic}, skipping message.")
        return None


"""
###############################################################################
# M A I N
###############################################################################
"""
if __name__ == "__main__":
    # initialize logger
    if os.getenv("DEBUG", "false").lower() == "true":
        log = __initialize_logger(logging.DEBUG)
    else:
        log = __initialize_logger(logging.INFO)
    log.info(f"Starting OITC Access Control System logging service version {__version__}")

    # validate configuration
    __db_password__, __api_key__ = __validate_configuration()

    # initialize prometheus exporter
    metrics = __initialize_prometheus_exporter()
    metrics["service_info"].info(
        {
            "version": __version__,
            "author": __author__,
            "status": __status__,
            "timezone": __local_tz__.zone,
        }
    )

    # Initialize database connection
    es = initialize_db_connection(
        db_password=__db_password__,
        api_key=__api_key__,
    )

    # Initialize MQTT client
    client = __initialize_mqtt_client()
    log.debug("MQTT client initialized")
    # connect to MQTT server
    log.debug(
        "Connecting to MQTT server {}:{}".format(
            os.environ.get("MQTT_SERVER", "localhost"), os.environ.get("MQTT_PORT", 1883)
        )
    )
    try:
        client.connect(os.environ.get("MQTT_SERVER", "localhost"), int(os.environ.get("MQTT_PORT", 1883)), 60)
    except ssl.SSLCertVerificationError as e:
        log.error("SSL certificate verification error: {}".format(e))
        sys.exit(1)
    log.debug("Connected to MQTT server")

    client.loop_forever()

    client.disconnect()

    log.info(f"Stopping OITC Access Control System logging service version {__version__}")
    sys.exit()
