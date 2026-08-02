package com.payer.claims.observability;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Enriches whatever span is currently active (typically the auto-instrumented Spring MVC server
 * span) with {@code fhir_agent.layer}/{@code .component}/{@code .verbosity} -- the custom
 * attribute namespace docs/phase6/telemetry-schema.md defines for architectural meaning, since
 * OTel's own {@code code.*} convention only covers literal source location.
 *
 * <p>Deliberately does not create new spans: this is the "standard" verbosity path
 * (attribute enrichment on spans that already exist), matching every other tier's default
 * (docs/phase6/decisions.md H25). Unlike triage-service's rules.py, claims-service's boundaries
 * do not get a "detailed" per-stage span tier here -- the telemetry schema names
 * {@code triage.rules} as the one place in this platform judged worth the extra span volume;
 * extending "detailed" to claims-service's pipeline stages is an explicit future decision, not
 * a default (see {@code telemetry-schema.md} Section 4.2).
 */
@Component
public class SpanTags {

    private final Tracer tracer;
    private final String verbosity;

    public SpanTags(
            Tracer tracer,
            @Value("${telemetry.verbosity:standard}") String verbosity) {
        this.tracer = tracer;
        this.verbosity = "detailed".equalsIgnoreCase(verbosity) ? "detailed" : "standard";
    }

    /** Tag the current span, if any. A no-op when nothing is active (e.g. outside a request). */
    public void tag(String layer, String component) {
        Span current = tracer.currentSpan();
        if (current == null) {
            return;
        }
        current.tag("fhir_agent.layer", layer);
        current.tag("fhir_agent.component", component);
        current.tag("fhir_agent.verbosity", verbosity);
    }

    /**
     * The current span's trace ID, or null if there is no active span. Surfaced to callers via
     * the X-Trace-Id response header (docs/phase6/telemetry-schema.md Section 5) -- a trace ID
     * only visible inside span context is useless to a caller who isn't already looking at
     * Jaeger.
     */
    public String currentTraceId() {
        Span current = tracer.currentSpan();
        return current == null ? null : current.context().traceId();
    }
}
