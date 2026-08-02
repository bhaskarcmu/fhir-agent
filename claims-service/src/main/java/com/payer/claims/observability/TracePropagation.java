package com.payer.claims.observability;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * Injects the current trace context into outbound request headers for the two HTTP clients
 * Spring's auto-instrumentation doesn't reach: the raw JDK {@code HttpClient} in
 * {@link com.payer.claims.client.HttpTriageClient} and HAPI's own {@code IGenericClient} in
 * {@link com.payer.claims.fhir.HapiFhirClient}. {@link com.payer.claims.client.HttpLegacyClient}
 * (Spring's {@code RestClient}, to rxclaim-emulator) already gets this automatically once
 * micrometer-tracing-bridge-otel is on the classpath -- no code needed there.
 *
 * <p>docs/phase6/decisions.md H16: closes the "traceID propagates into triage/fhir calls"
 * requirement for the two hops that needed manual work.
 */
@Component
public class TracePropagation {

    private final Tracer tracer;
    private final Propagator propagator;

    public TracePropagation(Tracer tracer, Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

    /** A no-op instance for tests/contexts with no configured Tracer -- never injects anything. */
    public static TracePropagation noop() {
        return new TracePropagation(null, null);
    }

    /** The current trace context as an outbound header map, e.g. {"traceparent": "..."}. */
    public Map<String, String> headers() {
        Map<String, String> headers = new LinkedHashMap<>();
        if (tracer == null || propagator == null) {
            return headers;
        }
        Span current = tracer.currentSpan();
        if (current == null) {
            return headers;
        }
        propagator.inject(current.context(), headers, Map::put);
        return headers;
    }
}
