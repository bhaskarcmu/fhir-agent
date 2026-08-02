package com.payer.claims.observability;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * Unit test for the no-Tracer-configured path -- the shape every
 * {@code HttpTriageClientTest} call site now exercises via
 * {@link TracePropagation#noop()}. The real-tracer injection path (a live span
 * actually producing a {@code traceparent} header) is Spring Boot's own
 * well-established tracing autoconfiguration wiring a real
 * {@code io.micrometer.tracing.Tracer}/{@code Propagator} pair into this
 * class's constructor -- verified by a live docker-compose smoke test
 * (docs/phase6), not re-tested here against mocked internals.
 */
class TracePropagationTest {

    @Test
    void noop_never_injects_anything() {
        assertThat(TracePropagation.noop().headers()).isEmpty();
    }
}
