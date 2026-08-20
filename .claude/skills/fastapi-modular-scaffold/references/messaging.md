# Messaging reference

## When a broker is warranted

RabbitMQ earns its operational cost when there is work that must not block the request (email, exports, third-party calls), work that must survive a restart, or cross-module reactions that should not couple the publisher to the consumer. Cross-module notification alone does not justify it — the in-process `EventBus` handles that until the modules actually separate.

## Where this lives

`app/integrations/queue/` owns the connection, the topology declaration, its
settings, constants and errors. Domain modules define their own events in
`<module>/events.py` and their exchange name in `<module>/constants.py`; they
never import aio_pika directly.

## Topology

One topic exchange per bounded context, routing keys shaped `<module>.<entity>.<action>`:

```
exchange: identity           type: topic, durable
  identity.user.email_changed  -> q.notifications.user_email
                               -> q.audit.user_events
```

Queues are owned by consumers, not publishers. A publisher that knows queue names is coupled to its consumers and loses the point of the exchange.

Every queue gets a dead-letter exchange at declaration time. Retrofitting a DLX means redeclaring a queue in production, which means downtime or a rename.

## The lost-event problem

Committing to Postgres and publishing to RabbitMQ are two systems with no shared transaction. A crash between them silently loses the event.

For non-critical events, accept it and log. For anything with business consequence — payment succeeded, subscription cancelled — use the outbox:

1. In the same transaction as the state change, insert into `outbox_events`
2. A relay process polls unpublished rows and publishes them
3. Mark published only after the broker acknowledges

The relay may publish twice (crash after ack, before marking). That is why consumers must be idempotent — at-least-once is what this buys, exactly-once is not available.

## Idempotent consumers

`Broker.consume` already binds the message's `correlation_id` into every log line the handler emits, the same way `RequestIdMiddleware` does for an HTTP request — see `references/logging.md`. That's separate from the idempotency concern below: correlation lets you find every log line belonging to one flow, idempotency is about not acting on the same message twice.

`integrations/queue/idempotency.py`'s `idempotent(store)` decorator wraps a handler so a message whose `event_id` was already processed is skipped — every event published via `Broker.publish` already carries one:

```python
handler = idempotent(RedisIdempotencyStore(redis))(handle_message)
```

`app/worker.py` wires this automatically when `queue` and `cache` are both selected. The `IdempotencyStore` `Protocol` (`exists(key)`/`mark(key)`, both async) isn't tied to Redis — bring your own backend (a table, a different cache) when `cache` isn't selected; only `RedisIdempotencyStore` itself requires it. Verified against a real Redis container: three deliveries of the same `event_id` run the handler exactly once. See `references/layer-examples.md` for the full decorator and how it stacks with the `@integration` role marker.

Or make the handler naturally idempotent instead — `SET status = 'paid'` is safe to repeat, `balance = balance - amount` is not. Preferring the former is worth some schema awkwardness, and doesn't need the decorator at all.

## Retry

Do not retry in a loop inside the handler; it holds the connection and blocks the queue. Publish to a delay queue with a TTL and let it dead-letter back:

```
q.work -> (nack) -> x.retry -> q.retry.30s (TTL 30s) -> x.work -> q.work
```

Cap attempts (3–5), then route to `q.work.failed` and alert. A queue that retries forever hides a bug and burns capacity.

This is a different retry than `app/retry.py`'s `@retry` decorator (`references/layer-examples.md`): the delay-queue dance above handles a message still failing after every *in-process* attempt is exhausted, across redeliveries and potentially minutes apart; `@retry` handles a single call's transient failure (a dropped connection) within one handler invocation, in milliseconds. Use `@retry` inside a handler for the external calls it makes; let this section's DLX topology be the backstop when the handler gives up entirely.

## Consumer process

Consumers run as a separate process, not inside the API. They import the same modules and call the same use cases — that reuse is the payoff for keeping `HTTPException` out of services.

Prefetch matters: unbounded prefetch makes one consumer hoard the queue while others idle. Start at 10–50 per consumer and tune from queue depth.

## Celery vs raw AMQP

Celery for scheduled and background tasks owned by the app (reports, cleanup, retries with backoff) — it brings beat, result backend and retry policy. Raw `aio-pika` for event-driven consumption where messages come from elsewhere and the topology matters. Running both is normal; running Celery as an event bus is not, because its task model hides the routing you need to reason about.

## Graceful shutdown

On SIGTERM: stop accepting, finish in-flight messages, then close. Killing mid-message means redelivery, which means idempotency is load-bearing during every deploy.
