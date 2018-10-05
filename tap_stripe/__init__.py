#!/usr/bin/env python3
import os
import json
import logging

import stripe
import singer
from singer import utils, Transformer

REQUIRED_CONFIG_KEYS = [
    "account_id",
    "client_secret"
]
STREAM_SDK_OBJECTS = {
    'charges': stripe.Charge,
}
LOGGER = singer.get_logger()

def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)

# Load schemas from schemas folder
def load_schemas():
    schemas = {}

    for filename in os.listdir(get_abs_path('schemas')):
        path = get_abs_path('schemas') + '/' + filename
        file_raw = filename.replace('.json', '')
        with open(path) as file:
            schemas[file_raw] = json.load(file)

    return schemas

def discover():
    raw_schemas = load_schemas()
    streams = []

    for schema_name, schema in raw_schemas.items():
        # create and add catalog entry
        catalog_entry = {
            'stream': schema_name,
            'tap_stream_id': schema_name,
            'schema': schema,
            'metadata': [],
            # TODO This might need to change for Events because their key property may not be 
            'key_properties': ['id']
        }
        streams.append(catalog_entry)

    return {'streams': streams}

def sync(config, state, catalog):
    # Loop over streams in catalog
    for stream in catalog['streams']:
        stream_id = stream['tap_stream_id']
        stream_schema = stream['schema']
        stream_key_properties = stream['key_properties']
        with Transformer(singer.UNIX_SECONDS_INTEGER_DATETIME_PARSING) as transformer:
            LOGGER.info('Syncing stream: %s', stream_id)
            singer.write_schema(stream_id,
                                stream_schema,
                                stream_key_properties)
            # TODO We are not bookmarking yet
            for obj in STREAM_SDK_OBJECTS[stream_id].list(
                    stripe_account=config.get(
                        'account_id')).auto_paging_iter():
                singer.write_record(stream_id,
                                    transformer.transform(
                                        obj,
                                        stream_schema,
                                        {}))
                singer.write_bookmark(state,
                                      stream_id,
                                      'id',
                                      obj.id)
                singer.write_state(state)

@utils.handle_top_exception(LOGGER)
def main():

    # Parse command line arguments
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)

    # Set the API key we'll be using
    # https://github.com/stripe/stripe-python/tree/a9a8d754b73ad47bdece6ac4b4850822fa19db4e#usage
    stripe.api_key = args.config.get('client_secret')
    # Allow ourselves to retry retriable network errors 5 times
    # https://github.com/stripe/stripe-python/tree/a9a8d754b73ad47bdece6ac4b4850822fa19db4e#configuring-automatic-retries
    stripe.max_network_retries = 5
    # Configure client-side network timeout of 1 second
    # https://github.com/stripe/stripe-python/tree/a9a8d754b73ad47bdece6ac4b4850822fa19db4e#configuring-a-client
    client = stripe.http_client.RequestsClient(timeout=1)
    stripe.default_http_client = client
    # Set stripe logging to INFO level
    # https://github.com/stripe/stripe-python/tree/a9a8d754b73ad47bdece6ac4b4850822fa19db4e#logging
    logging.getLogger('stripe').setLevel(logging.INFO)

    # Verify connectivity
    account = stripe.Account.retrieve(args.config.get('account_id'))
    msg = "Successfully connected to Stripe Account with display name" \
        + " `%s`"
    LOGGER.info(msg, account.display_name)

    # TODO need to exit early for a connection check

    catalog = discover()

    sync(args.config, args.state, catalog)

if __name__ == "__main__":
    main()
