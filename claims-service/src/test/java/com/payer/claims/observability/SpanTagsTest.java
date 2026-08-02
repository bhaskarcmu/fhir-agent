package com.payer.claims.observability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.TraceContext;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;

/**
 * Plain unit tests (no Spring context, no real Tracer) -- Tracer is an interface, so a Mockito
 * mock is enough to verify SpanTags' own logic without needing the real Micrometer/OTel bridge
 * wired up (that integration is exercised by the live docker-compose smoke test, not here).
 */
class SpanTagsTest {

    @Test
    void tag_is_a_noop_with_no_active_span() {
        Tracer tracer = mock(Tracer.class);
        when(tracer.currentSpan()).thenReturn(null);
        SpanTags spanTags = new SpanTags(tracer, "standard");

        spanTags.tag("claims.api", "ClaimController");  // must not throw

        assertThat(spanTags.currentTraceId()).isNull();
    }

    @Test
    void tag_sets_the_fhir_agent_namespace_on_the_current_span() {
        Tracer tracer = mock(Tracer.class);
        Span span = mock(Span.class);
        when(tracer.currentSpan()).thenReturn(span);
        SpanTags spanTags = new SpanTags(tracer, "standard");

        spanTags.tag("claims.api", "ClaimController");

        verify(span).tag("fhir_agent.layer", "claims.api");
        verify(span).tag("fhir_agent.component", "ClaimController");
        verify(span).tag("fhir_agent.verbosity", "standard");
    }

    @Test
    void unrecognized_verbosity_fails_closed_to_standard() {
        Tracer tracer = mock(Tracer.class);
        Span span = mock(Span.class);
        when(tracer.currentSpan()).thenReturn(span);
        SpanTags spanTags = new SpanTags(tracer, "maximum-overdrive");

        spanTags.tag("claims.api", "ClaimController");

        verify(span).tag("fhir_agent.verbosity", "standard");
    }

    @Test
    void current_trace_id_reads_from_the_active_span_context() {
        Tracer tracer = mock(Tracer.class);
        Span span = mock(Span.class);
        TraceContext context = mock(TraceContext.class);
        when(tracer.currentSpan()).thenReturn(span);
        when(span.context()).thenReturn(context);
        when(context.traceId()).thenReturn("abc123");
        SpanTags spanTags = new SpanTags(tracer, "standard");

        assertThat(spanTags.currentTraceId()).isEqualTo("abc123");
    }
}
