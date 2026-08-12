import logging
import os
import signal
import sys
from confluent_kafka import Consumer as KafkaConsumer, KafkaError, KafkaException
from config import AppConfig, get_logger_config



logger = logging.getLogger("xapi.main." + __name__)

class TubeConsumer:
    def __init__(self, topic: str, group_id: str, bootstrap_servers: str = "localhost:9092"):
        self.topic = topic
        self.group_id = group_id
        self.stop_flag = False
        
        # Optimized configuration footprint exploiting Kafka 4.x advancements
        config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True,
            # Leverage next-gen KIP-848 server-driven rebalancing on your 4.3.1 cluster
            'group.protocol': 'consumer'
        }
        
        self.consumer = KafkaConsumer(config)
        
        # Attach execution termination hooks
        signal.signal(signal.SIGINT, self.handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self.handle_shutdown_signal)

    def handle_shutdown_signal(self, signum, frame):
        print(f"\nReceived termination signal ({signum}). Initiating graceful worker teardown...")
        self.stop_flag = True

    def run(self):
        run_logger = logging.getLogger("main." + __name__)
        self.consumer.subscribe([self.topic])

        try:
            while not self.stop_flag:
                # Polling prevents worker thread blocks when no events exist
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        raise KafkaException(msg.error())
                
                # Extract message parameters cleanly
                payload = msg.value().decode('utf-8')
                key = msg.key().decode('utf-8') if msg.key() else "NoKey"
                
                run_logger.info(f"Received event <- Key: {key} | Payload: {payload}")
                
                # --- YOUR IDEMPOTENT DB CHECK LOGIC GOES HERE ---
                # Check your Python Database pool to verify the row exists 
                # before firing off the SMS gateway script!
                
        finally:
            print("Closing consumer channel sockets safely...")
            self.consumer.close()

def _get_kafka_worker_id() -> str:
    if len(sys.argv) >= 2:
        return sys.argv[1]
    
    env_worker_id = os.environ.get("KAFKA_WORKER_ID")
    if env_worker_id:
        return env_worker_id
        
    return str(os.getpid())

def start_worker():
    print(f"Initializing Kafka Consumer Process under PID: {os.getpid()}...")
    AppConfig.load()
    
    # FIX: Invoke the function with parentheses () to compute the string token
    worker_id = _get_kafka_worker_id()
    
    log_config = get_logger_config("kafka")
    log_file_name = log_config.log_file.format(**{"worker_id": worker_id})
    AppConfig.init_logging(log_file=log_file_name, log_level=log_config.log_level)

    logger.info(f"Kafka engine thread worker [{worker_id}] connected.")
    
    # Initialize the broker runtime engine
    worker = TubeConsumer(topic="xapi_tube", group_id="xapi_tube_worker", bootstrap_servers="localhost:9092")
    worker.run()

if __name__ == "__main__":
    start_worker()
